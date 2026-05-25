from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from khoji.phase1 import Phase1Identifier
from khoji.phase2 import SequenceSmoother


class SequenceSmootherTests(unittest.TestCase):
    def test_holds_one_off_shabad_change_until_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus_path = _write_corpus_fixture(Path(directory))
            identifier = Phase1Identifier(corpus_path)
            smoother = SequenceSmoother(identifier)

            first = smoother.update(identifier.identify_text("line one"))
            held = smoother.update(identifier.identify_text("other shabad first"))
            accepted = smoother.update(identifier.identify_text("other shabad first"))

            self.assertEqual(first["shabad"]["shabad_id"], "shabad_a")
            self.assertEqual(held["live"]["status"], "holding")
            self.assertEqual(held["shabad"]["shabad_id"], "shabad_a")
            self.assertEqual(accepted["live"]["decision"], "accepted_confirmed_shabad_change")
            self.assertEqual(accepted["shabad"]["shabad_id"], "shabad_b")

    def test_holds_impossible_line_jump(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus_path = _write_corpus_fixture(Path(directory))
            identifier = Phase1Identifier(corpus_path)
            smoother = SequenceSmoother(identifier)

            first = smoother.update(identifier.identify_text("line one"))
            candidate = identifier.response_for_line(
                first,
                shabad_id="shabad_a",
                line_id="a4",
            )
            candidate["top_lines"] = [
                {
                    "line_id": "a4",
                    "shabad_id": "shabad_a",
                    "order": 4,
                    "text": "line four",
                    "section": "",
                    "is_refrain": False,
                    "score": 1.0,
                    "confidence": 1.0,
                }
            ]
            jumped = smoother.update(candidate)

            self.assertEqual(first["active_line"]["line_id"], "a1")
            self.assertEqual(jumped["live"]["decision"], "held_impossible_line_jump")
            self.assertEqual(jumped["active_line"]["line_id"], "a1")

    def test_accepts_next_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus_path = _write_corpus_fixture(Path(directory))
            identifier = Phase1Identifier(corpus_path)
            smoother = SequenceSmoother(identifier)

            smoother.update(identifier.identify_text("line one"))
            next_line = smoother.update(identifier.identify_text("line two"))

            self.assertEqual(next_line["live"]["status"], "accepted")
            self.assertEqual(next_line["active_line"]["line_id"], "a2")

    def test_unknown_chunk_does_not_force_false_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus_path = _write_corpus_fixture(Path(directory))
            identifier = Phase1Identifier(corpus_path)
            smoother = SequenceSmoother(identifier)

            smoother.update(identifier.identify_text("line one"))
            unknown = smoother.update(
                {
                    "status": "unknown",
                    "unknown_reason": "fixture silence",
                    "confidence": 0.0,
                    "top_shabads": [],
                    "top_lines": [],
                    "model_votes": [],
                }
            )

            self.assertEqual(unknown["status"], "unknown")
            self.assertEqual(unknown["live"]["status"], "unknown")
            self.assertNotIn("active_line", unknown)


def _write_corpus_fixture(directory: Path) -> Path:
    corpus_path = directory / "corpus.jsonl"
    records = [
        {
            "shabad_id": "shabad_a",
            "title": "Shabad A",
            "lines": [
                {"line_id": "a1", "order": 1, "gurmukhi": "੧", "transliteration": "line one"},
                {"line_id": "a2", "order": 2, "gurmukhi": "੨", "transliteration": "line two"},
                {"line_id": "a3", "order": 3, "gurmukhi": "੩", "transliteration": "line three"},
                {"line_id": "a4", "order": 4, "gurmukhi": "੪", "transliteration": "line four"},
            ],
        },
        {
            "shabad_id": "shabad_b",
            "title": "Shabad B",
            "lines": [
                {
                    "line_id": "b1",
                    "order": 1,
                    "gurmukhi": "ਅ",
                    "transliteration": "other shabad first",
                }
            ],
        },
    ]
    corpus_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return corpus_path
