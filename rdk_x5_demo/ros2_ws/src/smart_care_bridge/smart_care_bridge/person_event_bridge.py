from __future__ import annotations

import time
from threading import Thread
from typing import Dict, List

from .bridge_core import PersonEventBridgeCore
from .config import load_bridge_config
from .detection_parsing import extract_detection_candidates, resolve_perception_targets_type
from .evidence_client import EvidenceClient
from .feishu_notifier import FeishuNotifier
from .jsonl_logger import JsonlEventLogger
from .models import DetectionCandidate, PersonEvent, VlmReviewResult
from .recording_config import load_recording_config
from .review_policy import failed_review_result, should_notify
from .vlm_review_client import VlmReviewClient


def build_log_entry(event: PersonEvent, evidence: Dict[str, object], review: VlmReviewResult, feishu_result: dict) -> dict:
    return {
        "timestamp": event.timestamp,
        "event_type": event.event_type,
        "camera_id": event.camera_id,
        "confidence": event.confidence,
        "bbox": event.bbox,
        "source": event.source,
        "image_path": evidence.get("image_path", ""),
        "image_status": evidence.get("image_status", ""),
        "video_path": evidence.get("video_path", ""),
        "video_status": evidence.get("video_status", ""),
        "video_error": evidence.get("video_error", ""),
        "gif_path": evidence.get("gif_path", ""),
        "frame_paths": evidence.get("frame_paths", []),
        "frame_status": evidence.get("frame_status", ""),
        "activity_label": review.activity_label,
        "risk_level": review.risk_level,
        "vlm_confidence": review.confidence,
        "vlm_description": review.description,
        "vlm_status": review.status,
        "feishu_status": feishu_result.get("status", "unknown"),
        "feishu_detail": feishu_result.get("detail", ""),
        "feishu_image_status": feishu_result.get("image_status", "unknown"),
        "feishu_image_detail": feishu_result.get("image_detail", ""),
        "video_delivery_status": feishu_result.get("video_status", "unknown"),
        "video_public_url": feishu_result.get("video_url", ""),
        "gif_delivery_status": feishu_result.get("gif_status", "unknown"),
        "gif_public_url": feishu_result.get("gif_url", ""),
    }
def main() -> None:  # pragma: no cover
    import rclpy
    from rclpy.node import Node

    config = load_bridge_config()
    recording_config = load_recording_config()
    perception_targets_type = resolve_perception_targets_type()

    class PersonEventBridgeNode(Node):
        def __init__(self) -> None:
            super().__init__("person_event_bridge")
            self.notifier = FeishuNotifier(
                config.feishu_webhook_url,
                config.device_name,
                config.evidence_public_base_url,
                {
                    "images": recording_config.evidence_image_dir,
                    "videos": recording_config.evidence_video_dir,
                    "gifs": recording_config.evidence_gif_dir,
                    "frames": recording_config.evidence_frame_dir,
                },
                app_id=config.feishu_app_id,
                app_secret=config.feishu_app_secret,
                chat_id=config.feishu_chat_id,
            )
            self.evidence_client = EvidenceClient(recording_config.recorder_port)
            self.vlm_client = VlmReviewClient(
                config.vlm_server_url,
                config.vlm_timeout_seconds,
                config.vlm_retry_count,
            )
            self.logger = JsonlEventLogger(config.event_log_path)
            self.core = PersonEventBridgeCore(
                camera_id=config.camera_id,
                source=config.person_topic,
                threshold=config.person_score_threshold,
                confirm_frames=config.person_confirm_frames,
                cooldown_seconds=config.alert_cooldown_seconds,
                person_labels=config.person_labels,
            )
            self._subscription = self.create_subscription(
                perception_targets_type,
                config.person_topic,
                self._on_message,
                10,
            )
            self.get_logger().info(f"listening on {config.person_topic}")

        def _on_message(self, message: object) -> None:
            candidates = extract_detection_candidates(message)
            decision = self.core.process(candidates, time.monotonic())
            if not decision.triggered or decision.event is None:
                return

            Thread(target=self._handle_event, args=(decision.event,), daemon=True).start()

        def _handle_event(self, event: PersonEvent) -> None:
            try:
                evidence = self.evidence_client.export_event(event.timestamp)
            except Exception as exc:
                evidence = {
                    "image_status": "failed",
                    "video_status": "failed",
                    "image_path": "",
                    "video_path": "",
                    "gif_path": "",
                    "frame_paths": [],
                    "frame_status": "failed",
                    "video_error": str(exc),
                }

            review = self._review_with_vlm(event, evidence)
            feishu_result = {
                "status": "skipped",
                "detail": "risk level normal",
                "image_status": "skipped",
                "image_detail": "risk level normal",
                "video_status": "skipped",
                "video_url": "",
                "gif_status": "skipped",
                "gif_url": "",
            }
            if should_notify(review):
                feishu_result = self.notifier.send(event, evidence, review)

            log_entry = build_log_entry(event, evidence, review, feishu_result)
            self.logger.write(log_entry)
            self.get_logger().info(
                f"alert status={feishu_result.get('status')} risk={review.risk_level} activity={review.activity_label} confidence={event.confidence:.2f} bbox={event.bbox}"
            )

        def _review_with_vlm(self, event: PersonEvent, evidence: Dict[str, object]) -> VlmReviewResult:
            try:
                return self.vlm_client.review_event(event, evidence)
            except Exception as exc:
                return failed_review_result(str(exc))

    rclpy.init()
    node = PersonEventBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
