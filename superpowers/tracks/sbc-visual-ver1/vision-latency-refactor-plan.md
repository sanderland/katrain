# Vision 预览延迟重构方案

> **日期:** 2026-04-07
> **问题:** 摄像头画面延迟 ~1 秒，用户体验不可接受
> **目标:** 实时画面延迟 < 100ms，算法叠加效果独立显示

---

## 1. 问题根因

当前架构是**单线程串行循环**：

```
采集帧 → motion filter → board finder (~30ms) → YOLO推理 (~600ms) → 编码预览 → 下一帧
                                                                       ↑
                                                              循环每 600ms+ 才转一圈
                                                              预览帧率 ≤ 1.5 FPS
```

即使有后台摄像头读取线程（最新帧始终可用），**预览编码仍然在处理循环内部**，被 YOLO 推理阻塞。用户看到的画面始终是 600ms+ 前的帧。

---

## 2. 目标架构

将 worker 进程拆分为**三个独立线程**：

```
┌─────────────────────────────────────────────────────────┐
│ Vision Worker Process                                    │
│                                                          │
│ ┌──────────────────────┐                                │
│ │ 摄像头读取线程 (已有)   │ ← 持续读取，持有最新帧         │
│ │ CameraManager._reader │                                │
│ └──────────┬─────────────┘                                │
│            │ latest_frame (lock-protected)                │
│            ├──────────────────────┐                       │
│            ▼                      ▼                       │
│ ┌──────────────────┐   ┌────────────────────────────┐   │
│ │ 预览线程 (新增)    │   │ 处理线程 (主循环改造)        │   │
│ │ 15-30 FPS         │   │ ~1-2 FPS (受推理限制)       │   │
│ │                    │   │                              │   │
│ │ 读最新帧           │   │ 读最新帧                     │   │
│ │ 缩放 + JPEG 编码   │   │ motion filter               │   │
│ │ 叠加算法延迟信息    │   │ board finder (~30ms)        │   │
│ │ → preview_queue    │   │ YOLO 推理 (~600ms)          │   │
│ │                    │   │ move detection + sync        │   │
│ │ 如果有检测结果:     │   │ → event_queue               │   │
│ │   叠加棋盘边界      │   │ → 更新共享的检测结果         │   │
│ │   叠加棋子位置      │   │                              │   │
│ │   叠加延迟数据      │   │                              │   │
│ └──────────────────┘   └────────────────────────────┘   │
│                                                          │
│ 共享状态 (lock-protected):                               │
│   - board_corners: 最近一次检测到的棋盘四角坐标            │
│   - detections: 最近一次 YOLO 检测到的棋子列表             │
│   - timing: { board_finder_ms, yolo_ms, total_ms }       │
└──────────────────────────────────────────────────────────┘
```

**关键设计：**
- 预览线程**直接从摄像头读取最新帧**，不经过任何处理
- 处理线程的结果（棋盘边界、棋子位置、延迟数据）通过**共享状态**传递给预览线程
- 预览线程在原始画面上**叠加**最近一次的检测结果，不阻塞等待新结果
- 两个线程完全独立，预览帧率不受推理速度影响

---

## 3. 具体改动

### 3.1 新增共享状态结构

**文件:** `katrain/vision/worker.py`

```python
@dataclass
class ProcessingOverlay:
    """Shared state between processing thread and preview thread."""
    board_corners: list[tuple[int, int]] | None = None  # 4 corners in raw frame coords
    detections: list[Detection] | None = None            # YOLO detection results
    warped_size: tuple[int, int] | None = None           # (w, h) of warped board
    transform_matrix: np.ndarray | None = None           # perspective transform M
    timing: dict[str, float] = field(default_factory=dict)  # ms timings
    # timing keys: "board_finder_ms", "yolo_ms", "total_ms"
```

### 3.2 改造 _VisionWorkerLoop

**文件:** `katrain/vision/worker.py`

**修改 `run()` 方法：**

```python
def run(self):
    self._running = True
    if not self._camera.open():
        logger.error("Failed to open camera, will keep retrying")
    try:
        self._init_inference()
    except Exception as e:
        logger.error("Failed to load inference backend: %s", e)
        self._running = False
        return

    # Shared overlay state (lock-protected)
    self._overlay = ProcessingOverlay()
    self._overlay_lock = threading.Lock()

    # Start preview thread (independent of processing)
    preview_thread = threading.Thread(
        target=self._preview_loop, daemon=True, name="preview"
    )
    preview_thread.start()

    # Main thread becomes the processing loop
    self._processing_loop()

    self._camera.close()
    logger.info("Worker process exiting")
```

**新增 `_preview_loop()` — 预览线程：**

```python
def _preview_loop(self):
    """Independent preview thread: reads latest camera frame, overlays
    detection results, encodes JPEG at high FPS."""
    interval = 1.0 / PREVIEW_FPS  # 67ms at 15 FPS
    while self._running:
        if not self._viewer_active:
            time.sleep(0.1)
            continue

        frame = self._camera.read_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        # Read overlay data (non-blocking)
        with self._overlay_lock:
            overlay = copy of self._overlay

        # Draw overlays on raw frame
        display = frame.copy()
        self._draw_overlays(display, overlay)

        # Resize and encode
        preview = self._resize_for_preview(display)
        _, jpeg = cv2.imencode(".jpg", preview,
                               [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

        # Put in preview queue (overwrite semantics)
        try:
            self._preview_queue.get_nowait()
        except queue.Empty:
            pass
        self._preview_queue.put(jpeg.tobytes())

        time.sleep(interval)
```

**新增 `_processing_loop()` — 处理线程（原主循环改造）：**

```python
def _processing_loop(self):
    """Processing loop: board detection + YOLO inference.
    Results written to shared overlay state for preview thread to consume."""
    while self._running:
        self._process_commands()

        frame = self._camera.read_frame()
        if frame is None:
            time.sleep(0.05)
            continue

        board_detected = False
        observed_board = None
        mean_confidence = 0.0

        if self._motion_filter.is_stable(frame):
            # --- Board detection ---
            t0 = time.monotonic()
            warped, found = self._board_finder.find_focus(
                frame, min_threshold=20,
                use_clahe=self._config.get("use_clahe", False)
            )
            board_finder_ms = (time.monotonic() - t0) * 1000

            if found and warped is not None:
                board_detected = True
                h, w = warped.shape[:2]

                # --- YOLO inference ---
                t1 = time.monotonic()
                detections = self._detector.detect(warped)
                yolo_ms = (time.monotonic() - t1) * 1000

                total_ms = board_finder_ms + yolo_ms

                # Update shared overlay state
                with self._overlay_lock:
                    self._overlay.board_corners = list(
                        self._board_finder.pre_corner_point
                    )
                    self._overlay.detections = detections
                    self._overlay.warped_size = (w, h)
                    self._overlay.transform_matrix = (
                        self._board_finder.last_transform_matrix
                    )
                    self._overlay.timing = {
                        "board_finder_ms": round(board_finder_ms, 1),
                        "yolo_ms": round(yolo_ms, 1),
                        "total_ms": round(total_ms, 1),
                    }

                # Board state + move detection
                observed_board = self._state_extractor.detections_to_board(
                    detections, img_w=w, img_h=h
                )
                if detections:
                    mean_confidence = (
                        sum(d.confidence for d in detections) / len(detections)
                    )
                if self._bound:
                    move_result = self._move_detector.detect_new_move(
                        observed_board
                    )
                    if move_result is not None:
                        row, col, color = move_result
                        self._event_queue.put(
                            ConfirmedMove(col=col, row=row, color=color)
                        )

        # Sync state machine
        if self._bound:
            events = self._sync.update(
                observed_board=observed_board,
                mean_confidence=mean_confidence,
                board_detected=board_detected,
            )
            for evt in events:
                self._event_queue.put(
                    {"type": evt.type.value, "data": evt.data}
                )

        self._maybe_publish_status()
        # No throttle — processing runs as fast as inference allows
```

### 3.3 新增叠加绘制方法

**文件:** `katrain/vision/worker.py`

```python
def _draw_overlays(self, frame: np.ndarray, overlay: ProcessingOverlay) -> None:
    """Draw detection results and timing info on the raw camera frame."""
    h, w = frame.shape[:2]

    # 1. 棋盘边界 (绿色四边形)
    if overlay.board_corners:
        corners = np.array(overlay.board_corners, dtype=np.int32)
        cv2.polylines(frame, [corners.reshape((-1, 1, 2))],
                      True, (0, 255, 0), 2)

    # 2. 棋子位置 (从 warped 坐标反投影到原始帧)
    if (overlay.detections and overlay.transform_matrix is not None
            and overlay.warped_size):
        M_inv = np.linalg.inv(overlay.transform_matrix)
        ww, wh = overlay.warped_size
        for det in overlay.detections:
            # Detection coords are in warped image space
            pt = np.float32([[det.x_center, det.y_center]]).reshape(-1, 1, 2)
            orig_pt = cv2.perspectiveTransform(pt, M_inv)
            ox, oy = int(orig_pt[0, 0, 0]), int(orig_pt[0, 0, 1])
            color = (0, 0, 0) if det.class_id == 0 else (255, 255, 255)
            cv2.circle(frame, (ox, oy), 8, color, -1)
            cv2.circle(frame, (ox, oy), 8, (0, 255, 0), 1)

    # 3. 延迟信息 (左下角半透明背景)
    if overlay.timing:
        lines = [
            f"Board: {overlay.timing.get('board_finder_ms', 0):.0f}ms",
            f"YOLO:  {overlay.timing.get('yolo_ms', 0):.0f}ms",
            f"Total: {overlay.timing.get('total_ms', 0):.0f}ms",
        ]
        y_base = h - 20
        for line in reversed(lines):
            (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (5, y_base - th - 4), (15 + tw, y_base + 4),
                          (0, 0, 0), -1)
            cv2.putText(frame, line, (10, y_base),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            y_base -= th + 10
```

### 3.4 删除旧的 _maybe_send_preview

`_maybe_send_preview()` 方法不再需要，预览编码完全由 `_preview_loop()` 负责。移除所有对它的调用。

### 3.5 不需要修改的文件

以下文件**无需修改**，接口保持不变：
- `katrain/vision/camera.py` — 后台读取线程已有
- `katrain/vision/service.py` — 通过 preview_queue 取帧，接口不变
- `katrain/web/api/v1/endpoints/vision.py` — MJPEG 流端点不变
- `katrain/web/ui/src/kiosk/pages/VisionSetupPage.tsx` — 前端不变

---

## 4. 叠加画面效果设计

最终用户看到的画面：

```
┌────────────────────────────────────────┐
│                                        │
│     原始摄像头实时画面 (1280x720)        │
│                                        │
│     ┌─────────────────────────┐        │
│     │  绿色四边形 = 棋盘边界    │        │
│     │                         │        │
│     │  ● ○ = 检测到的黑/白棋子  │        │
│     │                         │        │
│     └─────────────────────────┘        │
│                                        │
│  ┌─────────────────────┐               │
│  │ Board:  28ms        │ ← 半透明背景   │
│  │ YOLO:  612ms        │               │
│  │ Total: 640ms        │               │
│  └─────────────────────┘               │
└────────────────────────────────────────┘
```

**延迟信息说明：**
- **Board:** OpenCV 棋盘边界检测 + 透视变换耗时
- **YOLO:** YOLOv11 棋子检测 + 位置判定耗时
- **Total:** 两者总耗时（= 算法后处理一个完整周期）

用户可以通过延迟数据直观判断：
- 更换模型（n → s → m）对推理延迟的影响
- 更换分辨率（640 → 960 → 1280）对棋盘检测的影响
- 总延迟是否在可接受范围内

---

## 5. 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `katrain/vision/worker.py` | 拆分为 preview_loop + processing_loop 双线程；新增 ProcessingOverlay 共享状态；新增 _draw_overlays 叠加绘制；删除 _maybe_send_preview |

---

## 6. 预期效果

| 指标 | 修改前 | 修改后 |
|------|--------|--------|
| 实时画面延迟 | ~800-1000ms | **< 100ms** |
| 画面帧率 | ~1.5 FPS | **15 FPS** |
| 叠加效果刷新率 | 与画面同步 | ~1-2 FPS（跟随推理速度） |
| 延迟数据显示 | 无 | 实时显示 Board/YOLO/Total |

---

## 7. 验证步骤

1. 修改代码，git push
2. K7C 上 git pull，重启 katrain
3. 打开 vision setup 页面：
   - 摄像头画面应该流畅（15 FPS，无卡顿）
   - 用手在镜头前挥动，画面应即时响应（< 100ms 延迟）
4. 将摄像头对准棋盘：
   - 绿色四边形标出棋盘边界
   - 检测到的棋子以黑/白圆点标出
   - 左下角显示 Board / YOLO / Total 延迟数据
5. 更换模型路径（yolo11n → yolo11s），观察 YOLO 延迟变化
6. 更换分辨率（1280x720 → 640x480），观察 Board 延迟变化
