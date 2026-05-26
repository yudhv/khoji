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


def _translation_for_line(line: Line, language: str) -> str:
    for translation in line.metadata.get("translations", []):
        if translation.get("language") == language:
            return str(translation.get("text", ""))
    if language == "English":
        return line.english
    return ""
