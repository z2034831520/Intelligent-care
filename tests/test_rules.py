import unittest

from smart_care_edge.config import AppConfig
from smart_care_edge.models import SensorEvent, VisionEvent, VisionObject
from smart_care_edge.rules import RuleEngine


def make_config() -> AppConfig:
    return AppConfig(
        {
            "night_hours": [0, 23],
            "actions": {
                "warning": ["status_page", "local_log"],
                "alarm": ["buzzer", "snapshot", "local_log"],
            },
            "thresholds": {"smoke_alarm_confidence": 0.7},
        }
    )


class RuleEngineTests(unittest.TestCase):
    def test_smoke_triggers_alarm(self) -> None:
        engine = RuleEngine(make_config())
        decision = engine.decide(
            [SensorEvent(type="smoke", value=0.9, timestamp="t1", confidence=0.9)],
            None,
        )
        self.assertEqual(decision.level, "alarm")
        self.assertEqual(decision.reason, "smoke_detected")

    def test_presence_and_person_confirm_alarm(self) -> None:
        engine = RuleEngine(make_config())
        vision = VisionEvent(
            source="sim",
            timestamp="t2",
            frame_ref="frame://1",
            objects=[VisionObject(label="person", score=0.92, bbox=[0, 0, 10, 10])],
        )
        decision = engine.decide(
            [SensorEvent(type="pir", value=True, timestamp="t1", confidence=1.0)],
            vision,
        )
        self.assertEqual(decision.reason, "presence_confirmed_by_vision")
        self.assertEqual(decision.level, "alarm")

    def test_single_channel_presence_is_attention(self) -> None:
        engine = RuleEngine(make_config())
        decision = engine.decide(
            [SensorEvent(type="pir", value=True, timestamp="t1", confidence=1.0)],
            None,
        )
        self.assertEqual(decision.level, "attention")


if __name__ == "__main__":
    unittest.main()
