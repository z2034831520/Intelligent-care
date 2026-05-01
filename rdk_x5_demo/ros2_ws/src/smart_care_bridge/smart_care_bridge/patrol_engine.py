from __future__ import annotations

from pathlib import Path

from .config import BridgeConfig
from .feishu_notifier import FeishuNotifier
from .jsonl_logger import JsonlEventLogger
from .models import DailyReport, PatrolRecord, PersonEvent
from .patrol_capture import PatrolCapture
from .patrol_detection import PatrolDetector
from .recording_config import RecordingConfig
from .review_policy import failed_review_result, should_notify
from .vlm_review_client import VlmReviewClient


def _safe_file_token(timestamp: str) -> str:
    return timestamp.replace(":", "-").replace("+", "_").replace("T", "_")


class PatrolEngine:
    def __init__(self, bridge_config: BridgeConfig, recording_config: RecordingConfig) -> None:
        self.bridge_config = bridge_config
        self.recording_config = recording_config
        self.capture = PatrolCapture(recording_config)
        self.detector = PatrolDetector(
            bridge_config.detector_mode,
            bridge_config.detector_command,
            bridge_config.person_labels,
            bridge_config.person_topic,
            bridge_config.detector_timeout_seconds,
            bridge_config.detector_setup_script,
        )
        self.vlm_client = VlmReviewClient(
            bridge_config.vlm_server_url,
            bridge_config.vlm_timeout_seconds,
            bridge_config.vlm_retry_count,
        )
        self.notifier = FeishuNotifier(
            bridge_config.feishu_webhook_url,
            bridge_config.device_name,
            bridge_config.evidence_public_base_url,
            {
                "images": recording_config.evidence_image_dir,
                "videos": recording_config.evidence_video_dir,
                "gifs": recording_config.evidence_gif_dir,
                "frames": recording_config.evidence_frame_dir,
            },
            app_id=bridge_config.feishu_app_id,
            app_secret=bridge_config.feishu_app_secret,
            chat_id=bridge_config.feishu_chat_id,
        )
        self.logger = JsonlEventLogger(bridge_config.patrol_log_path)

    def _build_public_delivery(self, video_path: Path, gif_path: Path | None) -> tuple[str, str, str, str]:
        video_public_url = self.notifier.build_public_evidence_url(str(video_path), "videos")
        gif_public_url = self.notifier.build_public_evidence_url(str(gif_path), "gifs") if gif_path else ""
        video_delivery_status = "linked" if video_public_url else "unavailable"
        if gif_path:
            gif_delivery_status = "linked" if gif_public_url else "unavailable"
        else:
            gif_delivery_status = "skipped"
        return video_delivery_status, video_public_url, gif_delivery_status, gif_public_url

    def run_patrol(
        self,
        event: PersonEvent,
        *,
        notify: bool = True,
        always_generate_preview: bool = False,
    ) -> PatrolRecord:
        token = _safe_file_token(event.timestamp)
        image_path, video_path = self.capture.capture_snapshot_and_video(token)
        try:
            detection = self.detector.detect(image_path)
        except Exception as exc:
            frame_paths = self.capture.extract_key_frames(video_path, token) if always_generate_preview else []
            gif_path = self.capture.create_preview_gif(video_path, token) if always_generate_preview else None
            if always_generate_preview:
                video_delivery_status, video_public_url, gif_delivery_status, gif_public_url = self._build_public_delivery(
                    video_path, gif_path
                )
            else:
                video_delivery_status = "skipped"
                video_public_url = ""
                gif_delivery_status = "skipped"
                gif_public_url = ""

            record = PatrolRecord(
                patrol_time=event.timestamp,
                camera_id=event.camera_id,
                detection_status="failed",
                target_detected=False,
                detection_confidence=0.0,
                image_path=str(image_path),
                video_path=str(video_path),
                gif_path=str(gif_path) if gif_path else "",
                frame_paths=[str(path) for path in frame_paths],
                activity_label="uncertain",
                risk_level="warning",
                vlm_description=f"Detector failed: {exc}",
                vlm_status="failed",
                notify_status="skipped",
                notify_detail="detector failed",
                feishu_image_status="skipped",
                feishu_image_detail="detector failed",
                video_delivery_status=video_delivery_status,
                video_public_url=video_public_url,
                gif_delivery_status=gif_delivery_status,
                gif_public_url=gif_public_url,
            )
            self.logger.write(record.to_dict())
            return record

        if not detection.target_detected:
            frame_paths = self.capture.extract_key_frames(video_path, token) if always_generate_preview else []
            gif_path = self.capture.create_preview_gif(video_path, token) if always_generate_preview else None
            if always_generate_preview:
                video_delivery_status, video_public_url, gif_delivery_status, gif_public_url = self._build_public_delivery(
                    video_path, gif_path
                )
            else:
                video_delivery_status = "skipped"
                video_public_url = ""
                gif_delivery_status = "skipped"
                gif_public_url = ""
            record = PatrolRecord(
                patrol_time=event.timestamp,
                camera_id=event.camera_id,
                detection_status="empty",
                target_detected=False,
                detection_confidence=0.0,
                image_path=str(image_path),
                video_path=str(video_path),
                gif_path=str(gif_path) if gif_path else "",
                frame_paths=[str(path) for path in frame_paths],
                activity_label="empty",
                risk_level="normal",
                vlm_description="No target detected during patrol.",
                vlm_status="skipped",
                notify_status="skipped",
                notify_detail="risk level normal",
                feishu_image_status="skipped",
                feishu_image_detail="risk level normal",
                video_delivery_status=video_delivery_status,
                video_public_url=video_public_url,
                gif_delivery_status=gif_delivery_status,
                gif_public_url=gif_public_url,
            )
            self.logger.write(record.to_dict())
            return record

        frame_paths = self.capture.extract_key_frames(video_path, token)
        review = self.vlm_client.review_event(
            event,
            {
                "image_path": str(image_path),
                "video_path": str(video_path),
                "frame_paths": [str(path) for path in frame_paths],
            },
        )

        if review.status != "ok":
            review = failed_review_result(review.description)

        notify_status = "skipped"
        notify_detail = "risk level normal"
        feishu_image_status = "skipped"
        feishu_image_detail = "risk level normal"
        video_delivery_status = "skipped"
        video_public_url = ""
        gif_delivery_status = "skipped"
        gif_public_url = ""
        gif_path = None
        notify_required = should_notify(review)
        if always_generate_preview or (notify and notify_required):
            gif_path = self.capture.create_preview_gif(video_path, token)

        if notify and notify_required:
            notify_result = self.notifier.send_patrol_alert(
                event,
                {
                    "image_path": str(image_path),
                    "video_path": str(video_path),
                    "gif_path": str(gif_path) if gif_path else "",
                },
                review,
            )
            notify_status = notify_result.get("status", "unknown")
            notify_detail = notify_result.get("detail", "")
            feishu_image_status = notify_result.get("image_status", "unknown")
            feishu_image_detail = notify_result.get("image_detail", "")
            video_delivery_status = notify_result.get("video_status", "unknown")
            video_public_url = notify_result.get("video_url", "")
            gif_delivery_status = notify_result.get("gif_status", "unknown")
            gif_public_url = notify_result.get("gif_url", "")
        elif always_generate_preview:
            video_delivery_status, video_public_url, gif_delivery_status, gif_public_url = self._build_public_delivery(
                video_path, gif_path
            )

        record = PatrolRecord(
            patrol_time=event.timestamp,
            camera_id=event.camera_id,
            detection_status="detected",
            target_detected=True,
            detection_confidence=detection.best_confidence,
            image_path=str(image_path),
            video_path=str(video_path),
            gif_path=str(gif_path) if gif_path else "",
            frame_paths=[str(path) for path in frame_paths],
            activity_label=review.activity_label,
            risk_level=review.risk_level,
            vlm_description=review.description,
            vlm_status=review.status,
            notify_status=notify_status,
            notify_detail=notify_detail,
            feishu_image_status=feishu_image_status,
            feishu_image_detail=feishu_image_detail,
            video_delivery_status=video_delivery_status,
            video_public_url=video_public_url,
            gif_delivery_status=gif_delivery_status,
            gif_public_url=gif_public_url,
        )
        self.logger.write(record.to_dict())
        return record
