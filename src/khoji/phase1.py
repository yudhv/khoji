from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .asr import AudioTranscriber
from .corpus import load_shabads
from .models import Line, RankedLine, RankedShabad, Shabad
from .retriever import KhojiIndex


DEFAULT_TRANSLATION_LANGUAGE = "Punjabi"


@dataclass(frozen=True)
class BenchmarkClip:
    clip_id: str
    shabad_id: str
    line_id: str
    start_ms: int
    end_ms: int
    audio_path: Path
    split: str
    kind: str
    transcript: str
    sha256: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any], base_dir: Path) -> "BenchmarkClip":
        audio_path = Path(str(data["audio_path"]))
        if not audio_path.is_absolute():
            audio_path = base_dir / audio_path
        return cls(
            clip_id=str(data["clip_id"]),
            shabad_id=str(data["shabad_id"]),
            line_id=str(data["line_id"]),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
            audio_path=audio_path,
            split=str(data.get("split", "dev")),
            kind=str(data.get("kind", "unknown")),
            transcript=str(data.get("transcript", "")),
            sha256=str(data.get("sha256", "")),
        )

    def to_manifest_record(self, root: Path) -> dict[str, Any]:
        record = asdict(self)
        try:
            record["audio_path"] = str(self.audio_path.relative_to(root))
        except ValueError:
            record["audio_path"] = str(self.audio_path)
        return record


class Phase1Identifier:
    def __init__(
        self,
        corpus_path: str | Path,
        manifest_path: str | Path | None = None,
        *,
        translation_language: str = DEFAULT_TRANSLATION_LANGUAGE,
        audio_transcriber: AudioTranscriber | None = None,
    ) -> None:
        self.corpus_path = Path(corpus_path)
        self.translation_language = translation_language
        self.audio_transcriber = audio_transcriber
        self.shabads = load_shabads(self.corpus_path)
        self.index = KhojiIndex(self.shabads)
        self._shabads_by_id = {shabad.shabad_id: shabad for shabad in self.shabads}
        self._lines_by_id = {
            line.line_id: line for shabad in self.shabads for line in shabad.lines
        }
        self.clips = load_benchmark_manifest(manifest_path) if manifest_path else []
        self._clips_by_sha = {clip.sha256: clip for clip in self.clips if clip.sha256}

    def shabad_by_id(self, shabad_id: str) -> Shabad:
        try:
            return self._shabads_by_id[shabad_id]
        except KeyError as exc:
            raise KeyError(f"Unknown shabad_id: {shabad_id}") from exc

    def line_by_id(self, line_id: str) -> Line:
        try:
            return self._lines_by_id[line_id]
        except KeyError as exc:
            raise KeyError(f"Unknown line_id: {line_id}") from exc

    def shabad_for_line_id(self, line_id: str) -> Shabad:
        line = self.line_by_id(line_id)
        return self.shabad_by_id(line.shabad_id)

    def search_all_lines(self, query: str, *, top_k: int = 20) -> tuple[RankedLine, ...]:
        return self.index.search_all_lines(query, top_k=top_k)

    def identify_audio(
        self,
        audio_bytes: bytes,
        *,
        translation_language: str | None = None,
        within_shabad_id: str | None = None,
    ) -> dict[str, Any]:
        digest = sha256_bytes(audio_bytes)
        clip = self._clips_by_sha.get(digest)
        if clip is None:
            if self.audio_transcriber is None:
                return _unknown_response(
                    "audio fingerprint not found in the Phase 1 benchmark manifest",
                    digest,
                )
            return self._identify_audio_with_transcriber(
                audio_bytes,
                digest,
                translation_language=translation_language,
                within_shabad_id=within_shabad_id,
            )
        if not clip.transcript:
            return _unknown_response(
                f"benchmark clip has no transcript: {clip.clip_id}",
                digest,
            )

        response = self.identify_text(
            clip.transcript,
            translation_language=translation_language,
            within_shabad_id=within_shabad_id,
        )
        response["model_votes"].insert(
            0,
            {
                "model": "phase1_manifest_transcript",
                "confidence": 1.0,
                "detail": f"matched audio sha256 to benchmark clip {clip.clip_id}",
            },
        )
        response["benchmark_clip"] = {
            "clip_id": clip.clip_id,
            "kind": clip.kind,
            "split": clip.split,
            "label_shabad_id": clip.shabad_id,
            "label_line_id": clip.line_id,
        }
        response["audio_sha256"] = digest
        return response

    def _identify_audio_with_transcriber(
        self,
        audio_bytes: bytes,
        digest: str,
        *,
        translation_language: str | None = None,
        within_shabad_id: str | None = None,
    ) -> dict[str, Any]:
        assert self.audio_transcriber is not None
        transcription = self.audio_transcriber.transcribe_bytes(audio_bytes)
        if not transcription.text:
            return _unknown_response("ASR returned an empty transcript", digest)

        response = self.identify_text(
            transcription.text,
            translation_language=translation_language,
            within_shabad_id=within_shabad_id,
        )
        response["model_votes"].insert(
            0,
            {
                "model": transcription.model,
                "confidence": transcription.confidence,
                "detail": "transcribed audio, then queried Khoji text retrieval",
                "metadata": transcription.metadata,
            },
        )
        response["audio_sha256"] = digest
        response["asr"] = {
            "model": transcription.model,
            "text": transcription.text,
            "confidence": transcription.confidence,
            "metadata": transcription.metadata,
        }
        return response

    def identify_text(
        self,
        query: str,
        *,
        translation_language: str | None = None,
        within_shabad_id: str | None = None,
    ) -> dict[str, Any]:
        language = translation_language or self.translation_language
        top_shabads = self.index.search_shabads(query, top_k=5)
        if within_shabad_id:
            shabad = self.shabad_by_id(within_shabad_id)
            top_lines = self.index.search_lines(query, within_shabad_id, top_k=5)
            if not top_lines:
                return _unknown_response("no line candidate found in locked shabad")
            active_line = top_lines[0].line
            confidence = top_lines[0].confidence
            best_shabad_score = top_shabads[0].score if top_shabads else 0.0
            best_line_score = top_lines[0].score
            vote_detail = "ranked lines inside the locked shabad"
        else:
            result = self.index.identify(query, top_k_shabads=5, top_k_lines=5)
            if result.best_shabad is None or result.best_line is None:
                return _unknown_response("no shabad or line candidate found")
            shabad = result.best_shabad.shabad
            active_line = result.best_line.line
            confidence = min(result.best_shabad.confidence, result.best_line.confidence)
            top_shabads = result.top_shabads
            top_lines = result.top_lines
            best_shabad_score = result.best_shabad.score
            best_line_score = result.best_line.score
            vote_detail = "ranked shabad first, then ranked lines within the top shabad"

        if not top_shabads or not top_lines:
            return _unknown_response("no shabad or line candidate found")

        if best_shabad_score <= 0 and not within_shabad_id:
            return _unknown_response("retrieval confidence is zero")
        if best_line_score <= 0:
            return _unknown_response("retrieval confidence is zero")

        context_lines = _context_lines(
            shabad,
            active_line.line_id,
            translation_language=language,
        )
        active_context_line = next(
            line for line in context_lines if line["is_active"]
        )
        return {
            "status": "identified",
            "query": query,
            "shabad": _shabad_payload(shabad),
            "active_line": active_context_line,
            "context_lines": context_lines,
            "confidence": confidence,
            "top_shabads": [_ranked_shabad_payload(candidate) for candidate in top_shabads],
            "top_lines": [_ranked_line_payload(candidate) for candidate in top_lines],
            "model_votes": [
                {
                    "model": "khoji_text_retrieval",
                    "confidence": confidence,
                    "detail": vote_detail,
                }
            ],
            "unknown_reason": None,
            "within_shabad_id": within_shabad_id,
        }

    def response_for_line(
        self,
        base_response: dict[str, Any],
        *,
        shabad_id: str,
        line_id: str,
        translation_language: str | None = None,
    ) -> dict[str, Any]:
        shabad = self._shabads_by_id[shabad_id]
        language = translation_language or self.translation_language
        context_lines = _context_lines(
            shabad,
            line_id,
            translation_language=language,
        )
        active_context_line = next(line for line in context_lines if line["is_active"])
        response = dict(base_response)
        response["status"] = "identified"
        response["shabad"] = _shabad_payload(shabad)
        response["active_line"] = active_context_line
        response["context_lines"] = context_lines
        response["unknown_reason"] = None
        return response


def load_benchmark_manifest(path: str | Path | None) -> list[BenchmarkClip]:
    if path is None:
        return []
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Benchmark manifest does not exist: {manifest_path}")

    clips: list[BenchmarkClip] = []
    for line_number, raw_line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid benchmark JSONL line {line_number}: {exc}") from exc
        clip = BenchmarkClip.from_mapping(record, manifest_path.parent)
        clips.append(clip)
    return clips


def evaluate_benchmark(
    corpus_path: str | Path,
    manifest_path: str | Path,
    *,
    translation_language: str = DEFAULT_TRANSLATION_LANGUAGE,
) -> dict[str, Any]:
    identifier = Phase1Identifier(
        corpus_path,
        manifest_path,
        translation_language=translation_language,
    )
    examples: list[dict[str, Any]] = []
    shabad_top1 = 0
    line_top3 = 0
    identified_count = 0

    for clip in identifier.clips:
        audio_bytes = clip.audio_path.read_bytes()
        result = identifier.identify_audio(
            audio_bytes,
            translation_language=translation_language,
        )
        top_shabad_ids = [candidate["shabad_id"] for candidate in result.get("top_shabads", [])]
        top_line_ids = [candidate["line_id"] for candidate in result.get("top_lines", [])]
        shabad_ok = bool(top_shabad_ids and top_shabad_ids[0] == clip.shabad_id)
        line_ok = clip.line_id in top_line_ids[:3]
        identified = result["status"] == "identified"
        shabad_top1 += int(shabad_ok)
        line_top3 += int(line_ok)
        identified_count += int(identified)
        examples.append(
            {
                "clip_id": clip.clip_id,
                "kind": clip.kind,
                "split": clip.split,
                "label_shabad_id": clip.shabad_id,
                "label_line_id": clip.line_id,
                "predicted_shabad_id": top_shabad_ids[0] if top_shabad_ids else None,
                "predicted_line_id": top_line_ids[0] if top_line_ids else None,
                "shabad_top1": shabad_ok,
                "line_top3": line_ok,
                "status": result["status"],
                "unknown_reason": result.get("unknown_reason"),
            }
        )

    total = len(identifier.clips)
    return {
        "total_clips": total,
        "identified_clips": identified_count,
        "shabad_top1_accuracy": shabad_top1 / total if total else 0.0,
        "line_top3_accuracy": line_top3 / total if total else 0.0,
        "examples": examples,
    }


def write_benchmark_report(report: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _context_lines(
    shabad: Shabad,
    active_line_id: str,
    *,
    translation_language: str,
    radius: int = 2,
) -> list[dict[str, Any]]:
    active_index = next(
        (index for index, line in enumerate(shabad.lines) if line.line_id == active_line_id),
        0,
    )
    start = max(active_index - radius, 0)
    end = min(active_index + radius + 1, len(shabad.lines))
    rows: list[dict[str, Any]] = []
    for line in shabad.lines[start:end]:
        is_active = line.line_id == active_line_id
        rows.append(
            {
                "line_id": line.line_id,
                "order": line.order,
                "text": line.transliteration or line.gurmukhi,
                "gurmukhi": line.gurmukhi,
                "transliteration": line.transliteration,
                "section": line.section,
                "is_refrain": line.is_refrain,
                "is_active": is_active,
                "translation": _translation_for_line(line, translation_language) if is_active else "",
                "translation_language": translation_language if is_active else "",
            }
        )
    return rows


def _translation_for_line(line: Line, language: str) -> str:
    translations = line.metadata.get("translations", [])
    for translation in translations:
        if translation.get("language") == language:
            return str(translation.get("text", ""))
    if language == "English" and line.english:
        return line.english
    for translation in translations:
        if translation.get("language") == "English":
            return str(translation.get("text", ""))
    return line.english


def _shabad_payload(shabad: Shabad) -> dict[str, Any]:
    return {
        "shabad_id": shabad.shabad_id,
        "title": shabad.title,
        "ang": shabad.ang,
        "raag": shabad.raag,
        "author": shabad.author,
    }


def _ranked_shabad_payload(candidate: RankedShabad) -> dict[str, Any]:
    return {
        **_shabad_payload(candidate.shabad),
        "score": candidate.score,
        "confidence": candidate.confidence,
    }


def _ranked_line_payload(candidate: RankedLine) -> dict[str, Any]:
    return {
        "line_id": candidate.line.line_id,
        "shabad_id": candidate.line.shabad_id,
        "order": candidate.line.order,
        "text": candidate.line.transliteration or candidate.line.gurmukhi,
        "section": candidate.line.section,
        "is_refrain": candidate.line.is_refrain,
        "score": candidate.score,
        "confidence": candidate.confidence,
    }


def _unknown_response(reason: str, audio_sha256: str | None = None) -> dict[str, Any]:
    return {
        "status": "unknown",
        "query": "",
        "shabad": None,
        "active_line": None,
        "context_lines": [],
        "confidence": 0.0,
        "top_shabads": [],
        "top_lines": [],
        "model_votes": [],
        "unknown_reason": reason,
        "audio_sha256": audio_sha256,
    }
