from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SensorEvent:
    type: str
    value: Any
    timestamp: str
    confidence: float = 1.0
    source: str = "sensor"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VisionObject:
    label: str
    score: float
    bbox: List[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VisionEvent:
    source: str
    timestamp: str
    objects: List[VisionObject]
    frame_ref: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["objects"] = [obj.to_dict() for obj in self.objects]
        return data


@dataclass
class DecisionEvent:
    level: str
    reason: str
    action_list: List[str]
    timestamp: str
    sensor_events: List[Dict[str, Any]] = field(default_factory=list)
    vision_events: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionEvent:
    action: str
    status: str
    timestamp: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemState:
    level: str = "normal"
    updated_at: str = field(default_factory=utc_now)
    last_reason: str = "startup"
    last_snapshot_ref: Optional[str] = None
    latest_sensor_events: List[Dict[str, Any]] = field(default_factory=list)
    latest_vision_events: List[Dict[str, Any]] = field(default_factory=list)
    latest_actions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
