#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from khoji.asr import DEFAULT_SURT_MODEL_ID, build_audio_transcriber, extract_audio_window
from khoji.phase1 import Phase1Identifier, sha256_file


DEFAULT_AUDIO = Path("data/phase1/benchmark/audio/kahe.mp3")
DEFAULT_LABELS = Path("data/phase1/recordings/kahe_re_ban_full_001.line_labels.tsv")
DEFAULT_CORPUS = Path("data/shabados/sggs.jsonl")
DEFAULT_CACHE = Path("data/phase1/eval/surt_alignment_cache.jsonl")
DEFAULT_REPORT = Path("data/phase1/eval/surt_alignment_report.json")


@dataclass(frozen=True)
class LabelSegment:
    segment_id: str
    line_id: str
    shabad_id: str
    start_s: float
    end_s: float
    text: str

    @property
    def midpoint_s(self) -> float:
        return self.start_s + (self.end_s - self.start_s) / 2


@dataclass(frozen=True)
class AudioWindow:
    mode: str
    strategy: str
    start_s: float
    duration_s: float
    selection_time_s: float
    expected_line_id: str
    expected_segment_id: str

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s

    @property
    def cache_key(self) -> str:
        return f"{self.start_s:.3f}:{self.duration_s:.3f}"


def main() -> int:
    args = _parse_args()
    labels = _load_label_segments(args.labels)
    if not labels:
        raise SystemExit(f"No label rows found in {args.labels}")

    audio_bytes = args.audio.read_bytes()
    audio_sha = sha256_file(args.audio)
    identifier = Phase1Identifier(args.corpus)
    cache = _load_cache(args.cache, audio_sha=audio_sha, model_id=args.model_id)

    windows = _build_windows(
        labels,
        audio_duration_s=args.audio_duration_s or labels[-1].end_s,
        oracle_pads_s=args.oracle_pads_s,
        center_durations_s=args.center_durations_s,
        rolling_window_s=args.rolling_window_s,
        rolling_hop_s=args.rolling_hop_s,
    )

    missing_windows = []
    seen_missing: set[str] = set()
    for window in windows:
        if window.cache_key in cache or window.cache_key in seen_missing:
            continue
        missing_windows.append(window)
        seen_missing.add(window.cache_key)
    if missing_windows:
        transcriber = build_audio_transcriber(
            "surt-small-v3",
            model_id=args.model_id,
            device=args.device,
            chunk_length_s=args.asr_chunk_length_s,
        )
        assert transcriber is not None
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        with args.cache.open("a", encoding="utf-8") as output:
            for index, window in enumerate(missing_windows, 1):
                started = time.perf_counter()
                audio_window = extract_audio_window(
                    audio_bytes,
                    start_s=window.start_s,
                    duration_s=window.duration_s,
                )
                transcription = transcriber.transcribe_bytes(audio_window)
                record = {
                    "audio_sha256": audio_sha,
                    "model_id": args.model_id,
                    "cache_key": window.cache_key,
                    "start_s": window.start_s,
                    "duration_s": window.duration_s,
                    "text": transcription.text,
                    "metadata": transcription.metadata,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                cache[window.cache_key] = record
                print(
                    f"[{index}/{len(missing_windows)}] "
                    f"{window.cache_key} -> {transcription.text[:80]}",
                    flush=True,
                )

    evaluated = [
        _evaluate_window(
            identifier,
            window,
            transcript=str(cache[window.cache_key].get("text", "")),
            known_shabad_id=args.known_shabad_id,
        )
        for window in windows
    ]
    report = _summarize(evaluated, labels)
    report.update(
        {
            "audio": str(args.audio),
            "labels": str(args.labels),
            "corpus": str(args.corpus),
            "model_id": args.model_id,
            "device": args.device,
            "asr_chunk_length_s": args.asr_chunk_length_s,
            "audio_sha256": audio_sha,
            "window_count": len(windows),
        }
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["best_configs"], ensure_ascii=False, indent=2))
    print(f"Wrote report to {args.report}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Surt ASR windows against a Khoji line-label TSV."
    )
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--model-id", default=DEFAULT_SURT_MODEL_ID)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--known-shabad-id", default="SGGS:DSB")
    parser.add_argument("--asr-chunk-length-s", type=int, default=30)
    parser.add_argument("--audio-duration-s", type=float)
    parser.add_argument("--oracle-pads-s", type=_float_list, default=(0.0, 1.0, 2.0))
    parser.add_argument("--center-durations-s", type=_float_list, default=(8.0, 12.0, 16.0))
    parser.add_argument("--rolling-window-s", type=_float_list, default=(10.0, 12.0, 15.0))
    parser.add_argument("--rolling-hop-s", type=_float_list, default=(5.0,))
    return parser.parse_args()


def _float_list(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in value.split(",") if item.strip())


def _load_label_segments(path: Path) -> list[LabelSegment]:
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        rows = []
        for row in reader:
            if row.get("include_in_eval", "yes") != "yes":
                continue
            if not row.get("start_s") or not row.get("end_s"):
                continue
            rows.append(
                LabelSegment(
                    segment_id=str(row["segment_id"]),
                    line_id=str(row["line_id"]),
                    shabad_id=str(row["shabad_id"]),
                    start_s=float(row["start_s"]),
                    end_s=float(row["end_s"]),
                    text=str(row.get("text", "")),
                )
            )
        return rows


def _load_cache(
    path: Path,
    *,
    audio_sha: str,
    model_id: str,
) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return cache
    with path.open(encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            if record.get("audio_sha256") != audio_sha:
                continue
            if record.get("model_id") != model_id:
                continue
            cache[str(record["cache_key"])] = record
    return cache


def _build_windows(
    labels: list[LabelSegment],
    *,
    audio_duration_s: float,
    oracle_pads_s: tuple[float, ...],
    center_durations_s: tuple[float, ...],
    rolling_window_s: tuple[float, ...],
    rolling_hop_s: tuple[float, ...],
) -> list[AudioWindow]:
    windows: dict[tuple[str, str, float, float, float, str], AudioWindow] = {}
    for label in labels:
        for pad_s in oracle_pads_s:
            start_s = max(0.0, label.start_s - pad_s)
            end_s = min(audio_duration_s, label.end_s + pad_s)
            _add_window(
                windows,
                AudioWindow(
                    mode="oracle",
                    strategy=f"span+{pad_s:g}s-pad",
                    start_s=start_s,
                    duration_s=end_s - start_s,
                    selection_time_s=label.midpoint_s,
                    expected_line_id=label.line_id,
                    expected_segment_id=label.segment_id,
                ),
            )
        for duration_s in center_durations_s:
            start_s = min(
                max(0.0, label.midpoint_s - duration_s / 2),
                max(0.0, audio_duration_s - duration_s),
            )
            _add_window(
                windows,
                AudioWindow(
                    mode="center",
                    strategy=f"center-{duration_s:g}s",
                    start_s=start_s,
                    duration_s=min(duration_s, audio_duration_s - start_s),
                    selection_time_s=label.midpoint_s,
                    expected_line_id=label.line_id,
                    expected_segment_id=label.segment_id,
                ),
            )

    for duration_s in rolling_window_s:
        for hop_s in rolling_hop_s:
            start_s = 0.0
            while start_s < audio_duration_s:
                duration = min(duration_s, audio_duration_s - start_s)
                center_time = start_s + duration / 2
                center_label = _label_at_time(labels, center_time)
                if center_label is not None:
                    _add_window(
                        windows,
                        AudioWindow(
                            mode="rolling",
                            strategy=f"window-{duration_s:g}s-hop-{hop_s:g}s-center",
                            start_s=start_s,
                            duration_s=duration,
                            selection_time_s=center_time,
                            expected_line_id=center_label.line_id,
                            expected_segment_id=center_label.segment_id,
                        ),
                    )
                majority_label = _majority_overlap_label(labels, start_s, start_s + duration)
                if majority_label is not None:
                    _add_window(
                        windows,
                        AudioWindow(
                            mode="rolling",
                            strategy=f"window-{duration_s:g}s-hop-{hop_s:g}s-majority",
                            start_s=start_s,
                            duration_s=duration,
                            selection_time_s=center_time,
                            expected_line_id=majority_label.line_id,
                            expected_segment_id=majority_label.segment_id,
                        ),
                    )
                start_s += hop_s
    return list(windows.values())


def _add_window(
    windows: dict[tuple[str, str, float, float, float, str], AudioWindow],
    window: AudioWindow,
) -> None:
    key = (
        window.mode,
        window.strategy,
        round(window.start_s, 3),
        round(window.duration_s, 3),
        round(window.selection_time_s, 3),
        window.expected_line_id,
    )
    windows[key] = window


def _label_at_time(
    labels: list[LabelSegment],
    time_s: float,
) -> LabelSegment | None:
    for label in labels:
        if label.start_s <= time_s < label.end_s:
            return label
    return None


def _majority_overlap_label(
    labels: list[LabelSegment],
    start_s: float,
    end_s: float,
) -> LabelSegment | None:
    best_label = None
    best_overlap = 0.0
    for label in labels:
        overlap = max(0.0, min(end_s, label.end_s) - max(start_s, label.start_s))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label
    return best_label


def _evaluate_window(
    identifier: Phase1Identifier,
    window: AudioWindow,
    *,
    transcript: str,
    known_shabad_id: str,
) -> dict[str, Any]:
    normal = identifier.identify_text(transcript) if transcript else {"status": "unknown"}
    normal_line_id = (
        normal.get("active_line", {}).get("line_id")
        if normal.get("status") == "identified"
        else ""
    )
    normal_shabad_id = (
        normal.get("shabad", {}).get("shabad_id")
        if normal.get("status") == "identified"
        else ""
    )

    known_line_id = ""
    known_score = 0.0
    known_confidence = 0.0
    if transcript:
        known_lines = identifier.index.search_lines(
            transcript,
            shabad_id=known_shabad_id,
            top_k=5,
        )
        if known_lines:
            known_line_id = known_lines[0].line.line_id
            known_score = known_lines[0].score
            known_confidence = known_lines[0].confidence

    base = {
        **asdict(window),
        "transcript": transcript,
        "normal_shabad_id": normal_shabad_id,
        "normal_line_id": normal_line_id,
        "normal_correct": normal_line_id == window.expected_line_id,
        "known_shabad_line_id": known_line_id,
        "known_shabad_correct": known_line_id == window.expected_line_id,
        "known_shabad_score": known_score,
        "known_shabad_confidence": known_confidence,
    }
    return base


def _summarize(
    evaluated: list[dict[str, Any]],
    labels: list[LabelSegment],
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in evaluated:
        key = f"{row['mode']}::{row['strategy']}"
        groups.setdefault(key, []).append(row)

    configs = []
    for key, rows in groups.items():
        total = len(rows)
        normal_correct = sum(1 for row in rows if row["normal_correct"])
        known_correct = sum(1 for row in rows if row["known_shabad_correct"])
        rolling_metrics = (
            _rolling_boundary_metrics(rows, labels, field="known_shabad_line_id")
            if rows and rows[0]["mode"] == "rolling"
            else {}
        )
        configs.append(
            {
                "config": key,
                "mode": rows[0]["mode"],
                "strategy": rows[0]["strategy"],
                "window_count": total,
                "normal_accuracy": normal_correct / total if total else 0.0,
                "known_shabad_accuracy": known_correct / total if total else 0.0,
                **rolling_metrics,
            }
        )
    configs.sort(
        key=lambda item: (
            item["known_shabad_accuracy"],
            -item.get("median_boundary_error_s", 9999.0),
            item["normal_accuracy"],
        ),
        reverse=True,
    )
    return {
        "best_configs": configs[:10],
        "configs": configs,
        "windows": evaluated,
        "labels": [asdict(label) for label in labels],
    }


def _rolling_boundary_metrics(
    rows: list[dict[str, Any]],
    labels: list[LabelSegment],
    *,
    field: str,
) -> dict[str, Any]:
    rows = sorted(rows, key=lambda row: row["selection_time_s"])
    predicted_boundaries = []
    for previous, current in zip(rows, rows[1:], strict=False):
        if previous.get(field) != current.get(field):
            predicted_boundaries.append(
                {
                    "time_s": (
                        float(previous["selection_time_s"]) + float(current["selection_time_s"])
                    )
                    / 2,
                    "from_line_id": previous.get(field, ""),
                    "to_line_id": current.get(field, ""),
                }
            )

    collapsed_labels = _collapse_labels(labels)
    label_boundaries = [
        {
            "time_s": current.start_s,
            "from_line_id": previous.line_id,
            "to_line_id": current.line_id,
        }
        for previous, current in zip(collapsed_labels, collapsed_labels[1:], strict=False)
    ]
    errors = []
    matched = 0
    for label_boundary in label_boundaries:
        candidates = [
            abs(predicted["time_s"] - label_boundary["time_s"])
            for predicted in predicted_boundaries
            if predicted["from_line_id"] == label_boundary["from_line_id"]
            and predicted["to_line_id"] == label_boundary["to_line_id"]
        ]
        if candidates:
            matched += 1
            errors.append(min(candidates))
    errors.sort()
    median = errors[len(errors) // 2] if errors else None
    return {
        "label_boundary_count": len(label_boundaries),
        "predicted_boundary_count": len(predicted_boundaries),
        "matched_boundary_count": matched,
        "median_boundary_error_s": median,
        "boundaries_within_8s": sum(1 for error in errors if error <= 8.0),
    }


def _collapse_labels(labels: list[LabelSegment]) -> list[LabelSegment]:
    collapsed: list[LabelSegment] = []
    for label in labels:
        if collapsed and collapsed[-1].line_id == label.line_id:
            previous = collapsed[-1]
            collapsed[-1] = LabelSegment(
                segment_id=previous.segment_id,
                line_id=previous.line_id,
                shabad_id=previous.shabad_id,
                start_s=previous.start_s,
                end_s=label.end_s,
                text=previous.text,
            )
        else:
            collapsed.append(label)
    return collapsed


if __name__ == "__main__":
    raise SystemExit(main())
