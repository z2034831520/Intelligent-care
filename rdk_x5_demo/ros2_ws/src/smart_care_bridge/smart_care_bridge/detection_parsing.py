from __future__ import annotations

from importlib import import_module
from typing import List

from .models import DetectionCandidate


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _extract_bbox(rect: object) -> List[int]:
    if rect is None:
        return [0, 0, 0, 0]
    x = int(getattr(rect, "x_offset", 0))
    y = int(getattr(rect, "y_offset", 0))
    w = int(getattr(rect, "width", 0))
    h = int(getattr(rect, "height", 0))
    return [x, y, x + w, y + h]


def extract_detection_candidates(message: object) -> List[DetectionCandidate]:
    candidates: List[DetectionCandidate] = []
    for target in getattr(message, "targets", []) or []:
        candidates.extend(_extract_from_target(target))
    return candidates


def _extract_from_target(target: object) -> List[DetectionCandidate]:
    candidates: List[DetectionCandidate] = []
    rois = getattr(target, "rois", None) or []
    if rois:
        for roi in rois:
            label = str(getattr(roi, "type", "") or getattr(target, "type", "") or "")
            score = _extract_score(roi, target)
            bbox = _extract_bbox(getattr(roi, "rect", None))
            candidates.append(DetectionCandidate(label=label, score=score, bbox=bbox))
        return candidates

    label = str(getattr(target, "type", "") or "")
    score = _extract_score(target, None)
    bbox = _extract_bbox(getattr(target, "rect", None))
    if label:
        candidates.append(DetectionCandidate(label=label, score=score, bbox=bbox))
    return candidates


def _extract_score(primary: object, fallback: object | None) -> float:
    for holder in (primary, fallback):
        if holder is None:
            continue
        for attr in ("score", "confidence", "probability", "value"):
            if hasattr(holder, attr):
                return _safe_float(getattr(holder, attr))

        attributes = getattr(holder, "attributes", None) or []
        for item in attributes:
            key = str(getattr(item, "type", "")).lower()
            if key in {"score", "confidence", "probability"}:
                return _safe_float(getattr(item, "value", 0.0))
    return 0.0


def resolve_perception_targets_type():
    candidates = [
        ("ai_msgs.msg", "PerceptionTargets"),
        ("hobot_msgs.msg", "PerceptionTargets"),
    ]
    for module_name, class_name in candidates:
        try:
            module = import_module(module_name)
            return getattr(module, class_name)
        except Exception:
            continue
    raise RuntimeError(
        "Unable to import PerceptionTargets. Install the official RDK message packages and source /opt/tros/humble/setup.bash first."
    )
