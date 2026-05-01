from __future__ import annotations

import time
from datetime import datetime

from .config import load_bridge_config
from .daily_report import build_daily_report, load_patrol_records
from .feishu_notifier import FeishuNotifier
from .jsonl_logger import JsonlEventLogger
from .models import PersonEvent, local_timestamp
from .patrol_engine import PatrolEngine
from .recording_config import load_recording_config


def _today_string() -> str:
    return datetime.now().date().isoformat()


def _time_matches(now: datetime, report_time: str) -> bool:
    return now.strftime("%H:%M") == report_time


def main() -> None:  # pragma: no cover
    bridge_config = load_bridge_config()
    recording_config = load_recording_config()
    patrol_engine = PatrolEngine(bridge_config, recording_config)
    report_logger = JsonlEventLogger(bridge_config.daily_report_log_path)
    notifier = FeishuNotifier(bridge_config.feishu_webhook_url, bridge_config.device_name)
    last_report_date = ""

    while True:
        event = PersonEvent(
            event_type="person_detected",
            timestamp=local_timestamp(),
            camera_id=bridge_config.camera_id,
            confidence=0.0,
            bbox=[0, 0, 0, 0],
            source="periodic_patrol",
        )
        patrol_engine.run_patrol(event)

        now = datetime.now()
        if _time_matches(now, bridge_config.patrol_report_time) and last_report_date != now.date().isoformat():
            records = load_patrol_records(bridge_config.patrol_log_path, _today_string())
            report = build_daily_report(records, _today_string())
            report_logger.write(report.to_dict())
            notifier.send_daily_report(report)
            last_report_date = now.date().isoformat()

        time.sleep(bridge_config.patrol_interval_seconds)
