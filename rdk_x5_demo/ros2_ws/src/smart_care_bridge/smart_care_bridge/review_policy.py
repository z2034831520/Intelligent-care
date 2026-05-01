from __future__ import annotations

from typing import Any, Dict

from .models import VlmReviewResult


ALLOWED_RISK_LEVELS = {"normal", "warning", "alarm"}
NORMAL_ACTIVITY_LABELS = {
    "normal_walking",
    "normal_standing",
    "normal_cleaning",
    "normal_sitting",
}
DANGER_KEYWORDS = {
    "fall",
    "fell",
    "fallen",
    "injury",
    "unsafe",
    "collapsed",
    "lying on the floor",
    "跌倒",
    "受伤",
    "危险",
    "倒地",
}
LOW_POSTURE_WARNING_KEYWORDS = {
    "on the floor",
    "sitting on the floor",
    "kneeling",
    "kneeling on the floor",
    "low-to-floor",
    "low posture",
    "curled near the ground",
    "near the ground",
    "floor-level",
    "floor level",
    "leaning against furniture",
    "ground-level",
    "ground level",
    "跪",
    "地上",
    "地面",
    "坐在地上",
    "跪在地上",
}


def normalize_risk_level(value: str) -> str:
    value = (value or "").strip().lower()
    if value in ALLOWED_RISK_LEVELS:
        return value
    if value == "uncertain":
        return "warning"
    return "warning"


def postprocess_risk_level(activity_label: str, risk_level: str, description: str) -> str:
    label = (activity_label or "").strip().lower()
    desc = (description or "").strip().lower()
    normalized = normalize_risk_level(risk_level)

    if any(keyword in desc for keyword in DANGER_KEYWORDS):
        return normalized if normalized == "alarm" else "warning"

    # A floor-level posture is too risky to accept as ordinary sitting.
    if label == "normal_sitting" and any(keyword in desc for keyword in LOW_POSTURE_WARNING_KEYWORDS):
        return "warning"

    if label in NORMAL_ACTIVITY_LABELS:
        return "normal"

    return normalized


def review_result_from_payload(payload: Dict[str, Any]) -> VlmReviewResult:
    activity_label = str(payload.get("activity_label", "uncertain") or "uncertain")
    description = str(payload.get("description", "VLM returned no description.") or "VLM returned no description.")
    risk_level = postprocess_risk_level(
        activity_label,
        str(payload.get("risk_level", "warning")),
        description,
    )
    return VlmReviewResult(
        activity_label=activity_label,
        risk_level=risk_level,
        description=description,
        confidence=float(payload.get("confidence", 0.0) or 0.0),
        status=str(payload.get("status", "ok") or "ok"),
    )


def failed_review_result(reason: str) -> VlmReviewResult:
    return VlmReviewResult(
        activity_label="uncertain",
        risk_level="warning",
        description=f"VLM review failed: {reason}",
        confidence=0.0,
        status="failed",
    )


def should_notify(review: VlmReviewResult) -> bool:
    return review.risk_level in {"warning", "alarm"}
