"""Inference backend protocol and factory."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from katrain.vision.stone_detector import Detection


@runtime_checkable
class InferenceBackend(Protocol):
    """Protocol that all inference backends must implement."""

    def load(self, model_path: str, meta_path: str | None = None) -> None:
        """Load model weights and optional metadata sidecar."""
        ...

    def detect(self, image: np.ndarray, confidence_threshold: float) -> list[Detection]:
        """Run inference and return detections above confidence threshold."""
        ...

    def unload(self) -> None:
        """Release model resources."""
        ...

    @property
    def is_loaded(self) -> bool:
        """Whether a model is currently loaded."""
        ...


def create_backend(backend: str) -> InferenceBackend:
    """Factory function to create an inference backend by name.

    Args:
        backend: One of "onnx", "rknn", "ultralytics".

    Returns:
        An InferenceBackend instance (not yet loaded).
    """
    if backend == "onnx":
        from katrain.vision.inference.onnx_backend import OnnxBackend

        return OnnxBackend()
    elif backend == "rknn":
        from katrain.vision.inference.rknn_backend import RknnBackend

        return RknnBackend()
    elif backend == "ultralytics":
        from katrain.vision.inference.ultralytics_backend import UltralyticsBackend

        return UltralyticsBackend()
    else:
        raise ValueError(f"Unknown inference backend: {backend!r}. Choose from: onnx, rknn, ultralytics")


def letterbox_preprocess(image: np.ndarray, target_size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize image preserving aspect ratio, pad with gray (114) to square.

    Returns:
        (padded_image, scale, x_offset, y_offset)
    """
    h, w = image.shape[:2]
    scale = target_size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
    y_off = (target_size - new_h) // 2
    x_off = (target_size - new_w) // 2
    canvas[y_off : y_off + new_h, x_off : x_off + new_w] = resized
    return canvas, scale, x_off, y_off
