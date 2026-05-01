from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass
class BridgeConfig:
    feishu_webhook_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_chat_id: str
    device_name: str
    camera_id: str
    evidence_public_base_url: str
    evidence_server_host: str
    evidence_server_port: int
    person_score_threshold: float
    person_confirm_frames: int
    alert_cooldown_seconds: int
    person_topic: str
    event_log_path: Path
    person_labels: List[str]
    vlm_server_url: str
    vlm_timeout_seconds: int
    vlm_retry_count: int
    patrol_interval_seconds: int
    patrol_report_time: str
    patrol_log_path: Path
    daily_report_log_path: Path
    detector_mode: str
    detector_command: str
    detector_timeout_seconds: int
    detector_setup_script: str


def load_bridge_config() -> BridgeConfig:
    labels_raw = os.getenv("PERSON_LABELS", "person,body,human_body,person_body")
    return BridgeConfig(
        feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL", ""),
        feishu_app_id=os.getenv("FEISHU_APP_ID", "").strip(),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
        feishu_chat_id=os.getenv("FEISHU_CHAT_ID", "").strip(),
        device_name=os.getenv("DEVICE_NAME", "RDK X5"),
        camera_id=os.getenv("CAMERA_ID", "usb_cam_0"),
        evidence_public_base_url=os.getenv("EVIDENCE_PUBLIC_BASE_URL", "").rstrip("/"),
        evidence_server_host=os.getenv("EVIDENCE_SERVER_HOST", "0.0.0.0").strip(),
        evidence_server_port=_env_int("EVIDENCE_SERVER_PORT", 8080),
        person_score_threshold=_env_float("PERSON_SCORE_THRESHOLD", 0.7),
        person_confirm_frames=_env_int("PERSON_CONFIRM_FRAMES", 3),
        alert_cooldown_seconds=_env_int("ALERT_COOLDOWN_SECONDS", 30),
        person_topic=os.getenv("PERSON_TOPIC", "/hobot_mono2d_body_detection"),
        event_log_path=Path(os.getenv("EVENT_LOG_PATH", str(Path.home() / "smart-care-demo" / "logs" / "person_events.jsonl"))),
        person_labels=[item.strip().lower() for item in labels_raw.split(",") if item.strip()],
        vlm_server_url=os.getenv("VLM_SERVER_URL", ""),
        vlm_timeout_seconds=_env_int("VLM_TIMEOUT_SECONDS", 15),
        vlm_retry_count=_env_int("VLM_RETRY_COUNT", 1),
        patrol_interval_seconds=_env_int("PATROL_INTERVAL_SECONDS", 120),
        patrol_report_time=os.getenv("PATROL_REPORT_TIME", "18:00"),
        patrol_log_path=Path(os.getenv("PATROL_LOG_PATH", str(Path.home() / "smart-care-demo" / "logs" / "patrol_events.jsonl"))),
        daily_report_log_path=Path(os.getenv("DAILY_REPORT_LOG_PATH", str(Path.home() / "smart-care-demo" / "logs" / "daily_reports.jsonl"))),
        detector_mode=os.getenv("DETECTOR_MODE", "rdk_x5_ros2_image").strip().lower(),
        detector_command=os.getenv("DETECTOR_COMMAND", "").strip(),
        detector_timeout_seconds=_env_int("DETECTOR_TIMEOUT_SECONDS", 45),
        detector_setup_script=os.getenv("DETECTOR_SETUP_SCRIPT", "/opt/tros/humble/setup.bash").strip(),
    )
