import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "rdk_x5_demo" / "ros2_ws" / "src" / "smart_care_bridge"
sys.path.insert(0, str(PKG))

from smart_care_bridge.bridge_core import PersonEventBridgeCore
from smart_care_bridge.daily_report import build_daily_report
from smart_care_bridge.feishu_notifier import FeishuNotifier
from smart_care_bridge.models import DetectionCandidate, PersonEvent, VlmReviewResult
from smart_care_bridge.openclaw_patrol_command import (
    ACK_TEXT,
    BUSY_TEXT,
    handle_command,
    normalize_command_text,
    read_lock_pid,
)
from smart_care_bridge.openclaw_patrol_session_bridge import is_patrol_trigger_event
from smart_care_bridge.openclaw_patrol_worker import build_manual_patrol_result_text
from smart_care_bridge.patrol_engine import PatrolEngine
from smart_care_bridge.person_event_bridge import build_log_entry, extract_detection_candidates
from smart_care_bridge.patrol_detection import DetectionResult, PatrolDetector
from smart_care_bridge.record_buffer_service import select_segments_by_mtime
from smart_care_bridge.review_policy import (
    failed_review_result,
    normalize_risk_level,
    postprocess_risk_level,
    review_result_from_payload,
    should_notify,
)


class DummyRect:
    def __init__(self, x, y, w, h):
        self.x_offset = x
        self.y_offset = y
        self.width = w
        self.height = h


class DummyRoi:
    def __init__(self, label, score, rect):
        self.type = label
        self.score = score
        self.rect = rect


class DummyTarget:
    def __init__(self, rois):
        self.rois = rois


class DummyMsg:
    def __init__(self, targets):
        self.targets = targets


class BridgeCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = PersonEventBridgeCore(
            camera_id="usb_cam_0",
            source="/hobot_mono2d_body_detection",
            threshold=0.7,
            confirm_frames=3,
            cooldown_seconds=30,
            person_labels=["person", "body"],
        )

    def test_requires_three_consecutive_frames(self) -> None:
        candidate = DetectionCandidate(label="person", score=0.91, bbox=[1, 2, 3, 4])
        now = 100.0
        self.assertFalse(self.core.process([candidate], now).triggered)
        self.assertFalse(self.core.process([candidate], now + 0.1).triggered)
        third = self.core.process([candidate], now + 0.2)
        self.assertTrue(third.triggered)
        self.assertIsNotNone(third.event)

    def test_cooldown_prevents_spam(self) -> None:
        candidate = DetectionCandidate(label="person", score=0.91, bbox=[1, 2, 3, 4])
        self.core.process([candidate], 100.0)
        self.core.process([candidate], 100.1)
        self.assertTrue(self.core.process([candidate], 100.2).triggered)
        self.core.process([candidate], 101.0)
        self.core.process([candidate], 101.1)
        self.assertFalse(self.core.process([candidate], 101.2).triggered)

    def test_non_person_resets_counter(self) -> None:
        person = DetectionCandidate(label="person", score=0.91, bbox=[1, 2, 3, 4])
        cat = DetectionCandidate(label="cat", score=0.95, bbox=[1, 2, 3, 4])
        self.core.process([person], 100.0)
        self.core.process([cat], 100.1)
        result = self.core.process([person], 100.2)
        self.assertFalse(result.triggered)


class ParserTests(unittest.TestCase):
    def test_extract_detection_candidates_from_rois(self) -> None:
        msg = DummyMsg(
            [
                DummyTarget([DummyRoi("person", 0.88, DummyRect(10, 20, 30, 40))]),
                DummyTarget([DummyRoi("cat", 0.80, DummyRect(1, 2, 3, 4))]),
            ]
        )
        candidates = extract_detection_candidates(msg)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].bbox, [10, 20, 40, 60])
        self.assertEqual(candidates[0].label, "person")

    def test_build_log_entry(self) -> None:
        event = self.core_event()
        review = review_result_from_payload(
            {
                "activity_label": "possible_fall",
                "risk_level": "alarm",
                "description": "Possible fall detected.",
                "confidence": 0.9,
            }
        )
        log_entry = build_log_entry(
            event,
            {
                "image_path": "/tmp/a.jpg",
                "image_status": "saved",
                "video_path": "/tmp/a.mp4",
                "video_status": "saved",
                "frame_paths": ["/tmp/f1.jpg", "/tmp/f2.jpg"],
                "frame_status": "saved",
            },
            review,
            {
                "status": "sent",
                "detail": "ok",
                "image_status": "sent",
                "image_detail": "image_key=img_123 message_id=om_456",
                "video_status": "linked",
                "video_url": "http://board/evidence/videos/a.mp4",
                "gif_status": "linked",
                "gif_url": "http://board/evidence/gifs/a.gif",
            },
        )
        self.assertEqual(log_entry["event_type"], "person_detected")
        self.assertEqual(log_entry["feishu_status"], "sent")
        self.assertEqual(log_entry["image_path"], "/tmp/a.jpg")
        self.assertEqual(log_entry["video_path"], "/tmp/a.mp4")
        self.assertEqual(log_entry["activity_label"], "possible_fall")
        self.assertEqual(log_entry["risk_level"], "alarm")
        self.assertEqual(log_entry["feishu_image_status"], "sent")
        self.assertEqual(log_entry["video_delivery_status"], "linked")
        self.assertEqual(log_entry["video_public_url"], "http://board/evidence/videos/a.mp4")
        self.assertEqual(log_entry["gif_delivery_status"], "linked")
        self.assertEqual(log_entry["gif_public_url"], "http://board/evidence/gifs/a.gif")

    def core_event(self):
        candidate = DetectionCandidate(label="person", score=0.91, bbox=[1, 2, 3, 4])
        core = PersonEventBridgeCore(
            camera_id="usb_cam_0",
            source="/topic",
            threshold=0.7,
            confirm_frames=1,
            cooldown_seconds=30,
            person_labels=["person"],
        )
        decision = core.process([candidate], time.monotonic())
        return decision.event


class RecordingHelpersTests(unittest.TestCase):
    def test_select_segments_by_mtime(self) -> None:
        temp_dir = ROOT / "tmp_test_segments"
        temp_dir.mkdir(exist_ok=True)
        paths = []
        try:
            for idx, offset in enumerate((100.0, 106.0, 112.0)):
                path = temp_dir / f"segment_{idx}.mp4"
                path.write_text("x", encoding="utf-8")
                os.utime(path, (offset, offset))
                paths.append(path)
            selected = select_segments_by_mtime(paths, 104.0, 110.0)
            self.assertEqual([path.name for path in selected], ["segment_1.mp4"])
        finally:
            for path in paths:
                path.unlink(missing_ok=True)
            for leftover in temp_dir.glob("*"):
                leftover.unlink(missing_ok=True)
            temp_dir.rmdir()


class ReviewPolicyTests(unittest.TestCase):
    def test_uncertain_maps_to_warning(self) -> None:
        self.assertEqual(normalize_risk_level("uncertain"), "warning")

    def test_normal_activity_is_downgraded_to_normal(self) -> None:
        result = review_result_from_payload(
            {
                "activity_label": "normal_sitting",
                "risk_level": "warning",
                "description": "A person is seated at a computer desk.",
                "confidence": 0.59,
            }
        )
        self.assertEqual(result.risk_level, "normal")

    def test_danger_keywords_preserve_warning(self) -> None:
        self.assertEqual(
            postprocess_risk_level(
                "normal_sitting",
                "warning",
                "The person appears seated but may have fallen and is in an unsafe posture.",
            ),
            "warning",
        )

    def test_floor_sitting_is_not_treated_as_normal(self) -> None:
        result = review_result_from_payload(
            {
                "activity_label": "normal_sitting",
                "risk_level": "normal",
                "description": "A person is sitting on the floor near a desk with one leg bent.",
                "confidence": 0.82,
            }
        )
        self.assertEqual(result.risk_level, "warning")

    def test_should_notify(self) -> None:
        normal = review_result_from_payload(
            {
                "activity_label": "normal_cleaning",
                "risk_level": "normal",
                "description": "Normal cleaning.",
                "confidence": 0.8,
            }
        )
        alarm = review_result_from_payload(
            {
                "activity_label": "possible_fall",
                "risk_level": "alarm",
                "description": "Possible fall.",
                "confidence": 0.9,
            }
        )
        failed = failed_review_result("timeout")
        self.assertFalse(should_notify(normal))
        self.assertTrue(should_notify(alarm))
        self.assertTrue(should_notify(failed))


class FeishuNotifierTests(unittest.TestCase):
    def test_send_patrol_alert_sends_native_gif_image_when_app_configured(self) -> None:
        temp_root = ROOT / "tmp_evidence_videos"
        gif_root = ROOT / "tmp_evidence_gifs"
        temp_root.mkdir(exist_ok=True)
        gif_root.mkdir(exist_ok=True)
        video_path = temp_root / "clip.mp4"
        gif_path = gif_root / "clip.gif"
        video_path.write_bytes(b"demo")
        gif_path.write_bytes(b"gif")

        event = PersonEvent(
            event_type="person_detected",
            timestamp="2026-04-28T10:00:00+08:00",
            camera_id="usb_cam_0",
            confidence=0.91,
            bbox=[1, 2, 3, 4],
            source="/topic",
        )
        review = VlmReviewResult(
            activity_label="possible_fall",
            risk_level="alarm",
            description="Possible fall detected.",
            confidence=0.95,
        )
        notifier = FeishuNotifier(
            "https://example.test/hook",
            "RDK X5",
            "http://board/evidence",
            {"videos": temp_root, "gifs": gif_root},
            app_id="cli_test",
            app_secret="secret_test",
            chat_id="oc_test",
        )

        fake_requests = mock.Mock()
        token_response = mock.Mock(status_code=200)
        token_response.json.return_value = {"code": 0, "tenant_access_token": "tenant_token"}
        text_message_response = mock.Mock(status_code=200)
        text_message_response.json.return_value = {"code": 0, "data": {"message_id": "om_text"}}
        upload_response = mock.Mock(status_code=200)
        upload_response.json.return_value = {"code": 0, "data": {"image_key": "img_key"}}
        image_message_response = mock.Mock(status_code=200)
        image_message_response.json.return_value = {"code": 0, "data": {"message_id": "om_123"}}
        fake_requests.post.side_effect = [
            token_response,
            text_message_response,
            upload_response,
            image_message_response,
        ]

        try:
            with mock.patch.dict(sys.modules, {"requests": fake_requests}):
                result = notifier.send_patrol_alert(
                    event,
                    {"video_path": str(video_path), "gif_path": str(gif_path), "image_path": "/tmp/frame.jpg"},
                    review,
                )
        finally:
            video_path.unlink(missing_ok=True)
            gif_path.unlink(missing_ok=True)
            temp_root.rmdir()
            gif_root.rmdir()

        text_payload = fake_requests.post.call_args_list[1].kwargs["json"]
        self.assertIn("[ALARM] person activity review", json.loads(text_payload["content"])["text"])
        self.assertEqual(result["status"], "sent")
        self.assertIn("message_id=om_text", result["detail"])
        self.assertEqual(result["image_status"], "sent")
        self.assertIn("image_key=img_key", result["image_detail"])
        self.assertEqual(result["video_status"], "linked")
        self.assertEqual(result["video_url"], "http://board/evidence/videos/clip.mp4")
        self.assertEqual(result["gif_status"], "linked")
        self.assertEqual(result["gif_url"], "http://board/evidence/gifs/clip.gif")

    def test_send_openclaw_text_uses_app_identity(self) -> None:
        notifier = FeishuNotifier(
            "",
            "RDK X5",
            app_id="cli_test",
            app_secret="secret_test",
            chat_id="oc_test",
        )
        fake_requests = mock.Mock()
        token_response = mock.Mock(status_code=200)
        token_response.json.return_value = {"code": 0, "tenant_access_token": "tenant_token"}
        text_message_response = mock.Mock(status_code=200)
        text_message_response.json.return_value = {"code": 0, "data": {"message_id": "om_text"}}
        fake_requests.post.side_effect = [token_response, text_message_response]

        with mock.patch.dict(sys.modules, {"requests": fake_requests}):
            result = notifier.send_openclaw_text("已开始巡视，请稍候")

        self.assertEqual(result["status"], "sent")
        self.assertIn("message_id=om_text", result["detail"])


class OpenClawPatrolCommandTests(unittest.TestCase):
    def test_normalize_command_text_strips_plain_mention(self) -> None:
        self.assertEqual(normalize_command_text("@openclaw 巡视一下"), "巡视一下")

    def test_normalize_command_text_strips_at_tag(self) -> None:
        text = '<at user_id="ou_1">openclaw</at> 巡视一下'
        self.assertEqual(normalize_command_text(text), "巡视一下")

    def test_normalize_command_text_supports_ascii_alias(self) -> None:
        self.assertEqual(normalize_command_text("@openclaw patrol-now"), "patrol-now")

    def test_handle_command_rejects_other_chat(self) -> None:
        notifier = mock.Mock()
        result = handle_command(
            chat_id="oc_other",
            text="巡视一下",
            notifier=notifier,
            configured_chat_id="oc_target",
            lock_path=ROOT / "tmp_manual_patrol.lock",
            launcher=mock.Mock(),
        )
        self.assertEqual(result["status"], "ignored")
        notifier.send_openclaw_text.assert_not_called()

    def test_handle_command_reports_busy_when_lock_exists(self) -> None:
        lock_path = ROOT / "tmp_manual_patrol.lock"
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
        notifier = mock.Mock()
        notifier.send_openclaw_text.return_value = {"status": "sent", "detail": "message_id=busy"}
        try:
            result = handle_command(
                chat_id="oc_target",
                text="巡视一下",
                notifier=notifier,
                configured_chat_id="oc_target",
                lock_path=lock_path,
                launcher=mock.Mock(),
            )
        finally:
            lock_path.unlink(missing_ok=True)

        self.assertEqual(result["status"], "busy")
        notifier.send_openclaw_text.assert_called_once_with(BUSY_TEXT)

    def test_handle_command_clears_stale_lock_and_starts(self) -> None:
        lock_path = ROOT / "tmp_manual_patrol_stale.lock"
        lock_path.write_text("999999", encoding="utf-8")
        notifier = mock.Mock()
        notifier.send_openclaw_text.return_value = {"status": "sent", "detail": "message_id=ack"}
        launcher = mock.Mock(return_value=43210)
        try:
            result = handle_command(
                chat_id="oc_target",
                text="patrol-now",
                notifier=notifier,
                configured_chat_id="oc_target",
                lock_path=lock_path,
                launcher=launcher,
            )
            written_pid = read_lock_pid(lock_path)
        finally:
            lock_path.unlink(missing_ok=True)

        self.assertEqual(result["status"], "started")
        self.assertEqual(written_pid, 43210)
        notifier.send_openclaw_text.assert_called_once_with(ACK_TEXT)
        launcher.assert_called_once()

    def test_handle_command_sends_ack_and_launches_worker(self) -> None:
        lock_path = ROOT / "tmp_manual_patrol.lock"
        notifier = mock.Mock()
        notifier.send_openclaw_text.return_value = {"status": "sent", "detail": "message_id=ack"}
        launcher = mock.Mock(return_value=34567)
        try:
            result = handle_command(
                chat_id="oc_target",
                text="@openclaw 巡视一下",
                notifier=notifier,
                configured_chat_id="oc_target",
                lock_path=lock_path,
                launcher=launcher,
            )
            written_pid = read_lock_pid(lock_path)
        finally:
            lock_path.unlink(missing_ok=True)

        self.assertEqual(result["status"], "started")
        self.assertEqual(written_pid, 34567)
        notifier.send_openclaw_text.assert_called_once_with(ACK_TEXT)
        launcher.assert_called_once()

    def test_handle_command_accepts_ascii_alias(self) -> None:
        lock_path = ROOT / "tmp_manual_patrol_ascii.lock"
        notifier = mock.Mock()
        notifier.send_openclaw_text.return_value = {"status": "sent", "detail": "message_id=ack"}
        launcher = mock.Mock(return_value=45678)
        try:
            result = handle_command(
                chat_id="oc_target",
                text="patrol-now",
                notifier=notifier,
                configured_chat_id="oc_target",
                lock_path=lock_path,
                launcher=launcher,
            )
            written_pid = read_lock_pid(lock_path)
        finally:
            lock_path.unlink(missing_ok=True)

        self.assertEqual(result["status"], "started")
        self.assertEqual(written_pid, 45678)
        notifier.send_openclaw_text.assert_called_once_with(ACK_TEXT)
        launcher.assert_called_once()

    def test_build_manual_patrol_result_text(self) -> None:
        text = build_manual_patrol_result_text(
            mock.Mock(
                patrol_time="2026-04-29T10:00:00+08:00",
                camera_id="usb_cam_0",
                detection_status="detected",
                target_detected=True,
                activity_label="possible_fall",
                risk_level="warning",
                vlm_status="ok",
                vlm_description="Possible fall detected.",
                image_path="/tmp/frame.jpg",
                video_path="/tmp/clip.mp4",
                gif_path="/tmp/clip.gif",
                video_public_url="http://board/evidence/videos/clip.mp4",
                gif_public_url="http://board/evidence/gifs/clip.gif",
            ),
            "RDK X5",
        )
        self.assertIn("[主动巡视结果]", text)
        self.assertIn("检测状态: detected", text)
        self.assertIn("检测到目标: 是", text)
        self.assertIn("风险等级: warning", text)
        self.assertIn("GIF 链接: http://board/evidence/gifs/clip.gif", text)

    def test_build_manual_patrol_result_text_marks_detector_failure_as_unknown(self) -> None:
        text = build_manual_patrol_result_text(
            mock.Mock(
                patrol_time="2026-05-01T20:36:19+08:00",
                camera_id="usb_cam_0",
                detection_status="failed",
                target_detected=False,
                activity_label="uncertain",
                risk_level="warning",
                vlm_status="failed",
                vlm_description="Detector failed: timeout",
                image_path="/tmp/frame.jpg",
                video_path="/tmp/clip.mp4",
                gif_path="/tmp/clip.gif",
                video_public_url="http://board/evidence/videos/clip.mp4",
                gif_public_url="http://board/evidence/gifs/clip.gif",
            ),
            "RDK X5",
        )
        self.assertIn("检测状态: failed", text)
        self.assertIn("检测到目标: 未知", text)


class OpenClawPatrolSessionBridgeTests(unittest.TestCase):
    def test_detects_user_trigger_in_target_group(self) -> None:
        event = {
            "role": "user",
            "chat_id": "oc_target",
            "content": {"text": "@openclaw 巡视一下"},
        }
        self.assertTrue(is_patrol_trigger_event(event, "oc_target"))

    def test_detects_ascii_alias_in_target_group(self) -> None:
        event = {
            "author_role": "user",
            "metadata": {"chat_id": "oc_target"},
            "content": {"text": "@openclaw patrol-now"},
        }
        self.assertTrue(is_patrol_trigger_event(event, "oc_target"))

    def test_detects_mention_without_explicit_role_when_group_matches(self) -> None:
        event = {
            "metadata": {"chat_id": "oc_target"},
            "content": {"text": "@openclaw patrol-now"},
        }
        self.assertTrue(is_patrol_trigger_event(event, "oc_target"))

    def test_ignores_assistant_echoes(self) -> None:
        event = {
            "role": "assistant",
            "chat_id": "oc_target",
            "content": {"text": "@openclaw 巡视一下"},
        }
        self.assertFalse(is_patrol_trigger_event(event, "oc_target"))

    def test_ignores_other_groups(self) -> None:
        event = {
            "role": "user",
            "chat_id": "oc_other",
            "content": {"text": "@openclaw 巡视一下"},
        }
        self.assertFalse(is_patrol_trigger_event(event, "oc_target"))


class DailyReportTests(unittest.TestCase):
    def test_build_daily_report(self) -> None:
        report = build_daily_report(
            [
                {"patrol_time": "2026-04-26T10:00:00", "target_detected": False, "risk_level": "normal"},
                {"patrol_time": "2026-04-26T10:02:00", "target_detected": True, "risk_level": "normal"},
                {"patrol_time": "2026-04-26T10:04:00", "target_detected": True, "risk_level": "warning"},
                {"patrol_time": "2026-04-26T10:06:00", "target_detected": True, "risk_level": "alarm"},
            ],
            "2026-04-26",
        )
        self.assertEqual(report.patrol_count, 4)
        self.assertEqual(report.empty_count, 1)
        self.assertEqual(report.target_count, 3)
        self.assertEqual(report.normal_count, 1)
        self.assertEqual(report.warning_count, 1)
        self.assertEqual(report.alarm_count, 1)


class PatrolDetectorTests(unittest.TestCase):
    def test_rdk_x5_mode_dispatch(self) -> None:
        detector = PatrolDetector(
            mode="rdk_x5_ros2_image",
            command="",
            person_labels=["person"],
            topic="/hobot_mono2d_body_detection",
            timeout_seconds=20,
            setup_script="/opt/tros/humble/setup.bash",
        )
        expected = DetectionResult([DetectionCandidate(label="person", score=0.93, bbox=[1, 2, 3, 4])])
        with mock.patch.object(detector, "_detect_with_rdk_x5_ros2_image", return_value=expected) as patched:
            result = detector.detect(Path("/tmp/patrol.jpg"))
        patched.assert_called_once()
        self.assertTrue(result.target_detected)
        self.assertEqual(result.best_confidence, 0.93)

    def test_json_command_filters_non_person_labels(self) -> None:
        detector = PatrolDetector(
            mode="json_command",
            command="",
            person_labels=["person"],
            topic="/hobot_mono2d_body_detection",
            timeout_seconds=20,
            setup_script="/opt/tros/humble/setup.bash",
        )
        with mock.patch("subprocess.run") as patched_run:
            patched_run.return_value = mock.Mock(
                returncode=0,
                stdout='{"candidates":[{"label":"person","score":0.91,"bbox":[1,2,3,4]},{"label":"cat","score":0.8,"bbox":[5,6,7,8]}]}',
                stderr="",
            )
            detector.command = "fake {image_path}"
            result = detector.detect(Path("/tmp/patrol.jpg"))

        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].label, "person")


class PatrolEngineTests(unittest.TestCase):
    def test_detector_failure_still_returns_evidence_record(self) -> None:
        image_path = Path("/tmp/patrol.jpg")
        video_path = Path("/tmp/patrol.mp4")
        gif_path = Path("/tmp/patrol.gif")
        frame_paths = [Path("/tmp/frame_01.jpg"), Path("/tmp/frame_02.jpg")]
        bridge_config = mock.Mock(
            detector_mode="rdk_x5_ros2_image",
            detector_command="",
            person_labels=["person"],
            person_topic="/hobot_mono2d_body_detection",
            detector_timeout_seconds=45,
            detector_setup_script="/opt/tros/humble/setup.bash",
            vlm_server_url="http://example.test/analyze",
            vlm_timeout_seconds=45,
            vlm_retry_count=2,
            feishu_webhook_url="",
            device_name="RDK X5",
            evidence_public_base_url="http://board/evidence",
            feishu_app_id="cli_test",
            feishu_app_secret="secret_test",
            feishu_chat_id="oc_test",
            patrol_log_path=Path("/tmp/patrol_events.jsonl"),
        )
        recording_config = mock.Mock(
            evidence_image_dir=Path("/tmp/images"),
            evidence_video_dir=Path("/tmp/videos"),
            evidence_gif_dir=Path("/tmp/gifs"),
            evidence_frame_dir=Path("/tmp/frames"),
        )

        with (
            mock.patch("smart_care_bridge.patrol_engine.PatrolCapture") as capture_cls,
            mock.patch("smart_care_bridge.patrol_engine.PatrolDetector") as detector_cls,
            mock.patch("smart_care_bridge.patrol_engine.VlmReviewClient"),
            mock.patch("smart_care_bridge.patrol_engine.FeishuNotifier") as notifier_cls,
            mock.patch("smart_care_bridge.patrol_engine.JsonlEventLogger") as logger_cls,
        ):
            capture = capture_cls.return_value
            capture.capture_snapshot_and_video.return_value = (image_path, video_path)
            capture.extract_key_frames.return_value = frame_paths
            capture.create_preview_gif.return_value = gif_path
            detector_cls.return_value.detect.side_effect = TimeoutError("Timed out after 45s waiting for detector topic /hobot_mono2d_body_detection")
            notifier = notifier_cls.return_value
            notifier.build_public_evidence_url.side_effect = [
                "http://board/evidence/videos/patrol.mp4",
                "http://board/evidence/gifs/patrol.gif",
            ]
            logger = logger_cls.return_value

            engine = PatrolEngine(bridge_config, recording_config)
            event = PersonEvent(
                event_type="manual_patrol",
                timestamp="2026-05-01T20:00:00+08:00",
                camera_id="usb_cam_0",
                confidence=0.0,
                bbox=[],
                source="openclaw_manual_patrol",
            )
            record = engine.run_patrol(event, notify=False, always_generate_preview=True)

        self.assertFalse(record.target_detected)
        self.assertEqual(record.detection_status, "failed")
        self.assertEqual(record.activity_label, "uncertain")
        self.assertEqual(record.risk_level, "warning")
        self.assertEqual(record.vlm_status, "failed")
        self.assertIn("Detector failed:", record.vlm_description)
        self.assertEqual(record.image_path, str(image_path))
        self.assertEqual(record.video_path, str(video_path))
        self.assertEqual(record.gif_path, str(gif_path))
        self.assertEqual(record.frame_paths, [str(path) for path in frame_paths])
        self.assertEqual(record.video_public_url, "http://board/evidence/videos/patrol.mp4")
        self.assertEqual(record.gif_public_url, "http://board/evidence/gifs/patrol.gif")
        logger.write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
