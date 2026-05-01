from __future__ import annotations

from typing import Iterable, List

from .models import VisionEvent, VisionObject, utc_now


class CameraSnapshotProvider:
    def capture(self) -> str:
        return f"snapshot://{utc_now()}"


class VisionDetector:
    def inspect(self, frame_ref: str) -> VisionEvent:
        raise NotImplementedError


class SimulatedVisionDetector(VisionDetector):
    def __init__(self) -> None:
        self._objects: List[List[VisionObject]] = [
            [],
            [VisionObject(label="person", score=0.91, bbox=[128, 64, 220, 360])],
            [VisionObject(label="person", score=0.88, bbox=[108, 54, 210, 352])],
            [],
            [],
        ]
        self._index = 0

    def inspect(self, frame_ref: str) -> VisionEvent:
        objects = self._objects[self._index] if self._index < len(self._objects) else []
        self._index += 1
        return VisionEvent(source="simulated-yolo", timestamp=utc_now(), objects=objects, frame_ref=frame_ref)
