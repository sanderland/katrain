# Review Prompt: SBC Visual Recognition Integration — v1

## Your Role

You are reviewing an implementation plan for migrating an existing Go board visual recognition system from MacBook Pro to RK3562 SBC (single-board computer), and integrating it with a kiosk web UI. The plan was written by Claude and will be executed by Claude. Your job is to identify flaws, risks, missed edge cases, and architectural issues before implementation begins.

## Project Context

- **KaTrain** is a Go/Baduk teaching app with dual UI: a Galaxy web UI (desktop browsers) and a Kiosk UI (SBC touchscreen devices).
- Both UIs share a React frontend (`katrain/web/ui/src/`) with shared components in `components/` and UI-specific pages in `galaxy/` and `kiosk/`.
- The backend is FastAPI (`katrain/web/server.py`) with game sessions managed via WebSocket.
- The kiosk runs in Chromium `--kiosk` mode on Debian/ARM64, connecting to a remote KaTrain server in "board mode."
- **RK3562 hardware:** 4x Cortex-A55, 0.8 TOPS NPU, **2GB RAM + 2GB swap** — extremely memory-constrained.

### Existing Vision Pipeline (Fully Implemented, Validated on MacBook)

The complete vision pipeline exists in `katrain/vision/` (~700 lines, 10 test files, 70+ test cases):

```
Camera → MotionFilter (raw frame, skip if stable)
       → BoardFinder (Canny + ArUco hybrid, perspective transform)
       → StoneDetector (YOLO11, imgsz=960, agnostic_nms)
       → BoardStateExtractor (pixel→grid, confidence conflict resolution)
       → MoveDetector (3-frame consistency)
       → KaTrain Move (reuses sgf_parser.Move)
```

**Key modules:**
- `pipeline.py` — `DetectionPipeline.process_frame(frame) → FrameResult`
- `stone_detector.py` — wraps `ultralytics.YOLO`, returns `list[Detection]`
- `board_finder.py` — `BoardFinder.find_focus()` with ArUco + Canny fallback, transform caching
- `board_state.py` — `BoardStateExtractor.detections_to_board()` → `(19,19)` numpy matrix
- `move_detector.py` — `MoveDetector.detect_new_move()` with consistency check + `force_sync()`
- `katrain_bridge.py` — `vision_move_to_katrain(col, row, color)` flips Y axis for GTP convention
- `katrain_integration.py` — `VisionPlayerBridge.submit_move()` calls `session.katrain("play", coords)`
- `tools/live_demo.py` — full visualization with board overlay, YOLO bboxes, detection overlay

**Problem:** The pipeline uses the `ultralytics` library which alone consumes ~200MB+ RAM. Combined with OpenCV, the model, Chromium, and FastAPI, it exceeds the 2GB physical RAM budget on RK3562.

## User's Requirements

### 1. Memory-Efficient Inference

Support two lightweight inference backends, selectable via startup parameter:
- **ONNX Runtime** — export `.pt` → `.onnx`, use `onnxruntime` for CPU inference
- **RKNN NPU** — export `.onnx` → `.rknn`, use `rknn-toolkit-lite2` for NPU inference on RK3562

Both will be benchmarked on-device to compare performance. The full `ultralytics` library is NOT installed on SBC.

### 2. Kiosk UI Integration

**Target modules (this phase):** 对弈 (Game), 死活题 (Tsumego), 研究 (Research)

#### 2.1 Core Feature: Physical Board → Digital Board Sync

When a stone is placed on the physical Go board:
1. Camera captures frame
2. YOLO detects stones
3. Map detected stones to grid intersections
4. New move is auto-submitted to the game session (silent sync, no confirmation dialog)
5. Digital board updates in real time

The user places ALL stones on the physical board, including AI's response stones (user sees AI move on screen, then places it physically). This keeps physical and digital boards always in sync.

#### 2.2 Stone Removal & Board Integrity

ALL modules must detect:
- **Missed captures:** Game engine says stones were captured, but they're still on the physical board → popup: "请提走 D4, E4, E5 的 3 颗白子"
- **Unauthorized changes:** Stones appear/disappear without valid game reason → popup with "恢复棋局" / "重新同步" (resync only in research mode)
- **Ambiguous placement:** Stone between two intersections → popup: "无法确定落子位置，请调整棋子"

#### 2.3 Tsumego Initial Position Setup

When entering a tsumego problem, the digital board has an initial position (e.g., 23 stones) but the physical board is empty. The system must:
- Show a setup guide with live camera feed
- Overlay: green checkmarks on correctly placed stones, red dotted circles on missing stones
- Progress: "已匹配 15/23 颗子"
- Block problem interaction until physical board matches digital position
- "开始答题" button appears when all matched

#### 2.4 Initialization Flow

```
Kiosk boot
  → Backend auto-detects camera
  → StatusBar shows camera icon (red=disconnected / green=connected)
  → User enters /kiosk/vision/setup (calibration page)
  → Live MJPEG video stream + grid overlay + stone detection results
  → Board detected → "确认" button enables
  → User confirms → calibration locked for this boot session
  → StatusBar shows board match icon (green=calibrated)
```

Calibration data is **per-boot only** — camera is stowed between sessions, position changes every boot.

## Proposed Plan

See the attached `plan.md` for the full 14-task implementation plan. Summary:

### Task 1: Inference Backend Abstraction

Replace direct `ultralytics.YOLO` dependency with a pluggable `InferenceBackend` protocol:
- `OnnxBackend` — uses `onnxruntime`, implements YOLO output decoding + NMS manually
- `RknnBackend` — uses `rknn-toolkit-lite2`, handles INT8 dequantization
- `UltralyticsBackend` — wraps existing code, for dev/training only
- Factory function selects backend via `--vision-backend onnx|rknn|ultralytics`

### Task 2: Model Export Tools

- `export_onnx.py` — `.pt` → `.onnx` via ultralytics export API
- `export_rknn.py` — `.onnx` → `.rknn` via rknn-toolkit2 (x86 only)

### Task 3: Camera Manager

Simple `cv2.VideoCapture` wrapper with auto-detection (`detect_cameras()` probes /dev/video0..4).

### Task 4: Board Sync Engine

Core diff logic: `BoardSyncEngine.compare(vision_board) → list[SyncEvent]`

Events: `NEW_MOVE`, `CAPTURE_PENDING`, `ILLEGAL_CHANGE`, `SETUP_PROGRESS`, `SETUP_COMPLETE`, `AMBIGUOUS_STONE`, `BOARD_MATCHED`

Converts `GameState.stones` (GTP coords) to numpy matrix for comparison with vision board.

### Task 5: Vision Service

Background thread orchestrator: camera capture → pipeline → sync → event dispatch.
- Generates MJPEG frames with overlays
- Auto-submits detected moves via `POST /api/move`
- Pushes sync events via WebSocket

### Task 6: Vision API & WebSocket

REST: `GET /status`, `GET /stream` (MJPEG), `POST /calibrate/confirm`, `POST /bind`, `POST /unbind`, `POST /sync/reset`
WebSocket: `/ws/vision` — pushes `SyncEvent` JSON messages

### Tasks 7-8: Frontend Vision Infrastructure

`VisionContext` + `useVision` + `useVisionSync` hooks. StatusBar gets camera + board status icons.

### Task 9: Vision Setup Page

`/kiosk/vision/setup` — MJPEG `<img>` tag + status text + confirm button.

### Task 10: Sync Alert Components

4 popup types: `CaptureGuide`, `IllegalChangeDialog`, `BoardSetupGuide`, `AmbiguousStoneAlert`

### Tasks 11-13: Module Integration

GamePage (sync + AI move toast + capture alerts), TsumegoProblemPage (setup guide + sync), ResearchPage (sync + resync).

### Task 14: Backend Configuration

CLI args: `--vision-backend`, `--vision-model`, `--vision-camera`

## Review Checklist

### Memory & Performance

- [ ] Is the ONNX Runtime memory footprint realistic for 2GB RAM? What's the expected memory for loading a yolo11x .onnx model (114MB weights) + inference session?
- [ ] Is yolo11x the right model size for SBC? Should we default to yolo11n or yolo11s on SBC and reserve yolo11x for server-side?
- [ ] The MJPEG stream encodes ~30 JPEG frames/sec. Is this CPU overhead acceptable on 4x Cortex-A55 alongside YOLO inference?
- [ ] Should the processing loop frame rate be throttled (e.g., 5-10 fps) to save CPU/memory?
- [ ] Does `cv2.VideoCapture` on ARM/V4L2 have known memory leak issues?
- [ ] Is the `threading.Thread` approach for VisionService suitable, or should it be a separate process to isolate memory?

### Inference Backend

- [ ] Is the YOLO v11 ONNX output shape assumption (`(1, 6, 8400)`) correct? Does it vary by model size or export settings?
- [ ] The plan says to "implement YOLO output decoding + NMS manually" in `OnnxBackend`. This is non-trivial. Is there a lighter-weight library that provides this without pulling in full ultralytics?
- [ ] RKNN quantization to INT8 — does this significantly degrade detection accuracy for the Go stone use case? What's the expected mAP drop?
- [ ] Is `rknn-toolkit-lite2` stable on RK3562? The RK3562 NPU is smaller than RK3588 — are all YOLO11 operations supported?
- [ ] Should we consider `ncnn` as a third backend option? It's widely used on ARM SBCs and has good YOLO support.

### Sync Engine

- [ ] The sync engine compares full 19x19 boards. Vision detection has noise — a stone might flicker (detected in frame N, missing in frame N+1). How does the sync engine handle transient detection failures without triggering false ILLEGAL_CHANGE alerts?
- [ ] The existing `MoveDetector` requires 3-frame consistency for confirming a new move. But `BoardSyncEngine` also does comparison. Is there redundant logic? How do these two components interact?
- [ ] When the user places an AI response stone, the sync engine sees the expected board (with AI stone) but vision detects a new stone appearing. Does this correctly register as "board matched" rather than "new move"?
- [ ] Capture detection: after a move with captures, the game engine updates `expected_board` immediately (captured stones removed). But the physical stones are still there. The plan says `CAPTURE_PENDING` fires. What's the timeout? What if the user takes 30+ seconds to remove stones — does the system stay in alert state?
- [ ] In tsumego setup mode, can the user place stones in any order, or must they follow a specific sequence? What if they accidentally place a wrong-color stone?
- [ ] Research mode "重新同步" resets expected board to physical board. But the game tree in KaTrain doesn't know about this reset. How is the game tree kept consistent?

### Architecture

- [ ] VisionService runs in a background thread and calls `POST /api/move` to submit moves. But the game session has a `threading.Lock`. Could there be deadlocks if the vision thread and a WebSocket handler both try to modify the session simultaneously?
- [ ] The plan has VisionService running as part of the FastAPI process. On 2GB RAM, should it be a separate lightweight process communicating via IPC/socket to isolate its memory footprint?
- [ ] The MJPEG stream endpoint (`GET /api/v1/vision/stream`) is a long-lived HTTP response. How does this interact with Uvicorn's worker model? Does it block a worker thread?
- [ ] `vision.bind_session(session_id)` couples the vision service to one game session at a time. Is this the right model? What happens if the user opens a second browser tab?

### Frontend

- [ ] The MJPEG `<img>` tag approach is simple but has no error recovery. If the stream breaks (camera disconnect), does the `<img>` tag show a broken image? Should there be a fallback UI?
- [ ] The `VisionSyncAlert` component renders popups over the game page. On 800x480 screens, do these popups obscure the board? Should they be non-modal (snackbar/toast) for less critical alerts?
- [ ] The `BoardSetupGuide` for tsumego shows split view (digital board + camera feed). On a 5" 800x480 screen, is there enough space for both to be usable?
- [ ] Vision WebSocket (`/ws/vision`) is separate from the game WebSocket (`/ws/{sessionId}`). The frontend manages two WebSocket connections. Is this necessary, or could vision events be multiplexed on the game WebSocket?

### Edge Cases

- [ ] What happens if the camera is unplugged mid-game? Does the game continue with touch-only input?
- [ ] What if the physical board is bumped and multiple stones shift? The sync engine would see many simultaneous changes — does it handle this gracefully?
- [ ] What if lighting conditions change (shadow, lamp turned on/off) and detection accuracy drops? Is there a confidence-based degradation mode?
- [ ] Two players at a kiosk — one places a stone while the other's hand is still over the board. The motion filter rejects the frame. What's the user experience?
- [ ] Board rotation: the kiosk supports 0/90/180/270 degree rotation. Does the vision system need to know about the display rotation, or is it independent?

### Testing

- [ ] The plan lists test files but doesn't detail how to test ONNX/RKNN backends in CI (no ARM runner, no NPU). How are these tested?
- [ ] The sync engine tests need realistic board state sequences. Should there be golden test data (recorded frame sequences from actual games)?
- [ ] Integration testing: how to test the full flow (camera → pipeline → sync → WebSocket → UI) without physical hardware?

## Key Files for Reference

```
# Existing vision pipeline
katrain/vision/pipeline.py              # DetectionPipeline orchestrator
katrain/vision/stone_detector.py        # YOLO11 wrapper (to be refactored)
katrain/vision/board_finder.py          # Board detection + perspective transform
katrain/vision/board_state.py           # Detections → 19x19 grid matrix
katrain/vision/move_detector.py         # Multi-frame consistency check
katrain/vision/motion_filter.py         # Inter-frame motion rejection
katrain/vision/coordinates.py           # Pixel ↔ physical ↔ grid mapping
katrain/vision/config.py                # BoardConfig + CameraConfig
katrain/vision/katrain_bridge.py        # Vision coords → KaTrain Move
katrain/vision/katrain_integration.py   # VisionPlayerBridge → session.katrain("play")
katrain/vision/tools/live_demo.py       # Overlay rendering reference implementation

# Kiosk frontend
katrain/web/ui/src/kiosk/KioskApp.tsx                   # Router
katrain/web/ui/src/kiosk/pages/GamePage.tsx              # Active game page
katrain/web/ui/src/kiosk/pages/TsumegoProblemPage.tsx    # Tsumego problem page
katrain/web/ui/src/kiosk/pages/ResearchPage.tsx          # Research/study page
katrain/web/ui/src/kiosk/components/layout/StatusBar.tsx  # Header with status icons
katrain/web/ui/src/hooks/useGameSession.ts               # Game session + WebSocket hook
katrain/web/ui/src/api.ts                                # Frontend API client

# Backend
katrain/web/server.py       # FastAPI app, lifespan, WebSocket handlers
katrain/web/session.py      # SessionManager, WebSession
katrain/web/core/config.py  # Board mode config, env vars
```

## Expected Output

For each task area, provide:

1. **Agreement or disagreement** with the approach
2. **Concerns or risks** with specific technical reasoning
3. **Alternative approaches** if you see a better way
4. **Missing considerations** the plan doesn't address

End with an overall assessment: **Approve**, **Approve with changes**, or **Reject with reasons**.
