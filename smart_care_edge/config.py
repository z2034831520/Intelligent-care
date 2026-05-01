from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class AppConfig:
    raw: Dict[str, Any]

    @property
    def dashboard_port(self) -> int:
        return int(self.raw.get("dashboard_port", 8080))

    @property
    def database_path(self) -> Path:
        return Path(self.raw.get("database_path", "runtime/smart_care.db"))

    @property
    def event_log_limit(self) -> int:
        return int(self.raw.get("event_log_limit", 100))

    @property
    def night_hours(self) -> tuple[int, int]:
        start, end = self.raw.get("night_hours", [22, 6])
        return int(start), int(end)

    @property
    def simulated(self) -> bool:
        return bool(self.raw.get("simulated", True))

    @property
    def thresholds(self) -> Dict[str, Any]:
        return dict(self.raw.get("thresholds", {}))

    @property
    def actions(self) -> Dict[str, Any]:
        return dict(self.raw.get("actions", {}))

    @property
    def remote_notifications_enabled(self) -> bool:
        return bool(self.raw.get("remote_notifications_enabled", False))


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as fh:
        return AppConfig(json.load(fh))
