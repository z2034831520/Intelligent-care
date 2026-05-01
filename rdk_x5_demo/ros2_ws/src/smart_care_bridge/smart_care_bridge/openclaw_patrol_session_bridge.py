from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .config import load_bridge_config
from .openclaw_patrol_command import SUPPORTED_COMMANDS, normalize_command_text

USER_ROLE_VALUES = {"user", "human"}
ASSISTANT_ROLE_VALUES = {"assistant", "agent", "system", "tool"}
ROLE_KEYS = {"role", "speaker_role", "author_role"}
MENTION_HINTS = ("@openclaw", "<at")


def iter_dicts(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_dicts(item)


def iter_strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_strings(item)


def detect_event_role(node: Any) -> str | None:
    for payload in iter_dicts(node):
        for key, value in payload.items():
            if key.lower() in ROLE_KEYS and isinstance(value, str):
                lowered = value.lower()
                if lowered in USER_ROLE_VALUES | ASSISTANT_ROLE_VALUES:
                    return lowered
    return None


def is_patrol_trigger_event(event: Any, target_chat_id: str) -> bool:
    strings = list(iter_strings(event))
    normalized_strings = {normalize_command_text(text) for text in strings if text}
    has_command = any(text in SUPPORTED_COMMANDS for text in normalized_strings)
    if not has_command:
        return False

    role = detect_event_role(event)
    if role in ASSISTANT_ROLE_VALUES:
        return False

    has_chat_id = target_chat_id in strings
    has_any_chat_id = any(text.startswith("oc_") for text in strings if isinstance(text, str))
    has_mention = any(any(hint in text for hint in MENTION_HINTS) for text in strings)
    if role in USER_ROLE_VALUES:
        if has_any_chat_id:
            return has_chat_id
        return has_mention

    if has_any_chat_id and not has_chat_id:
        return False
    return has_mention


def default_sessions_dir() -> Path:
    return Path.home() / ".openclaw" / "agents"


def default_log_path() -> Path:
    bridge_config = load_bridge_config()
    return bridge_config.patrol_log_path.parent / "openclaw_patrol_session_bridge.log"


def default_state_path() -> Path:
    bridge_config = load_bridge_config()
    return bridge_config.patrol_log_path.parent / "openclaw_patrol_session_bridge_state.json"


class SessionBridge:
    def __init__(
        self,
        *,
        sessions_dir: Path,
        state_path: Path,
        log_path: Path,
        target_chat_id: str,
        command_script: Path,
        poll_interval: float = 1.0,
    ) -> None:
        self.sessions_dir = sessions_dir
        self.state_path = state_path
        self.log_path = log_path
        self.target_chat_id = target_chat_id
        self.command_script = command_script
        self.poll_interval = poll_interval
        self.offsets = self._load_state()
        self._setup_logger()

    def _setup_logger(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f"openclaw_patrol_session_bridge:{self.log_path}")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(handler)

    def _load_state(self) -> dict[str, int]:
        if not self.state_path.exists():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {str(key): int(value) for key, value in data.items()}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.offsets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _session_files(self) -> list[Path]:
        if not self.sessions_dir.exists():
            return []
        return sorted(
            path
            for path in self.sessions_dir.glob("**/sessions/*.jsonl")
            if path.name != "sessions.jsonl" and path.is_file()
        )

    def _bootstrap_offsets(self) -> None:
        changed = False
        tracked: list[str] = []
        for path in self._session_files():
            key = str(path)
            if key not in self.offsets:
                self.offsets[key] = path.stat().st_size
                changed = True
            tracked.append(key)
        if changed:
            self._save_state()
        self.logger.info("tracking %d session files", len(tracked))
        for item in tracked:
            self.logger.info("session file: %s", item)

    def run_forever(self) -> None:
        self.logger.info("bridge started: sessions_dir=%s", self.sessions_dir)
        self._bootstrap_offsets()
        while True:
            self.poll_once()
            time.sleep(self.poll_interval)

    def poll_once(self) -> None:
        changed = False
        for path in self._session_files():
            key = str(path)
            last_offset = self.offsets.get(key, 0)
            current_size = path.stat().st_size
            if last_offset > current_size:
                last_offset = 0
            if key not in self.offsets and current_size > 0:
                self.offsets[key] = current_size
                changed = True
                self.logger.info("new session file discovered: %s", path)
                continue
            if current_size == last_offset:
                continue

            self.logger.info("reading new session data: %s", path)
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(last_offset)
                for line in handle:
                    self._handle_line(line.rstrip("\n"))
                self.offsets[key] = handle.tell()
                changed = True
        if changed:
            self._save_state()

    def _handle_line(self, line: str) -> None:
        if not line.strip():
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return

        line_preview = line[:240]
        if any(token in line_preview for token in ("@openclaw", "patrol-now", "巡视一下")):
            self.logger.info("candidate line: %s", line_preview)

        if not is_patrol_trigger_event(payload, self.target_chat_id):
            return

        digest = hashlib.sha256(line.encode("utf-8")).hexdigest()[:12]
        self.logger.info("trigger matched hash=%s", digest)
        self._launch_patrol()

    def _launch_patrol(self) -> None:
        subprocess.Popen(
            ["bash", str(self.command_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.logger.info("launched patrol command: %s", self.command_script)


def main() -> None:  # pragma: no cover
    bridge_config = load_bridge_config()
    parser = argparse.ArgumentParser(description="Watch OpenClaw sessions and trigger patrol commands.")
    parser.add_argument("--sessions-dir", default=str(default_sessions_dir()))
    parser.add_argument("--state-path", default=str(default_state_path()))
    parser.add_argument("--log-path", default=str(default_log_path()))
    parser.add_argument("--chat-id", default=bridge_config.feishu_chat_id)
    parser.add_argument(
        "--command-script",
        default=str(Path.home() / "rdk_x5_demo" / "scripts" / "run_openclaw_group_patrol.sh"),
    )
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()

    bridge = SessionBridge(
        sessions_dir=Path(args.sessions_dir),
        state_path=Path(args.state_path),
        log_path=Path(args.log_path),
        target_chat_id=args.chat_id,
        command_script=Path(args.command_script),
        poll_interval=args.poll_interval,
    )
    bridge.run_forever()
