"""Vision service configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VisionServiceConfig:
    """Configuration for the vision service."""

    enabled: bool = False
    backend: str = "onnx"  # "onnx" | "rknn" | "ultralytics"
    model_path: str = ""
    camera_device: int | str = 0
    camera_width: int = 1280
    camera_height: int = 720
    board_size: int = 19
    confidence_threshold: float = 0.5
    imgsz: int = 960
    use_clahe: bool = False
    intrinsics_file: str | None = None  # persistent camera calibration .npz
    process_mode: str = "worker"  # "worker" (subprocess) | "inprocess" (dev)
    capture_fps: int = 8

    def to_worker_config(self) -> dict:
        """Convert to dict for passing to worker process."""
        return {
            "backend": self.backend,
            "model_path": self.model_path,
            "camera_device": self.camera_device,
            "camera_width": self.camera_width,
            "camera_height": self.camera_height,
            "confidence_threshold": self.confidence_threshold,
            "use_clahe": self.use_clahe,
            "capture_fps": self.capture_fps,
        }
