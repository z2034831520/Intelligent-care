from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RecordingConfig:
    video_device: str
    video_input_format: str
    video_size: str
    evidence_video_codec: str
    evidence_video_preset: str
    evidence_video_crf: int
    recorder_port: int
    segment_seconds: int
    pre_event_seconds: int
    post_event_seconds: int
    tmp_segment_dir: Path
    evidence_image_dir: Path
    evidence_video_dir: Path
    evidence_gif_dir: Path
    evidence_frame_dir: Path
    key_frame_count: int
    evidence_gif_fps: int
    evidence_gif_width: int
    evidence_gif_seconds: int


def load_recording_config() -> RecordingConfig:
    return RecordingConfig(
        video_device=os.getenv("VIDEO_DEVICE", "/dev/video0"),
        video_input_format=os.getenv("VIDEO_INPUT_FORMAT", "mjpeg"),
        video_size=os.getenv("VIDEO_SIZE", "1920x1080"),
        evidence_video_codec=os.getenv("EVIDENCE_VIDEO_CODEC", "libx264"),
        evidence_video_preset=os.getenv("EVIDENCE_VIDEO_PRESET", "veryfast"),
        evidence_video_crf=int(os.getenv("EVIDENCE_VIDEO_CRF", "28")),
        recorder_port=int(os.getenv("RECORDER_PORT", "8765")),
        segment_seconds=int(os.getenv("SEGMENT_SECONDS", "1")),
        pre_event_seconds=int(os.getenv("PRE_EVENT_SECONDS", "5")),
        post_event_seconds=int(os.getenv("POST_EVENT_SECONDS", "10")),
        tmp_segment_dir=Path(os.getenv("TMP_SEGMENT_DIR", str(Path.home() / "smart-care-demo" / "tmp" / "segments"))),
        evidence_image_dir=Path(os.getenv("EVIDENCE_IMAGE_DIR", str(Path.home() / "smart-care-demo" / "evidence" / "images"))),
        evidence_video_dir=Path(os.getenv("EVIDENCE_VIDEO_DIR", str(Path.home() / "smart-care-demo" / "evidence" / "videos"))),
        evidence_gif_dir=Path(os.getenv("EVIDENCE_GIF_DIR", str(Path.home() / "smart-care-demo" / "evidence" / "gifs"))),
        evidence_frame_dir=Path(os.getenv("EVIDENCE_FRAME_DIR", str(Path.home() / "smart-care-demo" / "evidence" / "frames"))),
        key_frame_count=int(os.getenv("KEY_FRAME_COUNT", "4")),
        evidence_gif_fps=int(os.getenv("EVIDENCE_GIF_FPS", "8")),
        evidence_gif_width=int(os.getenv("EVIDENCE_GIF_WIDTH", "640")),
        evidence_gif_seconds=int(os.getenv("EVIDENCE_GIF_SECONDS", "5")),
    )
