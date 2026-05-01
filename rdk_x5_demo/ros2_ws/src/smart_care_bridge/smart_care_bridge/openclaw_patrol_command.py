from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from .config import load_bridge_config
from .feishu_notifier import FeishuNotifier
from .recording_config import load_recording_config

SUPPORTED_COMMANDS = {"巡视一下", "patrol-now"}
ACK_TEXT = "已开始巡视，请稍候"
BUSY_TEXT = "当前已有巡视任务在执行，请稍后再试"

MENTION_TAG_RE = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE | re.DOTALL)
PLAIN_MENTION_RE = re.compile(r"^@openclaw\b", re.IGNORECASE)


def normalize_command_text(text: str) -> str:
    normalized = MENTION_TAG_RE.sub(" ", text or "")
    normalized = PLAIN_MENTION_RE.sub("", normalized.strip())
    return " ".join(normalized.split())


def default_lock_path() -> Path:
    bridge_config = load_bridge_config()
    return bridge_config.patrol_log_path.parent / "manual_patrol.lock"


def read_lock_pid(lock_path: Path) -> int | None:
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None

    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def is_process_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def write_lock_pid(lock_path: Path, pid: int) -> None:
    lock_path.write_text(str(pid), encoding="utf-8")


def acquire_lock(lock_path: Path, pid: int | None = None) -> bool:
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(pid if pid is not None else os.getpid()))
    return True


def release_lock(lock_path: Path) -> None:
    lock_path.unlink(missing_ok=True)


def ensure_fresh_lock(lock_path: Path) -> bool:
    if acquire_lock(lock_path):
        return True

    if is_process_running(read_lock_pid(lock_path)):
        return False

    release_lock(lock_path)
    return acquire_lock(lock_path)


def _build_notifier() -> FeishuNotifier:
    bridge_config = load_bridge_config()
    recording_config = load_recording_config()
    return FeishuNotifier(
        bridge_config.feishu_webhook_url,
        bridge_config.device_name,
        bridge_config.evidence_public_base_url,
        {
            "images": recording_config.evidence_image_dir,
            "videos": recording_config.evidence_video_dir,
            "gifs": recording_config.evidence_gif_dir,
            "frames": recording_config.evidence_frame_dir,
        },
        app_id=bridge_config.feishu_app_id,
        app_secret=bridge_config.feishu_app_secret,
        chat_id=bridge_config.feishu_chat_id,
    )


def default_worker_log_path() -> Path:
    bridge_config = load_bridge_config()
    return bridge_config.patrol_log_path.parent / "openclaw_patrol_worker.log"


def resolve_worker_command(lock_path: Path) -> list[str]:
    sibling_worker = Path(sys.argv[0]).resolve().with_name("openclaw_patrol_worker")
    if sibling_worker.is_file():
        return [str(sibling_worker), "--lock-path", str(lock_path)]

    worker_script = shutil.which("openclaw_patrol_worker")
    if worker_script:
        return [worker_script, "--lock-path", str(lock_path)]

    ros2_bin = shutil.which("ros2")
    if ros2_bin:
        return [ros2_bin, "run", "smart_care_bridge", "openclaw_patrol_worker", "--lock-path", str(lock_path)]

    return [sys.executable, "-m", "smart_care_bridge.openclaw_patrol_worker", "--lock-path", str(lock_path)]


def launch_worker(lock_path: Path) -> int:
    cmd = resolve_worker_command(lock_path)
    log_path = default_worker_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[launch] cmd={cmd} lock_path={lock_path} argv0={sys.argv[0]}\n")

    log_fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        process = subprocess.Popen(
            cmd,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        os.close(log_fd)

    time.sleep(0.2)
    returncode = process.poll()
    with log_path.open("a", encoding="utf-8") as handle:
        if returncode is None:
            handle.write(f"[launch-ok] pid={process.pid}\n")
        else:
            handle.write(f"[launch-exit] pid={process.pid} returncode={returncode}\n")
    return process.pid


def handle_command(
    *,
    chat_id: str,
    text: str,
    notifier: FeishuNotifier,
    configured_chat_id: str,
    lock_path: Path,
    launcher: Callable[[Path], int] = launch_worker,
) -> dict[str, str]:
    if chat_id != configured_chat_id:
        return {"status": "ignored", "detail": "chat id not allowed"}

    if normalize_command_text(text) not in SUPPORTED_COMMANDS:
        return {"status": "ignored", "detail": "unsupported command"}

    if not ensure_fresh_lock(lock_path):
        busy_result = notifier.send_openclaw_text(BUSY_TEXT)
        return {"status": "busy", "detail": busy_result["detail"]}

    ack_result = notifier.send_openclaw_text(ACK_TEXT)
    if ack_result["status"] != "sent":
        release_lock(lock_path)
        return {"status": "failed", "detail": ack_result["detail"]}

    try:
        worker_pid = launcher(lock_path)
        write_lock_pid(lock_path, worker_pid)
    except Exception as exc:
        release_lock(lock_path)
        notifier.send_openclaw_text(f"主动巡视启动失败: {exc}")
        return {"status": "failed", "detail": str(exc)}

    return {"status": "started", "detail": ack_result["detail"]}


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Handle OpenClaw manual patrol command.")
    parser.add_argument("--chat-id", required=True, help="Source Feishu chat_id.")
    parser.add_argument("--text", required=True, help="Plain-text command body after mention stripping or raw text.")
    parser.add_argument("--lock-path", default="", help="Override lock file path.")
    args = parser.parse_args()

    bridge_config = load_bridge_config()
    notifier = _build_notifier()
    lock_path = Path(args.lock_path) if args.lock_path else default_lock_path()
    result = handle_command(
        chat_id=args.chat_id,
        text=args.text,
        notifier=notifier,
        configured_chat_id=bridge_config.feishu_chat_id,
        lock_path=lock_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
