from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from khoji.phase1 import (
    BenchmarkClip,
    Phase1Identifier,
    evaluate_benchmark,
    sha256_file,
)


class Phase1IdentifierTests(unittest.TestCase):
    def test_identifies_known_benchmark_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus_path = _write_corpus_fixture(root)
            manifest_path, audio_path = _write_manifest_fixture(root)
            identifier = Phase1Identifier(corpus_path, manifest_path)

            result = identifier.identify_audio(audio_path.read_bytes())

            self.assertEqual(result["status"], "identified")
            self.assertEqual(result["shabad"]["shabad_id"], "sample_kahe_re_ban")
            self.assertEqual(result["active_line"]["line_id"], "kahe_re_ban_001")
            self.assertTrue(result["active_line"]["translation"])
            inactive_lines = [
                line for line in result["context_lines"] if not line["is_active"]
            ]
            self.assertTrue(inactive_lines)
            self.assertTrue(all(line["translation"] == "" for line in inactive_lines))

    def test_unknown_audio_does_not_force_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus_path = _write_corpus_fixture(root)
            manifest_path, _ = _write_manifest_fixture(root)
            identifier = Phase1Identifier(corpus_path, manifest_path)

            result = identifier.identify_audio(b"not a known benchmark clip")

            self.assertEqual(result["status"], "unknown")
            self.assertIn("fingerprint", result["unknown_reason"])

    def test_evaluates_benchmark_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus_path = _write_corpus_fixture(root)
            manifest_path, _ = _write_manifest_fixture(root)

            report = evaluate_benchmark(corpus_path, manifest_path)

            self.assertEqual(report["total_clips"], 1)
            self.assertEqual(report["shabad_top1_accuracy"], 1.0)
            self.assertEqual(report["line_top3_accuracy"], 1.0)


def _write_manifest_fixture(directory: Path) -> tuple[Path, Path]:
    audio_path = directory / "clip.wav"
    audio_path.write_bytes(b"fake wav bytes for fingerprinted phase one test")
    clip = BenchmarkClip(
        clip_id="clip-1",
        shabad_id="sample_kahe_re_ban",
        line_id="kahe_re_ban_001",
        start_ms=0,
        end_ms=2000,
        audio_path=audio_path,
        split="dev",
        kind="paath",
        transcript="kahe re ban khojan jai",
        sha256=sha256_file(audio_path),
    )
    manifest_path = directory / "manifest.jsonl"
    manifest_path.write_text(
        json.dumps(clip.to_manifest_record(directory), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path, audio_path


def _write_corpus_fixture(directory: Path) -> Path:
    corpus_path = directory / "corpus.jsonl"
    record = {
        "shabad_id": "sample_kahe_re_ban",
        "title": "Kahe Re Ban Khojan Jaai",
        "ang": 684,
        "raag": "Dhanasri",
        "author": "Guru Tegh Bahadur",
        "lines": [
            {
                "line_id": "kahe_re_ban_001",
                "order": 1,
                "gurmukhi": "ਕਾਹੇ ਰੇ ਬਨ ਖੋਜਨ ਜਾਈ ॥",
                "transliteration": "kahe re ban khojan jai",
                "metadata": {
                    "translations": [
                        {
                            "source": "Fixture",
                            "language": "Punjabi",
                            "text": "ਹੇ ਭਾਈ! ਜੰਗਲ ਵਿਚ ਕਿਉਂ ਲੱਭਣ ਜਾਂਦਾ ਹੈਂ?",
                        }
                    ]
                },
            },
            {
                "line_id": "kahe_re_ban_002",
                "order": 2,
                "gurmukhi": "ਸਰਬ ਨਿਵਾਸੀ ਸਦਾ ਅਲੇਪਾ ਤੋਹੀ ਸੰਗਿ ਸਮਾਈ ॥੧॥ ਰਹਾਉ ॥",
                "transliteration": "sarab nivasi sada alepa tohi sang samai rahao",
                "metadata": {
                    "translations": [
                        {
                            "source": "Fixture",
                            "language": "Punjabi",
                            "text": "ਉਹ ਤੇਰੇ ਨਾਲ ਹੀ ਵੱਸਦਾ ਹੈ।",
                        }
                    ]
                },
            },
        ],
    }
    corpus_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return corpus_path


if __name__ == "__main__":
    unittest.main()
