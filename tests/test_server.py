from __future__ import annotations

import json
import os
import io
import wave
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from khoji.phase1 import BenchmarkClip, sha256_file
from khoji.server import DEFAULT_STATIC_DIR, create_server


class ServerTests(unittest.TestCase):
    def test_serves_html_and_identifies_multipart_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus_path = _write_corpus_fixture(root)
            manifest_path, audio_path = _write_manifest_fixture(root)
            recording_manifest_path = _write_recording_manifest_fixture(root, audio_path)
            server = create_server(
                corpus_path=corpus_path,
                manifest_path=manifest_path,
                host="127.0.0.1",
                port=0,
                static_dir=DEFAULT_STATIC_DIR,
                recording_manifest_path=recording_manifest_path,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_port}"
                html = urlopen(f"{base_url}/", timeout=5).read().decode("utf-8")
                self.assertIn("micButton", html)
                self.assertIn("mediaPlayer", html)
                self.assertIn("Add media", html)
                self.assertIn("transcriptView", html)
                self.assertIn("searchTranscript", html)
                app_js = urlopen(f"{base_url}/app.js", timeout=5).read().decode("utf-8")
                self.assertIn("mic-recording.webm", app_js)
                self.assertIn("renderTranscript", app_js)
                self.assertIn("start_s: start", app_js)
                self.assertNotIn("live-window.webm", app_js)

                response = _post_multipart_audio(
                    f"{base_url}/api/identify-audio",
                    audio_path.read_bytes(),
                )
                self.assertEqual(response["status"], "identified")
                self.assertEqual(response["active_line"]["line_id"], "sample_line_1")
                self.assertTrue(response["active_line"]["translation"])
                self.assertTrue(
                    all(
                        line["translation"] == ""
                        for line in response["context_lines"]
                        if not line["is_active"]
                    )
                )

                live_response = _post_multipart_audio(
                    f"{base_url}/api/live-chunk",
                    audio_path.read_bytes(),
                    session_id="test-session",
                    fields={"within_shabad_id": "sample_shabad"},
                )
                self.assertEqual(live_response["status"], "identified")
                self.assertEqual(live_response["session_id"], "test-session")
                self.assertEqual(live_response["live"]["status"], "accepted")
                self.assertEqual(live_response["within_shabad_id"], "sample_shabad")
                self.assertEqual(live_response["latest_query"], "kahe re ban khojan jai")

                labeler_html = urlopen(f"{base_url}/labeler", timeout=5).read().decode("utf-8")
                self.assertIn("labelAudio", labeler_html)

                state = json.loads(
                    urlopen(
                        f"{base_url}/api/labeler-state?recording_id=recording-1",
                        timeout=5,
                    ).read().decode("utf-8")
                )
                self.assertEqual(state["recording"]["recording_id"], "recording-1")
                self.assertEqual(state["shabad"]["lines"][0]["line_id"], "sample_line_1")

                audio_response = urlopen(
                    f"{base_url}/api/recording-audio?recording_id=recording-1",
                    timeout=5,
                ).read()
                self.assertEqual(audio_response, audio_path.read_bytes())

                search = json.loads(
                    urlopen(
                        f"{base_url}/api/search-lines?q=sarab+nivasi&top_k=5",
                        timeout=5,
                    ).read().decode("utf-8")
                )
                self.assertEqual(search["results"][0]["line_id"], "sample_line_2")
                self.assertEqual(search["results"][0]["shabad_id"], "sample_shabad")

                first_letter_search = json.loads(
                    urlopen(
                        f"{base_url}/api/search-lines?q=krbkj&top_k=5",
                        timeout=5,
                    ).read().decode("utf-8")
                )
                self.assertEqual(first_letter_search["results"][0]["line_id"], "sample_line_1")

                first_label = _post_json(
                    f"{base_url}/api/label-line-click",
                    {"recording_id": "recording-1", "line_id": "sample_line_1", "time_s": 1.25},
                )
                self.assertEqual(first_label["labels"][0]["start_s"], "1.25")
                self.assertEqual(first_label["labels"][0]["end_s"], "")

                second_label = _post_json(
                    f"{base_url}/api/label-line-click",
                    {"recording_id": "recording-1", "line_id": "sample_line_2", "time_s": 4.0},
                )
                self.assertEqual(second_label["labels"][0]["end_s"], "4")
                self.assertEqual(second_label["labels"][1]["line_id"], "sample_line_2")

                finished = _post_json(
                    f"{base_url}/api/label-finish",
                    {"recording_id": "recording-1", "time_s": 7.5},
                )
                self.assertEqual(finished["labels"][1]["end_s"], "7.5")

                reset = _post_json(
                    f"{base_url}/api/label-reset",
                    {"recording_id": "recording-1"},
                )
                self.assertEqual(reset["labels"], [])

                upload_audio = _wav_bytes()
                uploaded = _post_multipart_audio(
                    f"{base_url}/api/recording-upload",
                    upload_audio,
                )
                self.assertEqual(uploaded["recording"]["shabad_id"], "")
                self.assertIsNone(uploaded["shabad"])
                self.assertEqual(uploaded["labels"], [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


def _post_multipart_audio(
    url: str,
    audio_bytes: bytes,
    *,
    session_id: str | None = None,
    fields: dict[str, str] | None = None,
) -> dict:
    boundary = "----KhojiBoundary"
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Disposition: form-data; name="translation_language"\r\n\r\n',
        b"Punjabi\r\n",
    ]
    if session_id is not None:
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                b'Content-Disposition: form-data; name="session_id"\r\n\r\n',
                session_id.encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, value in (fields or {}).items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            b'Content-Disposition: form-data; name="audio"; filename="clip.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            audio_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    body = b"".join(parts)
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return json.loads(urlopen(request, timeout=5).read().decode("utf-8"))


def _post_json(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urlopen(request, timeout=5).read().decode("utf-8"))


def _write_manifest_fixture(directory: Path) -> tuple[Path, Path]:
    audio_path = directory / "clip.wav"
    audio_path.write_bytes(b"server fixture audio bytes")
    clip = BenchmarkClip(
        clip_id="clip-1",
        shabad_id="sample_shabad",
        line_id="sample_line_1",
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


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


def _write_recording_manifest_fixture(directory: Path, audio_path: Path) -> Path:
    recording_dir = directory / "recordings"
    recording_dir.mkdir()
    manifest_path = recording_dir / "manifest.jsonl"
    record = {
        "recording_id": "recording-1",
        "shabad_id": "sample_shabad",
        "audio_path": os.path.relpath(audio_path, recording_dir),
        "duration_ms": 10000,
        "sha256": sha256_file(audio_path),
        "kind": "kirtan",
        "split": "dev",
        "has_vocals": True,
        "source": "fixture",
        "notes": "",
        "line_labels_path": "",
    }
    manifest_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def _write_corpus_fixture(directory: Path) -> Path:
    corpus_path = directory / "corpus.jsonl"
    record = {
        "shabad_id": "sample_shabad",
        "title": "Sample Shabad",
        "ang": 684,
        "raag": "Dhanasri",
        "author": "Fixture",
        "lines": [
            {
                "line_id": "sample_line_1",
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
                "line_id": "sample_line_2",
                "order": 2,
                "gurmukhi": "ਸਰਬ ਨਿਵਾਸੀ ਸਦਾ ਅਲੇਪਾ ॥",
                "transliteration": "sarab nivasi sada alepa",
            },
        ],
    }
    corpus_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return corpus_path


if __name__ == "__main__":
    unittest.main()
