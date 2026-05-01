from __future__ import annotations

import json

from .config import load_bridge_config
from .models import PersonEvent, local_timestamp
from .patrol_engine import PatrolEngine
from .recording_config import load_recording_config


def main() -> None:  # pragma: no cover
    bridge_config = load_bridge_config()
    recording_config = load_recording_config()
    patrol_engine = PatrolEngine(bridge_config, recording_config)

    event = PersonEvent(
        event_type="person_detected",
        timestamp=local_timestamp(),
        camera_id=bridge_config.camera_id,
        confidence=0.0,
        bbox=[0, 0, 0, 0],
        source="manual_patrol",
    )
    record = patrol_engine.run_patrol(event)
    print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
