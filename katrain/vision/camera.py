"""Camera lifecycle manager for Go board visual recognition on SBC devices."""

from __future__ import annotations

import glob
import logging
import os
import sys
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _device_to_capture_arg(device_id: int | str) -> str | int:
    """Convert device ID to the argument for cv2.VideoCapture.

    On Linux with high device numbers (e.g. /dev/video73 for USB cameras on
    Rockchip SBCs), OpenCV's V4L2 backend can't open by integer index.
    Using the path string with CAP_ANY (auto backend selection) works reliably.
    """
    if isinstance(device_id, str):
        return device_id  # Already a path like "/dev/video73"
    if sys.platform == "linux" and device_id > 9:
        return f"/dev/video{device_id}"
    return device_id


def _get_camera_name(device_id: int | str) -> str | None:
    """Read the V4L2 device name from sysfs (Linux only).

    Returns e.g. "USB Camera: USB Camera" or a model-specific string.
    This name is stable across reconnections for the same physical device.
    """
    if sys.platform != "linux":
        return None
    if isinstance(device_id, str):
        dev_num = device_id.replace("/dev/video", "")
    else:
        dev_num = str(device_id)
    try:
        with open(f"/sys/class/video4linux/video{dev_num}/name") as f:
            return f.read().strip()
    except OSError:
        return None


def _find_device_by_name(name: str, original_id: int | str) -> int | None:
    """Scan all /dev/video* devices to find one matching *name*.

    Skips the original device ID (already known to be gone).
    Returns the device number, or None if not found.
    """
    if sys.platform != "linux":
        return None
    orig_num = str(original_id).replace("/dev/video", "")
    for entry in sorted(glob.glob("/sys/class/video4linux/video*")):
        dev_num = entry.rsplit("video", 1)[-1]
        if dev_num == orig_num:
            continue
        try:
            with open(os.path.join(entry, "name")) as f:
                dev_name = f.read().strip()
            if dev_name == name and os.path.exists(f"/dev/video{dev_num}"):
                return int(dev_num)
        except (OSError, ValueError):
            continue
    return None


class CameraManager:
    """Manages a single camera with a background reader thread.

    A dedicated thread continuously reads frames from the camera, ensuring
    that ``read_frame()`` always returns the **latest** frame rather than a
    stale buffered one.  This is critical on SBCs where heavy processing
    (YOLO inference ~600ms) causes OpenCV's internal buffer to fill up.
    """

    RECONNECT_COOLDOWN = 5.0  # seconds between reconnect attempts

    def __init__(self, device_id: int | str = 0, width: int = 1280, height: int = 720, warmup_seconds: float = 2.0) -> None:
        """Initialize with device ID (int) or path (e.g. "/dev/video73")."""
        self._device_id = device_id
        self._capture_arg = _device_to_capture_arg(device_id)
        self._width = width
        self._height = height
        self._warmup_seconds = warmup_seconds
        self._cap: cv2.VideoCapture | None = None
        self._connected = False
        self._last_reconnect_attempt = 0.0
        self._camera_name: str | None = None  # V4L2 device name for reconnection
        # Background reader thread state
        self._reader_thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def is_connected(self) -> bool:
        """Whether the camera is currently open and readable."""
        return self._connected and self._cap is not None and self._cap.isOpened()

    def open(self) -> bool:
        """Open the camera device and start the background reader thread."""
        self.close()
        cap = cv2.VideoCapture(self._capture_arg)
        if cap.isOpened():
            # Use MJPEG to reduce USB bandwidth (critical for USB cameras on SBC)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc_raw = int(cap.get(cv2.CAP_PROP_FOURCC))
            fourcc_str = "".join(chr((fourcc_raw >> (8 * i)) & 0xFF) for i in range(4))
            logger.info(
                "Camera %s opened: %dx%d format=%s (threaded reader)",
                self._device_id, actual_w, actual_h, fourcc_str,
            )

            # Record V4L2 device name for reconnection after device renumbering
            if self._camera_name is None:
                self._camera_name = _get_camera_name(self._device_id)
                if self._camera_name:
                    logger.info("Camera identity recorded: %r", self._camera_name)

            # Enable auto-focus if supported
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)

            # Drain frames to let auto-focus and auto-exposure settle
            if self._warmup_seconds > 0:
                deadline = time.monotonic() + self._warmup_seconds
                while time.monotonic() < deadline:
                    cap.read()
                logger.info("Camera %s focus stabilized (%.1fs warmup)", self._device_id, self._warmup_seconds)

            self._cap = cap
            self._connected = True

            # Start background reader thread
            self._stop_event.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True, name="cam-reader"
            )
            self._reader_thread.start()
            return True
        cap.release()
        logger.warning("Failed to open camera %s", self._device_id)
        return False

    def close(self) -> None:
        """Stop the reader thread and release the camera device."""
        self._stop_event.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)
            self._reader_thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            self._connected = False
            with self._frame_lock:
                self._latest_frame = None
            logger.info("Camera %s closed", self._device_id)

    def read_frame(self) -> np.ndarray | None:
        """Return the latest frame captured by the background thread.

        Always returns the freshest available frame, never a stale buffered
        one.  Returns None if the camera is disconnected.
        """
        if not self._connected:
            return self._try_reconnect()

        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    # ------------------------------------------------------------------
    # Background reader
    # ------------------------------------------------------------------

    def _reader_loop(self) -> None:
        """Continuously read frames in background, keeping only the latest."""
        while not self._stop_event.is_set():
            try:
                ret, frame = self._cap.read()  # type: ignore[union-attr]
            except cv2.error as exc:
                logger.warning("Camera %s read error: %s", self._device_id, exc)
                self._mark_disconnected()
                return

            if not ret or frame is None:
                logger.warning("Camera %s returned empty frame", self._device_id)
                self._mark_disconnected()
                return

            with self._frame_lock:
                self._latest_frame = frame

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _mark_disconnected(self) -> None:
        self._connected = False
        logger.warning("Camera %s marked as disconnected", self._device_id)

    def _try_reconnect(self) -> np.ndarray | None:
        """Attempt reconnect after cooldown. Returns a frame on success, else None.

        If the original device path no longer exists (USB renumbering after
        physical disconnect/reconnect), scans all video devices by the V4L2
        device name recorded on first connection.
        """
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self.RECONNECT_COOLDOWN:
            return None

        self._last_reconnect_attempt = now
        logger.info("Attempting to reconnect camera %s ...", self._device_id)

        # Try the original device path first
        if self.open():
            logger.info("Camera %s reconnected", self._device_id)
            return self.read_frame()

        # Original path failed — scan by device name (handles USB renumbering)
        if self._camera_name:
            new_id = _find_device_by_name(self._camera_name, self._device_id)
            if new_id is not None:
                logger.info(
                    "Camera %r found at new device /dev/video%d (was %s)",
                    self._camera_name, new_id, self._device_id,
                )
                self._device_id = new_id
                self._capture_arg = _device_to_capture_arg(new_id)
                if self.open():
                    logger.info("Camera reconnected at /dev/video%d", new_id)
                    return self.read_frame()

        logger.warning("Camera %s reconnect failed, will retry in %.0fs", self._device_id, self.RECONNECT_COOLDOWN)
        return None

    # ------------------------------------------------------------------
    # Static utilities
    # ------------------------------------------------------------------

    @staticmethod
    def detect_cameras(max_id: int = 4) -> list[int]:
        """Probe /dev/video0..max_id to find available cameras."""
        available: list[int] = []
        for dev_id in range(max_id + 1):
            cap = cv2.VideoCapture(_device_to_capture_arg(dev_id))
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
