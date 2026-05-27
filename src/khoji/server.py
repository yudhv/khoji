from __future__ import annotations

import json
import re
from datetime import datetime
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .asr import AudioTranscriber
from .line_labels import (
    apply_line_click,
    finish_open_segment,
    label_segments,
    load_line_label_rows,
    reset_label_rows,
    write_line_label_rows,
)
from .phase1 import DEFAULT_TRANSLATION_LANGUAGE, Phase1Identifier
from .phase2 import SequenceSmoother
from .recordings import RecordingLabel, load_recording_manifest, register_recording


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATIC_DIR = REPO_ROOT / "web"
DEFAULT_RECORDING_MANIFEST = REPO_ROOT / "data/phase1/recordings/manifest.jsonl"


class KhojiServerError(ValueError):
    pass


def run_server(
    *,
    corpus_path: str | Path,
    manifest_path: str | Path | None,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_dir: str | Path = DEFAULT_STATIC_DIR,
    audio_transcriber: AudioTranscriber | None = None,
    recording_manifest_path: str | Path = DEFAULT_RECORDING_MANIFEST,
) -> None:
    server = create_server(
        corpus_path=corpus_path,
        manifest_path=manifest_path,
        host=host,
        port=port,
        static_dir=static_dir,
        audio_transcriber=audio_transcriber,
        recording_manifest_path=recording_manifest_path,
    )
    print(f"Khoji server listening on http://{host}:{port}")
    server.serve_forever()


def create_server(
    *,
    corpus_path: str | Path,
    manifest_path: str | Path | None,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_dir: str | Path = DEFAULT_STATIC_DIR,
    audio_transcriber: AudioTranscriber | None = None,
    recording_manifest_path: str | Path = DEFAULT_RECORDING_MANIFEST,
) -> ThreadingHTTPServer:
    identifier = Phase1Identifier(
        corpus_path,
        manifest_path,
        audio_transcriber=audio_transcriber,
    )
    handler = _make_handler(identifier, Path(static_dir), Path(recording_manifest_path))
    return ThreadingHTTPServer((host, port), handler)


def _make_handler(
    identifier: Phase1Identifier,
    static_dir: Path,
    recording_manifest_path: Path,
):
    live_sessions: dict[str, SequenceSmoother] = {}

    class KhojiRequestHandler(BaseHTTPRequestHandler):
        server_version = "KhojiHTTP/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._send_json(
                    {"ok": True, "clips": len(identifier.clips), "live_sessions": len(live_sessions)}
                )
                return
            if parsed.path == "/api/labeler-state":
                query = parse_qs(parsed.query)
                recording_id = (query.get("recording_id") or [""])[0]
                self._send_json(
                    _labeler_state(
                        identifier,
                        recording_manifest_path,
                        recording_id=recording_id,
                    )
                )
                return
            if parsed.path == "/api/search-lines":
                query = parse_qs(parsed.query)
                search_query = (query.get("q") or [""])[0]
                top_k = _parse_top_k((query.get("top_k") or ["20"])[0], default=20)
                self._send_json(
                    _search_lines(
                        identifier,
                        query=search_query,
                        top_k=top_k,
                    )
                )
                return
            if parsed.path == "/api/recording-audio":
                query = parse_qs(parsed.query)
                recording_id = (query.get("recording_id") or [""])[0]
                recording = _recording_by_id(recording_manifest_path, recording_id)
                self._send_binary_file(_recording_audio_path(recording_manifest_path, recording))
                return
            if parsed.path == "/":
                self._send_static_file(static_dir / "index.html")
                return
            if parsed.path == "/labeler":
                self._send_static_file(static_dir / "labeler.html")
                return
            static_path = (static_dir / parsed.path.lstrip("/")).resolve()
            if not _is_relative_to(static_path, static_dir.resolve()):
                self._send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            self._send_static_file(static_path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/identify-audio":
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    audio_bytes, fields = _extract_audio_request(
                        body,
                        self.headers.get("Content-Type", ""),
                    )
                    language = fields.get("translation_language", DEFAULT_TRANSLATION_LANGUAGE)
                    result = identifier.identify_audio(
                        audio_bytes,
                        translation_language=language,
                    )
                    self._send_json(result)
                    return
                if parsed.path == "/api/recording-upload":
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    audio_bytes, fields = _extract_audio_request(
                        body,
                        self.headers.get("Content-Type", ""),
                    )
                    result = _recording_upload(
                        identifier,
                        recording_manifest_path,
                        audio_bytes=audio_bytes,
                        filename=fields.get("_audio_filename", "recording"),
                        recording_id=fields.get("recording_id", ""),
                    )
                    self._send_json(result)
                    return
                if parsed.path == "/api/live-chunk":
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    audio_bytes, fields = _extract_audio_request(
                        body,
                        self.headers.get("Content-Type", ""),
                    )
                    query = parse_qs(parsed.query)
                    session_id = (
                        fields.get("session_id")
                        or (query.get("session_id") or ["default"])[0]
                        or "default"
                    )
                    language = fields.get("translation_language", DEFAULT_TRANSLATION_LANGUAGE)
                    raw_result = identifier.identify_audio(
                        audio_bytes,
                        translation_language=language,
                    )
                    smoother = live_sessions.setdefault(
                        session_id,
                        SequenceSmoother(identifier),
                    )
                    result = smoother.update(
                        raw_result,
                        translation_language=language,
                    )
                    result["session_id"] = session_id
                    self._send_json(result)
                    return
                if parsed.path == "/api/identify-text":
                    payload = self._read_json()
                    query = str(payload.get("query", ""))
                    language = str(
                        payload.get("translation_language", DEFAULT_TRANSLATION_LANGUAGE)
                    )
                    self._send_json(
                        identifier.identify_text(query, translation_language=language)
                    )
                    return
                if parsed.path == "/api/label-line-click":
                    payload = self._read_json()
                    result = _label_line_click(
                        identifier,
                        recording_manifest_path,
                        recording_id=str(payload["recording_id"]),
                        line_id=str(payload["line_id"]),
                        time_s=float(payload["time_s"]),
                    )
                    self._send_json(result)
                    return
                if parsed.path == "/api/label-finish":
                    payload = self._read_json()
                    result = _label_finish(
                        identifier,
                        recording_manifest_path,
                        recording_id=str(payload["recording_id"]),
                        time_s=float(payload["time_s"]),
                    )
                    self._send_json(result)
                    return
                if parsed.path == "/api/label-reset":
                    payload = self._read_json()
                    result = _label_reset(
                        identifier,
                        recording_manifest_path,
                        recording_id=str(payload["recording_id"]),
                    )
                    self._send_json(result)
                    return
            except (KhojiServerError, KeyError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def _send_json(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_static_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            content_type = _content_type(path)
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_binary_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", _content_type(path))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"ok": False, "error": message}, status=status)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

    return KhojiRequestHandler


def _labeler_state(
    identifier: Phase1Identifier,
    recording_manifest_path: Path,
    *,
    recording_id: str = "",
) -> dict[str, Any]:
    recording = _recording_by_id(recording_manifest_path, recording_id)
    label_path = _recording_label_path(recording_manifest_path, recording)
    labels = label_segments(load_line_label_rows(label_path))
    shabad = _active_labeler_shabad(identifier, recording, labels)
    return {
        "ok": True,
        "recording": {
            "recording_id": recording.recording_id,
            "shabad_id": recording.shabad_id,
            "audio_path": recording.audio_path,
            "duration_ms": recording.duration_ms,
            "label_path": str(label_path),
            "audio_url": f"/api/recording-audio?recording_id={recording.recording_id}",
        },
        "shabad": _label_shabad_payload(shabad) if shabad is not None else None,
        "labels": labels,
    }


def _recording_upload(
    identifier: Phase1Identifier,
    recording_manifest_path: Path,
    *,
    audio_bytes: bytes,
    filename: str,
    recording_id: str = "",
) -> dict[str, Any]:
    if not audio_bytes:
        raise KhojiServerError("Uploaded media is empty")
    recording_id = recording_id or _recording_id_from_filename(filename)
    suffix = _safe_suffix(filename)
    audio_dir = recording_manifest_path.parent / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{recording_id}{suffix}"
    audio_path.write_bytes(audio_bytes)
    register_recording(
        audio_path=audio_path,
        manifest_path=recording_manifest_path,
        recording_id=recording_id,
        shabad_id="",
        kind="kirtan",
        split="dev",
        has_vocals=True,
        source="local_upload",
        notes=f"Uploaded from Khoji labeler as {filename}",
    )
    return _labeler_state(identifier, recording_manifest_path, recording_id=recording_id)


def _label_line_click(
    identifier: Phase1Identifier,
    recording_manifest_path: Path,
    *,
    recording_id: str,
    line_id: str,
    time_s: float,
) -> dict[str, Any]:
    recording = _recording_by_id(recording_manifest_path, recording_id)
    shabad = identifier.shabad_for_line_id(line_id)
    label_path = _recording_label_path(recording_manifest_path, recording)
    rows = apply_line_click(
        load_line_label_rows(label_path),
        shabad,
        recording_id=recording.recording_id,
        audio_path=recording.audio_path,
        line_id=line_id,
        time_s=time_s,
    )
    write_line_label_rows(rows, label_path)
    return _labeler_state(identifier, recording_manifest_path, recording_id=recording_id)


def _search_lines(
    identifier: Phase1Identifier,
    *,
    query: str,
    top_k: int,
) -> dict[str, Any]:
    results = identifier.search_all_lines(query, top_k=top_k)
    return {
        "ok": True,
        "query": query,
        "results": [
            _label_search_result_payload(identifier, candidate)
            for candidate in results
            if candidate.score > 0
        ],
    }


def _label_finish(
    identifier: Phase1Identifier,
    recording_manifest_path: Path,
    *,
    recording_id: str,
    time_s: float,
) -> dict[str, Any]:
    recording = _recording_by_id(recording_manifest_path, recording_id)
    label_path = _recording_label_path(recording_manifest_path, recording)
    rows = finish_open_segment(load_line_label_rows(label_path), time_s=time_s)
    write_line_label_rows(rows, label_path)
    return _labeler_state(identifier, recording_manifest_path, recording_id=recording_id)


def _label_reset(
    identifier: Phase1Identifier,
    recording_manifest_path: Path,
    *,
    recording_id: str,
) -> dict[str, Any]:
    recording = _recording_by_id(recording_manifest_path, recording_id)
    label_path = _recording_label_path(recording_manifest_path, recording)
    write_line_label_rows(reset_label_rows(), label_path)
    return _labeler_state(identifier, recording_manifest_path, recording_id=recording_id)


def _recording_by_id(
    recording_manifest_path: Path,
    recording_id: str,
) -> RecordingLabel:
    recordings = load_recording_manifest(recording_manifest_path)
    if not recordings:
        raise KhojiServerError(f"No recording manifest found at {recording_manifest_path}")
    if not recording_id:
        return recordings[0]
    for recording in recordings:
        if recording.recording_id == recording_id:
            return recording
    raise KhojiServerError(f"Unknown recording_id: {recording_id}")


def _recording_audio_path(
    recording_manifest_path: Path,
    recording: RecordingLabel,
) -> Path:
    audio_path = Path(recording.audio_path)
    if audio_path.is_absolute():
        return audio_path
    return (recording_manifest_path.parent / audio_path).resolve()


def _recording_label_path(
    recording_manifest_path: Path,
    recording: RecordingLabel,
) -> Path:
    if recording.line_labels_path:
        label_path = Path(recording.line_labels_path)
        if label_path.is_absolute():
            return label_path
        return (recording_manifest_path.parent / label_path).resolve()
    return (recording_manifest_path.parent / f"{recording.recording_id}.line_labels.tsv").resolve()


def _active_labeler_shabad(
    identifier: Phase1Identifier,
    recording: RecordingLabel,
    labels: list[dict[str, Any]],
):
    if labels:
        shabad_id = str(labels[-1].get("shabad_id", ""))
        if shabad_id:
            return identifier.shabad_by_id(shabad_id)
    if recording.shabad_id:
        return identifier.shabad_by_id(recording.shabad_id)
    return None


def _label_shabad_payload(shabad) -> dict[str, Any]:
    return {
        "shabad_id": shabad.shabad_id,
        "title": shabad.title,
        "ang": shabad.ang,
        "raag": shabad.raag,
        "author": shabad.author,
        "lines": [_label_line_payload(line) for line in shabad.lines],
    }


def _label_line_payload(line) -> dict[str, Any]:
    return {
        "line_id": line.line_id,
        "order": line.order,
        "gurmukhi": line.gurmukhi,
        "transliteration": line.transliteration,
        "text": line.transliteration or line.gurmukhi,
        "section": line.section,
        "is_refrain": line.is_refrain,
        "punjabi_translation": _translation_for_line(line, "Punjabi"),
        "english_translation": _translation_for_line(line, "English"),
    }


def _label_search_result_payload(identifier: Phase1Identifier, candidate) -> dict[str, Any]:
    shabad = identifier.shabad_by_id(candidate.line.shabad_id)
    payload = _label_line_payload(candidate.line)
    return {
        **payload,
        "score": candidate.score,
        "confidence": candidate.confidence,
        "shabad_id": shabad.shabad_id,
        "shabad_title": shabad.title,
        "ang": shabad.ang,
        "raag": shabad.raag,
        "author": shabad.author,
    }


def _translation_for_line(line, language: str) -> str:
    for translation in line.metadata.get("translations", []):
        if translation.get("language") == language:
            return str(translation.get("text", ""))
    if language == "English":
        return line.english
    return ""


def _parse_top_k(raw: str, *, default: int) -> int:
    try:
        return max(1, min(int(raw), 50))
    except ValueError:
        return default


def _recording_id_from_filename(filename: str) -> str:
    stem = Path(filename).stem or "recording"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower() or "recording"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{slug}_{timestamp}"


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    return ".bin"


def _extract_audio_request(body: bytes, content_type: str) -> tuple[bytes, dict[str, str]]:
    if content_type.startswith("application/octet-stream"):
        return body, {}
    if not content_type.startswith("multipart/form-data"):
        raise KhojiServerError("Expected multipart/form-data or application/octet-stream")

    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        + body
    )
    fields: dict[str, str] = {}
    audio_bytes: bytes | None = None
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        params = dict(part.get_params(header="content-disposition") or [])
        name = params.get("name")
        if not name or "form-data" not in disposition:
            continue
        payload = part.get_payload(decode=True) or b""
        if name == "audio":
            audio_bytes = payload
            if params.get("filename"):
                fields["_audio_filename"] = str(params["filename"])
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8")
    if audio_bytes is None:
        raise KhojiServerError("No multipart field named 'audio' found")
    return audio_bytes, fields


def _content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    if path.suffix == ".mp3":
        return "audio/mpeg"
    if path.suffix == ".wav":
        return "audio/wav"
    if path.suffix == ".webm":
        return "audio/webm"
    return "application/octet-stream"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
