from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List

from .recording_config import RecordingConfig, load_recording_config


def _timestamp_for_filename(event_time: str) -> str:
    safe = event_time.replace(":", "-").replace("+", "_").replace("T", "_")
    return safe


def select_segments_by_mtime(paths: List[Path], window_start: float, window_end: float) -> List[Path]:
    selected = []
    for path in sorted(paths, key=lambda item: item.stat().st_mtime):
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if window_start <= mtime <= window_end:
            selected.append(path)
    return selected


class SegmentRecorder:
    def __init__(self, config: RecordingConfig) -> None:
        self.config = config
        self.config.tmp_segment_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_image_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_video_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_gif_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_frame_dir.mkdir(parents=True, exist_ok=True)
        self._ffmpeg_process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        pattern = str(self.config.tmp_segment_dir / "segment_%Y%m%d_%H%M%S.mp4")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-input_format",
            self.config.video_input_format,
            "-video_size",
            self.config.video_size,
            "-i",
            self.config.video_device,
            "-c:v",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(self.config.segment_seconds),
            "-reset_timestamps",
            "1",
            "-strftime",
            "1",
            pattern,
        ]
        self._ffmpeg_process = subprocess.Popen(cmd)
        threading.Thread(target=self._cleanup_loop, daemon=True).start()

    def stop(self) -> None:
        if self._ffmpeg_process and self._ffmpeg_process.poll() is None:
            self._ffmpeg_process.terminate()
            self._ffmpeg_process.wait(timeout=5)

    def export_event(self, event_time: str) -> Dict[str, object]:
        with self._lock:
            request_time = time.time()
            time.sleep(self.config.post_event_seconds)
            window_start = request_time - self.config.pre_event_seconds - self.config.segment_seconds
            window_end = time.time() + self.config.segment_seconds
            segment_paths = select_segments_by_mtime(list(self.config.tmp_segment_dir.glob("segment_*.mp4")), window_start, window_end)
            if not segment_paths:
                return {
                    "image_status": "failed",
                    "video_status": "failed",
                    "image_path": "",
                    "video_path": "",
                    "frame_paths": [],
                    "frame_status": "failed",
                    "video_error": "no segments available",
                }

            file_token = _timestamp_for_filename(event_time)
            image_path = self.config.evidence_image_dir / f"{file_token}.jpg"
            video_path = self.config.evidence_video_dir / f"{file_token}.mp4"
            gif_path = self.config.evidence_gif_dir / f"{file_token}.gif"
            frame_dir = self.config.evidence_frame_dir / file_token

            image_result = self._extract_snapshot(segment_paths[-1], image_path)
            video_result = self._concat_segments(segment_paths, video_path)
            gif_result = self._create_preview_gif(video_path, gif_path) if video_result else False
            frame_paths = self._extract_key_frames(video_path, frame_dir) if video_result else []
            return {
                "image_status": "saved" if image_result else "failed",
                "video_status": "saved" if video_result else "failed",
                "image_path": str(image_path) if image_result else "",
                "video_path": str(video_path) if video_result else "",
                "gif_path": str(gif_path) if gif_result else "",
                "frame_paths": [str(path) for path in frame_paths],
                "frame_status": "saved" if frame_paths else "failed",
                "video_error": "" if video_result else "ffmpeg concat failed",
            }

    def _extract_snapshot(self, input_path: Path, output_path: Path) -> bool:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            str(output_path),
        ]
        return subprocess.run(cmd, check=False).returncode == 0 and output_path.exists()

    def _concat_segments(self, segment_paths: List[Path], output_path: Path) -> bool:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as manifest:
            for path in segment_paths:
                manifest.write(f"file '{path.as_posix()}'\n")
            manifest_path = Path(manifest.name)

        try:
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest_path),
                "-c:v",
                self.config.evidence_video_codec,
                "-preset",
                self.config.evidence_video_preset,
                "-crf",
                str(self.config.evidence_video_crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            return subprocess.run(cmd, check=False).returncode == 0 and output_path.exists()
        finally:
            manifest_path.unlink(missing_ok=True)

    def _extract_key_frames(self, video_path: Path, frame_dir: Path) -> List[Path]:
        frame_dir.mkdir(parents=True, exist_ok=True)
        duration = self._probe_duration(video_path)
        if duration <= 0:
            timestamps = [0.0] * self.config.key_frame_count
        else:
            max_time = max(duration - 0.2, 0.0)
            if self.config.key_frame_count == 1:
                timestamps = [0.0]
            else:
                step = max_time / float(self.config.key_frame_count - 1) if max_time > 0 else 0.0
                timestamps = [round(step * idx, 2) for idx in range(self.config.key_frame_count)]

        extracted: List[Path] = []
        for idx, timestamp in enumerate(timestamps, start=1):
            output_path = frame_dir / f"frame_{idx:02d}.jpg"
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(output_path),
            ]
            if subprocess.run(cmd, check=False).returncode == 0 and output_path.exists():
                extracted.append(output_path)
        return extracted

    def _create_preview_gif(self, video_path: Path, gif_path: Path) -> bool:
        filter_graph = (
            f"fps={self.config.evidence_gif_fps},"
            f"scale={self.config.evidence_gif_width}:-1:flags=lanczos,"
            "split[s0][s1];"
            "[s0]palettegen=stats_mode=diff[p];"
            "[s1][p]paletteuse=dither=bayer:bayer_scale=3"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-t",
            str(self.config.evidence_gif_seconds),
            "-i",
            str(video_path),
            "-vf",
            filter_graph,
            str(gif_path),
        ]
        return subprocess.run(cmd, check=False).returncode == 0 and gif_path.exists()

    def _probe_duration(self, video_path: Path) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            return 0.0
        try:
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _cleanup_loop(self) -> None:
        retain_seconds = self.config.pre_event_seconds + self.config.post_event_seconds + 10
        while True:
            cutoff = time.time() - retain_seconds
            for path in self.config.tmp_segment_dir.glob("segment_*.mp4"):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                except FileNotFoundError:
                    continue
            time.sleep(2)


def main() -> None:  # pragma: no cover
    config = load_recording_config()
    recorder = SegmentRecorder(config)
    recorder.start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._json({"status": "ok"})
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/export_event":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8"))
            event_time = payload.get("event_time") or datetime.now().astimezone().isoformat(timespec="seconds")
            result = recorder.export_event(event_time)
            self._json(result)

        def log_message(self, format: str, *args) -> None:
            return

        def _json(self, payload: Dict[str, object]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", config.recorder_port), Handler)
    try:
        server.serve_forever()
    finally:
        recorder.stop()
