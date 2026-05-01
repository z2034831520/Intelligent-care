from __future__ import annotations

from typing import List

from .config import AppConfig
from .models import ActionEvent, DecisionEvent, utc_now
from .runtime import RuntimeState
from .storage import EventStore


class ActionExecutor:
    def __init__(self, config: AppConfig, runtime_state: RuntimeState, store: EventStore) -> None:
        self.config = config
        self.runtime_state = runtime_state
        self.store = store

    def execute(self, decision: DecisionEvent) -> List[ActionEvent]:
        events: List[ActionEvent] = []
        for action in decision.action_list:
            detail = self._detail_for(action, decision)
            status = "sent"
            if action == "remote_notify" and not self.config.remote_notifications_enabled:
                status = "skipped"
                detail = "remote notification disabled; kept local-only for offline reliability"
            action_event = ActionEvent(action=action, status=status, timestamp=utc_now(), detail=detail)
            self.runtime_state.remember_action(action_event)
            self.store.insert_event("action", action_event.timestamp, action_event.to_dict(), decision.level)
            events.append(action_event)
        return events

    def _detail_for(self, action: str, decision: DecisionEvent) -> str:
        mapping = {
            "buzzer": f"activate buzzer for {decision.reason}",
            "light": f"turn on light for {decision.reason}",
            "snapshot": "capture and archive evidence frame",
            "local_log": "persist local decision trace",
            "status_page": "update local dashboard state",
            "remote_notify": "send notification to remote assistant channel",
        }
        return mapping.get(action, f"perform {action}")
