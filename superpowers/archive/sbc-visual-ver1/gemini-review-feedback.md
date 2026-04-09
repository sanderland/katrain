# Gemini Review Feedback: SBC Visual Recognition Integration — v1

## 1. Overall Assessment
**Status: Approve with changes**

The implementation plan is exceptionally thorough and technically sound. It correctly identifies the primary bottleneck (memory on RK3562) and proposes a modern, decoupled architecture (Worker Process + Pluggable Backends) that is much more robust than a simple threaded implementation. The "Phase 0" feasibility gate is a high-signal addition that significantly reduces project risk.

---

## 2. Technical Review

### 2.1 Memory & Performance
- **Process Isolation:** Moving the vision pipeline to a separate process is the correct choice. It prevents a memory-intensive YOLO session from starving the FastAPI server and allows for independent crash recovery.
- **Frame Rate Budget:** The proposed throttling (Inference 2-5fps, Preview 2-3fps) is realistic for Cortex-A55. 
- **Risk:** Even with ONNX, 2GB RAM is "dangerously low" for Chromium + Python. 
    - **Recommendation:** In Phase 0, specifically measure the **Resident Set Size (RSS)** of Chromium in `--kiosk` mode while the vision worker is active. If swap usage is high, UI responsiveness will suffer.

### 2.2 Inference Backend
- **Metadata Sidecar:** The `model.meta.json` approach is brilliant. It makes the backend truly agnostic to model version/export settings.
- **NMS Optimization:** Using `cv2.dnn.NMSBoxes` is a smart way to get C++ performance for NMS without extra dependencies.
- **Alternative:** If Phase 0 shows ONNX is too heavy (>500MB), consider **ncnn** as a fallback. It is often the gold standard for ARM-based SBCs due to its aggressive memory management.

### 2.3 Sync Engine & State Machine
- **Noise Rejection:** The "N consecutive stable frames" requirement for `ILLEGAL_CHANGE` is critical. It correctly handles stone flickering.
- **Capture Logic:** The `CAPTURE_PENDING` state being "sticky" is the correct UX. It avoids the system moving forward while the physical board is in an inconsistent state.
- **Y-Axis Flip:** Task 3.2 correctly addresses the GTP vs. Vision coordinate discrepancy.

### 2.4 Architecture & IPC
- **VisionPlayerBridge:** Reusing this domain layer instead of an HTTP self-call is a major improvement (Codex #4). It avoids potential deadlocks and reduces latency.
- **MJPEG Backpressure:** The plan mentions being "backpressure-aware." 
    - **Refinement:** Ensure the worker uses a non-blocking queue for the preview frame. If the main process is slow to read, the worker should just overwrite the old frame in shared memory rather than queuing up JPEGs.

---

## 3. Improvements & Missing Considerations

### 3.1 Board Rotation (Missing)
The Kiosk UI supports 90/180/270 degree rotation. 
- **Requirement:** The vision system must know the UI's rotation state to map detections correctly. 
- **Proposed Change:** Add a `set_ui_rotation` command to `WorkerCommand`. The `BoardSyncEngine` should apply this rotation before comparing with the `expected_board`.

### 3.2 Camera Hot-plugging
Kiosk environments often have loose cables or stowed cameras.
- **Requirement:** The `CameraManager` should gracefully handle `/dev/video*` disconnects.
- **Proposed Change:** In Task 2.2, ensure the worker loop has a `try-except` around `read_frame` that triggers an `auto-reconnect` attempt every 5 seconds if the camera is lost, rather than exiting the process.

### 3.3 Confidence & Degradation Mode
- **Requirement:** Define how `DEGRADED` mode is triggered.
- **Proposed Change:** Monitor the `mean_confidence` of all detections. If it drops below a secondary threshold (e.g., 0.35) for 10 seconds, trigger `DEGRADED`. This warns the user about poor lighting before the system starts making errors.

### 3.4 MJPEG Encoding Performance
- **Concern:** Software JPEG encoding at 960x960 might consume significant CPU.
- **Proposed Change:** If Phase 0 shows CPU bottlenecks, consider resizing the preview frame to 480x480 *before* JPEG encoding. The user doesn't need high-res MJPEG for a setup guide.

---

## 4. Suggested Refinements to Task List

- **Task 2.1 (Camera):** Add "Robustness: Handle device disconnection/reconnection."
- **Task 3.1 (Sync):** Add "Rotation: Support 0/90/180/270 degree coordinate mapping."
- **Task 5.3 (Research):** Prioritize the routing fix early in Phase 5 to avoid integration testing delays.
- **Phase 6 (Gate):** Add a specific "Memory Stress Test" — run a 1-hour game while Chromium has 5+ tabs open in the background (to simulate leak/bloat).

## 5. Decision
**Approve with the above changes.** The plan is a solid foundation for a high-quality integration.
