from __future__ import annotations

from typing import Iterable, Iterator, List

from .models import SensorEvent, utc_now


class SensorAdapter:
    def poll(self) -> Iterable[SensorEvent]:
        raise NotImplementedError


class SimulatedSensorAdapter(SensorAdapter):
    def __init__(self) -> None:
        self._scenes: List[List[SensorEvent]] = [
            [],
            [SensorEvent(type="door", value="open", timestamp=utc_now(), source="reed-switch")],
            [SensorEvent(type="pir", value=True, timestamp=utc_now(), source="gpio-pir")],
            [SensorEvent(type="presence_mmwave", value=True, timestamp=utc_now(), source="uart-mmwave")],
            [SensorEvent(type="smoke", value=0.82, timestamp=utc_now(), confidence=0.92, source="adc-smoke")],
            [SensorEvent(type="fall_button", value=True, timestamp=utc_now(), source="gpio-button")],
        ]
        self._index = 0

    def poll(self) -> Iterator[SensorEvent]:
        if self._index >= len(self._scenes):
            return iter([])
        scene = self._scenes[self._index]
        self._index += 1
        return iter(scene)
