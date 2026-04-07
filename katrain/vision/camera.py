"""Camera lifecycle manager for Go board visual recognition on SBC devices."""

from __future__ import annotations

import logging
import sys
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Use V4L2 backend on Linux (typical for SBC like RK3588), default elsewhere.
_BACKEND = cv2.CAP_V4L2 if sys.platform == "linux" else cv2.CAP_ANY


class CameraManager:
    """Manages a single V4L2 camera with hot-plug robustness and auto-reconnect."""

    RECONNECT_COOLDOWN = 5.0  # seconds between reconnect attempts

    def __init__(self, device_id: int = 0) -> None:
        """Initialize with V4L2 device ID (e.g., 0 for /dev/video0)."""
        self._device_id = device_id
        self._cap: cv2.VideoCapture | None = None
        self._connected = False
        self._last_reconnect_attempt = 0.0

    @property
    def is_connected(self) -> bool:
        """Whether the camera is currently open and readable."""
        return self._connected and self._cap is not None and self._cap.isOpened()

    def open(self) -> bool:
        """Open the camera device. Returns True on success.

        Applies latency-reduction settings:
        - MJPEG format (less USB bandwidth than raw YUYV)
        - 640x480 resolution (sufficient for stone detection)
        - Minimal buffer (1 frame) to avoid stale-frame latency
        """
        self.close()
        cap = cv2.VideoCapture(self._device_id, _BACKEND)
        if cap.isOpened():
            # Use MJPEG to reduce USB bandwidth (critical for USB cameras on SBC)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            # 640x480 is sufficient for board detection; 2K is wasteful on SBC
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            # Minimize internal buffer to reduce latency (only keep latest frame)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc_raw = int(cap.get(cv2.CAP_PROP_FOURCC))
            fourcc_str = "".join(chr((fourcc_raw >> (8 * i)) & 0xFF) for i in range(4))
            logger.info(
                "Camera %d opened: %dx%d format=%s", self._device_id, actual_w, actual_h, fourcc_str
            )

            self._cap = cap
            self._connected = True
            return True
        cap.release()
        logger.warning("Failed to open camera %d", self._device_id)
        return False

    def close(self) -> None:
        """Release the camera device."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._connected = False
            logger.info("Camera %d closed", self._device_id)

    def read_frame(self) -> np.ndarray | None:
        """Read a single frame. Returns None if camera is disconnected.

        Hot-plug robustness: catches cv2 exceptions on device disconnect.
        When disconnected, attempts auto-reconnect every 5 seconds.
        Does NOT crash -- emits a log warning and returns None.
        """
        if not self._connected:
            return self._try_reconnect()

        try:
            ret, frame = self._cap.read()  # type: ignore[union-attr]
        except cv2.error as exc:
            logger.warning("Camera %d read error: %s", self._device_id, exc)
            self._mark_disconnected()
            return None

        if not ret or frame is None:
            logger.warning("Camera %d returned empty frame -- device may be disconnected", self._device_id)
            self._mark_disconnected()
            return None

        return frame

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _mark_disconnected(self) -> None:
        self._connected = False
        logger.warning("Camera %d marked as disconnected", self._device_id)

    def _try_reconnect(self) -> np.ndarray | None:
        """Attempt reconnect after cooldown. Returns a frame on success, else None."""
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self.RECONNECT_COOLDOWN:
            return None

        self._last_reconnect_attempt = now
        logger.info("Attempting to reconnect camera %d ...", self._device_id)

        if self.open():
            logger.info("Camera %d reconnected", self._device_id)
            return self.read_frame()

        logger.warning("Camera %d reconnect failed, will retry in %.0fs", self._device_id, self.RECONNECT_COOLDOWN)
        return None

    # ------------------------------------------------------------------
    # Static utilities
    # ------------------------------------------------------------------

    @staticmethod
    def detect_cameras(max_id: int = 4) -> list[int]:
        """Probe /dev/video0..max_id to find available cameras."""
        available: list[int] = []
        for dev_id in range(max_id + 1):
            cap = cv2.VideoCapture(dev_id, _BACKEND)
            if cap.isOpened():
                available.append(dev_id)
            cap.release()
        logger.info("Detected cameras: %s", available)
        return available

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> CameraManager:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"CameraManager(device_id={self._device_id}, {status})"
