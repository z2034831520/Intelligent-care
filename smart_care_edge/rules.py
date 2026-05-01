from __future__ import annotations

from datetime import datetime
from typing import List

from .config import AppConfig
from .models import DecisionEvent, SensorEvent, VisionEvent, utc_now


class RuleEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def decide(self, sensor_events: List[SensorEvent], vision_event: VisionEvent | None) -> DecisionEvent:
        sensor_payload = [event.to_dict() for event in sensor_events]
        vision_payload = [vision_event.to_dict()] if vision_event else []

        if any(event.type == "fall_button" and bool(event.value) for event in sensor_events):
            return DecisionEvent(
                level="alarm",
                reason="manual_fall_alarm",
                action_list=self.config.actions.get("alarm", []),
                timestamp=utc_now(),
                sensor_events=sensor_payload,
                vision_events=vision_payload,
            )

        if any(event.type == "smoke" and float(event.value) >= self.config.thresholds.get("smoke_alarm_confidence", 0.7) for event in sensor_events):
            return DecisionEvent(
                level="alarm",
                reason="smoke_detected",
                action_list=self.config.actions.get("alarm", []),
                timestamp=utc_now(),
                sensor_events=sensor_payload,
                vision_events=vision_payload,
            )

        if any(event.type == "door" and event.value == "open" for event in sensor_events) and self._is_night():
            return DecisionEvent(
                level="warning",
                reason="night_door_open",
                action_list=self.config.actions.get("warning", []),
                timestamp=utc_now(),
                sensor_events=sensor_payload,
                vision_events=vision_payload,
            )

        has_presence = any(event.type in {"pir", "presence_mmwave"} and bool(event.value) for event in sensor_events)
        has_person = bool(vision_event and any(obj.label == "person" and obj.score >= 0.7 for obj in vision_event.objects))

        if has_presence and has_person:
            return DecisionEvent(
                level="alarm" if self._is_night() else "warning",
                reason="presence_confirmed_by_vision",
                action_list=self.config.actions.get("alarm" if self._is_night() else "warning", []),
                timestamp=utc_now(),
                sensor_events=sensor_payload,
                vision_events=vision_payload,
            )

        if has_presence or has_person:
            return DecisionEvent(
                level="attention",
                reason="single_channel_presence",
                action_list=["status_page", "local_log"],
                timestamp=utc_now(),
                sensor_events=sensor_payload,
                vision_events=vision_payload,
            )

        return DecisionEvent(
            level="normal",
            reason="no_anomaly",
            action_list=["local_log"],
            timestamp=utc_now(),
            sensor_events=sensor_payload,
            vision_events=vision_payload,
        )

    def _is_night(self) -> bool:
        start, end = self.config.night_hours
        hour = datetime.now().hour
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end
