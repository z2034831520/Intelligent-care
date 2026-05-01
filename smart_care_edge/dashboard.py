from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Dict
from urllib.parse import urlparse

from .runtime import RuntimeState


class DashboardServer:
    def __init__(self, port: int, runtime_state: RuntimeState) -> None:
        self.port = port
        self.runtime_state = runtime_state
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler_factory())
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=2)

    def _handler_factory(self):
        runtime_state = self.runtime_state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == "/api/status":
                    self._json(runtime_state.status_payload())
                    return
                if parsed.path == "/api/events":
                    self._json(runtime_state.latest_payload())
                    return
                if parsed.path == "/":
                    self._html(self._render_index(runtime_state.status_payload(), runtime_state.latest_payload()))
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _json(self, payload: Dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _html(self, html: str) -> None:
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _render_index(self, status: Dict[str, Any], latest: Dict[str, Any]) -> str:
                return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Smart Care Edge</title>
  <style>
    body {{ font-family: "Segoe UI", sans-serif; margin: 24px; background: #f6f8fb; color: #1b2430; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
    .card {{ background: white; border-radius: 16px; padding: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); }}
    .level {{ font-size: 32px; font-weight: 700; text-transform: uppercase; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 12px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>智能看护边缘终端</h1>
  <div class="grid">
    <div class="card">
      <div>当前等级</div>
      <div class="level">{status["level"]}</div>
      <div>更新时间：{status["updated_at"]}</div>
      <div>最近原因：{status["last_reason"]}</div>
    </div>
    <div class="card">
      <div>最近动作</div>
      <pre>{json.dumps(status.get("latest_actions", []), ensure_ascii=False, indent=2)}</pre>
    </div>
    <div class="card">
      <div>最近传感器事件</div>
      <pre>{json.dumps(latest.get("sensor_events", []), ensure_ascii=False, indent=2)}</pre>
    </div>
    <div class="card">
      <div>最近视觉事件</div>
      <pre>{json.dumps(latest.get("vision_events", []), ensure_ascii=False, indent=2)}</pre>
    </div>
  </div>
</body>
</html>
"""

        return Handler
