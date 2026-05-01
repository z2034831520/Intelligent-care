from __future__ import annotations

from .config import load_bridge_config
from .models import PatrolRecord, PersonEvent, local_timestamp
from .patrol_engine import PatrolEngine
from .recording_config import load_recording_config


def run_manual_patrol() -> PatrolRecord:
    bridge_config = load_bridge_config()
    recording_config = load_recording_config()
    patrol_engine = PatrolEngine(bridge_config, recording_config)
    event = PersonEvent(
        event_type="manual_patrol",
        timestamp=local_timestamp(),
        camera_id=bridge_config.camera_id,
        confidence=0.0,
        bbox=[],
        source="openclaw_manual_patrol",
    )
    return patrol_engine.run_patrol(event, notify=False, always_generate_preview=True)
