# SBC Visual Recognition Integration Plan — v1 (Revised)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the existing Go board visual recognition system from MacBook Pro to RK3562 SBC (2GB RAM + 2GB swap), and integrate it with the kiosk web UI so that camera-detected moves appear on the digital board in real time.

**Context:** The full vision pipeline already exists in `katrain/vision/` (7 core modules, ~700 lines) and was validated on MacBook. The main challenges are (1) replacing the heavy `ultralytics` library with lightweight inference backends suitable for 2GB RAM, (2) building a camera calibration UI, and (3) wiring vision events into the kiosk game/tsumego/research pages with sync alerts.

**Target modules (this phase):** 对弈 (GamePage), 死活题 (TsumegoProblemPage), 研究 (ResearchPage)

**Revision notes:** Incorporates Codex review feedback (all items verified against codebase) and Gemini review feedback.

Codex feedback (structural):
- Added Phase 0 feasibility gate before building anything
- Switched to separate worker process architecture (not in-process thread)
- Fixed GameState.stones structure: tuple `[player, coords, scoreLoss, moveNumber][]`, not object
- TsumegoProblemPage uses frontend-local state, not WebSession — sync via "frontend sends expected board"
- ResearchPage has a routing gap (navigates to non-existent route) — must fix before vision integration
- GamePage is fullscreen (no KioskLayout/StatusBar) — needs independent status overlay
- Reuse/extend VisionPlayerBridge instead of HTTP self-call
- Clear separation: MoveDetector confirms new stones, SyncStateMachine compares overall state
- Export contract with `model.meta.json` sidecar instead of hardcoded output shapes

Gemini feedback (incremental):
- Phase 0: explicitly measure Chromium kiosk RSS while vision worker active
- Camera hot-plug auto-reconnect in worker loop (not crash)
- MJPEG preview: shared memory overwrite (not queue), resize to 480x480 before encoding
- Degraded mode trigger: mean detection confidence < 0.35 for 10 consecutive seconds
- Phase 6: add 1-hour memory stress test
- UI rotation does NOT affect vision coordinates (camera works in physical space; display rotation is frontend rendering only, handled by board pose calibration)
- Throttled frame rates: capture 8-10fps, inference 2-5fps, preview 2-3fps
- Separate "camera intrinsics" (persistent) from "board pose lock" (per-boot)
- Research resync creates setup node in game tree (not fake UI-only sync)
- Added replay tests, contract tests, soak test requirements

---

## Design Decisions (Confirmed + Revised)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Inference backend | ONNX Runtime (primary) + RKNN NPU (experimental), via `--vision-backend` | ONNX first; RKNN only after feasibility gate passes on real hardware |
| Process model | **Separate worker process** on SBC; in-process adapter for dev | Isolate vision memory from FastAPI/Chromium; crash recovery without killing main service (Codex #1) |
| Video stream | MJPEG from backend, **2-3 fps preview** | 30fps is unrealistic on A55; human stone placement doesn't need high fps (Codex #7) |
| Frame rate budget | Capture 8-10fps, inference 2-5fps (motion-gated), preview 2-3fps | Separate loop rates to avoid CPU contention (Codex #7) |
| Interaction mode | Silent sync: auto-submit detected moves, alert on divergence | No confirmation dialog; popups only for errors |
| AI response stones | User places AI stones on physical board too | Physical & digital boards stay in sync; unified sync logic |
| Calibration naming | **Camera intrinsics** (persistent .npz) + **Board pose lock** (per-boot) | Two different lifecycles — don't conflate (Codex #8) |
| Move confirmation | **MoveDetector only** (existing 3-frame consistency) | SyncStateMachine does NOT re-confirm new stones — avoids double-judgment conflicts (Codex #3) |
| Move submission | Via **VisionPlayerBridge** (domain layer), not HTTP self-call | Reuse existing `session.katrain("play", coords)` path; avoids latency and lock issues (Codex #4, #2.5) |
| Tsumego integration | Frontend sends expected board to vision worker; no WebSession bind | TsumegoProblemPage uses `useTsumegoProblem` hook (frontend-local), not session-driven (Codex #2.2) |
| Research resync | Creates **setup node** (AE/AB/AW) in game tree | Must update KaTrain state + frontend + vision expected board together (Codex #9) |
| Export contract | `model.meta.json` sidecar with input/output specs | OnnxBackend/RknnBackend read metadata, not hardcoded shapes (Codex #5) |
| Stone removal | Detected in ALL modules; popup if captures missed or board tampered | Core requirement for game integrity |
| Initial position setup | Guided mode for tsumego: overlay missing stones, progress bar | Required when digital board starts non-empty |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                  FastAPI Main Process                          │
│                                                                │
│  SessionManager, WebSession, KioskLayout pages                │
│  Vision API endpoints (thin proxy to worker)                  │
│  WebSocket /ws/vision (relay events from worker)              │
│  WebSocket /ws/{sessionId} (game updates)                     │
│                                                                │
│  VisionPlayerBridge ←── receives confirmed moves from worker  │
│  └─ session.katrain("play", coords)                          │
│                                                                │
│  GET /api/v1/vision/stream ←── reads preview JPEG from IPC   │
└───────────────────┬──────────────────────────────────────────┘
                    │ IPC (shared memory / pipe / unix socket)
                    │
┌───────────────────▼──────────────────────────────────────────┐
│              Vision Worker Process (SBC only)                  │
│                                                                │
│  CameraManager (cv2.VideoCapture)                             │
│       ↓ 8-10 fps                                              │
│  MotionFilter (raw frame)                                     │
│       ↓ only stable frames                                    │
│  BoardFinder (Canny + ArUco, perspective transform)           │
│       ↓ warped image                                          │
│  InferenceBackend (OnnxBackend | RknnBackend)                 │
│       ↓ 2-5 fps, list[Detection]                              │
│  BoardStateExtractor (pixel→grid, conflict resolution)        │
│       ↓ observed_board (19x19 matrix)                         │
│  MoveDetector (3-frame consistency → confirmed_move)          │
│       ↓                                                        │
│  SyncStateMachine (compare observed vs expected)              │
│       ↓ SyncEvent stream                                       │
│  JPEG encoder (2-3 fps, with overlays, only if viewer active) │
│                                                                │
│  Inputs (from main process):                                  │
│    set_expected_board, confirm_pose_lock, reset_sync,         │
│    enter_setup_mode(target_board), bind/unbind                │
│                                                                │
│  Outputs (to main process):                                   │
│    camera_status, pose_lock_status, observed_board,           │
│    confirmed_move, sync_events[], preview_jpeg                │
└──────────────────────────────────────────────────────────────┘
```

### On Dev Machine (MacBook)

Vision runs in-process via an adapter that mimics the IPC interface but calls modules directly. This allows development/debugging without the separate process overhead.

---

## Phase 0: Feasibility Gate

**Purpose:** Validate that ONNX inference is viable on RK3562 before building 13 tasks on top of it. This is a non-coding investigation phase.

### Phase 0A: ONNX CPU Benchmark — COMPLETED ✅

**Hardware:** RK3562 (4x Cortex-A55, 2GB RAM + 2GB swap), Debian, Python 3.11, onnxruntime CPU.

**Benchmark results (imgsz=640, COCO pretrained weights, dummy input):**

| Model | ONNX Size | Load Time | RSS (推理中) | Avg Latency | 可行性 |
|-------|-----------|-----------|-------------|-------------|--------|
| **yolo11n** | 10MB | 0.23s | **135MB** | **600ms** | ✅ **最佳选择** |
| yolo11s | 36MB | 0.37s | 221MB | 1.56s | ⚠️ 勉强可用 |
| yolo11m | 77MB | 0.56s | 369MB | 4.3s | ⚠️ CPU 慢，但功能可用 |
| yolo11x | 217MB | 3.87s | 631MB | 11.4s | ❌ 不可行 |

**ONNX CPU 结论:**
- **yolo11n 为首选**：135MB RSS + 600ms 延迟，远低于内存/延迟阈值。
- yolo11s 可作为备选（1.5s 延迟可接受，221MB RSS 安全）。
- yolo11m 在 CPU 上太慢（4.3s），但如果 NPU 能加速则仍有价值。
- yolo11x 在 RK3562 上完全不可行（11s + 631MB）。
- **精度是独立问题**：yolo11n 之前在真实棋盘上泛化差是训练数据不足（仅 201 张合成图），不是模型能力问题。需要更多/更好的训练数据重新训练。

**实际使用延迟估算**（含运动过滤 — 仅画面稳定后推理）：
- yolo11n：落子后 ~1-2s 响应（流畅）
- yolo11s：落子后 ~2-3s 响应（可接受）
- yolo11m：落子后 ~5-6s 响应（能用但��）

### Phase 0B: RKNN NPU Benchmark — BLOCKED (驱动过旧)

**硬件探测结果 (2026-03-29):**
- NPU 硬件存在：`/sys/class/devfreq/ff300000.npu`，映射为 DRI 设备（card1 / renderD129）
- NPU 频率：当前 600MHz，可用 300MHz-1GHz
- 内核配置：`CONFIG_ROCKCHIP_RKNPU=y`，`CONFIG_ROCKCHIP_RKNPU_DRM_GEM=y`（编译进内核）
- **驱动版本：RKNPU v0.9.8** — 使用 DRM GEM 模式，无 `/dev/rknpu` 设备节点
- 内核：5.10.209，Debian 11 (bullseye)

**阻塞原因：** `rknn-toolkit-lite2` 需要 RKNPU 驱动 >= v1.4.0 和 `/dev/rknpu` 设备节点。当前 v0.9.8 不兼容。升级驱动需要更新内核/固件，或联系厂商（格致培特）提供新固件。

**厂商资料调研 (2026-03-29):** 已翻阅广州佩特科技全部资料（Debian 应用编程手册 8 页、主板规格书、一体屏/一体机规格书）。规格书仅列出"1TOPS NPU"参数，**无任何 NPU 开发指南、RKNN SDK 安装说明或驱动升级文档**。厂商联系方式：www.gzpeite.net，微信二维码在 Debian 手册最后一页。

**决定：NPU 搁置为后续优化项。** 当前使用 ONNX CPU (yolo11n) 推进所有后续 Phase。如需 NPU 支持，需主动联系厂商索要新固件。

**NPU 升级工具调研 (2026-03-29):**
- 系统预装了 `/usr/bin/npu_upgrade`，用法：`npu_upgrade loader uboot trust boot`
- 这是硬件级固件刷写工具，需要 4 个固件文件（loader、uboot、trust、boot），不是简单的驱动更新
- 还有 `/usr/bin/upgrade_tool`（Rockchip 通用刷机工具），需要 USB rockusb 连接
- 系统也安装了 Rockchip MPP 多媒体库（`librockchip-mpp1` v1.5.0），说明厂商有定制 BSP
- **操作风险高**：刷错固件可能变砖，不建议自行操作
- **正确路径：联系格致培特(gzpeite)厂商，索要包含 RKNPU v1.6+ 驱动的完整固件包**

**NPU 未来启用路径（供参考）：**
1. 联系厂商获取新固件（包含 RKNPU v1.6+ 驱动），用 `npu_upgrade` 刷入
2. 在 x86 Linux (Docker) 上安装 `rknn-toolkit2`，将 ONNX 转为 RKNN（含 INT8 量化）
3. 在 RK3562 上安装 `rknn-toolkit-lite2` ARM wheel
4. 预期加速：yolo11n CPU 600ms → NPU 估计 60-200ms；yolo11m CPU 4.3s → NPU 估计 0.5-1.5s

_(以下旧步骤已废弃，保留供未来参考)_

在 RK3562 上运行：
```bash
# 检查 NPU 驱动是否加载
dmesg | grep -i npu
ls /dev/npu*
cat /sys/kernel/debug/rknpu/version 2>/dev/null

# 检查 rknn_lite 是否可用
pip list | grep rknn
python -c "from rknnlite.api import RKNNLite; print('rknn-lite OK')"
```

如果 NPU 驱动不存在或 `rknn-toolkit-lite2` 未安装，需要：
```bash
# 安装 rknn-toolkit-lite2 (ARM64 wheel)
# 从 https://github.com/airockchip/rknn-toolkit2/tree/master/rknn-toolkit-lite2/packages 下载
pip install rknn_toolkit_lite2-2.3.0-cp311-cp311-linux_aarch64.whl
```

**Step 2: 在开发机 (x86) 上将 ONNX 转为 RKNN**

需要在 x86 机器上安装 `rknn-toolkit2`（不能在 ARM 上运行），转换脚本：
```python
# export_rknn.py (在 MacBook 或 x86 Linux 上运行)
from rknn.api import RKNN

rknn = RKNN()
rknn.config(target_platform='rk3562', quantized_dtype='w8a8')  # INT8 量化
rknn.load_onnx(model='yolo11n.onnx')
rknn.build(do_quantization=True, dataset='calibration_images.txt')  # 需要校准图片
rknn.export_rknn('yolo11n.rknn')
```

注意：
- `rknn-toolkit2` 仅支持 x86 Linux（不��持 macOS），可能需要 Docker 或 Linux VM
- INT8 量化需要校准图片集（10-50 张棋盘图）
- RK3562 NPU 是 RK3588 NPU 的缩减版（0.8 TOPS vs 6 TOPS），部分算子可能不支持

**Step 3: 在 RK3562 上运行 RKNN benchmark**

```python
# benchmark_rknn.py
from rknnlite.api import RKNNLite
import numpy as np, time

rknn = RKNNLite()
rknn.load_rknn('yolo11n.rknn')
rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_AUTO)

img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
# warmup
rknn.inference(inputs=[img])
# benchmark
for i in range(10):
    t0 = time.perf_counter()
    rknn.inference(inputs=[img])
    print(f"Run {i+1}: {(time.perf_counter()-t0)*1000:.1f} ms")
```

**NPU 预期加速比：**
- RK3562 NPU 0.8 TOPS INT8，理论上比 4x A55 CPU 快 3-10 倍
- yolo11n: CPU 600ms → NPU 估计 60-200ms（如果算子全支持）
- yolo11m: CPU 4.3s → NPU 估计 0.5-1.5s（如果可行，精度显著提升）
- 实际加速比取决于算子支持度和量化精度损失

**Pass criteria (NPU):**
- 至少 yolo11n 可在 NPU 上运行且延迟 < 300ms
- RSS 增量 < 200MB（RKNN runtime 通常比 onnxruntime 更轻）
- INT8 量化后检测精���无显著下降（对比 ONNX FP32 输出）

### Phase 0 总体通过状态

| Gate | 状态 |
|------|------|
| ONNX CPU 可行性 | ✅ PASSED — yolo11n 135MB/600ms |
| RKNN NPU 可行性 | ❌ BLOCKED — 驱动 v0.9.8 过旧，需 v1.4+；联系厂商升级固件后重试 |
| 整机内存预算 | ⏳ TODO — 需要 Chromium + FastAPI + vision worker 同时运行测量 |
| 真实棋盘精度 | ⏳ TODO — 需要用围棋训练数据重新训练后测试 |

**Phase 0 决定：以 ONNX CPU + yolo11n 为主路径推进 Phase 1-6。** yolo11s (1.56s) 作为备选。NPU 加速和 yolo11m/x 大模型作为后续优化，取决于厂商固件更新。

### 已导出的 ONNX 模型（存放于 MacBook `katrain-visual-recognition/models/`）

| 文件 | 大小 | 来源 | 备注 |
|------|------|------|------|
| `yolo11n.onnx` | 10MB | COCO 预训练 | 首选部署模型 |
| `yolo11s.onnx` | 36MB | COCO 预训练 | 备选 |
| `yolo11m.onnx` | 77MB | COCO 预训练 | 仅在 NPU 启用后考虑 |
| `yolo11x.onnx` | 217MB | COCO 预训练 | RK3562 上不可行 |

注：以上均为 COCO 80 类预训练权重（输出 shape `(1, 84, 8400)`），用于 benchmark。实际部署需要用围棋数据集重新训练的 2 类模型（输出 shape `(1, 6, 8400)`）。围棋训练后的 `best.pt` 文件（`runs/detect/go_stones_sam_*/weights/`）已丢失，需要重新训练。

---

## Phase 1: Inference Contract + Replay Harness

**Purpose:** Lock down the model export format and build offline testing infrastructure before touching any UI code.

### Task 1.1: Inference Backend Protocol + Export Contract

**Files:**
- Create: `katrain/vision/inference/__init__.py`
- Create: `katrain/vision/inference/base.py`
- Create: `katrain/vision/tools/export_onnx.py`

**Step 1: Define backend protocol**

```python
# katrain/vision/inference/base.py
from typing import Protocol, runtime_checkable
import numpy as np
from katrain.vision.stone_detector import Detection

@runtime_checkable
class InferenceBackend(Protocol):
    def load(self, model_path: str, meta_path: str | None = None) -> None: ...
    def detect(self, image: np.ndarray, confidence_threshold: float) -> list[Detection]: ...
    def unload(self) -> None: ...
    @property
    def is_loaded(self) -> bool: ...
```

All backends return `list[Detection]` — the existing dataclass stays unchanged.

**Step 2: Export tool with metadata sidecar**

`export_onnx.py` exports `.onnx` model AND `model.meta.json`:

```json
{
  "format": "onnx",
  "source": "yolo11m",
  "imgsz": 960,
  "input_name": "images",
  "input_shape": [1, 3, 960, 960],
  "input_normalize": "0-1",
  "input_channel_order": "RGB",
  "output_name": "output0",
  "output_shape": [1, 6, 8400],
  "output_format": "yolo_v8_raw",
  "classes": ["black", "white"],
  "includes_nms": false,
  "bbox_format": "xywh_center_normalized"
}
```

`OnnxBackend.load()` reads this sidecar to configure pre/post-processing. No hardcoded shapes.

### Task 1.2: ONNX Backend Implementation

**Files:**
- Create: `katrain/vision/inference/onnx_backend.py`

**Key implementation details:**
- Uses `onnxruntime.InferenceSession`
- Pre-processing: resize to `meta.imgsz`, normalize per `meta.input_normalize`, reorder channels
- Post-processing: decode YOLO raw output tensor → boxes + scores → NMS → `list[Detection]`
- NMS implementation: use `cv2.dnn.NMSBoxes` (already available via OpenCV, no extra dependency)

### Task 1.3: Ultralytics Backend (Dev Only)

**Files:**
- Create: `katrain/vision/inference/ultralytics_backend.py`

Extract current `StoneDetector.__init__` + `detect()` logic into this backend. Development/training only — not installed on SBC.

### Task 1.4: Refactor StoneDetector

**Files:**
- Modify: `katrain/vision/stone_detector.py`

```python
class StoneDetector:
    def __init__(self, model_path: str, backend: str = "ultralytics",
                 confidence_threshold: float = 0.5, imgsz: int = 960):
        self.backend_impl = create_backend(backend)
        self.backend_impl.load(model_path)
        ...
    def detect(self, image: np.ndarray) -> list[Detection]:
        return self.backend_impl.detect(image, self.confidence_threshold)
```

### Task 1.5: RKNN Backend (Experimental)

**Files:**
- Create: `katrain/vision/inference/rknn_backend.py`
- Create: `katrain/vision/tools/export_rknn.py`

Only implemented if Phase 0 confirms RKNN toolchain works. Uses `rknnlite2`. Same `InferenceBackend` protocol. Reads `model.meta.json` for dequantization parameters.

### Task 1.6: Replay Harness + Contract Tests

**Files:**
- Create: `tests/test_vision/test_inference_contract.py`
- Create: `tests/test_vision/data/` — test fixtures (sample images + expected detections)

**Contract tests:**
- Load a fixed ONNX artifact + its `model.meta.json`
- Run inference on a known test image
- Assert detection count, positions, and confidences within tolerance
- If export parameters change, this test breaks → prevents silent regression

**Replay harness:**
- `tests/test_vision/test_replay.py` — feed recorded frame sequences through the pipeline
- Verify expected moves are detected in correct order
- Test scenarios: clean game, hand occlusion, capture sequence, lighting change

### Task 1.7: Update pyproject.toml

**Files:**
- Modify: `pyproject.toml`

```toml
[project.optional-dependencies]
vision = ["opencv-python>=4.8.0", "numpy>=1.24.0"]
vision-train = ["ultralytics>=8.3.0"]
vision-onnx = ["onnxruntime>=1.16.0"]
vision-rknn = ["rknn-toolkit-lite2>=2.0.0"]
```

---

## Phase 2: Vision Worker Process

**Purpose:** Camera capture, inference, and state tracking in an isolated process. Main process communicates via lightweight IPC.

### Task 2.1: Camera Manager

**Files:**
- Create: `katrain/vision/camera.py`
- Create: `tests/test_vision/test_camera.py`

```python
class CameraManager:
    def __init__(self, device_id: int = 0): ...
    @property
    def is_connected(self) -> bool: ...
    def open(self) -> bool: ...
    def close(self) -> None: ...
    def read_frame(self) -> np.ndarray | None: ...
    @staticmethod
    def detect_cameras(max_id: int = 4) -> list[int]: ...
```

**Hot-plug robustness (Gemini #3.2):** `read_frame()` catches `cv2` exceptions on device disconnect. When disconnected, `is_connected` returns False and auto-reconnect is attempted every 5 seconds. The worker loop does NOT crash on camera loss — it emits a `camera_disconnected` status and keeps running, waiting for reconnection.

### Task 2.2: Vision Worker

**Files:**
- Create: `katrain/vision/worker.py`
- Create: `katrain/vision/ipc.py`

**Worker process responsibilities:**
- Camera capture loop (8-10 fps)
- Run existing `DetectionPipeline` stages (motion filter → board finder → inference → board state → move detector)
- Maintain sync state machine (Phase 3)
- JPEG encode preview frames (2-3 fps, only when viewer is active — backpressure-aware). Preview frames are **resized to 480x480** before JPEG encoding to save CPU (Gemini #3.4). Uses **shared memory overwrite** (not queue) — worker overwrites the latest frame; if main process is slow to read, old frame is silently replaced (Gemini #2.4 backpressure refinement)
- Expose outputs via IPC

**IPC protocol** (`ipc.py`):

```python
@dataclass
class WorkerState:
    """Read by main process (shared memory or pipe)."""
    camera_status: str          # "disconnected" | "connected"
    pose_lock_status: str       # "unlocked" | "locked"
    observed_board: np.ndarray  # (19,19) int matrix
    confirmed_move: tuple | None  # (col, row, color) or None
    sync_events: list[dict]     # pending events for frontend
    preview_jpeg: bytes | None  # latest JPEG frame

@dataclass
class WorkerCommand:
    """Sent by main process to worker."""
    action: str  # "set_expected_board" | "confirm_pose_lock" | "reset_sync"
                 # | "enter_setup_mode" | "bind" | "unbind" | "set_viewer_active"
    data: dict
```

**IPC mechanism:** `multiprocessing.Queue` for commands (main→worker), `multiprocessing.Value`/shared memory for state (worker→main). Alternative: Unix socket with msgpack serialization if shared memory is too complex.

**Dev mode adapter:** `katrain/vision/worker_inprocess.py` — same interface but runs pipeline in-thread for MacBook development. No process spawn.

### Task 2.3: Vision Service (Main Process Side)

**Files:**
- Create: `katrain/vision/service.py`

**VisionService is a thin proxy in the main process:**

```python
class VisionService:
    """Main-process controller for the vision worker."""

    def __init__(self, config: VisionServiceConfig):
        self.worker: WorkerProcess | InProcessAdapter = ...
        self._event_callbacks: list[Callable] = []

    def start(self) -> None:
        """Spawn worker process (or in-process adapter on dev)."""

    def stop(self) -> None: ...

    @property
    def camera_status(self) -> str: ...

    @property
    def pose_lock_status(self) -> str: ...

    def confirm_pose_lock(self) -> bool:
        """Send confirm command to worker."""

    def set_expected_board(self, board: np.ndarray) -> None:
        """Update expected board for sync comparison."""

    def enter_setup_mode(self, target_board: np.ndarray) -> None:
        """Enter tsumego setup mode with target position."""

    def reset_sync(self) -> None:
        """Accept current physical board as new baseline."""

    def get_preview_jpeg(self) -> bytes | None:
        """Get latest JPEG for MJPEG stream."""

    def poll_events(self) -> list[dict]:
        """Read pending sync events from worker."""

    def get_confirmed_move(self) -> tuple | None:
        """Read and consume latest confirmed move."""
```

**Move submission loop:** A background asyncio task in main process periodically polls `get_confirmed_move()`. When a move is found, it calls `VisionPlayerBridge.submit_move()` (existing domain layer), which calls `session.katrain("play", coords)`. After the session processes the move (including captures), the updated game state is read back and `set_expected_board()` is called with the new board.

---

## Phase 3: Sync State Machine

**Purpose:** Clear separation from MoveDetector. MoveDetector (existing) confirms "a new stone appeared." SyncStateMachine (new) compares the overall observed board vs expected board.

### Task 3.1: Sync State Machine

**Files:**
- Create: `katrain/vision/sync.py`
- Create: `tests/test_vision/test_sync.py`

**State diagram:**

```
UNBOUND ──bind──→ CALIBRATING ──pose_lock──→ READY
                                                │
                                          set_expected
                                                │
                                                ▼
                              ┌──────────── SYNCED ◄───────────────┐
                              │                │                    │
                         board matches    captures detected    stones removed
                              │                │                    │
                              ▼                ▼                    │
                           SYNCED       CAPTURE_PENDING ───────────┘
                                               │
                                          timeout/stuck
                                               │
                                               ▼
                              ┌──── MISMATCH_WARNING ◄────┐
                              │           │                │
                         user restores  unexpected change  │
                              │           (N frames stable)│
                              ▼                            │
                           SYNCED                    BOARD_LOST
                                                    (board corners
                                                     not detected)
```

Additional states:
- `SETUP_IN_PROGRESS` — tsumego initial position matching
- `DEGRADED` — detection confidence dropped (lighting change); warn but don't sync

**Key design principles (from Codex #3):**
1. **New stone confirmation** stays in `MoveDetector` (3-frame consistency). SyncStateMachine trusts its output.
2. **ILLEGAL_CHANGE** requires N consecutive frames (default 5) of stable mismatch — not a single-frame glitch.
3. **CAPTURE_PENDING** is a persistent state (sticky), not a one-time event. Stays until stones are physically removed.
4. **Board displacement** (many positions change simultaneously) triggers `BOARD_LOST`, not N illegal changes.
5. **Degraded mode (Gemini #3.3):** Monitor mean confidence of all detections per frame. If mean_confidence < 0.35 persists for 10 consecutive seconds, enter DEGRADED — show warning "检测质量下降，请检查光线", stop auto-submitting. Exit DEGRADED when mean_confidence recovers above 0.45 for 5 seconds (hysteresis to prevent flapping).

**SyncEvent types:**

```python
class SyncEventType(Enum):
    MOVE_CONFIRMED = "move_confirmed"       # MoveDetector confirmed a new stone
    CAPTURE_PENDING = "capture_pending"     # Stones need physical removal
    CAPTURES_CLEARED = "captures_cleared"   # User removed captured stones
    ILLEGAL_CHANGE = "illegal_change"       # Stable unexpected board change
    SETUP_PROGRESS = "setup_progress"       # N/M stones matched
    SETUP_COMPLETE = "setup_complete"       # All target stones placed
    AMBIGUOUS_STONE = "ambiguous_stone"     # Stone between intersections
    BOARD_LOST = "board_lost"              # Board corners not detected
    BOARD_REACQUIRED = "board_reacquired"  # Board detected again after loss
    DEGRADED = "degraded"                  # Low confidence, stop syncing
    SYNCED = "synced"                      # Everything matches
```

### Task 3.2: GameState → Board Matrix Conversion

**Files:**
- Add function to: `katrain/vision/sync.py`

**Critical fix (Codex #2.1):** GameState.stones is `[player, coords, scoreLoss, moveNumber][]`, NOT `{color, coords}`.

```python
def game_state_stones_to_board(
    stones: list[list],  # [[player, [col, row]|null, scoreLoss, moveNum], ...]
    board_size: int = 19,
) -> np.ndarray:
    """Convert GameState.stones tuple array to vision board matrix.

    GameState coords: (col, gtp_row) where gtp_row 0 = bottom.
    Vision board: board[row][col] where row 0 = top.
    Conversion: vision_row = board_size - 1 - gtp_row
    """
    board = np.zeros((board_size, board_size), dtype=int)
    for entry in stones:
        player, coords = entry[0], entry[1]
        if coords is None:
            continue  # pass move
        col, gtp_row = coords
        vision_row = board_size - 1 - gtp_row
        board[vision_row][col] = BLACK if player == "B" else WHITE
    return board
```

### Task 3.3: Sync Tests

Test scenarios:
- Normal play: place stone → MOVE_CONFIRMED → set new expected → SYNCED
- Capture: move causes captures → expected board updated → CAPTURE_PENDING → user removes → CAPTURES_CLEARED → SYNCED
- Illegal change: stone disappears for 5+ stable frames → ILLEGAL_CHANGE
- Board bump: 10+ positions change at once → BOARD_LOST (not 10 illegal changes)
- Tsumego setup: place stones one by one → SETUP_PROGRESS(1/23, 2/23, ...) → SETUP_COMPLETE
- Tsumego wrong color: place white where black expected → SETUP_PROGRESS reports mismatch
- Degraded: confidence drops → DEGRADED
- Capture sticky: CAPTURE_PENDING persists across frames until stones removed
- Transient noise: single-frame detection flicker does NOT trigger ILLEGAL_CHANGE

---

## Phase 4: Vision API, WebSocket & Frontend Infrastructure

### Task 4.1: Vision REST API

**Files:**
- Create: `katrain/web/api/v1/endpoints/vision.py`
- Modify: `katrain/web/server.py` — include router, start/stop VisionService in lifespan

**Endpoints (thin proxies to VisionService):**

```python
router = APIRouter(prefix="/api/v1/vision", tags=["vision"])

GET  /status              → { enabled, camera_status, pose_lock_status, sync_state }
GET  /stream              → MJPEG StreamingResponse (2-3 fps, backpressure-aware)
POST /pose-lock/confirm   → confirm_pose_lock()
POST /bind                → bind to session_id, set expected board from session state
POST /unbind              → unbind from session
POST /sync/reset          → reset_sync() — research mode only
POST /setup-mode          → enter_setup_mode(target_board) — tsumego
```

**MJPEG stream backpressure (Codex #7):**
- Only encode JPEG when at least one viewer is connected
- If encode takes longer than frame interval, drop oldest frame
- Track viewer count via connection/disconnection

### Task 4.2: Vision WebSocket

**Files:**
- Modify: `katrain/web/server.py`

```python
@app.websocket("/ws/vision")
async def vision_websocket(ws: WebSocket):
    # Relay sync events from VisionService to frontend
    # Also relay camera_status and pose_lock_status changes
```

**For session-bound pages (GamePage):** Vision events can optionally be multiplexed onto the existing game WebSocket (`/ws/{sessionId}`) as `type: "vision_event"` messages, to avoid a second WebSocket connection. The dedicated `/ws/vision` is used only by VisionSetupPage.

### Task 4.3: Server Lifespan Integration

**Files:**
- Modify: `katrain/web/server.py`

```python
@asynccontextmanager
async def lifespan(app):
    # ... existing setup ...
    if settings.vision_enabled:
        vision = VisionService(settings.vision_config)
        vision.start()
        app.state.vision = vision
    else:
        app.state.vision = None
    yield
    if app.state.vision:
        app.state.vision.stop()
```

**Move submission loop** (asyncio task in main process):
```python
async def vision_move_poller(app):
    """Poll vision worker for confirmed moves, submit via VisionPlayerBridge."""
    while True:
        vision = app.state.vision
        if vision and vision.bound_session_id:
            move_data = vision.get_confirmed_move()
            if move_data:
                session = app.state.session_manager.get_session(vision.bound_session_id)
                bridge = VisionPlayerBridge(session.katrain)
                bridge.submit_move(move)
                # After move processed, update expected board
                new_state = session.get_game_state()
                new_board = game_state_stones_to_board(new_state["stones"])
                vision.set_expected_board(new_board)
        await asyncio.sleep(0.1)
```

### Task 4.4: Frontend API Client

**Files:**
- Modify: `katrain/web/ui/src/api.ts`

Add vision API methods:
```typescript
visionStatus: () => fetch("/api/v1/vision/status").then(r => r.json()),
visionConfirmPoseLock: () => apiPost("/api/v1/vision/pose-lock/confirm", {}),
visionBind: (sessionId: string) => apiPost("/api/v1/vision/bind", { session_id: sessionId }),
visionUnbind: () => apiPost("/api/v1/vision/unbind", {}),
visionResetSync: () => apiPost("/api/v1/vision/sync/reset", {}),
visionSetupMode: (targetBoard: number[][]) => apiPost("/api/v1/vision/setup-mode", { target_board: targetBoard }),
```

### Task 4.5: Frontend Vision Context & Hooks

**Files:**
- Create: `katrain/web/ui/src/kiosk/context/VisionContext.tsx`
- Create: `katrain/web/ui/src/kiosk/hooks/useVision.ts`
- Create: `katrain/web/ui/src/kiosk/hooks/useVisionSync.ts`

**VisionContext:** Polls `/api/v1/vision/status` every 3s, provides `{ enabled, cameraConnected, poseLocked, syncState }`.

**useVision:** Simple accessor for vision status.

**useVisionSync:** Connects to vision WebSocket (or listens to game WebSocket for `vision_event` messages). Returns `syncEvents`, `latestEvent`, `setupProgress`, `isSetupComplete`. Auto-binds on mount (with sessionId), auto-unbinds on unmount.

### Task 4.6: StatusBar Vision Indicators

**Files:**
- Modify: `katrain/web/ui/src/kiosk/components/layout/StatusBar.tsx`

Add two icons next to existing engine status dot:
- Camera icon: red (disconnected) / green (connected). Clickable → navigates to `/kiosk/vision/setup`.
- Board pose icon (shown only after pose lock): green (synced) / yellow (setup/calibrating) / red (mismatch/lost).

**Note (Codex #2.4):** StatusBar is only visible in KioskLayout-wrapped pages. GamePage (fullscreen) needs its own status overlay — handled in Task 5.2.

### Task 4.7: Vision Setup Page

**Files:**
- Create: `katrain/web/ui/src/kiosk/pages/VisionSetupPage.tsx`
- Modify: `katrain/web/ui/src/kiosk/KioskApp.tsx` — add route

**Page layout:**
```
┌──────────────────────────────────────────────┐
│  StatusBar                                    │
├──────────────────────────────────────────────┤
│                                               │
│   ┌──────────────────────────────────────┐   │
│   │  MJPEG Stream <img> tag              │   │
│   │  /api/v1/vision/stream               │   │
│   │  Grid overlay + stone detection      │   │
│   └──────────────────────────────────────┘   │
│                                               │
│   "正在检测棋盘..." / "棋盘已识别"            │
│                                               │
│   [ 确认 ]  [ 返回 ]                         │
└──────────────────────────────────────────────┘
```

Route: `<Route path="vision/setup" element={<VisionSetupPage />} />`

On confirm: calls `POST /api/v1/vision/pose-lock/confirm`, then navigates back.

MJPEG `<img>` fallback: if stream disconnects, show placeholder with "摄像头连接中断" message and retry button.

---

## Phase 5: Module Integration

**Order: GamePage first (standard session) → Research (fix routing gap, then integrate) → Tsumego (frontend-driven)**

### Task 5.1: Sync Alert Components

**Files:**
- Create: `katrain/web/ui/src/kiosk/components/vision/VisionSyncOverlay.tsx`
- Create: `katrain/web/ui/src/kiosk/components/vision/CaptureGuide.tsx`
- Create: `katrain/web/ui/src/kiosk/components/vision/BoardSetupGuide.tsx`
- Create: `katrain/web/ui/src/kiosk/components/vision/AmbiguousStoneAlert.tsx`

**Alert hierarchy (Codex #Phase 5):**

Non-blocking (snackbar/toast):
- Camera status changes
- AI move placement hint: "AI 落子 D4，请在棋盘上摆放"
- Ambiguous stone: "无法确定落子位置，请调整棋子"
- Degraded mode: "检测质量下降，请检查光线"
- Board reacquired after loss

Blocking (modal):
- **CAPTURE_PENDING**: "请提走 D4、E4、E5 的 3 颗白子" — must resolve before next move. Auto-dismisses when stones removed. Escape hatch "跳过" button after 30s.
- **Tsumego setup incomplete**: Full-screen guide blocks interaction until physical board matches.
- **Severe mismatch / BOARD_LOST** lasting >10s: "棋盘检测异常，请检查摄像头和棋盘位置"

### Task 5.2: GamePage Integration

**Files:**
- Modify: `katrain/web/ui/src/kiosk/pages/GamePage.tsx`

**Changes:**
1. On mount: if vision enabled and pose locked, call `API.visionBind(sessionId)`. On unmount: `API.visionUnbind()`.
2. Add `<VisionSyncOverlay />` — listens to vision events via game WebSocket (`type: "vision_event"`).
3. **Floating status bar** for fullscreen GamePage (since no KioskLayout StatusBar): small translucent overlay in corner showing camera + sync status icons.
4. AI move toast: when `gameState` updates with AI's move, show non-blocking toast "AI 落子 {position}，请在棋盘上摆放". Auto-dismiss when vision detects stone placed.
5. Camera disconnect: if camera goes offline mid-game, dismiss all vision overlays, show toast "摄像头断开，已切换为触屏模式". Game continues with touch input only.

### Task 5.3: Research Page — Fix Routing Gap + Integration

**Files:**
- Modify: `katrain/web/ui/src/kiosk/KioskApp.tsx` — add research session route
- Create or modify: research session game page (may reuse GamePage with `mode="research"`)
- Modify: `katrain/web/ui/src/kiosk/pages/ResearchPage.tsx` — verify navigation target

**Codex #2.3:** `ResearchPage.tsx:45` navigates to `/kiosk/research/session/${sessionId}` but the route doesn't exist. Must fix this first.

Options:
- a) Add route: `<Route path="research/session/:sessionId" element={<GamePage mode="research" />} />`
- b) Create dedicated `ResearchSessionPage` if research needs different layout

**Research vision integration:**
- Same as GamePage sync + overlay
- Additional: "重新同步" button in the control panel
- **Resync semantics (Codex #9):** When user clicks "重新同步":
  1. Read current observed_board from vision worker
  2. Create a setup node in KaTrain game tree (AE clear + AB/AW for current stones)
  3. Update session state, frontend board, and vision expected board all together
  4. This is a POST to a new endpoint: `POST /api/research/resync` which handles game tree mutation

### Task 5.4: Tsumego Integration

**Files:**
- Modify: `katrain/web/ui/src/kiosk/pages/TsumegoProblemPage.tsx`

**Codex #2.2:** This page uses `useTsumegoProblem` (frontend-local state), NOT WebSession. Cannot use `visionBind(sessionId)`.

**Integration pattern:**
1. On mount: if vision enabled, extract initial position from problem data and call `API.visionSetupMode(targetBoard)`.
2. Show `<BoardSetupGuide />`:
   - Full-screen camera view with overlay (matched stones green, missing stones red dotted)
   - Small reference board in corner showing target position
   - Progress: "已匹配 15/23 颗子"
   - User can place stones in ANY order; wrong-color stones shown with X
   - When all matched → SETUP_COMPLETE → "开始答题" button
   - "跳过设置" → disables vision for this problem, allows touch input
3. During solving: vision updates expected board based on `useTsumegoProblem` state changes (frontend sends new expected board after each move via `API.visionSetupMode` or a new `API.visionSetExpectedBoard`).
4. On problem complete / navigate to next: reset vision, re-enter setup mode for new problem.

---

## Phase 6: Backend Configuration

### Task 6.1: CLI Arguments & Config

**Files:**
- Create: `katrain/vision/config_service.py`
- Modify: `katrain/web/core/config.py` — add vision config fields
- Modify: `katrain/__main__.py` — add CLI args

```
python -m katrain --ui web \
  --vision-backend onnx \
  --vision-model /path/to/best.onnx \
  --vision-camera 0
```

```python
@dataclass
class VisionServiceConfig:
    enabled: bool = False
    backend: str = "onnx"            # "onnx" | "rknn" | "ultralytics"
    model_path: str = ""
    camera_device: int = 0
    board_size: int = 19
    confidence_threshold: float = 0.5
    imgsz: int = 960
    use_clahe: bool = False
    intrinsics_file: str | None = None  # persistent camera calibration .npz
    process_mode: str = "worker"     # "worker" (subprocess) | "inprocess" (dev)
```

When `--vision-model` is provided, vision is automatically enabled.

---

## Test Plan

### New test files

| Test File | Phase | Coverage |
|-----------|-------|----------|
| `tests/test_vision/test_inference_contract.py` | 1 | Fixed ONNX artifact input/output, metadata sidecar |
| `tests/test_vision/test_onnx_backend.py` | 1 | ONNX pre/post processing, NMS, Detection output |
| `tests/test_vision/test_replay.py` | 1 | Recorded frame sequence replay through pipeline |
| `tests/test_vision/test_camera.py` | 2 | Camera open/close/detect (mocked cv2) |
| `tests/test_vision/test_worker.py` | 2 | Worker lifecycle, IPC command/response |
| `tests/test_vision/test_sync.py` | 3 | All sync states, transitions, edge cases (12+ scenarios) |
| `tests/test_vision/test_game_state_conversion.py` | 3 | Tuple stones → board matrix with Y-flip |
| `kiosk/__tests__/VisionSetupPage.test.tsx` | 4 | MJPEG display, confirm button, stream fallback |
| `kiosk/__tests__/VisionSyncOverlay.test.tsx` | 5 | All popup/toast variants, auto-dismiss, blocking vs non-blocking |
| `kiosk/__tests__/BoardSetupGuide.test.tsx` | 5 | Progress display, setup complete, skip button |

### Existing tests requiring updates

| Test File | Change |
|-----------|--------|
| `tests/test_vision/test_pipeline.py` | Verify pipeline works with mocked inference backend |
| `tests/test_vision/test_stone_detector.py` | Test backend selection factory |
| `kiosk/__tests__/GamePage.test.tsx` | Verify VisionSyncOverlay renders when vision enabled |
| `kiosk/__tests__/StatusBar.test.tsx` | Verify camera/board status icons |

### On-device verification (RK3562)

- [ ] Vision worker process starts, camera detected
- [ ] Total system RSS (Chromium + FastAPI + vision worker) < 1.8GB
- [ ] `/kiosk/vision/setup` shows MJPEG stream, grid overlay works
- [ ] Pose lock confirmed, StatusBar shows green icons
- [ ] 对弈: place stone → digital board updates within 2s
- [ ] 对弈: AI responds → toast shows position → place stone → sync resumes
- [ ] 对弈: capture → "请提走" alert → remove stones → alert dismisses
- [ ] 对弈: camera disconnect → falls back to touch-only, game continues
- [ ] 死活题: setup guide → place initial stones → progress updates → "开始答题"
- [ ] 死活题: skip setup → touch-only mode works
- [ ] 研究: place/remove stones → resync option works
- [ ] Soak test: 30+ minutes continuous operation, no memory leak or crash
- [ ] Camera hot-plug: unplug → "disconnected" → replug → "connected" (auto-recover)

### Soak test (Phase 6 gate)

```bash
# Run on RK3562 for 30+ minutes, monitor:
watch -n 5 'ps aux | grep -E "katrain|chromium" | awk "{print \$6/1024\"MB\", \$11}"'
```

Must verify:
- No RSS growth >50MB over 30 minutes
- **1-hour stress test (Gemini #4):** Run a full game session while Chromium has kiosk page active. Monitor for memory leaks, swap growth, and UI responsiveness degradation. Swap usage must stay < 500MB under steady-state.

---

## Implementation Order

| Phase | Tasks | Effort | Dependencies | Notes |
|-------|-------|--------|-------------|-------|
| **0** | Feasibility Gate | ~2h | RK3562 hardware | Blocking: must pass before Phase 1 |
| **1** | 1.1-1.7: Inference contract + backends + replay | ~6h | Phase 0 results | No UI work yet |
| **2** | 2.1-2.3: Camera + worker process + service proxy | ~4h | Phase 1 (backends) | Core infrastructure |
| **3** | 3.1-3.3: Sync state machine + GameState conversion | ~3h | None (can parallel with Phase 2) | Well-testable in isolation |
| **4** | 4.1-4.7: API + WebSocket + frontend infra + setup page | ~5h | Phases 2+3 | REST + React |
| **5** | 5.1-5.4: Module integration (Game→Research→Tsumego) | ~5h | Phase 4 | Research route fix included |
| **6** | Config + soak test | ~2h | Phase 5 | Final validation gate |

**Parallelizable:** Phase 1 tasks 1.1-1.4 are independent. Phase 3 can run parallel with Phase 2. Phase 5 tasks 5.2-5.4 are independent.

---

## Module Structure (New & Modified Files)

```
katrain/vision/
├── inference/                     # NEW — pluggable backends
│   ├── __init__.py
│   ├── base.py                    # InferenceBackend protocol
│   ├── onnx_backend.py            # ONNX Runtime inference
│   ├── rknn_backend.py            # RKNN NPU inference (experimental)
│   └── ultralytics_backend.py     # Dev/training backend
├── camera.py                      # NEW — camera lifecycle manager
├── sync.py                        # NEW — SyncStateMachine + GameState conversion
├── worker.py                      # NEW — separate process: capture + infer + sync
├── ipc.py                         # NEW — IPC protocol (WorkerState, WorkerCommand)
├── worker_inprocess.py            # NEW — in-process adapter for dev
├── service.py                     # NEW — main-process proxy to worker
├── config_service.py              # NEW — VisionServiceConfig
├── stone_detector.py              # MODIFIED — use InferenceBackend
├── pipeline.py                    # EXISTING (no changes)
├── board_finder.py                # EXISTING (no changes)
├── board_state.py                 # EXISTING (no changes)
├── move_detector.py               # EXISTING (no changes)
├── motion_filter.py               # EXISTING (no changes)
├── coordinates.py                 # EXISTING (no changes)
├── katrain_bridge.py              # EXISTING (no changes)
├── katrain_integration.py         # EXISTING (reused by main process)
├── config.py                      # EXISTING (no changes)
├── tools/
│   ├── export_onnx.py             # NEW — .pt → .onnx + model.meta.json
│   ├── export_rknn.py             # NEW — .onnx → .rknn (experimental)
│   ├── benchmark_onnx.py          # NEW — SBC performance benchmarking
│   └── ... (existing tools unchanged)
└── DEPLOY.md                      # NEW — SBC deployment guide

katrain/web/
├── server.py                      # MODIFIED — lifespan, vision WS, move poller
├── api/v1/endpoints/
│   └── vision.py                  # NEW — vision REST API
└── ui/src/kiosk/
    ├── KioskApp.tsx               # MODIFIED — vision setup route + research session route
    ├── context/
    │   └── VisionContext.tsx       # NEW
    ├── hooks/
    │   ├── useVision.ts           # NEW
    │   └── useVisionSync.ts       # NEW
    ├── components/
    │   ├── layout/
    │   │   └── StatusBar.tsx      # MODIFIED — camera/pose icons
    │   └── vision/                # NEW
    │       ├── VisionSyncOverlay.tsx
    │       ├── CaptureGuide.tsx
    │       ├── BoardSetupGuide.tsx
    │       └── AmbiguousStoneAlert.tsx
    └── pages/
        ├── VisionSetupPage.tsx    # NEW
        ├── GamePage.tsx           # MODIFIED — vision sync + floating status
        ├── TsumegoProblemPage.tsx # MODIFIED — setup guide
        └── ResearchPage.tsx       # MODIFIED (+ route fix in KioskApp)
```
