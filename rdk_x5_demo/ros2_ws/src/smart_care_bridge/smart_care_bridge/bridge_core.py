from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .models import DetectionCandidate, PersonEvent, local_timestamp


@dataclass
class BridgeDecision:
    triggered: bool
    event: Optional[PersonEvent]
    consecutive_frames: int


class PersonEventBridgeCore:
    def __init__(
        self,
        camera_id: str,
        source: str,
        threshold: float,
        confirm_frames: int,
        cooldown_seconds: int,
        person_labels: Iterable[str],
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.threshold = threshold
        self.confirm_frames = confirm_frames
        self.cooldown_seconds = cooldown_seconds
        self.person_labels = {label.lower() for label in person_labels}
        self.consecutive_person_frames = 0
        self.last_alert_monotonic = -10**9
        self.latest_person_confidence = 0.0
        self.latest_bbox = [0, 0, 0, 0]

    def process(self, candidates: Iterable[DetectionCandidate], now_monotonic: float) -> BridgeDecision:
        best = self._best_person(candidates)
        if best is None:
            self.consecutive_person_frames = 0
            return BridgeDecision(triggered=False, event=None, consecutive_frames=0)

        self.latest_person_confidence = best.score
        self.latest_bbox = best.bbox
        self.consecutive_person_frames += 1

        if self.consecutive_person_frames < self.confirm_frames:
            return BridgeDecision(triggered=False, event=None, consecutive_frames=self.consecutive_person_frames)

        if now_monotonic - self.last_alert_monotonic < self.cooldown_seconds:
            return BridgeDecision(triggered=False, event=None, consecutive_frames=self.consecutive_person_frames)

        event = PersonEvent(
            event_type="person_detected",
            timestamp=local_timestamp(),
            camera_id=self.camera_id,
            confidence=best.score,
            bbox=best.bbox,
            source=self.source,
        )
        self.last_alert_monotonic = now_monotonic
        self.consecutive_person_frames = 0
        return BridgeDecision(triggered=True, event=event, consecutive_frames=0)

    def _best_person(self, candidates: Iterable[DetectionCandidate]) -> Optional[DetectionCandidate]:
        person_candidates = [
            candidate
            for candidate in candidates
            if candidate.label.lower() in self.person_labels and candidate.score >= self.threshold
        ]
        if not person_candidates:
            return None
        return max(person_candidates, key=lambda item: item.score)
