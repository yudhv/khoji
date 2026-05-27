from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from khoji.line_labels import (
    apply_line_click,
    build_line_label_template_rows,
    finish_open_segment,
    write_line_label_template,
)
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

    def test_line_click_closes_previous_segment_and_starts_next(self) -> None:
        shabad = _sample_shabad()

        rows = apply_line_click(
            [],
            shabad,
            recording_id="rec",
            audio_path="audio.mp3",
            line_id="line_1",
            time_s=12.3456,
        )
        rows = apply_line_click(
            rows,
            shabad,
            recording_id="rec",
            audio_path="audio.mp3",
            line_id="line_1",
            time_s=20.0,
        )

        self.assertEqual(rows[0]["start_s"], "12.346")
        self.assertEqual(rows[0]["end_s"], "20")
        self.assertEqual(rows[1]["line_id"], "line_1")
        self.assertEqual(rows[1]["start_s"], "20")
        self.assertEqual(rows[1]["end_s"], "")

    def test_finish_open_segment_records_final_end_time(self) -> None:
        shabad = _sample_shabad()
        rows = apply_line_click(
            [],
            shabad,
            recording_id="rec",
            audio_path="audio.mp3",
            line_id="line_1",
            time_s=5.0,
        )

        finished = finish_open_segment(rows, time_s=9.25)

        self.assertEqual(finished[0]["end_s"], "9.25")


def _sample_shabad() -> Shabad:
    return Shabad(
        shabad_id="SGGS:DSB",
        title="Kahe Re Ban",
        lines=(
            Line(
                shabad_id="SGGS:DSB",
                line_id="line_1",
                order=1,
                gurmukhi="",
                transliteration="kaahe re; ban khojan jaaee |",
                english="Why do you go looking for Him in the forest?",
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
