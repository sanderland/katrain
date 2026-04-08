"""ONNX Runtime inference backend for YOLO v8/v11 stone detection."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from katrain.vision.inference.base import letterbox_preprocess
from katrain.vision.stone_detector import Detection

logger = logging.getLogger(__name__)


class OnnxBackend:
    """ONNX Runtime backend for YOLO v8/v11 stone detection models.

    Expects a model sidecar ``{model_stem}.meta.json`` describing input/output
    layout so that pre- and post-processing can be driven generically.
    """

    NMS_IOU_THRESHOLD = 0.5  # agnostic NMS, same as ultralytics default

    def __init__(self) -> None:
        self._session = None  # ort.InferenceSession once loaded
        self._meta: dict[str, Any] = {}
        self._last_scale: float = 1.0
        self._last_x_off: int = 0
        self._last_y_off: int = 0

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def load(self, model_path: str, meta_path: str | None = None) -> None:
        """Load an ONNX model and its metadata sidecar.

        Args:
            model_path: Path to the ``.onnx`` model file.
            meta_path: Path to the JSON sidecar.  When *None*, the sidecar is
                auto-discovered as ``{model_stem}.meta.json`` next to the model.

        Raises:
            FileNotFoundError: If model or meta file does not exist.
            ValueError: If the meta file cannot be parsed.
        """
        model = Path(model_path)
        if not model.is_file():
            raise FileNotFoundError(f"ONNX model not found: {model}")

        if meta_path is None:
            meta_file = model.with_suffix(".meta.json")
        else:
            meta_file = Path(meta_path)

        if not meta_file.is_file():
            raise FileNotFoundError(
                f"Model metadata sidecar not found: {meta_file}. "
                "Export one with `python -m katrain.vision.tools.export_onnx` or create it manually."
            )

        with open(meta_file, "r") as f:
            self._meta = json.load(f)

        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ImportError(
                "onnxruntime is required for the ONNX backend. Install with: pip install onnxruntime"
            ) from exc

        logger.info("Loading ONNX model %s (source=%s, imgsz=%d)", model.name, self._meta.get("source"), self.imgsz)

        self._session = ort.InferenceSession(
            str(model),
            providers=["CPUExecutionProvider"],
        )

    def detect(self, image: np.ndarray, confidence_threshold: float) -> list[Detection]:
        """Run detection on a BGR image and return filtered detections.

        Args:
            image: Input image in BGR channel order (OpenCV default).
            confidence_threshold: Minimum class score to keep a detection.

        Returns:
            List of :class:`Detection` objects in the original image coordinate space.
        """
        if self._session is None:
            raise RuntimeError("Model is not loaded. Call load() first.")

        orig_h, orig_w = image.shape[:2]

        # --- pre-process ---
        tensor = self._preprocess(image)

        # --- inference ---
        input_name = self._meta.get("input_name", "images")
        output_name = self._meta.get("output_name", "output0")
        (raw_output,) = self._session.run([output_name], {input_name: tensor})

        # --- post-process ---
        return self._postprocess(raw_output, orig_w, orig_h, confidence_threshold)

    def unload(self) -> None:
        """Release the ONNX Runtime session."""
        self._session = None
        self._meta = {}

    @property
    def is_loaded(self) -> bool:
        """Whether a model session is currently active."""
        return self._session is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def imgsz(self) -> int:
        return int(self._meta.get("imgsz", 640))

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Letterbox-resize, normalise, and convert a BGR image to an NCHW float32 tensor."""
        size = self.imgsz
        resized, scale, x_off, y_off = letterbox_preprocess(image, size)
        self._last_scale = scale
        self._last_x_off = x_off
        self._last_y_off = y_off

        # BGR -> RGB when required by the model
        if self._meta.get("input_channel_order", "RGB") == "RGB":
            resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # HWC -> CHW
        tensor = resized.transpose(2, 0, 1).astype(np.float32)

        # Normalise
        if self._meta.get("input_normalize", "0-1") == "0-1":
            tensor /= 255.0

        # Add batch dimension -> NCHW
        return tensor[np.newaxis, ...]

    def _postprocess(
        self,
        raw_output: np.ndarray,
        orig_w: int,
        orig_h: int,
        confidence_threshold: float,
    ) -> list[Detection]:
        """Decode YOLO v8/v11 raw output tensor into :class:`Detection` objects.

        The raw tensor has shape ``(1, num_classes+4, num_detections)``.  After
        transposing to ``(num_detections, num_classes+4)`` each row is::

            [cx, cy, w, h, class0_score, class1_score, ...]

        where ``cx/cy/w/h`` are in *pixel* coordinates relative to ``imgsz``.
        """
        # (1, 4+C, N) -> (N, 4+C)
        predictions = raw_output[0].T

        num_classes = len(self._meta.get("classes", ["black", "white"]))
        boxes_xywh = predictions[:, :4]  # cx, cy, w, h in imgsz pixel space
        class_scores = predictions[:, 4 : 4 + num_classes]

        # Per-detection best class
        class_ids = class_scores.argmax(axis=1)
        confidences = class_scores.max(axis=1)

        # Confidence filter
        mask = confidences >= confidence_threshold
        boxes_xywh = boxes_xywh[mask]
        class_ids = class_ids[mask]
        confidences = confidences[mask]

        if len(boxes_xywh) == 0:
            return []

        # --- NMS via OpenCV (expects top-left x, y, w, h) ---
        # Convert centre-format to top-left-format for cv2.dnn.NMSBoxes
        tl_boxes = boxes_xywh.copy()
        tl_boxes[:, 0] -= tl_boxes[:, 2] / 2  # x_topleft = cx - w/2
        tl_boxes[:, 1] -= tl_boxes[:, 3] / 2  # y_topleft = cy - h/2

        indices = cv2.dnn.NMSBoxes(
            bboxes=tl_boxes.tolist(),
            scores=confidences.tolist(),
            score_threshold=confidence_threshold,
            nms_threshold=self.NMS_IOU_THRESHOLD,
        )

        if len(indices) == 0:
            return []

        # Flatten indices (OpenCV may return column vector or flat list)
        indices = np.asarray(indices).flatten()

        detections: list[Detection] = []
        for idx in indices:
            cx, cy, w, h = boxes_xywh[idx]
            # Map from model space -> original image space via letterbox
            cx_orig = float((cx - self._last_x_off) / self._last_scale)
            cy_orig = float((cy - self._last_y_off) / self._last_scale)
            w_orig = float(w / self._last_scale)
            h_orig = float(h / self._last_scale)

            x1 = cx_orig - w_orig / 2
            y1 = cy_orig - h_orig / 2
            x2 = cx_orig + w_orig / 2
            y2 = cy_orig + h_orig / 2

            detections.append(
                Detection(
                    x_center=cx_orig,
                    y_center=cy_orig,
                    class_id=int(class_ids[idx]),
                    confidence=float(confidences[idx]),
                    bbox=(x1, y1, x2, y2),
                )
            )

        return detections
