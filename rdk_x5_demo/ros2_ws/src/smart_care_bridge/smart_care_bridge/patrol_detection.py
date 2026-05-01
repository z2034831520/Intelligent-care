from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .detection_parsing import extract_detection_candidates, resolve_perception_targets_type
from .models import DetectionCandidate


@dataclass
class DetectionResult:
    candidates: List[DetectionCandidate]

    @property
    def target_detected(self) -> bool:
        return bool(self.candidates)

    @property
    def best_confidence(self) -> float:
        if not self.candidates:
            return 0.0
        return max(item.score for item in self.candidates)


class PatrolDetector:
    def __init__(
        self,
        mode: str,
        command: str,
        person_labels: List[str],
        topic: str,
        timeout_seconds: int,
        setup_script: str,
    ) -> None:
        self.mode = mode
        self.command = command
        self.person_labels = {item.lower() for item in person_labels}
        self.topic = topic
        self.timeout_seconds = timeout_seconds
        self.setup_script = setup_script

    def detect(self, image_path: Path) -> DetectionResult:
        if self.mode == "mock":
            return DetectionResult([])
        if self.mode == "rdk_x5_ros2_image":
            return self._detect_with_rdk_x5_ros2_image(image_path)
        if self.mode == "json_command":
            return self._detect_with_command(image_path)
        raise RuntimeError(f"unsupported DETECTOR_MODE: {self.mode}")

    def _detect_with_command(self, image_path: Path) -> DetectionResult:
        if not self.command:
            raise RuntimeError("DETECTOR_COMMAND is empty")
        result = subprocess.run(
            self.command.format(image_path=str(image_path)),
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "detector command failed")
        payload = json.loads(result.stdout)
        candidates = []
        for item in payload.get("candidates", []):
            label = str(item.get("label", "")).lower()
            score = float(item.get("score", 0.0))
            bbox = [int(v) for v in item.get("bbox", [0, 0, 0, 0])]
            if label in self.person_labels:
                candidates.append(DetectionCandidate(label=label, score=score, bbox=bbox))
        return DetectionResult(candidates)

    def _detect_with_rdk_x5_ros2_image(self, image_path: Path) -> DetectionResult:
        if not image_path.exists():
            raise RuntimeError(f"image not found: {image_path}")

        try:
            import rclpy
            from rclpy.node import Node
        except Exception as exc:  # pragma: no cover - only exercised on RDK target
            raise RuntimeError(
                "rclpy is unavailable. Source /opt/tros/humble/setup.bash and run this detector on the RDK X5."
            ) from exc

        perception_targets_type = resolve_perception_targets_type()
        initialized_here = False
        if not rclpy.ok():
            rclpy.init(args=None)
            initialized_here = True

        node = Node("patrol_detector_once")
        captured: dict[str, object] = {}

        def _callback(message: object) -> None:
            captured["message"] = message

        node.create_subscription(
            perception_targets_type,
            self.topic,
            _callback,
            10,
        )

        launch_process = self._start_rdk_x5_launch(image_path)
        deadline = time.monotonic() + float(self.timeout_seconds)
        try:
            while time.monotonic() < deadline:
                if "message" in captured:
                    candidates = self._filter_person_candidates(
                        extract_detection_candidates(captured["message"])
                    )
                    return DetectionResult(candidates)

                if launch_process.poll() is not None:
                    raise RuntimeError(
                        "RDK detector process exited before publishing a result. "
                        f"stderr: {self._read_stderr(launch_process)}"
                    )

                rclpy.spin_once(node, timeout_sec=0.2)

            raise TimeoutError(
                f"Timed out after {self.timeout_seconds}s waiting for detector topic {self.topic}"
            )
        finally:
            node.destroy_node()
            if initialized_here and rclpy.ok():
                rclpy.shutdown()
            self._stop_process(launch_process)

    def _filter_person_candidates(self, candidates: List[DetectionCandidate]) -> List[DetectionCandidate]:
        return [item for item in candidates if item.label.lower() in self.person_labels]

    def _start_rdk_x5_launch(self, image_path: Path) -> subprocess.Popen:
        image_arg = shlex.quote(str(image_path))
        launch_command = (
            f"source {shlex.quote(self.setup_script)} && "
            "export CAM_TYPE=fb && "
            "ros2 launch mono2d_body_detection mono2d_body_detection.launch.py "
            f"publish_image_source:={image_arg} "
            "publish_image_format:=jpg "
            "publish_output_image_w:=960 "
            "publish_output_image_h:=544"
        )
        return subprocess.Popen(
            ["bash", "-lc", launch_command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=(os.name != "nt"),
        )

    def _stop_process(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return

        try:
            if os.name == "nt":  # pragma: no cover - RDK target is Linux
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except Exception:
            try:
                if os.name == "nt":  # pragma: no cover - RDK target is Linux
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            except Exception:
                pass

    def _read_stderr(self, process: subprocess.Popen) -> str:
        if process.stderr is None:
            return ""
        try:
            return process.stderr.read().strip()
        except Exception:
            return ""
