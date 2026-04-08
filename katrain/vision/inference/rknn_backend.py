"""RKNN NPU inference backend for YOLO v8/v11 stone detection.

Uses rknn-toolkit-lite2 to run .rknn models on Rockchip NPU hardware
(RK3576, RK3588, RK3562, etc.).  Requires ``librknnrt.so`` on the system
and the ``rknn-toolkit-lite2`` Python package matching the runtime version.
"""

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


class RknnBackend:
    """RKNN NPU backend for YOLO v8/v11 stone detection models.

    Expects a ``.rknn`` model file and a metadata sidecar ``{model_stem}.meta.json``
    describing input/output layout for pre- and post-processing.
    """

    NMS_IOU_THRESHOLD = 0.5  # agnostic NMS, same as ultralytics default

    def __init__(self) -> None:
        self._rknn = None  # RKNNLite instance once loaded
        self._meta: dict[str, Any] = {}
        self._last_scale: float = 1.0
        self._last_x_off: int = 0
        self._last_y_off: int = 0

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def load(self, model_path: str, meta_path: str | None = None) -> None:
        """Load an RKNN model and its metadata sidecar.

        Args:
            model_path: Path to the ``.rknn`` model file.
            meta_path: Path to the JSON sidecar.  When *None*, the sidecar is
                auto-discovered as ``{model_stem}.meta.json`` next to the model.
        """
        model = Path(model_path)
        if not model.is_file():
            raise FileNotFoundError(f"RKNN model not found: {model}")

        if meta_path is None:
            meta_file = model.with_suffix(".meta.json")
        else:
            meta_file = Path(meta_path)

        if not meta_file.is_file():
            raise FileNotFoundError(
                f"Model metadata sidecar not found: {meta_file}. "
                "Export one with `python -m katrain.vision.tools.export_rknn` or create it manually."
            )

        with open(meta_file, "r") as f:
            self._meta = json.load(f)

        try:
            from rknnlite.api import RKNNLite
        except ImportError as exc:
            raise ImportError(
                "rknn-toolkit-lite2 is required for the RKNN backend. "
                "Install with: pip install rknn-toolkit-lite2"
            ) from exc

        logger.info("Loading RKNN model %s (source=%s, imgsz=%d)", model.name, self._meta.get("source"), self.imgsz)

        rknn = RKNNLite()
        ret = rknn.load_rknn(str(model))
        if ret != 0:
            raise RuntimeError(f"Failed to load RKNN model: {model} (error code: {ret})")

        ret = rknn.init_runtime()
        if ret != 0:
            rknn.release()
            raise RuntimeError(f"Failed to init RKNN runtime (error code: {ret})")

        self._rknn = rknn
        logger.info("RKNN model loaded successfully")

    def detect(self, image: np.ndarray, confidence_threshold: float) -> list[Detection]:
        """Run detection on a BGR image and return filtered detections.

        Args:
            image: Input image in BGR channel order (OpenCV default).
            confidence_threshold: Minimum class score to keep a detection.

        Returns:
            List of :class:`Detection` objects in the original image coordinate space.
        """
        if self._rknn is None:
            raise RuntimeError("Model is not loaded. Call load() first.")

        orig_h, orig_w = image.shape[:2]

        # --- pre-process ---
        tensor = self._preprocess(image)

        # --- inference ---
        outputs = self._rknn.inference(inputs=[tensor])
        if outputs is None:
            logger.warning("RKNN inference returned None")
            return []

        # --- post-process ---
        return self._postprocess(outputs[0], orig_w, orig_h, confidence_threshold)

    def unload(self) -> None:
        """Release the RKNN runtime."""
        if self._rknn is not None:
            self._rknn.release()
            self._rknn = None
        self._meta = {}

    @property
    def is_loaded(self) -> bool:
        """Whether a model is currently loaded."""
        return self._rknn is not None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def imgsz(self) -> int:
        return int(self._meta.get("imgsz", 640))

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Letterbox-resize and prepare image for RKNN inference.

        RKNN models converted with mean/std normalization baked in expect
        NHWC uint8 input.  Models without baked-in normalization expect the
        same NCHW float32 as the ONNX backend.  Controlled by ``input_format``
        in the metadata sidecar (default: ``nhwc_uint8``).
        """
        size = self.imgsz
        resized, scale, x_off, y_off = letterbox_preprocess(image, size)
        self._last_scale = scale
        self._last_x_off = x_off
        self._last_y_off = y_off

        # BGR -> RGB when required by the model
        if self._meta.get("input_channel_order", "RGB") == "RGB":
            resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        input_format = self._meta.get("input_format", "nhwc_uint8")

        if input_format == "nchw_float32":
            # Same layout as ONNX: CHW float32 normalized 0-1
            tensor = resized.transpose(2, 0, 1).astype(np.float32)
            if self._meta.get("input_normalize", "0-1") == "0-1":
                tensor /= 255.0
            return tensor[np.newaxis, ...]
        else:
            # Default RKNN layout: NHWC uint8 (normalization baked into model)
            return resized[np.newaxis, ...].astype(np.uint8)

    def _postprocess(
        self,
        raw_output: np.ndarray,
        orig_w: int,
        orig_h: int,
        confidence_threshold: float,
    ) -> list[Detection]:
        """Decode YOLO v8/v11 raw output tensor into :class:`Detection` objects.

        Same decoding as :class:`OnnxBackend` -- raw tensor shape
        ``(1, num_classes+4, num_detections)``.  Each detection row after
        transposing to ``(num_detections, num_classes+4)`` is::

            [cx, cy, w, h, class0_score, class1_score, ...]

        where ``cx/cy/w/h`` are in *pixel* coordinates relative to ``imgsz``.
        """
        # Ensure float32 for consistent math (RKNN may return FP16)
        raw_output = raw_output.astype(np.float32)

        # (1, 4+C, N) -> (N, 4+C)
        if raw_output.ndim == 3:
            predictions = raw_output[0].T
        else:
            predictions = raw_output.T

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
