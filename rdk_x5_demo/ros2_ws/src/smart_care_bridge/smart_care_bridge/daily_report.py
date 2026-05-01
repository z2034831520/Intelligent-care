from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import List

from .jsonl_logger import JsonlEventLogger
from .models import DailyReport


def load_patrol_records(path: Path, target_date: str) -> List[dict]:
    if not path.exists():
        return []
    items: List[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            payload = json.loads(line)
            if str(payload.get("patrol_time", "")).startswith(target_date):
                items.append(payload)
    return items


def build_daily_report(records: List[dict], target_date: str) -> DailyReport:
    patrol_count = len(records)
    empty_count = sum(1 for item in records if not item.get("target_detected", False))
    target_count = patrol_count - empty_count
    normal_count = sum(1 for item in records if item.get("risk_level") == "normal" and item.get("target_detected", False))
    warning_count = sum(1 for item in records if item.get("risk_level") == "warning")
    alarm_count = sum(1 for item in records if item.get("risk_level") == "alarm")
    summary = (
        f"Today there were {patrol_count} patrols. "
        f"Targets appeared {target_count} times. "
        f"Warnings: {warning_count}, alarms: {alarm_count}."
    )
    return DailyReport(
        date=target_date,
        patrol_count=patrol_count,
        empty_count=empty_count,
        target_count=target_count,
        normal_count=normal_count,
        warning_count=warning_count,
        alarm_count=alarm_count,
        summary=summary,
    )
