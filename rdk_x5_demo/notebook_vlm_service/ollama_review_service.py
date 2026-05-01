from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib import request
from urllib.error import HTTPError


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _config() -> Dict[str, str]:
    return {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/api/chat"),
        "model": os.getenv("OLLAMA_MODEL", "minicpm-v"),
        "host": os.getenv("VLM_SERVICE_HOST", "0.0.0.0"),
        "port": os.getenv("VLM_SERVICE_PORT", "9000"),
        "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "10m"),
        "timeout_seconds": os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"),
    }


def _schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "activity_label": {"type": "string"},
            "risk_level": {"type": "string", "enum": ["normal", "warning", "alarm", "uncertain"]},
            "description": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["activity_label", "risk_level", "description", "confidence"],
    }


def _prompt(metadata: Dict[str, Any]) -> str:
    return (
        "You are reviewing multiple key frames from a smart-care event.\n"
        "Choose activity_label from: normal_walking, normal_standing, normal_cleaning, normal_sitting, possible_fall, possible_injury, uncertain.\n"
        "Choose risk_level from: normal, warning, alarm, uncertain.\n"
        "Use alarm only for strong evidence of a fall, injury, or unsafe collapsed posture.\n"
        "Use warning when you are unsure or see possibly unsafe posture.\n"
        "Use normal only for clearly ordinary activity such as walking, cleaning, standing, or sitting on a chair/sofa/bed.\n"
        "Do not classify a person on the floor as normal_sitting unless it is clearly a safe intentional floor activity.\n"
        "If the person is sitting on the floor, kneeling on the floor, curled near the ground, leaning against furniture at floor level, or otherwise in a low-to-floor posture, prefer possible_fall or uncertain with risk_level warning unless the scene is clearly safe.\n"
        "If the person appears collapsed, lying on the floor, unable to rise, or in an obviously unstable posture, use possible_fall or possible_injury and choose alarm.\n"
        "When in doubt between normal_sitting and possible_fall for a person on the floor, choose possible_fall.\n"
        f"Metadata: {json.dumps(metadata, ensure_ascii=False)}\n"
        "Return valid JSON only."
    )


def _failed_result(message: str) -> Dict[str, Any]:
    return {
        "activity_label": "uncertain",
        "risk_level": "warning",
        "description": f"VLM review failed: {message}",
        "confidence": 0.0,
        "status": "failed",
    }


def _decode_ollama_content(body: Dict[str, Any]) -> Dict[str, Any]:
    content = body.get("message", {}).get("content", "{}")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {
            "activity_label": "uncertain",
            "risk_level": "warning",
            "description": content,
            "confidence": 0.0,
        }
    parsed["status"] = "ok"
    return parsed


def _request_ollama(frame_images: List[str], metadata: Dict[str, Any], *, use_schema: bool) -> Dict[str, Any]:
    cfg = _config()
    payload = {
        "model": cfg["model"],
        "stream": False,
        "keep_alive": cfg["keep_alive"],
        "messages": [
            {
                "role": "user",
                "content": _prompt(metadata),
                "images": frame_images,
            }
        ],
    }
    if use_schema:
        payload["format"] = _schema()
    req = request.Request(
        cfg["base_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=int(cfg["timeout_seconds"])) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = ""
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "<unreadable error body>"
        raise RuntimeError(f"Ollama HTTP {exc.code}: {error_body}") from exc

    return _decode_ollama_content(body)


def call_ollama(frame_images: List[str], metadata: Dict[str, Any]) -> Dict[str, Any]:
    if not frame_images:
        return _failed_result("no frame images provided")

    attempts: list[tuple[str, List[str], bool]] = [("multi-frame/schema", frame_images, True)]
    if len(frame_images) > 1:
        attempts.append(("single-frame/schema", [frame_images[0]], True))
    attempts.append(("single-frame/no-schema", [frame_images[0]], False))

    errors: list[str] = []
    for label, attempt_images, use_schema in attempts:
        try:
            logging.info("ollama attempt=%s images=%s schema=%s", label, len(attempt_images), use_schema)
            return _request_ollama(attempt_images, metadata, use_schema=use_schema)
        except Exception as exc:  # noqa: BLE001
            logging.exception("ollama attempt failed: %s", label)
            errors.append(f"{label}: {exc}")

    return _failed_result("; ".join(errors))


def main() -> None:
    load_env_file(Path(os.getenv("SMART_CARE_NOTEBOOK_ENV", Path(__file__).with_name(".env"))))
    cfg = _config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json({"status": "ok"})
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/analyze":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8"))
            frame_images = payload.get("frame_images", []) or []
            metadata = payload.get("metadata", {}) or {}
            logging.info("analyze request from=%s frames=%s metadata_keys=%s", self.client_address[0], len(frame_images), sorted(metadata.keys()))
            result = call_ollama(frame_images, metadata)
            self._json(result)

        def log_message(self, format: str, *args) -> None:
            return

        def _json(self, payload: Dict[str, Any], status_code: int = 200) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer((cfg["host"], int(cfg["port"])), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
