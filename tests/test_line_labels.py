from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from khoji.line_labels import build_line_label_template_rows, write_line_label_template
from khoji.models import Line, Shabad


class LineLabelTemplateTests(unittest.TestCase):
    def test_writes_fillable_tsv_template(self) -> None:
        shabad = Shabad(
            shabad_id="SGGS:DSB",
            title="Kahe Re Ban",
            lines=(
                Line(
                    shabad_id="SGGS:DSB",
                    line_id="SGGS:Q7PD",
                    order=3,
                    gurmukhi="",
                    transliteration="kaahe re; ban khojan jaaee |",
                    english="Why do you go looking for Him in the forest?",
                    metadata={
                        "translations": [
                            {
                                "language": "Punjabi",
                                "text": "ਹੇ ਭਾਈ! ਤੂੰ ਜੰਗਲਾਂ ਵਿਚ ਕਿਉਂ ਜਾਂਦਾ ਹੈਂ?",
                            }
                        ]
                    },
                ),
            ),
        )

        rows = build_line_label_template_rows(
            shabad,
            recording_id="kahe_re_ban_full_001",
            audio_path="../benchmark/audio/kahe.mp3",
        )

        self.assertEqual(rows[0]["segment_id"], "kahe_re_ban_full_001_003")
        self.assertEqual(rows[0]["line_id"], "SGGS:Q7PD")
        self.assertEqual(rows[0]["start_s"], "")
        self.assertEqual(rows[0]["segment_type"], "vocal")
        self.assertEqual(rows[0]["include_in_eval"], "yes")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "labels.tsv"
            write_line_label_template(rows, output)
            with output.open(encoding="utf-8", newline="") as file:
                parsed = list(csv.DictReader(file, delimiter="\t"))

        self.assertEqual(parsed[0]["audio_path"], "../benchmark/audio/kahe.mp3")
        self.assertEqual(parsed[0]["english_translation"], shabad.lines[0].english)


if __name__ == "__main__":
    unittest.main()
