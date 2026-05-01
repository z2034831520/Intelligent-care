from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import load_bridge_config
from .recording_config import load_recording_config


def _resolve_path(roots: dict[str, Path], request_path: str) -> Path | None:
    parsed = urlparse(request_path)
    path = parsed.path.rstrip("/")
    if path == "/health":
        return None

    prefix = "/evidence/"
    if not path.startswith(prefix):
        raise FileNotFoundError("unsupported path")

    remainder = path[len(prefix):]
    media_kind, _, relative_path = remainder.partition("/")
    if not media_kind or not relative_path:
        raise FileNotFoundError("missing media path")

    root = roots.get(media_kind)
    if root is None:
        raise FileNotFoundError("unsupported media kind")

    relative = Path(unquote(relative_path))
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except Exception as exc:
        raise FileNotFoundError("path traversal blocked") from exc

    if not candidate.is_file():
        raise FileNotFoundError("file not found")
    return candidate


def main() -> None:  # pragma: no cover
    bridge_config = load_bridge_config()
    recording_config = load_recording_config()
    roots = {
        "images": recording_config.evidence_image_dir,
        "videos": recording_config.evidence_video_dir,
        "gifs": recording_config.evidence_gif_dir,
        "frames": recording_config.evidence_frame_dir,
    }

    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json({"status": "ok"})
                return

            try:
                target = _resolve_path(roots, self.path)
                if target is None:
                    self._json({"status": "ok"})
                    return
            except FileNotFoundError:
                self.send_error(404)
                return

            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            payload = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition", f'inline; filename="{target.name}"')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args) -> None:
            return

        def _json(self, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer((bridge_config.evidence_server_host, bridge_config.evidence_server_port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
