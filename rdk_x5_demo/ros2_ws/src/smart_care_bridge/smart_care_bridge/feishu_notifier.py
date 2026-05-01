from __future__ import annotations

import json
from pathlib import Path
from typing import Dict
from urllib.parse import quote

from .models import DailyReport, PersonEvent, VlmReviewResult


class FeishuNotifier:
    def __init__(
        self,
        webhook_url: str,
        device_name: str,
        evidence_public_base_url: str = "",
        evidence_roots: Dict[str, Path] | None = None,
        app_id: str = "",
        app_secret: str = "",
        chat_id: str = "",
    ) -> None:
        self.webhook_url = webhook_url
        self.device_name = device_name
        self.evidence_public_base_url = evidence_public_base_url.rstrip("/")
        self.evidence_roots = evidence_roots or {}
        self.app_id = app_id
        self.app_secret = app_secret
        self.chat_id = chat_id

    def _build_public_evidence_url(self, evidence_path: str, media_kind: str) -> str:
        if not self.evidence_public_base_url or not evidence_path:
            return ""

        root = self.evidence_roots.get(media_kind)
        if root is None:
            return ""

        try:
            relative = Path(evidence_path).resolve().relative_to(root.resolve())
        except Exception:
            return ""

        encoded = "/".join(quote(part) for part in relative.parts)
        return f"{self.evidence_public_base_url}/{media_kind}/{encoded}"

    def build_public_evidence_url(self, evidence_path: str, media_kind: str) -> str:
        return self._build_public_evidence_url(evidence_path, media_kind)

    def _load_requests(self):
        try:
            import requests  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(f"requests unavailable: {exc}") from exc
        return requests

    def _response_json(self, response) -> dict:
        try:
            data = response.json()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"unexpected Feishu response: {response.text[:200]}") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")

        if data.get("code", 0) != 0:
            raise RuntimeError(data.get("msg", response.text[:200]) or "unknown Feishu API error")

        return data

    def _get_tenant_access_token(self) -> str:
        if not self.app_id or not self.app_secret:
            raise RuntimeError("missing FEISHU_APP_ID or FEISHU_APP_SECRET")

        requests = self._load_requests()
        response = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        data = self._response_json(response)
        token = data.get("tenant_access_token", "")
        if not token:
            raise RuntimeError("Feishu token response missing tenant_access_token")
        return token

    def _upload_message_image(self, token: str, gif_path: str) -> str:
        path = Path(gif_path)
        if not path.is_file():
            raise RuntimeError(f"gif file not found: {gif_path}")

        requests = self._load_requests()
        with path.open("rb") as handle:
            response = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                data={"image_type": "message"},
                files={"image": (path.name, handle, "image/gif")},
                timeout=20,
            )
        data = self._response_json(response)
        image_key = (data.get("data") or {}).get("image_key", "")
        if not image_key:
            raise RuntimeError("Feishu upload response missing image_key")
        return image_key

    def _send_image_message(self, token: str, image_key: str) -> str:
        if not self.chat_id:
            raise RuntimeError("missing FEISHU_CHAT_ID")

        requests = self._load_requests()
        response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": self.chat_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
            },
            timeout=10,
        )
        data = self._response_json(response)
        message_id = (data.get("data") or {}).get("message_id", "")
        if not message_id:
            raise RuntimeError("Feishu send message response missing message_id")
        return message_id

    def _send_text_message(self, token: str, text: str) -> str:
        if not self.chat_id:
            raise RuntimeError("missing FEISHU_CHAT_ID")

        requests = self._load_requests()
        response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": self.chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=10,
        )
        data = self._response_json(response)
        message_id = (data.get("data") or {}).get("message_id", "")
        if not message_id:
            raise RuntimeError("Feishu send text response missing message_id")
        return message_id

    def _send_native_gif_image(self, gif_path: str, token: str | None = None) -> Dict[str, str]:
        if not gif_path:
            return {"status": "skipped", "detail": "missing gif path"}
        if not self.app_id or not self.app_secret:
            return {"status": "skipped", "detail": "missing FEISHU_APP_ID or FEISHU_APP_SECRET"}
        if not self.chat_id:
            return {"status": "skipped", "detail": "missing FEISHU_CHAT_ID"}

        try:
            tenant_token = token or self._get_tenant_access_token()
            image_key = self._upload_message_image(tenant_token, gif_path)
            message_id = self._send_image_message(tenant_token, image_key)
            return {"status": "sent", "detail": f"image_key={image_key} message_id={message_id}"}
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "detail": str(exc)}

    def send_openclaw_text(self, text: str) -> Dict[str, str]:
        if not self.app_id or not self.app_secret:
            return {"status": "skipped", "detail": "missing FEISHU_APP_ID or FEISHU_APP_SECRET"}
        if not self.chat_id:
            return {"status": "skipped", "detail": "missing FEISHU_CHAT_ID"}

        try:
            token = self._get_tenant_access_token()
            message_id = self._send_text_message(token, text)
            return {"status": "sent", "detail": f"message_id={message_id}"}
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "detail": str(exc)}

    def send_openclaw_gif(self, gif_path: str) -> Dict[str, str]:
        return self._send_native_gif_image(gif_path)

    def send_patrol_alert(
        self,
        event: PersonEvent,
        evidence: Dict[str, object] | None = None,
        review: VlmReviewResult | None = None,
    ) -> Dict[str, str]:
        evidence = evidence or {}
        review = review or VlmReviewResult(
            activity_label="uncertain",
            risk_level="warning",
            description="No review result available.",
            confidence=0.0,
        )
        gif_path = str(evidence.get("gif_path", ""))
        gif_url = self._build_public_evidence_url(gif_path, "gifs")
        video_url = self._build_public_evidence_url(str(evidence.get("video_path", "")), "videos")
        video_status = "linked" if video_url else "unavailable"
        gif_status = "linked" if gif_url else "unavailable"

        lines = [
            f"[{review.risk_level.upper()}] person activity review",
            f"Time: {event.timestamp}",
            f"Device: {self.device_name}",
            f"Camera: {event.camera_id}",
            f"Activity: {review.activity_label}",
            f"Review confidence: {review.confidence:.2f}",
            f"Description: {review.description}",
            f"Image: {evidence.get('image_path', '')}",
            f"Video: {evidence.get('video_path', '')}",
        ]
        if gif_path:
            lines.append(f"GIF: {gif_path}")
        if gif_url:
            lines.append(f"GIF URL: {gif_url}")
        elif video_url:
            lines.append("GIF delivery: unavailable, falling back to raw video link")
            lines.append(f"Video URL: {video_url}")
        else:
            lines.append("Preview delivery: unavailable (set EVIDENCE_PUBLIC_BASE_URL and run evidence_file_server)")

        text_body = "\n".join(lines)
        text_result = {"status": "skipped", "detail": "missing FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_CHAT_ID"}
        image_result = {"status": "skipped", "detail": "missing gif path or app config"}
        token = None
        if self.app_id and self.app_secret and self.chat_id:
            try:
                token = self._get_tenant_access_token()
                message_id = self._send_text_message(token, text_body)
                text_result = {"status": "sent", "detail": f"message_id={message_id}"}
            except Exception as exc:  # pragma: no cover
                text_result = {"status": "failed", "detail": str(exc)}
            image_result = self._send_native_gif_image(gif_path, token=token)

        if not self.webhook_url:
            return {
                "status": text_result["status"],
                "detail": text_result["detail"],
                "image_status": image_result["status"],
                "image_detail": image_result["detail"],
                "video_status": video_status,
                "video_url": video_url,
                "gif_status": gif_status,
                "gif_url": gif_url,
            }

        if text_result["status"] == "sent":
            return {
                "status": "sent",
                "detail": text_result["detail"],
                "image_status": image_result["status"],
                "image_detail": image_result["detail"],
                "video_status": video_status,
                "video_url": video_url,
                "gif_status": gif_status,
                "gif_url": gif_url,
            }

        payload = {"msg_type": "text", "content": {"text": text_body}}

        try:
            requests = self._load_requests()
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            return {
                "status": "sent",
                "detail": f"fallback webhook: {response.text[:160]}",
                "image_status": image_result["status"],
                "image_detail": image_result["detail"],
                "video_status": video_status,
                "video_url": video_url,
                "gif_status": gif_status,
                "gif_url": gif_url,
            }
        except Exception as exc:  # pragma: no cover
            return {
                "status": "failed",
                "detail": str(exc),
                "image_status": image_result["status"],
                "image_detail": image_result["detail"],
                "video_status": video_status,
                "video_url": video_url,
                "gif_status": gif_status,
                "gif_url": gif_url,
            }

    def send(
        self,
        event: PersonEvent,
        evidence: Dict[str, object] | None = None,
        review: VlmReviewResult | None = None,
    ) -> Dict[str, str]:
        return self.send_patrol_alert(event, evidence, review)

    def send_daily_report(self, report: DailyReport) -> Dict[str, str]:
        if not self.webhook_url:
            if self.app_id and self.app_secret and self.chat_id:
                try:
                    token = self._get_tenant_access_token()
                    text = (
                        f"[DAILY REPORT] {report.date}\n"
                        f"Patrols: {report.patrol_count}\n"
                        f"Empty: {report.empty_count}\n"
                        f"Target detected: {report.target_count}\n"
                        f"Normal: {report.normal_count}\n"
                        f"Warning: {report.warning_count}\n"
                        f"Alarm: {report.alarm_count}\n"
                        f"Summary: {report.summary}"
                    )
                    message_id = self._send_text_message(token, text)
                    return {"status": "sent", "detail": f"message_id={message_id}"}
                except Exception as exc:  # pragma: no cover
                    return {"status": "failed", "detail": str(exc)}
            return {"status": "skipped", "detail": "missing webhook url"}

        text = (
            f"[DAILY REPORT] {report.date}\n"
            f"Patrols: {report.patrol_count}\n"
            f"Empty: {report.empty_count}\n"
            f"Target detected: {report.target_count}\n"
            f"Normal: {report.normal_count}\n"
            f"Warning: {report.warning_count}\n"
            f"Alarm: {report.alarm_count}\n"
            f"Summary: {report.summary}"
        )

        if self.app_id and self.app_secret and self.chat_id:
            try:
                token = self._get_tenant_access_token()
                message_id = self._send_text_message(token, text)
                return {"status": "sent", "detail": f"message_id={message_id}"}
            except Exception:
                pass

        payload = {"msg_type": "text", "content": {"text": text}}

        try:
            requests = self._load_requests()
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            return {"status": "sent", "detail": response.text[:200]}
        except Exception as exc:  # pragma: no cover
            return {"status": "failed", "detail": str(exc)}
