from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_bridge_config
from .feishu_notifier import FeishuNotifier
from .manual_patrol import run_manual_patrol
from .models import PatrolRecord
from .recording_config import load_recording_config


def render_detection_target_text(record: PatrolRecord) -> str:
    if getattr(record, "detection_status", "") == "failed":
        return "未知"
    return "是" if record.target_detected else "否"


def build_manual_patrol_result_text(record: PatrolRecord, device_name: str) -> str:
    lines = [
        "[主动巡视结果]",
        f"时间: {record.patrol_time}",
        f"设备: {device_name}",
        f"摄像头: {record.camera_id}",
        f"检测状态: {getattr(record, 'detection_status', 'unknown')}",
        f"检测到目标: {render_detection_target_text(record)}",
        f"活动: {record.activity_label}",
        f"风险等级: {record.risk_level}",
        f"审查状态: {record.vlm_status}",
        f"描述: {record.vlm_description}",
        f"图片: {record.image_path}",
        f"视频: {record.video_path}",
    ]
    if record.gif_path:
        lines.append(f"GIF: {record.gif_path}")
    if record.video_public_url:
        lines.append(f"视频链接: {record.video_public_url}")
    if record.gif_public_url:
        lines.append(f"GIF 链接: {record.gif_public_url}")
    return "\n".join(lines)


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


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Run one OpenClaw-triggered manual patrol worker.")
    parser.add_argument("--lock-path", required=True, help="Lock file path for single-flight control.")
    args = parser.parse_args()

    lock_path = Path(args.lock_path)
    notifier = _build_notifier()
    bridge_config = load_bridge_config()
    payload: dict[str, object]

    try:
        record = run_manual_patrol()
        text_result = notifier.send_openclaw_text(build_manual_patrol_result_text(record, bridge_config.device_name))
        gif_result = notifier.send_openclaw_gif(record.gif_path) if record.gif_path else {"status": "skipped", "detail": "missing gif path"}
        if gif_result["status"] != "sent":
            fallback_lines = [f"GIF 发送失败: {gif_result['detail']}"]
            if record.gif_public_url:
                fallback_lines.append(f"GIF 链接: {record.gif_public_url}")
            notifier.send_openclaw_text("\n".join(fallback_lines))
        payload = {
            "status": "completed",
            "text_status": text_result["status"],
            "text_detail": text_result["detail"],
            "gif_status": gif_result["status"],
            "gif_detail": gif_result["detail"],
            "record": record.to_dict(),
        }
    except Exception as exc:
        error_text = f"主动巡视执行失败: {exc}"
        error_result = notifier.send_openclaw_text(error_text)
        payload = {
            "status": "failed",
            "detail": str(exc),
            "text_status": error_result["status"],
            "text_detail": error_result["detail"],
        }
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass

    print(json.dumps(payload, ensure_ascii=False, indent=2))
