from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

from khoji.recordings import load_recording_manifest, register_recording


class RecordingManifestTests(unittest.TestCase):
    def test_registers_real_recording_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_path = root / "clip.wav"
            _write_silence(audio_path)
            manifest_path = root / "recordings" / "manifest.jsonl"

            label = register_recording(
                audio_path=audio_path,
                manifest_path=manifest_path,
                recording_id="kahe_full",
                shabad_id="SGGS:DSB",
                notes="fixture",
            )

            loaded = load_recording_manifest(manifest_path)
            self.assertEqual(label.recording_id, "kahe_full")
            self.assertEqual(label.shabad_id, "SGGS:DSB")
            self.assertEqual(label.audio_path, "../clip.wav")
            self.assertGreater(label.duration_ms, 900)
            self.assertEqual(loaded, [label])

    def test_replaces_existing_recording_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio_path = root / "clip.wav"
            _write_silence(audio_path)
            manifest_path = root / "manifest.jsonl"

            register_recording(
                audio_path=audio_path,
                manifest_path=manifest_path,
                recording_id="same",
                shabad_id="SGGS:OLD",
            )
            register_recording(
                audio_path=audio_path,
                manifest_path=manifest_path,
                recording_id="same",
                shabad_id="SGGS:NEW",
            )

            rows = [
                json.loads(line)
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["shabad_id"], "SGGS:NEW")


def _write_silence(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)


if __name__ == "__main__":
    unittest.main()

