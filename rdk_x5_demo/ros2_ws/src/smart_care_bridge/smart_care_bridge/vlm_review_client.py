from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict
from urllib import request

from .models import PersonEvent, VlmReviewResult
from .review_policy import failed_review_result, review_result_from_payload


class VlmReviewClient:
    def __init__(self, server_url: str, timeout_seconds: int, retry_count: int) -> None:
        self.server_url = server_url
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count

    def review_event(self, event: PersonEvent, evidence: Dict[str, object]) -> VlmReviewResult:
        if not self.server_url:
            return failed_review_result("missing VLM_SERVER_URL")

        frame_paths = [str(item) for item in evidence.get("frame_paths", []) or []]
        if not frame_paths:
            return failed_review_result("no frame paths available")

        payload = {
            "event_id": event.timestamp,
            "camera_id": event.camera_id,
            "frames": frame_paths,
            "frame_images": [self._encode_base64(Path(path)) for path in frame_paths],
            "metadata": {
                "person_confidence": event.confidence,
                "bbox": event.bbox,
                "video_path": evidence.get("video_path", ""),
                "image_path": evidence.get("image_path", ""),
                "source": event.source,
            },
        }

        last_error = "unknown error"
        for _ in range(self.retry_count + 1):
            try:
                result = self._post_json(payload)
                return review_result_from_payload(result)
            except Exception as exc:
                last_error = str(exc)
        return failed_review_result(last_error)

    def _post_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = request.Request(
            self.server_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _encode_base64(self, path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode("utf-8")
