from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from .recording_config import RecordingConfig


class PatrolCapture:
    def __init__(self, config: RecordingConfig) -> None:
        self.config = config
        self.config.evidence_image_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_video_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_gif_dir.mkdir(parents=True, exist_ok=True)
        self.config.evidence_frame_dir.mkdir(parents=True, exist_ok=True)

    def capture_snapshot_and_video(self, file_token: str) -> tuple[Path, Path]:
        image_path = self.config.evidence_image_dir / f"{file_token}.jpg"
        video_path = self.config.evidence_video_dir / f"{file_token}.mp4"

        self._capture_image(image_path)
        self._capture_video(video_path)
        return image_path, video_path

    def extract_key_frames(self, video_path: Path, frame_token: str) -> List[Path]:
        frame_dir = self.config.evidence_frame_dir / frame_token
        frame_dir.mkdir(parents=True, exist_ok=True)
        duration = self._probe_duration(video_path)
        count = self.config.key_frame_count
        if duration <= 0:
            timestamps = [0.0] * count
        else:
            max_time = max(duration - 0.2, 0.0)
            step = max_time / float(max(count - 1, 1))
            timestamps = [round(step * idx, 2) for idx in range(count)]

        frames: List[Path] = []
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
                frames.append(output_path)
        return frames

    def create_preview_gif(self, video_path: Path, file_token: str) -> Path | None:
        gif_path = self.config.evidence_gif_dir / f"{file_token}.gif"
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
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0 or not gif_path.exists():
            return None
        return gif_path

    def _capture_image(self, image_path: Path) -> None:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "v4l2",
            "-input_format",
            self.config.video_input_format,
            "-video_size",
            self.config.video_size,
            "-i",
            self.config.video_device,
            "-frames:v",
            "1",
            str(image_path),
        ]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0 or not image_path.exists():
            raise RuntimeError(f"failed to capture snapshot: {result.stderr.strip()}")

    def _capture_video(self, video_path: Path) -> None:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "v4l2",
            "-input_format",
            self.config.video_input_format,
            "-video_size",
            self.config.video_size,
            "-i",
            self.config.video_device,
            "-t",
            str(self.config.pre_event_seconds),
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
            str(video_path),
        ]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0 or not video_path.exists():
            raise RuntimeError(f"failed to capture patrol video: {result.stderr.strip()}")

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
