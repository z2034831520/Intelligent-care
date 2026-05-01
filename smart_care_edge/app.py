from __future__ import annotations

import argparse
import time
from typing import List

from .actions import ActionExecutor
from .config import AppConfig, load_config
from .dashboard import DashboardServer
from .models import SensorEvent, VisionEvent
from .rules import RuleEngine
from .runtime import RuntimeState
from .sensors import SimulatedSensorAdapter
from .storage import EventStore
from .vision import CameraSnapshotProvider, SimulatedVisionDetector


class SmartCareApp:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.runtime_state = RuntimeState(event_log_limit=config.event_log_limit)
        self.store = EventStore(config.database_path)
        self.sensors = SimulatedSensorAdapter()
        self.camera = CameraSnapshotProvider()
        self.vision = SimulatedVisionDetector()
        self.rules = RuleEngine(config)
        self.actions = ActionExecutor(config, self.runtime_state, self.store)
        self.dashboard = DashboardServer(config.dashboard_port, self.runtime_state)

    def run(self) -> None:
        self.dashboard.start()
        try:
            for _ in range(6):
                sensor_events = list(self.sensors.poll())
                vision_event = self._maybe_inspect(sensor_events)
                self._record_sensor_events(sensor_events)
                if vision_event:
                    self.runtime_state.remember_vision(vision_event)
                    self.store.insert_event("vision", vision_event.timestamp, vision_event.to_dict())
                decision = self.rules.decide(sensor_events, vision_event)
                self.runtime_state.remember_decision(decision)
                self.store.insert_event("decision", decision.timestamp, decision.to_dict(), decision.level)
                self.actions.execute(decision)
                time.sleep(1)
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.dashboard.stop()

    def _record_sensor_events(self, sensor_events: List[SensorEvent]) -> None:
        for event in sensor_events:
            self.runtime_state.remember_sensor(event)
            self.store.insert_event("sensor", event.timestamp, event.to_dict())

    def _maybe_inspect(self, sensor_events: List[SensorEvent]) -> VisionEvent | None:
        should_inspect = any(event.type in {"door", "pir", "presence_mmwave"} for event in sensor_events)
        if not should_inspect:
            return None
        frame_ref = self.camera.capture()
        vision_event = self.vision.inspect(frame_ref)
        self.runtime_state.system.last_snapshot_ref = frame_ref
        return vision_event


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the smart care edge demo app")
    parser.add_argument("--config", default="config/default_config.json", help="Path to JSON config")
    args = parser.parse_args()

    config = load_config(args.config)
    SmartCareApp(config).run()


if __name__ == "__main__":
    main()
