from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Shabad


class CorpusError(ValueError):
    pass


def load_shabads(path: str | Path) -> list[Shabad]:
    corpus_path = Path(path)
    if not corpus_path.exists():
        raise CorpusError(f"Corpus does not exist: {corpus_path}")

    if corpus_path.suffix == ".jsonl":
        records = _load_jsonl(corpus_path)
    else:
        payload = json.loads(corpus_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            records = payload.get("shabads", [])
        else:
            records = payload

    if not isinstance(records, list):
        raise CorpusError("Corpus must be a list or an object with a 'shabads' list")

    shabads = [Shabad.from_mapping(record) for record in records]
    validate_shabads(shabads)
    return shabads


def validate_shabads(shabads: list[Shabad]) -> None:
    seen_shabads: set[str] = set()
    seen_lines: set[str] = set()
    problems: list[str] = []

    for shabad in shabads:
        if shabad.shabad_id in seen_shabads:
            problems.append(f"Duplicate shabad_id: {shabad.shabad_id}")
        seen_shabads.add(shabad.shabad_id)

        if not shabad.lines:
            problems.append(f"Shabad has no lines: {shabad.shabad_id}")

        previous_order = 0
        for line in shabad.lines:
            if line.line_id in seen_lines:
                problems.append(f"Duplicate line_id: {line.line_id}")
            seen_lines.add(line.line_id)

            if line.order <= previous_order:
                problems.append(
                    f"Line order must increase in {shabad.shabad_id}: {line.line_id}"
                )
            previous_order = line.order

            if not line.gurmukhi and not line.transliteration:
                problems.append(f"Line has no searchable text: {line.line_id}")

    if problems:
        raise CorpusError("\n".join(problems))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CorpusError(f"Invalid JSONL on line {line_number}: {exc}") from exc
        if not isinstance(record, dict):
            raise CorpusError(f"JSONL line {line_number} must be an object")
        records.append(record)
    return records

