from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .models import Line, Shabad


LINE_LABEL_COLUMNS = (
    "segment_id",
    "recording_id",
    "audio_path",
    "shabad_id",
    "line_id",
    "line_order",
    "start_s",
    "end_s",
    "segment_type",
    "include_in_eval",
    "text",
    "punjabi_translation",
    "english_translation",
    "notes",
)


def build_line_label_template_rows(
    shabad: Shabad,
    *,
    recording_id: str,
    audio_path: str = "",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in shabad.lines:
        rows.append(
            {
                "segment_id": f"{recording_id}_{line.order:03d}",
                "recording_id": recording_id,
                "audio_path": audio_path,
                "shabad_id": shabad.shabad_id,
                "line_id": line.line_id,
                "line_order": line.order,
                "start_s": "",
                "end_s": "",
                "segment_type": "vocal",
                "include_in_eval": "yes",
                "text": line.transliteration or line.gurmukhi,
                "punjabi_translation": _translation_for_line(line, "Punjabi"),
                "english_translation": _translation_for_line(line, "English"),
                "notes": "",
            }
        )
    return rows


def write_line_label_template(
    rows: list[dict[str, Any]],
    path: str | Path,
) -> None:
    write_line_label_rows(rows, path)


def load_line_label_rows(path: str | Path) -> list[dict[str, str]]:
    label_path = Path(path)
    if not label_path.exists():
        return []
    with label_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        return [dict(row) for row in reader]


def write_line_label_rows(rows: list[dict[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=LINE_LABEL_COLUMNS,
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def label_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if str(row.get("start_s", "")).strip()]


def apply_line_click(
    rows: list[dict[str, Any]],
    shabad: Shabad,
    *,
    recording_id: str,
    audio_path: str,
    line_id: str,
    time_s: float,
) -> list[dict[str, Any]]:
    if time_s < 0:
        raise ValueError("Label timestamp must be >= 0")
    line = _line_by_id(shabad, line_id)
    segments = label_segments(rows)
    _close_open_segment(segments, time_s)
    segments.append(
        _segment_row(
            shabad,
            line,
            recording_id=recording_id,
            audio_path=audio_path,
            sequence=len(segments) + 1,
            start_s=time_s,
            end_s="",
            segment_type="vocal",
            include_in_eval="yes",
            notes="",
        )
    )
    return segments


def finish_open_segment(
    rows: list[dict[str, Any]],
    *,
    time_s: float,
) -> list[dict[str, Any]]:
    if time_s < 0:
        raise ValueError("Label timestamp must be >= 0")
    segments = label_segments(rows)
    _close_open_segment(segments, time_s)
    return segments


def reset_label_rows() -> list[dict[str, Any]]:
    return []


def _segment_row(
    shabad: Shabad,
    line: Line,
    *,
    recording_id: str,
    audio_path: str,
    sequence: int,
    start_s: float,
    end_s: str | float,
    segment_type: str,
    include_in_eval: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "segment_id": f"{recording_id}_{sequence:04d}",
        "recording_id": recording_id,
        "audio_path": audio_path,
        "shabad_id": shabad.shabad_id,
        "line_id": line.line_id,
        "line_order": line.order,
        "start_s": format_seconds(start_s),
        "end_s": format_seconds(end_s) if isinstance(end_s, (int, float)) else end_s,
        "segment_type": segment_type,
        "include_in_eval": include_in_eval,
        "text": line.transliteration or line.gurmukhi,
        "punjabi_translation": _translation_for_line(line, "Punjabi"),
        "english_translation": _translation_for_line(line, "English"),
        "notes": notes,
    }


def _close_open_segment(rows: list[dict[str, Any]], time_s: float) -> None:
    if not rows:
        return
    last = rows[-1]
    if str(last.get("end_s", "")).strip():
        return
    start_s = _parse_seconds(last.get("start_s", "0"))
    if time_s < start_s:
        raise ValueError("Label timestamp cannot move backward")
    last["end_s"] = format_seconds(time_s)


def _line_by_id(shabad: Shabad, line_id: str) -> Line:
    for line in shabad.lines:
        if line.line_id == line_id:
            return line
    raise ValueError(f"Line {line_id} is not part of shabad {shabad.shabad_id}")


def _parse_seconds(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timestamp: {value}") from exc


def format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _translation_for_line(line: Line, language: str) -> str:
    for translation in line.metadata.get("translations", []):
        if translation.get("language") == language:
            return str(translation.get("text", ""))
    if language == "English":
        return line.english
    return ""
