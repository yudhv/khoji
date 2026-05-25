from __future__ import annotations

import json
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
            server = create_server(
                corpus_path=corpus_path,
                manifest_path=manifest_path,
                host="127.0.0.1",
                port=0,
                static_dir=DEFAULT_STATIC_DIR,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_port}"
                html = urlopen(f"{base_url}/", timeout=5).read().decode("utf-8")
                self.assertIn("micButton", html)

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
                )
                self.assertEqual(live_response["status"], "identified")
                self.assertEqual(live_response["session_id"], "test-session")
                self.assertEqual(live_response["live"]["status"], "accepted")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


def _post_multipart_audio(
    url: str,
    audio_bytes: bytes,
    *,
    session_id: str | None = None,
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
