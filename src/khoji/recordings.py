from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .phase1 import sha256_file


@dataclass(frozen=True)
class RecordingLabel:
    recording_id: str
    shabad_id: str
    audio_path: str
    duration_ms: int
    sha256: str
    kind: str
    split: str
    has_vocals: bool
    source: str
    notes: str = ""
    line_labels_path: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "RecordingLabel":
        return cls(
            recording_id=str(data["recording_id"]),
            shabad_id=str(data["shabad_id"]),
            audio_path=str(data["audio_path"]),
            duration_ms=int(data["duration_ms"]),
            sha256=str(data["sha256"]),
            kind=str(data.get("kind", "kirtan")),
            split=str(data.get("split", "dev")),
            has_vocals=bool(data.get("has_vocals", True)),
            source=str(data.get("source", "local")),
            notes=str(data.get("notes", "")),
            line_labels_path=str(data.get("line_labels_path", "")),
        )


def register_recording(
    *,
    audio_path: str | Path,
    manifest_path: str | Path,
    recording_id: str,
    shabad_id: str,
    kind: str = "kirtan",
    split: str = "dev",
    has_vocals: bool = True,
    source: str = "local",
    notes: str = "",
    line_labels_path: str = "",
) -> RecordingLabel:
    audio = Path(audio_path)
    manifest = Path(manifest_path)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    relative_audio = os.path.relpath(audio, manifest.parent)

    label = RecordingLabel(
        recording_id=recording_id,
        shabad_id=shabad_id,
        audio_path=relative_audio,
        duration_ms=probe_duration_ms(audio),
        sha256=sha256_file(audio),
        kind=kind,
        split=split,
        has_vocals=has_vocals,
        source=source,
        notes=notes,
        line_labels_path=line_labels_path,
    )
    labels = [
        existing
        for existing in load_recording_manifest(manifest)
        if existing.recording_id != recording_id
    ]
    labels.append(label)
    with manifest.open("w", encoding="utf-8") as output:
        for item in sorted(labels, key=lambda record: record.recording_id):
            output.write(json.dumps(asdict(item), ensure_ascii=False, separators=(",", ":")))
            output.write("\n")
    return label


def load_recording_manifest(path: str | Path) -> list[RecordingLabel]:
    manifest = Path(path)
    if not manifest.exists():
        return []
    labels: list[RecordingLabel] = []
    for line_number, raw_line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            labels.append(RecordingLabel.from_mapping(json.loads(line)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid recording manifest line {line_number}: {exc}") from exc
    return labels


def probe_duration_ms(audio_path: str | Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(float(result.stdout.strip()) * 1000)
