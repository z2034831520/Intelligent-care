import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "rdk_x5_demo" / "notebook_vlm_service"
sys.path.insert(0, str(NOTEBOOK))

from ollama_review_service import call_ollama


class OllamaReviewServiceTests(unittest.TestCase):
    def test_falls_back_to_single_frame_after_multi_frame_failure(self) -> None:
        attempts = []

        def fake_request(frame_images, metadata, *, use_schema):
            attempts.append((len(frame_images), use_schema))
            if len(frame_images) > 1:
                raise RuntimeError("multi-frame rejected")
            return {
                "activity_label": "normal_sitting",
                "risk_level": "normal",
                "description": "ok",
                "confidence": 0.9,
                "status": "ok",
            }

        with mock.patch("ollama_review_service._request_ollama", side_effect=fake_request):
            result = call_ollama(["a", "b", "c"], {"source": "test"})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(attempts, [(3, True), (1, True)])

    def test_returns_failed_payload_after_all_attempts(self) -> None:
        with mock.patch("ollama_review_service._request_ollama", side_effect=RuntimeError("bad request")):
            result = call_ollama(["a"], {"source": "test"})

        self.assertEqual(result["status"], "failed")
        self.assertIn("single-frame/no-schema", result["description"])


if __name__ == "__main__":
    unittest.main()
