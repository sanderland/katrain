"""Vision worker process — runs camera capture, inference, and sync in isolation.

On SBC this runs as a separate process to isolate vision memory from
FastAPI/Chromium. On dev machines an in-process adapter is used instead
(see worker_inprocess.py).
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import time
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

        self._last_preview_time = 0.0
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
        """Main loop: capture → infer → sync → publish events."""
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

        target_frame_interval = 1.0 / self._config.get("capture_fps", 8)

        while self._running:
            loop_start = time.monotonic()

            # Process commands
            self._process_commands()

            # Camera frame
            frame = self._camera.read_frame()
            board_detected = False
            observed_board = None
            mean_confidence = 0.0

            if frame is not None:
                # Motion filter
                if self._motion_filter.is_stable(frame):
                    # Board detection + perspective transform
                    warped, found = self._board_finder.find_focus(
                        frame, min_threshold=20, use_clahe=self._config.get("use_clahe", False)
                    )
                    if found and warped is not None:
                        board_detected = True
                        h, w = warped.shape[:2]

                        # Inference
                        detections = self._detector.detect(warped)

                        # Board state
                        observed_board = self._state_extractor.detections_to_board(detections, img_w=w, img_h=h)

                        # Mean confidence
                        if detections:
                            mean_confidence = sum(d.confidence for d in detections) / len(detections)

                        # Move detection
                        if self._bound:
                            move_result = self._move_detector.detect_new_move(observed_board)
                            if move_result is not None:
                                row, col, color = move_result
                                self._event_queue.put(ConfirmedMove(col=col, row=row, color=color))

                        # Preview frame generation (warped board view)
                        self._maybe_send_preview(frame, warped)

                # Send raw camera preview even when board is not detected
                if not board_detected:
                    self._maybe_send_preview(frame, None)

            # Sync state machine update
            if self._bound:
                events = self._sync.update(
                    observed_board=observed_board,
                    mean_confidence=mean_confidence,
                    board_detected=board_detected,
                )
                for evt in events:
                    self._event_queue.put({"type": evt.type.value, "data": evt.data})

            # Publish status periodically
            self._maybe_publish_status()

            # Throttle to target FPS
            elapsed = time.monotonic() - loop_start
            sleep_time = target_frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._camera.close()
        logger.info("Worker process exiting")

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

    def _maybe_send_preview(self, raw_frame: np.ndarray, warped: np.ndarray | None) -> None:
        """Encode and send a preview JPEG if a viewer is active and enough time has passed."""
        if not self._viewer_active:
            return

        now = time.monotonic()
        if now - self._last_preview_time < 1.0 / PREVIEW_FPS:
            return

        # Use warped board view when available, otherwise show raw camera feed
        source = warped if warped is not None else raw_frame
        h, w = source.shape[:2]
        # Resize to square preview, preserving aspect ratio with padding for raw frames
        if warped is not None:
            preview = cv2.resize(source, (PREVIEW_SIZE, PREVIEW_SIZE), interpolation=cv2.INTER_LINEAR)
        else:
            scale = PREVIEW_SIZE / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            resized = cv2.resize(source, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            preview = np.zeros((PREVIEW_SIZE, PREVIEW_SIZE, 3), dtype=np.uint8)
            y_off, x_off = (PREVIEW_SIZE - new_h) // 2, (PREVIEW_SIZE - new_w) // 2
            preview[y_off : y_off + new_h, x_off : x_off + new_w] = resized
        _, jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

        # Overwrite semantics: drain old frame, put new one
        try:
            self._preview_queue.get_nowait()
        except queue.Empty:
            pass
        self._preview_queue.put(jpeg.tobytes())
        self._last_preview_time = now

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
