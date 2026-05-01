from __future__ import annotations

import argparse
import json
from datetime import datetime

from .config import load_bridge_config
from .daily_report import build_daily_report, load_patrol_records
from .feishu_notifier import FeishuNotifier
from .jsonl_logger import JsonlEventLogger


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Generate one daily report from patrol logs.")
    parser.add_argument("--date", default=datetime.now().date().isoformat(), help="Target date in YYYY-MM-DD format.")
    parser.add_argument("--send", action="store_true", help="Send the generated report to Feishu.")
    args = parser.parse_args()

    bridge_config = load_bridge_config()
    records = load_patrol_records(bridge_config.patrol_log_path, args.date)
    report = build_daily_report(records, args.date)

    JsonlEventLogger(bridge_config.daily_report_log_path).write(report.to_dict())
    if args.send:
        FeishuNotifier(bridge_config.feishu_webhook_url, bridge_config.device_name).send_daily_report(report)

    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
