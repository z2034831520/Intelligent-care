from __future__ import annotations

import json
from typing import Dict
from urllib import request


class EvidenceClient:
    def __init__(self, recorder_port: int) -> None:
        self.base_url = f"http://127.0.0.1:{recorder_port}"

    def export_event(self, event_time: str) -> Dict[str, object]:
        payload = json.dumps({"event_time": event_time}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/export_event",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
