# Vision Pipeline V2: Letterbox + Hough Grid Calibration + Camera Focus

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three critical issues in the Go board vision pipeline that currently prevent accurate stone detection and grid coordinate mapping:
1. YOLO preprocessing squishes non-square warped images, distorting stones (2→13 detections with letterbox)
2. Board detection finds wood boundary, not grid boundary — stones can't map to 19x19 coordinates
3. Camera auto-focus not stabilized at startup — blurry frames drastically reduce detection accuracy

**Context:** Testing on real HIK 2K camera frames showed:
- Squish preprocessing: 2 detections (max conf 49%)
- Letterbox preprocessing: 13 detections (max conf 97%), all stones found
- Blurry vs sharp frame: 9 vs 13 detections — focus is the #1 factor
- Hough line detection successfully finds all 19x19 grid lines and 361 intersections

**Scope:** Backend inference only. No frontend changes. No model retraining.

---

## Task 1: Letterbox preprocessing in ONNX and RKNN backends

**Files:**
- Modify: `katrain/vision/inference/onnx_backend.py` (lines 123-140)
- Modify: `katrain/vision/inference/rknn_backend.py` (lines 136-161)
- Modify: `katrain/vision/inference/onnx_backend.py` `_postprocess` (lines 142+)
- Modify: `katrain/vision/inference/rknn_backend.py` `_postprocess` (lines 163+)
- Add test: `tests/test_vision/test_letterbox.py`

**Rationale:** The warped board image is typically 1.5-1.6:1 aspect ratio due to perspective. Current `_preprocess` does `cv2.resize(image, (size, size))` which squishes stones into ovals. YOLO was trained on round stones, so confidence drops from 89% to 49%. Letterbox (resize preserving aspect + gray padding) fixes this completely.

**Step 1: Add shared letterbox utility**

Create a `_letterbox` static method usable by both backends. Add to `katrain/vision/inference/base.py` or as a module-level function:

```python
def letterbox_preprocess(image: np.ndarray, target_size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize image preserving aspect ratio, pad with gray (114) to square.
    
    Returns:
        (padded_image, scale, x_offset, y_offset)
    """
    h, w = image.shape[:2]
    scale = target_size / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
    y_off = (target_size - new_h) // 2
    x_off = (target_size - new_w) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return canvas, scale, x_off, y_off
```

**Step 2: Update `OnnxBackend._preprocess`**

Replace `cv2.resize(image, (size, size))` with `letterbox_preprocess`. Store `self._last_scale`, `self._last_x_off`, `self._last_y_off` for postprocess coordinate correction.

**Step 3: Update `OnnxBackend._postprocess`**

After decoding cx/cy from model output (in `imgsz` pixel space), subtract letterbox offsets and divide by scale to map back to original image coordinates:

```python
cx_orig = (cx - self._last_x_off) / self._last_scale
cy_orig = (cy - self._last_y_off) / self._last_scale
```

Same for bounding box w/h: divide by scale.

**Step 4: Update `RknnBackend._preprocess` and `_postprocess`**

Same changes as ONNX backend. The RKNN backend has two input formats (`nhwc_uint8` and `nchw_float32`) — apply letterbox before format conversion in both paths.

**Step 5: Add tests**

Test that:
- `letterbox_preprocess` preserves aspect ratio (output is square, content centered)
- A 400x257 image letterboxed to 640 has correct scale/offsets
- Postprocess coordinate remapping is inverse of preprocess
- Detection count on the test warped image (`/tmp/sharp_warped.jpg` or synthetic) improves vs squish

**Step 6: Commit**

```
feat(vision): letterbox preprocessing for ONNX and RKNN backends

Replaces squish resize with aspect-ratio-preserving letterbox + gray
padding. Stones stay round, improving detection from 2→13 on real
board frames. Coordinate postprocessing accounts for padding offsets.
```

**Verification:**
```bash
CI=true uv run pytest tests/test_vision/ -x -q
```

---

## Task 2: Camera auto-focus stabilization

**Files:**
- Modify: `katrain/vision/camera.py` — `open()` method (line ~106)

**Rationale:** HIK 2K camera needs ~2-3 seconds after opening for auto-focus and auto-exposure to stabilize. Current code starts reading immediately after `cap.isOpened()`, producing blurry frames that reduce YOLO detection from 13→9 stones and drop white stone detection entirely.

**Step 1: Add focus stabilization to `CameraManager.open()`**

After `self._cap = cap` and before starting the reader thread, drain frames for a configurable warmup period:

```python
# Drain frames to let auto-focus and auto-exposure settle
warmup_seconds = 2.0
import time
deadline = time.monotonic() + warmup_seconds
while time.monotonic() < deadline:
    cap.read()
logger.info("Camera %s focus stabilized (%0.1fs warmup)", self._device_id, warmup_seconds)
```

Also enable auto-focus if supported:
```python
cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
```

**Step 2: Make warmup configurable**

Add `warmup_seconds: float = 2.0` parameter to `CameraManager.__init__`.

**Step 3: Commit**

```
fix(vision): wait for camera auto-focus before reading frames

Drains frames for 2s after opening to let auto-focus and auto-exposure
settle. Prevents blurry initial frames that halve detection accuracy.
```

**Verification:** Capture frame before/after warmup and compare file sizes (sharp frames are 2-3x larger due to more detail).

---

## Task 3: Hough grid calibration module

**Files:**
- Create: `katrain/vision/grid_calibrator.py`
- Add test: `tests/test_vision/test_grid_calibrator.py`

**Rationale:** Board detection (color segmentation) finds the wood boundary, which includes a ~16-20mm border around the 19x19 grid. Without knowing the exact border offset, stones can't be accurately mapped to grid coordinates. Hough line detection can find the actual grid lines and compute the precise border offset. This only needs to run once at startup (when the board is empty or has few stones) since the physical board doesn't move.

**Step 1: Create `GridCalibrator` class**

```python
class GridCalibrator:
    """Detects 19x19 grid lines via Hough transform and computes border offsets.
    
    Run once on a warped board image (ideally with few/no stones) to calibrate
    the mapping between pixel coordinates and grid positions.
    """
    
    def calibrate(self, warped: np.ndarray) -> GridCalibration | None:
        """Detect grid lines and return calibration result, or None if failed."""
        
    def _detect_lines(self, warped: np.ndarray) -> tuple[list[float], list[float]]:
        """Detect horizontal and vertical line positions using HoughLinesP."""
        
    def _fit_regular_grid(self, positions: list[float], n_lines: int = 19) -> tuple[float, float] | None:
        """RANSAC fit: find (offset, spacing) that best explains detected line positions."""
```

**Step 2: Implement line detection pipeline**

Based on the successful approach-B prototype (`/tmp/hough_grid_detect.py`):

1. Convert warped to grayscale
2. CLAHE for contrast enhancement
3. Adaptive threshold (inverted — dark lines on light wood)
4. Directional morphological filtering:
   - Horizontal kernel `(width//15, 1)` → suppress stones, keep H lines
   - Vertical kernel `(1, height//15)` → suppress stones, keep V lines
5. `cv2.HoughLinesP` on each directional mask
6. Cluster line segments by position (weighted histogram)
7. RANSAC grid fitting: find 19 evenly-spaced lines

**Step 3: Return `GridCalibration` dataclass**

```python
@dataclass
class GridCalibration:
    h_offset: float     # first horizontal line y-position (pixels)
    h_spacing: float    # horizontal line spacing (pixels)
    v_offset: float     # first vertical line x-position (pixels)
    v_spacing: float    # vertical line spacing (pixels)
    border_top: float   # pixels from image top to first H line
    border_bottom: float
    border_left: float
    border_right: float
    confidence: float   # 0-1 quality metric (spacing CV, line count)
```

**Step 4: Integrate with worker**

In `_VisionWorkerLoop._processing_loop` (`worker.py`):
- After first successful `find_focus`, run `GridCalibrator.calibrate(warped)`
- Store result in `self._grid_calibration`
- Pass calibration to `BoardStateExtractor` for coordinate mapping
- Only re-calibrate on pose reset (board physically moved)

**Step 5: Update `BoardStateExtractor` to use calibration**

When `GridCalibration` is available, use `(v_offset, v_spacing, h_offset, h_spacing)` directly for pixel→grid mapping instead of the geometric calculation based on `BoardConfig` border values.

```python
def pixel_to_grid_calibrated(x_px, y_px, cal: GridCalibration) -> tuple[int, int]:
    col = round((x_px - cal.v_offset) / cal.v_spacing)
    row = round((y_px - cal.h_offset) / cal.h_spacing)
    return max(0, min(18, col)), max(0, min(18, row))
```

**Step 6: Add tests**

- Synthetic test: create an image with known grid lines, verify calibrator finds correct spacing/offset
- Verify `pixel_to_grid_calibrated` maps correctly
- Edge case: too few lines detected → returns None (graceful fallback)

**Step 7: Commit**

```
feat(vision): Hough-based grid calibration for accurate coordinate mapping

Detects 19x19 grid lines via HoughLinesP + RANSAC fitting on the warped
board image. Computes pixel-accurate border offsets and grid spacing,
replacing the approximate BoardConfig-based geometric mapping.
Runs once at startup when the board has few stones.
```

**Verification:**
```bash
CI=true uv run pytest tests/test_vision/ -x -q
# Manual: run on /tmp/hik_sharp.jpg, verify 19 H + 19 V lines detected
python3 -c "
from katrain.vision.board_finder import BoardFinder
from katrain.vision.grid_calibrator import GridCalibrator
import cv2
img = cv2.imread('/tmp/hik_sharp.jpg')
finder = BoardFinder()
warped, _ = finder.find_focus(img, min_threshold=20)
cal = GridCalibrator().calibrate(warped)
print(cal)
"
```

---

## Task 4: End-to-end integration test

**Files:**
- Create: `tests/test_vision/test_e2e_pipeline.py`

**Rationale:** After Tasks 1-3, verify the full pipeline works end-to-end: camera frame → board detection → grid calibration → YOLO with letterbox → stone-to-grid mapping.

**Step 1: Write integration test**

Using the saved test frame (`/tmp/hik_sharp.jpg` or a committed test fixture):
1. `BoardFinder.find_focus` → warped image
2. `GridCalibrator.calibrate` → grid calibration
3. `StoneDetector.detect` (with letterbox) → detections
4. Map each detection to grid coordinates using calibration
5. Assert: expected stones are at expected grid positions

**Step 2: Add test fixture**

Save a representative board frame to `tests/data/` (or use synthetic generation).

**Step 3: Commit**

```
test(vision): end-to-end pipeline integration test
```

**Verification:**
```bash
CI=true uv run pytest tests/test_vision/test_e2e_pipeline.py -v
```

---

## Dependencies

```
Task 1 (letterbox) ──→ Task 4 (e2e test)
Task 2 (camera)    ──→ Task 4
Task 3 (Hough)     ──→ Task 4

Tasks 1, 2, 3 are independent of each other and can be implemented in parallel.
```

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Hough fails in dim lighting | Grid calibration returns None | Fallback to BoardConfig geometric mapping (current behavior) |
| Letterbox changes break RKNN on RK3576 | Inference fails | Test both `nhwc_uint8` and `nchw_float32` paths |
| Camera warmup delays startup | 2s slower launch | Acceptable; consider making warmup async |
| Hough fails with many stones | Can't calibrate mid-game | Run calibration at game start (empty board); cache result |

## Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| Stone detection (clear frame) | 2 (squish) | 13 (letterbox) |
| White stone detection | 0-2 | 6 (all) |
| Max confidence | 49% | 97% |
| Grid coordinate accuracy | ~1 grid spacing error | Sub-grid-spacing accuracy |
| YOLO latency (RKNN NPU) | 80ms | ~80ms (unchanged) |
| Camera startup | Immediate (blurry) | +2s warmup (sharp) |
