from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List


def local_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class DetectionCandidate:
    label: str
    score: float
    bbox: List[int]


@dataclass
class PersonEvent:
    event_type: str
    timestamp: str
    camera_id: str
    confidence: float
    bbox: List[int]
    source: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class VlmReviewResult:
    activity_label: str
    risk_level: str
    description: str
    confidence: float
    status: str = "ok"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class PatrolRecord:
    patrol_time: str
    camera_id: str
    detection_status: str
    target_detected: bool
    detection_confidence: float
    image_path: str
    video_path: str
    gif_path: str
    frame_paths: List[str]
    activity_label: str
    risk_level: str
    vlm_description: str
    vlm_status: str
    notify_status: str
    notify_detail: str
    feishu_image_status: str
    feishu_image_detail: str
    video_delivery_status: str
    video_public_url: str
    gif_delivery_status: str
    gif_public_url: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class DailyReport:
    date: str
    patrol_count: int
    empty_count: int
    target_count: int
    normal_count: int
    warning_count: int
    alarm_count: int
    summary: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
