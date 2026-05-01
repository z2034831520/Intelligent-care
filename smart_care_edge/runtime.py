from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List

from .models import ActionEvent, DecisionEvent, SensorEvent, SystemState, VisionEvent


class RuntimeState:
    def __init__(self, event_log_limit: int) -> None:
        self.system = SystemState()
        self.sensor_events: Deque[Dict[str, Any]] = deque(maxlen=event_log_limit)
        self.vision_events: Deque[Dict[str, Any]] = deque(maxlen=event_log_limit)
        self.decision_events: Deque[Dict[str, Any]] = deque(maxlen=event_log_limit)
        self.action_events: Deque[Dict[str, Any]] = deque(maxlen=event_log_limit)

    def remember_sensor(self, event: SensorEvent) -> None:
        data = event.to_dict()
        self.sensor_events.appendleft(data)
        self.system.latest_sensor_events = list(self.sensor_events)[:10]

    def remember_vision(self, event: VisionEvent) -> None:
        data = event.to_dict()
        self.vision_events.appendleft(data)
        self.system.latest_vision_events = list(self.vision_events)[:10]

    def remember_decision(self, event: DecisionEvent) -> None:
        data = event.to_dict()
        self.decision_events.appendleft(data)
        self.system.level = event.level
        self.system.updated_at = event.timestamp
        self.system.last_reason = event.reason

    def remember_action(self, event: ActionEvent) -> None:
        data = event.to_dict()
        self.action_events.appendleft(data)
        self.system.latest_actions = list(self.action_events)[:10]

    def status_payload(self) -> Dict[str, Any]:
        return self.system.to_dict()

    def latest_payload(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "sensor_events": list(self.sensor_events),
            "vision_events": list(self.vision_events),
            "decision_events": list(self.decision_events),
            "action_events": list(self.action_events),
        }
