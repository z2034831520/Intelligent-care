from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MENTION_NAME_RE = re.compile(r"^@\S+\s*")


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


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class BridgeConfig:
    host: str
    port: int
    verification_token: str
    target_chat_id: str
    bot_open_id: str
    trigger_texts: frozenset[str]
    ssh_path: str
    ssh_user: str
    ssh_host: str
    ssh_identity_file: str
    ssh_options: tuple[str, ...]
    remote_command: str
    log_path: Path
    dedup_ttl_seconds: int


def load_config() -> BridgeConfig:
    env_path = Path(os.getenv("SMART_CARE_NOTEBOOK_ENV", Path(__file__).with_name(".env")))
    load_env_file(env_path)

    trigger_texts = frozenset(
        text.strip() for text in _split_csv(os.getenv("FEISHU_COMMAND_TRIGGER_TEXTS", "patrol-now,巡视一下"))
    )
    ssh_options = tuple(shlex.split(os.getenv("PATROL_SSH_OPTIONS", "-o BatchMode=yes -o ConnectTimeout=10")))
    log_path = Path(os.getenv("FEISHU_COMMAND_BRIDGE_LOG", str(Path(__file__).with_name("feishu_command_bridge.log"))))

    return BridgeConfig(
        host=os.getenv("FEISHU_COMMAND_BRIDGE_HOST", "0.0.0.0"),
        port=int(os.getenv("FEISHU_COMMAND_BRIDGE_PORT", "19100")),
        verification_token=os.getenv("FEISHU_COMMAND_VERIFICATION_TOKEN", "").strip(),
        target_chat_id=os.getenv("FEISHU_COMMAND_TARGET_CHAT_ID", "").strip(),
        bot_open_id=os.getenv("FEISHU_COMMAND_BOT_OPEN_ID", "").strip(),
        trigger_texts=trigger_texts,
        ssh_path=os.getenv("PATROL_SSH_PATH", "ssh").strip() or "ssh",
        ssh_user=os.getenv("PATROL_SSH_USER", "").strip(),
        ssh_host=os.getenv("PATROL_SSH_HOST", "").strip(),
        ssh_identity_file=os.getenv("PATROL_SSH_IDENTITY_FILE", "").strip(),
        ssh_options=ssh_options,
        remote_command=os.getenv("PATROL_REMOTE_COMMAND", "bash ~/.local/bin/openclaw-patrol-now").strip(),
        log_path=log_path,
        dedup_ttl_seconds=int(os.getenv("FEISHU_COMMAND_DEDUP_TTL_SECONDS", "600")),
    )


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def parse_text_content(content: str, mentions: list[dict[str, Any]]) -> str:
    parsed_content = content
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed_content = str(parsed.get("text", ""))
    except json.JSONDecodeError:
        pass

    normalized = parsed_content
    for mention in mentions:
        key = mention.get("key")
        if isinstance(key, str) and key:
            normalized = normalized.replace(key, " ")
    normalized = MENTION_NAME_RE.sub("", normalized.strip())
    return " ".join(normalized.split())


def parse_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    header = payload.get("header") or {}
    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}

    if not isinstance(message, dict):
        return None

    mentions = message.get("mentions") or []
    content = parse_text_content(str(message.get("content", "")), mentions if isinstance(mentions, list) else [])

    return {
        "event_type": header.get("event_type") or payload.get("type") or "",
        "event_id": header.get("event_id") or payload.get("uuid") or "",
        "message_id": message.get("message_id") or "",
        "chat_id": message.get("chat_id") or "",
        "chat_type": message.get("chat_type") or "",
        "message_type": message.get("message_type") or "",
        "content_text": content,
        "mentions": mentions if isinstance(mentions, list) else [],
        "sender_open_id": sender_id.get("open_id") or "",
    }


def should_trigger_patrol(event: dict[str, Any], cfg: BridgeConfig) -> bool:
    if event.get("event_type") != "im.message.receive_v1":
        return False
    if event.get("message_type") != "text":
        return False
    if cfg.target_chat_id and event.get("chat_id") != cfg.target_chat_id:
        return False
    if cfg.bot_open_id:
        mentioned_ids = []
        for mention in event.get("mentions", []):
            mention_id = (mention.get("id") or {}).get("open_id")
            if mention_id:
                mentioned_ids.append(mention_id)
        if cfg.bot_open_id not in mentioned_ids:
            return False
    return event.get("content_text", "").strip() in cfg.trigger_texts


class EventDeduper:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._seen: dict[str, float] = {}

    def seen(self, key: str) -> bool:
        if not key:
            return False
        now = time.time()
        with self._lock:
            expired = [item for item, ts in self._seen.items() if now - ts > self.ttl_seconds]
            for item in expired:
                self._seen.pop(item, None)
            if key in self._seen:
                return True
            self._seen[key] = now
            return False


def build_ssh_command(cfg: BridgeConfig) -> list[str]:
    target = f"{cfg.ssh_user}@{cfg.ssh_host}" if cfg.ssh_user else cfg.ssh_host
    cmd = [cfg.ssh_path]
    if cfg.ssh_identity_file:
        cmd.extend(["-i", cfg.ssh_identity_file])
    cmd.extend(cfg.ssh_options)
    cmd.append(target)
    cmd.append(cfg.remote_command)
    return cmd


def launch_remote_patrol(cfg: BridgeConfig, event: dict[str, Any]) -> None:
    cmd = build_ssh_command(cfg)
    logging.info("triggering remote patrol: chat_id=%s sender=%s command=%s", event.get("chat_id"), event.get("sender_open_id"), cmd)

    def _run() -> None:
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
                check=False,
            )
        except Exception:
            logging.exception("remote patrol launch failed")
            return

        logging.info(
            "remote patrol exit=%s stdout=%s stderr=%s",
            completed.returncode,
            completed.stdout.strip(),
            completed.stderr.strip(),
        )

    threading.Thread(target=_run, daemon=True).start()


def make_handler(cfg: BridgeConfig, deduper: EventDeduper):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json({"status": "ok"})
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/", "/events", "/feishu/events"}:
                self.send_error(404)
                return

            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self.send_error(400, "invalid json")
                return

            token = str(payload.get("token") or (payload.get("header") or {}).get("token") or "")
            if cfg.verification_token and token and token != cfg.verification_token:
                logging.warning("verification token mismatch")
                self.send_error(403, "token mismatch")
                return

            challenge = payload.get("challenge")
            if isinstance(challenge, str) and challenge:
                self._json({"challenge": challenge})
                return

            event = parse_event(payload)
            if event is None:
                self._json({"code": 0})
                return

            dedup_key = event.get("event_id") or event.get("message_id") or ""
            if deduper.seen(dedup_key):
                logging.info("duplicate event ignored: %s", dedup_key)
                self._json({"code": 0})
                return

            logging.info(
                "received event: type=%s chat_id=%s sender=%s text=%s",
                event.get("event_type"),
                event.get("chat_id"),
                event.get("sender_open_id"),
                event.get("content_text"),
            )

            if should_trigger_patrol(event, cfg):
                launch_remote_patrol(cfg, event)

            self._json({"code": 0})

        def log_message(self, format: str, *args) -> None:
            return

        def _json(self, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


def main() -> None:
    cfg = load_config()
    configure_logging(cfg.log_path)
    logging.info("starting feishu command bridge: host=%s port=%s target_chat_id=%s", cfg.host, cfg.port, cfg.target_chat_id)
    logging.info("trigger texts: %s", sorted(cfg.trigger_texts))
    deduper = EventDeduper(cfg.dedup_ttl_seconds)
    server = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(cfg, deduper))
    server.serve_forever()


if __name__ == "__main__":
    main()
