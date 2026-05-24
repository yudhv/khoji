from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .phase1 import DEFAULT_TRANSLATION_LANGUAGE, Phase1Identifier


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATIC_DIR = REPO_ROOT / "web"


class KhojiServerError(ValueError):
    pass


def run_server(
    *,
    corpus_path: str | Path,
    manifest_path: str | Path | None,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_dir: str | Path = DEFAULT_STATIC_DIR,
) -> None:
    server = create_server(
        corpus_path=corpus_path,
        manifest_path=manifest_path,
        host=host,
        port=port,
        static_dir=static_dir,
    )
    print(f"Khoji server listening on http://{host}:{port}")
    server.serve_forever()


def create_server(
    *,
    corpus_path: str | Path,
    manifest_path: str | Path | None,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_dir: str | Path = DEFAULT_STATIC_DIR,
) -> ThreadingHTTPServer:
    identifier = Phase1Identifier(corpus_path, manifest_path)
    handler = _make_handler(identifier, Path(static_dir))
    return ThreadingHTTPServer((host, port), handler)


def _make_handler(identifier: Phase1Identifier, static_dir: Path):
    class KhojiRequestHandler(BaseHTTPRequestHandler):
        server_version = "KhojiHTTP/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._send_json({"ok": True, "clips": len(identifier.clips)})
                return
            if parsed.path == "/":
                self._send_static_file(static_dir / "index.html")
                return
            static_path = (static_dir / parsed.path.lstrip("/")).resolve()
            if not _is_relative_to(static_path, static_dir.resolve()):
                self._send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            self._send_static_file(static_path)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/identify-audio":
                    body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                    audio_bytes, fields = _extract_audio_request(
                        body,
                        self.headers.get("Content-Type", ""),
                    )
                    language = fields.get("translation_language", DEFAULT_TRANSLATION_LANGUAGE)
                    result = identifier.identify_audio(
                        audio_bytes,
                        translation_language=language,
                    )
                    self._send_json(result)
                    return
                if parsed.path == "/api/identify-text":
                    payload = self._read_json()
                    query = str(payload.get("query", ""))
                    language = str(
                        payload.get("translation_language", DEFAULT_TRANSLATION_LANGUAGE)
                    )
                    self._send_json(
                        identifier.identify_text(query, translation_language=language)
                    )
                    return
            except (KhojiServerError, ValueError, json.JSONDecodeError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def _send_json(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_static_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            content_type = _content_type(path)
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"ok": False, "error": message}, status=status)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

    return KhojiRequestHandler


def _extract_audio_request(body: bytes, content_type: str) -> tuple[bytes, dict[str, str]]:
    if content_type.startswith("application/octet-stream"):
        return body, {}
    if not content_type.startswith("multipart/form-data"):
        raise KhojiServerError("Expected multipart/form-data or application/octet-stream")

    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        + body
    )
    fields: dict[str, str] = {}
    audio_bytes: bytes | None = None
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        params = dict(part.get_params(header="content-disposition") or [])
        name = params.get("name")
        if not name or "form-data" not in disposition:
            continue
        payload = part.get_payload(decode=True) or b""
        if name == "audio":
            audio_bytes = payload
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8")
    if audio_bytes is None:
        raise KhojiServerError("No multipart field named 'audio' found")
    return audio_bytes, fields


def _content_type(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    return "application/octet-stream"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
