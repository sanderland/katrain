"""Vision worker process — runs camera capture, inference, and sync in isolation.

On SBC this runs as a separate process to isolate vision memory from
FastAPI/Chromium. On dev machines an in-process adapter is used instead
(see worker_inprocess.py).

Architecture:
  - CameraManager: background thread continuously reads camera, holds latest frame
  - Preview thread: reads latest frame at high FPS, encodes JPEG → preview_queue
  - Processing thread (main loop): reads latest frame, runs board finder + YOLO,
    sends sync events — completely independent of preview
"""

from __future__ import annotations

import copy
import logging
import multiprocessing as mp
import queue
import threading
import time
from dataclasses import dataclass, field
from multiprocessing import Queue
from typing import Any

import cv2
import numpy as np

from katrain.vision.board_state import BoardStateExtractor
from katrain.vision.camera import CameraManager
from katrain.vision.config import BoardConfig, CameraConfig
from katrain.vision.ipc import CommandType, ConfirmedMove, WorkerCommand, WorkerStatus
from katrain.vision.motion_filter import MotionFilter
from katrain.vision.move_detector import MoveDetector
from katrain.vision.sync import SyncState, SyncStateMachine

logger = logging.getLogger(__name__)

# Preview frame settings
PREVIEW_SIZE = 480
PREVIEW_FPS = 15
JPEG_QUALITY = 60


@dataclass
class ProcessingOverlay:
    """Shared state between processing thread and preview thread."""

    board_corners: list[tuple[int, int]] | None = None  # 4 corners in raw frame coords
    detections: list | None = None  # YOLO Detection results
    warped_size: tuple[int, int] | None = None  # (w, h) of warped board
    transform_matrix: np.ndarray | None = None  # perspective transform M
    timing: dict[str, float] = field(default_factory=dict)  # ms timings


def _run_worker(
    cmd_queue: Queue,
    event_queue: Queue,
    status_queue: Queue,
    preview_queue: Queue,
    config: dict[str, Any],
) -> None:
    """Entry point for the worker process. Runs the main loop until SHUTDOWN."""
    logging.basicConfig(level=logging.INFO, format="[vision-worker] %(levelname)s %(message)s")
    w = _VisionWorkerLoop(cmd_queue, event_queue, status_queue, preview_queue, config)
    w.run()


class _VisionWorkerLoop:
    """Internal class encapsulating the worker main loop."""

    def __init__(
        self,
        cmd_queue: Queue,
        event_queue: Queue,
        status_queue: Queue,
        preview_queue: Queue,
        config: dict[str, Any],
    ):
        self._cmd_queue = cmd_queue
        self._event_queue = event_queue
        self._status_queue = status_queue
        self._preview_queue = preview_queue
        self._config = config

        self._running = False
        self._viewer_active = False
        self._bound = False

        # Initialise components
        board_config = BoardConfig()
        camera_config = CameraConfig()

        self._camera = CameraManager(
            device_id=config.get("camera_device", 0),
            width=config.get("camera_width", 1280),
            height=config.get("camera_height", 720),
        )
        self._motion_filter = MotionFilter()
        self._state_extractor = BoardStateExtractor(board_config)
        self._move_detector = MoveDetector()
        self._sync = SyncStateMachine()

        # Inference backend — lazy import so the heavy deps only load in the worker process
        self._detector = None
        self._board_finder = None

        self._last_status_time = 0.0

    def _init_inference(self) -> None:
        """Load inference backend and board finder (heavy imports)."""
        from katrain.vision.board_finder import BoardFinder
        from katrain.vision.stone_detector import StoneDetector

        backend = self._config.get("backend", "onnx")
        model_path = self._config.get("model_path", "")
        confidence = self._config.get("confidence_threshold", 0.5)

        logger.info("Loading inference backend=%s model=%s", backend, model_path)
        self._detector = StoneDetector(model_path, backend=backend, confidence_threshold=confidence)
        self._board_finder = BoardFinder(camera_config=CameraConfig())
        logger.info("Inference backend ready")

    def run(self) -> None:
        """Start preview thread + processing loop, then clean up."""
        self._running = True

        # Open camera
        if not self._camera.open():
            logger.error("Failed to open camera, will keep retrying")

        # Load inference backend
        try:
            self._init_inference()
        except Exception as e:
            logger.error("Failed to load inference backend: %s", e)
            self._running = False
            return

        # Shared overlay state (lock-protected)
        self._overlay = ProcessingOverlay()
        self._overlay_lock = threading.Lock()

        # Start independent preview thread
        preview_thread = threading.Thread(target=self._preview_loop, daemon=True, name="preview")
        preview_thread.start()

        # Main thread runs the processing loop (board detection + YOLO)
        self._processing_loop()

        self._camera.close()
        logger.info("Worker process exiting")

    def _processing_loop(self) -> None:
        """Processing loop: board detection + YOLO inference.
        Results written to shared overlay state for preview thread to consume."""
        while self._running:
            self._process_commands()

            frame = self._camera.read_frame()
            board_detected = False
            observed_board = None
            mean_confidence = 0.0

            if frame is not None and self._motion_filter.is_stable(frame):
                # Board detection + perspective transform
                t0 = time.monotonic()
                warped, found = self._board_finder.find_focus(
                    frame, min_threshold=20, use_clahe=self._config.get("use_clahe", False)
                )
                board_finder_ms = (time.monotonic() - t0) * 1000

                if found and warped is not None:
                    board_detected = True
                    h, w = warped.shape[:2]

                    # YOLO inference (heavy — 600ms+ on SBC CPU)
                    t1 = time.monotonic()
                    detections = self._detector.detect(warped)
                    yolo_ms = (time.monotonic() - t1) * 1000

                    total_ms = board_finder_ms + yolo_ms

                    # Update shared overlay state for preview thread
                    with self._overlay_lock:
                        self._overlay.board_corners = list(self._board_finder.pre_corner_point)
                        self._overlay.detections = detections
                        self._overlay.warped_size = (w, h)
                        self._overlay.transform_matrix = self._board_finder.last_transform_matrix
                        self._overlay.timing = {
                            "board_finder_ms": round(board_finder_ms, 1),
                            "yolo_ms": round(yolo_ms, 1),
                            "total_ms": round(total_ms, 1),
                        }

                    # Board state + move detection
                    observed_board = self._state_extractor.detections_to_board(detections, img_w=w, img_h=h)
                    if detections:
                        mean_confidence = sum(d.confidence for d in detections) / len(detections)
                    if self._bound:
                        move_result = self._move_detector.detect_new_move(observed_board)
                        if move_result is not None:
                            row, col, color = move_result
                            self._event_queue.put(ConfirmedMove(col=col, row=row, color=color))

            # Sync state machine update
            if self._bound:
                events = self._sync.update(
                    observed_board=observed_board,
                    mean_confidence=mean_confidence,
                    board_detected=board_detected,
                )
                for evt in events:
                    self._event_queue.put({"type": evt.type.value, "data": evt.data})

            self._maybe_publish_status()
            # No throttle — processing runs as fast as inference allows

    def _process_commands(self) -> None:
        """Drain the command queue (non-blocking)."""
        while True:
            try:
                cmd: WorkerCommand = self._cmd_queue.get_nowait()
            except queue.Empty:
                break

            if cmd.action == CommandType.SHUTDOWN:
                self._running = False
            elif cmd.action == CommandType.BIND:
                self._bound = True
                self._sync.bind()
            elif cmd.action == CommandType.UNBIND:
                self._bound = False
                self._sync = SyncStateMachine()  # Reset
            elif cmd.action == CommandType.CONFIRM_POSE_LOCK:
                self._sync.confirm_pose_lock()
            elif cmd.action == CommandType.SET_EXPECTED_BOARD:
                board = np.array(cmd.data["board"], dtype=int)
                self._sync.set_expected_board(board)
                self._move_detector.force_sync(board)
            elif cmd.action == CommandType.ENTER_SETUP_MODE:
                target = np.array(cmd.data["target_board"], dtype=int)
                self._sync.enter_setup_mode(target)
            elif cmd.action == CommandType.RESET_SYNC:
                self._sync.reset()
            elif cmd.action == CommandType.SET_VIEWER_ACTIVE:
                self._viewer_active = cmd.data.get("active", False)

    def _draw_overlays(self, frame: np.ndarray, overlay: ProcessingOverlay) -> None:
        """Draw detection results and timing info on the raw camera frame."""
        h, w = frame.shape[:2]

        # 1. Board boundary (green quadrilateral)
        if overlay.board_corners:
            corners = np.array(overlay.board_corners, dtype=np.int32)
            cv2.polylines(frame, [corners.reshape((-1, 1, 2))], True, (0, 255, 0), 2)

        # 2. Stones back-projected from warped coords to raw frame
        if overlay.detections and overlay.transform_matrix is not None and overlay.warped_size:
            try:
                M_inv = np.linalg.inv(overlay.transform_matrix)
            except np.linalg.LinAlgError:
                M_inv = None
            if M_inv is not None:
                for det in overlay.detections:
                    pt = np.float32([[det.x_center, det.y_center]]).reshape(-1, 1, 2)
                    orig_pt = cv2.perspectiveTransform(pt, M_inv)
                    ox, oy = int(orig_pt[0, 0, 0]), int(orig_pt[0, 0, 1])
                    color = (0, 0, 0) if det.class_id == 0 else (255, 255, 255)
                    cv2.circle(frame, (ox, oy), 8, color, -1)
                    cv2.circle(frame, (ox, oy), 8, (0, 255, 0), 1)

        # 3. Timing info (bottom-left with black background)
        if overlay.timing:
            lines = [
                f"Board: {overlay.timing.get('board_finder_ms', 0):.0f}ms",
                f"YOLO:  {overlay.timing.get('yolo_ms', 0):.0f}ms",
                f"Total: {overlay.timing.get('total_ms', 0):.0f}ms",
            ]
            y_base = h - 20
            for line in reversed(lines):
                (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (5, y_base - th - 4), (15 + tw, y_base + 4), (0, 0, 0), -1)
                cv2.putText(frame, line, (10, y_base), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                y_base -= th + 10

    @staticmethod
    def _resize_for_preview(frame: np.ndarray) -> np.ndarray:
        """Resize frame to PREVIEW_SIZE, preserving aspect ratio with letterboxing."""
        h, w = frame.shape[:2]
        scale = PREVIEW_SIZE / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        preview = np.zeros((PREVIEW_SIZE, PREVIEW_SIZE, 3), dtype=np.uint8)
        y_off, x_off = (PREVIEW_SIZE - new_h) // 2, (PREVIEW_SIZE - new_w) // 2
        preview[y_off : y_off + new_h, x_off : x_off + new_w] = resized
        return preview

    def _preview_loop(self) -> None:
        """Independent preview thread: reads latest camera frame, overlays
        detection results, encodes JPEG at high FPS."""
        interval = 1.0 / PREVIEW_FPS
        while self._running:
            if not self._viewer_active:
                time.sleep(0.1)
                continue

            frame = self._camera.read_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            # Read overlay data (non-blocking snapshot)
            with self._overlay_lock:
                overlay = copy.copy(self._overlay)

            # Draw overlays on a copy of the raw frame
            display = frame.copy()
            self._draw_overlays(display, overlay)

            # Resize and encode
            preview = self._resize_for_preview(display)
            _, jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

            # Overwrite semantics: drain old frame, put new one
            try:
                self._preview_queue.get_nowait()
            except queue.Empty:
                pass
            self._preview_queue.put(jpeg.tobytes())

            time.sleep(interval)

    def _maybe_publish_status(self) -> None:
        """Publish status to main process every ~1 second."""
        now = time.monotonic()
        if now - self._last_status_time < 1.0:
            return

        status = WorkerStatus(
            camera_status="connected" if self._camera.is_connected else "disconnected",
            pose_lock_status="locked" if self._sync.state not in (SyncState.UNBOUND, SyncState.CALIBRATING) else "unlocked",
            sync_state=self._sync.state.value,
        )

        # Overwrite: drain old, put new
        try:
            self._status_queue.get_nowait()
        except queue.Empty:
            pass
        self._status_queue.put(status)
        self._last_status_time = now


class VisionWorkerProcess:
    """Manages the vision worker subprocess from the main process side."""

    def __init__(self, config: dict[str, Any]):
        self._config = config
        self._process: mp.Process | None = None
        self._cmd_queue: Queue = Queue()
        self._event_queue: Queue = Queue()
        self._status_queue: Queue = Queue()
        self._preview_queue: Queue = Queue(maxsize=1)

    def start(self) -> None:
        """Spawn the worker process."""
        self._process = mp.Process(
            target=_run_worker,
            args=(self._cmd_queue, self._event_queue, self._status_queue, self._preview_queue, self._config),
            daemon=True,
            name="vision-worker",
        )
        self._process.start()
        logger.info("Vision worker process started (pid=%s)", self._process.pid)

    def stop(self) -> None:
        """Send SHUTDOWN command and wait for process to exit."""
        if self._process and self._process.is_alive():
            self.send_command(WorkerCommand(action=CommandType.SHUTDOWN))
            self._process.join(timeout=5)
            if self._process.is_alive():
                logger.warning("Vision worker did not exit cleanly, terminating")
                self._process.terminate()
        self._process = None

    def send_command(self, cmd: WorkerCommand) -> None:
        """Send a command to the worker."""
        self._cmd_queue.put(cmd)

    def get_event(self, timeout: float = 0) -> Any | None:
        """Get next event from worker. Returns None if queue is empty."""
        try:
            return self._event_queue.get(timeout=timeout) if timeout > 0 else self._event_queue.get_nowait()
        except queue.Empty:
            return None

    def get_status(self) -> WorkerStatus | None:
        """Get latest worker status (or None)."""
        status = None
        # Drain to get latest
        while True:
            try:
                status = self._status_queue.get_nowait()
            except queue.Empty:
                break
        return status

    def get_preview_jpeg(self) -> bytes | None:
        """Get latest preview JPEG (or None)."""
        try:
            return self._preview_queue.get_nowait()
        except queue.Empty:
            return None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()
