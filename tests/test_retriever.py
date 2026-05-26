from __future__ import annotations

import unittest
from pathlib import Path

from khoji.corpus import CorpusError, load_shabads, validate_shabads
from khoji.models import Line, Shabad
from khoji.normalization import normalize_text, transliterate_gurmukhi_to_ascii
from khoji.retriever import KhojiIndex


SAMPLE_CORPUS = Path(__file__).resolve().parents[1] / "data/sample/shabads.jsonl"


class NormalizationTests(unittest.TestCase):
    def test_normalizes_punctuation_and_case(self) -> None:
        self.assertEqual(normalize_text("Sochai, SOCH!"), "sochai soch")

    def test_transliterates_unicode_gurmukhi_for_search(self) -> None:
        self.assertEqual(
            normalize_text(transliterate_gurmukhi_to_ascii("ਕਾਹੇ ਰੇ ਬਨ ਖੋਜਨ ਜਾਈ")),
            "kaahe re ban khojan jaaee",
        )


class CorpusTests(unittest.TestCase):
    def test_loads_sample_corpus(self) -> None:
        shabads = load_shabads(SAMPLE_CORPUS)
        self.assertEqual(len(shabads), 3)
        self.assertEqual(shabads[0].lines[0].shabad_id, shabads[0].shabad_id)

    def test_rejects_duplicate_shabad_ids(self) -> None:
        line = Line(
            shabad_id="duplicate",
            line_id="line-1",
            order=1,
            gurmukhi="",
            transliteration="sample",
        )
        shabads = [
            Shabad(shabad_id="duplicate", title="A", lines=(line,)),
            Shabad(shabad_id="duplicate", title="B", lines=(line,)),
        ]
        with self.assertRaises(CorpusError):
            validate_shabads(shabads)


class RetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = KhojiIndex(load_shabads(SAMPLE_CORPUS))

    def test_identifies_shabad_first(self) -> None:
        result = self.index.identify("kahe re ban khojan jai")
        self.assertEqual(result.best_shabad.shabad.shabad_id, "sample_kahe_re_ban")

    def test_identifies_unicode_gurmukhi_asr_output_against_transliteration(self) -> None:
        result = self.index.identify("ਕਾਹੇ ਰੇ ਬਨ ਖੋਜਨ ਜਾਈ")
        self.assertEqual(result.best_shabad.shabad.shabad_id, "sample_kahe_re_ban")

    def test_identifies_line_inside_best_shabad(self) -> None:
        result = self.index.identify("sochai soch na hovai je sochi lakh vaar")
        self.assertEqual(result.best_shabad.shabad.shabad_id, "sample_japji_001")
        self.assertEqual(result.best_line.line.line_id, "japji_001_006")

    def test_can_search_lines_with_known_shabad(self) -> None:
        result = self.index.identify(
            "tum maat pita ham baarik tere",
            within_shabad_id="sample_tu_thakur",
        )
        self.assertEqual(result.best_line.line.line_id, "tu_thakur_003")


if __name__ == "__main__":
    unittest.main()
