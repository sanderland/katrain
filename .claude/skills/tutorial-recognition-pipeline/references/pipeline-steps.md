# Pipeline Steps Detail

## S0: Bounding Box Detection (pure CV, <100ms)

Detect individual diagram regions on a multi-diagram page using `cv_detect_bboxes()`.

**Method**: Morphological line detection → find regions with dense horizontal AND vertical lines.
1. Binary threshold (< 160)
2. Detect H lines: morph open with `(min_line_len, 1)` kernel
3. Detect V lines: morph open with `(1, min_line_len)` kernel
4. Bitwise OR → dilate → find contours → filter by area
5. Sort top-to-bottom, left-to-right

Output: list of `(x1, y1, x2, y2)` tuples in pixel coordinates.

## Deskew: Straighten Tilted Scans (<50ms)

Correct rotation from scanned book pages using `deskew_board()`.

**Method**: HoughLinesP angle detection → warpAffine rotation.
1. Detect long lines (min length = image/3) with high-precision angle resolution (π/1800)
2. Classify lines as near-horizontal (<10°) or near-vertical (80-100°)
3. Compute trimmed mean angle (remove outlier 20%) for robustness
4. Only correct small tilts (0.1°–5.0°); skip if below threshold
5. Apply `cv2.warpAffine` with white border fill

Each figure is independently deskewed — angle is adaptive per crop image.

**Debug visualization**: Two overlay images for verification:
- `deskew_debug.png` — grid lines projected back (inverse rotation) onto original crop. Shows both deskew accuracy and grid alignment on the untouched image.
- `grid_debug.png` — grid lines drawn on deskewed crop. Shows grid detection accuracy after deskew correction.

Both are shown side-by-side in the frontend `RecognitionDebugPanel` under the "纠偏与网格" section.

## S1: Region Calibration (pure CV, <30ms)

Determine which portion of the 19x19 board is shown using `calibrate_region()` in `katrain/web/tutorials/vision/region_calibrator.py`.

**Pre-step: Border detection** (`_detect_borders()` → `_count_extending_lines()`):
- For each edge (left/right/top/bottom), check if grid lines extend past the outermost line toward the image boundary
- If few/no lines extend → edge IS a board border (grid lines stop here)
- If many lines extend → edge is NOT a border (board continues beyond crop)
- Threshold: `extending_count / total_lines < 0.08` → is a border
- Extension detection uses a tolerance band (`spacing × 0.25`) and minimum extension length (`spacing × 0.4`)

**Multi-evidence scoring** over all possible (col_start, row_start) candidates:
- **Border hard constraints** (-100): if edge is NOT a border, hard-reject candidates placing board edge there
- **Border match** (+5.0 / -5.0): if edge IS a border, reward aligned candidates (+5.0) and penalize misaligned ones (-5.0)
- **Star point matching** (+1.5 each): hoshi at known 19×19 positions (`_count_star_matches()`)
- **Layout bias** (+0.5): prefer col_start=0 / row_start=0 (most diagrams show corners)
- **Bounds check** (-100): col_start + num_cols > 19 → impossible

Rules:
- No lines extending past left edge → left is a border → `col_start = 0`
- No lines extending past right edge → right is a border → `col_start = 19 - num_v_lines`
- Star points at known positions constrain the solution
- Evidence stored as list: `["left_border", "top_border", "stars=4"]`

## S2: OpenCV Grid Detection (`cv_detect_grid()`)

Morphological line detection + sub-pixel centroid refinement for precise grid positions.

1. Threshold to binary (< 160)
2. Horizontal kernel (`min_line_len × 1`) → morphological open → horizontal lines
3. Vertical kernel (`1 × min_line_len`) → morphological open → vertical lines
4. Project to 1D (sum along axis)
5. Peak detection with minimum distance constraint → integer pixel positions
6. Gap filling: if gap between adjacent lines > 1.6× spacing, interpolate missing lines
7. **Sub-pixel refinement** (`_refine_positions()`): weighted centroid on morphological line image within ±40% spacing window → float positions

Returns: `(h_positions[], v_positions[], spacing)` — sub-pixel float coordinates.

## S3: Occupied Intersection Detection (`cv_detect_occupied()`)

Multi-feature anomaly detection at every intersection.

**Features per intersection:**
- `dark_ratio`: fraction of pixels < 100 (black stone signature)
- `edge_ratio`: Canny edge density (stone border signature)
- `std_val`: pixel standard deviation (texture vs. flat background)
- `circ_contrast`: mean(outside) - mean(inside) circular mask (white stone signature)

**Occupied if ANY of:**
- `dark_ratio > median + 2σ`
- `edge_ratio > median + 2σ`
- `std_val > median + 2σ`
- `circ_contrast < -15` (white stone)
- `dark_ratio > 0.28` (absolute threshold for numbered stones)

**Letter detection (second pass):** For unoccupied non-border intersections, mask out the grid cross pattern, count remaining dark pixels. `outside_ratio > 0.12` → letter candidate.

**CV pre-classification** (`cv_preclass_confident()`):
- `dark_ratio > 0.55 && mean < 80` → "black" (confident)
- `mean > 180 && dark_ratio < 0.05` → "white" (confident)
- Else → "ambiguous" (needs Haiku classification)

All results (including "ambiguous") are stored in `recognition_debug.classification.cv_preclass` for debugging.

## S4: CV Pre-classify + Claude Haiku Per-Patch

Two-tier classification:

**Tier 1 — CV confident (instant):** handled by `cv_preclass_confident()` above. No API call needed.

**Tier 2 — Haiku per-patch (concurrent, ~1-2s total):** Ambiguous patches sent concurrently to Claude Haiku.
- Model: `claude-haiku-4-5-20251001`
- Auth: Anthropic SDK with `ANTHROPIC_API_KEY` (or Max OAuth fallback)
- Concurrency: ThreadPoolExecutor, max 8 threads (all patches in parallel)
- Input: single ~40x40px grayscale patch image + classification prompt
- Output: one classification string per patch

**Categories:**
- `"black"` / `"white"`: plain stones
- `"black+N"` / `"white+N"`: stones with move number N (1-999, can be 3 digits)
- `"triangle"`: triangle mark on stone or empty intersection
- `"letter_X"`: letter annotation (A-Z or a-z, NEVER digits) on empty intersection
- `"empty"`: false detection

**Key prompt rules (to avoid common Haiku errors):**
- Numbers on stones (1, 2, 3...) are MOVE numbers → `black+N` / `white+N`, NOT `letter_N`
- Letters are ONLY alphabetic A-Z, never numeric
- White stones have THICK circular border vs THIN crossing lines for empty intersections

**Debug data stored per figure:**
- `cv_preclass`: every label → CV result ("black"/"white" or "ambiguous")
- `classifications`: every label → final result (from CV or Haiku)
- `patch_images`: every label → relative path to patch PNG file

**Key design choices:**
- Individual patches, NOT composite/batch images (much more accurate)
- CV-confident results used directly, only ambiguous patches sent to Haiku (typically 3-8 per figure)

**Merging:** Haiku results fill in ambiguous positions. CV-confident results are kept as-is.

## S5: Payload Construction (`classification_to_payload()`)

Convert classification results + label_map + region offsets → `BoardPayload` JSON.

Maps each classified position:
- `"black"/"black+N"` → `stones.B` + optional `labels`
- `"white"/"white+N"` → `stones.W` + optional `labels`
- `"letter_X"` → `letters`
- `"triangle_*"` etc. → `shapes`

Viewport computed server-side via `compute_viewport()`.
