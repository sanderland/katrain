# Tutorial Module Stage 3 — Book Board Diagram Recognition

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically recognize Go board diagrams from scanned book pages and convert them to `board_payload` JSON, including stone positions, colors, move numbers, letter annotations, and shape markers.

**Scope:** Recognition pipeline for printed Go book diagrams. Covers stone detection, color classification, move number OCR, and annotation detection (△/□/○, A/B/C). Does NOT cover AI narration generation or TTS (future stage).

**Prerequisites:** Stage 2 completed — DB schema (TutorialBook/Chapter/Section/Figure), import script, editable SVG board, and page screenshot assets all in place.

**Revision:** v2 (2026-03-27) — incorporates review feedback from Gemini and Codex. Key changes: multi-evidence region calibration (replaces star-point-only), three-tier classification (CV confident → VLLM ambiguous → unknown), structured output schema with `base_type` + `attributes`, module split, manifest.jsonl for training data provenance, fix DB direct-write to call `compute_viewport()`, separate OCR from classification, per-figure status tracking, acceptance metrics.

---

## Architecture Overview

### Problem Statement

Direct VLLM-based recognition has ±1-2 grid line counting errors, making results unusable. Pure CV-based classification misidentifies white stones with dark numbers as black stones and cannot read move numbers or annotations.

### Solution: Hybrid CV + VLLM Pipeline

**Principle: CV handles WHERE (precise grid/position detection), VLLM handles WHAT (classification + OCR).**

```
Page Image (1655×2382 px)
  │
  ├── Phase A: CV Pipeline (local, instant)
  │     ├─ A1. Detect diagram bboxes on page (CV projection analysis)
  │     ├─ A2. Crop each diagram
  │     ├─ A3. Detect grid lines (morphological + projection + gap-fill)
  │     ├─ A4. Multi-evidence region calibration (border + star + line count)
  │     ├─ A5. Detect occupied intersections (multi-feature anomaly)
  │     ├─ A6. Pre-classify high-confidence patches (obvious B/W → skip VLLM)
  │     └─ A7. Crop patches: classification size + enlarged OCR size
  │
  ├── Phase B: Contact Sheet (local, instant)
  │     └─ B1. Build sheet with ONLY ambiguous/numbered patches (not all)
  │
  ├── Phase C: VLLM Classification (one call per figure, only ambiguous patches)
  │     └─ C1. Classify: base_type (B/W/empty) + text (number/letter/null)
  │                       + shape (triangle/square/circle/null) + confidence
  │
  └── Phase D: Assembly + Write
        ├─ D1. Merge CV confident + VLLM results → board_payload
        ├─ D2. Call compute_viewport() before DB write
        └─ D3. Save patches + manifest.jsonl for training data
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Grid detection | Morphological line isolation + 1D projection + gap-fill | Pixel-precise; stones occluding lines are interpolated |
| Stone detection | Multi-feature anomaly (not binary threshold) | Prevents both false positives and false negatives |
| Classification | Three-tier: CV confident → VLLM ambiguous → unknown | CV handles 60-80% of patches; VLLM only for hard cases; unknown enters review queue |
| VLLM invocation | Subagent (Claude Max membership) | No API credits; contact sheet only contains ambiguous patches |
| Region mapping | Multi-evidence: border detection + star points + line count + VLLM fallback | Star-point-only fails when stones cover hoshi or diagram is mid-board |
| OCR | Separate from classification; enlarged patches with CLAHE preprocessing | 40px patches too small for 2-digit numbers; separate pipeline more reliable |
| Training data | manifest.jsonl with full provenance; three tiers: raw_auto/reviewed/gold | Prevents VLLM error propagation; enables data cleaning and auditing |
| DB write | Call `compute_viewport()` before write; skip-if-not-null safety check | Direct DB write without viewport computation is a real bug (Codex finding) |
| Per-figure status | success / needs_review / failed_cv / failed_semantic | Batch processing must not abort on single-figure failure |

### Coordinate System

```
Full 19×19 board:
  col=0 (leftmost) → col=18 (rightmost)
  row=0 (topmost)  → row=18 (bottommost)

Star points (hoshi): (3,3) (9,3) (15,3) (3,9) (9,9) (15,9) (3,15) (9,15) (15,15)

board_payload format:
  {
    "size": 19,
    "stones": {"B": [[col, row], ...], "W": [[col, row], ...]},
    "labels": {"col,row": "1", ...},      // move numbers
    "letters": {"col,row": "A", ...},     // letter annotations
    "shapes": {"col,row": "triangle", ...}, // shape markers
    "highlights": []
  }
```

---

## File Structure

**Module split** (per Gemini/Codex feedback: single file → testable modules):

```
katrain/web/tutorials/vision/            # NEW: CV + classification modules
  ├─ grid_detector.py                    # cv_detect_grid(), _find_peaks(), _fill_gaps()
  ├─ occupied_detector.py                # cv_detect_occupied(), cv_preclass_confident()
  ├─ region_calibrator.py                # multi-evidence col_start/row_start inference
  ├─ contact_sheet.py                    # build_contact_sheet(), patch preprocessing (CLAHE)
  ├─ payload_builder.py                  # classification_to_payload(), structured output schema
  └─ __init__.py

scripts/
  ├─ recognize_boards_v2.py              # CLI orchestrator: prepare → classify → review → apply → report
  └─ train_classifier.py                 # Phase 2: model training

data/training_patches/                   # Auto-collected patches + manifest.jsonl (gitignored)
models/                                  # Trained model weights (gitignored)
```

**Structured classification output schema** (per Codex: decouple base_type + attributes):

```python
@dataclass
class PatchClassification:
    label: str                            # contact sheet label: "A", "B", ...
    local_col: int                        # grid index in cropped diagram
    local_row: int
    base_type: str                        # "black" | "white" | "empty" | "unknown"
    text: Optional[str] = None            # move number "1"-"99+" or letter "A"-"Z" or None
    shape: Optional[str] = None           # "triangle" | "square" | "circle" | None
    confidence: float = 1.0               # 0.0-1.0; <0.8 → needs_review
    source: str = "cv"                    # "cv" | "vllm" | "model" | "human"
```

---

## Phase 1: CV + VLLM Contact Sheet Pipeline

### Chunk 1: Refactor CV — Occupied Detection

Replace `cv_detect_stones()` (which tries to classify B/W) with `cv_detect_occupied()` (which only detects presence).

- [ ] **Step 1.1: Implement `cv_detect_occupied()`**

**File:** `scripts/recognize_boards_v2.py`

```python
def cv_detect_occupied(gray, h_positions, v_positions, spacing):
    """Detect all non-empty intersections using multi-feature anomaly detection.

    Returns list of (col_idx, row_idx, patch) where patch is the cropped grayscale image.
    Does NOT classify color — that's VLLM's job.
    """
    h_img, w_img = gray.shape
    r = int(spacing * 0.5)  # slightly larger than before for better patch quality
    if r < 3:
        return []

    # Compute features for every intersection
    features = []
    for ci, vx in enumerate(v_positions):
        for ri, hy in enumerate(h_positions):
            y1, y2 = max(0, int(hy) - r), min(h_img, int(hy) + r)
            x1, x2 = max(0, int(vx) - r), min(w_img, int(vx) + r)
            roi = gray[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            # Multi-dimensional features
            dark_ratio = float(np.sum(roi < 100) / roi.size)
            edges = cv2.Canny(roi, 50, 150)
            edge_ratio = float(np.sum(edges > 0) / edges.size)
            std_val = float(np.std(roi.astype(float)))

            # Circular contrast (white stone signature)
            mask = np.zeros_like(roi, dtype=np.uint8)
            cr = roi.shape[0] // 2
            cv2.circle(mask, (cr, cr), max(1, cr - 2), 255, -1)
            inside = roi[mask > 0]
            outside = roi[mask == 0]
            circ_contrast = float(np.mean(outside) - np.mean(inside)) if inside.size > 0 and outside.size > 0 else 0.0

            features.append((ci, ri, int(vx), int(hy), dark_ratio, edge_ratio, std_val, circ_contrast, roi.copy()))

    if not features:
        return []

    # Compute background statistics (median ± std for each feature)
    darks = np.array([f[4] for f in features])
    edges_arr = np.array([f[5] for f in features])
    stds = np.array([f[6] for f in features])
    contrasts = np.array([f[7] for f in features])

    dark_med, dark_std = float(np.median(darks)), float(np.std(darks))
    edge_med, edge_std = float(np.median(edges_arr)), float(np.std(edges_arr))
    std_med, std_std = float(np.median(stds)), float(np.std(stds))

    # Mark as occupied if ANY feature is anomalous (wide net, minimal false negatives)
    occupied = []
    for ci, ri, vx, hy, dark, edge, std_v, circ, roi in features:
        is_occupied = (
            dark > dark_med + 2.0 * dark_std or          # high dark content
            edge > edge_med + 2.0 * edge_std or          # high edge content
            std_v > std_med + 2.0 * std_std or            # high texture variance
            circ < -15 or                                  # white stone signature (light center)
            dark > 0.28                                    # absolute threshold for numbered stones
        )
        if is_occupied:
            occupied.append((ci, ri, roi))

    return occupied
```

- [ ] **Step 1.2: Keep `cv_detect_stones()` as fallback**

Rename to `cv_detect_stones_legacy()`. Keep it available for `--test-cv` mode comparison.

- [ ] **Step 1.3: Verify on 图4 (reference data)**

```bash
python -c "
import sys; sys.path.insert(0, '.')
import cv2, numpy as np
from scripts.recognize_boards_v2 import cv_detect_grid, cv_detect_occupied

gray = cv2.cvtColor(cv2.imread('/tmp/cv_crop_图4.png'), cv2.COLOR_BGR2GRAY)
h_pos, v_pos, spacing = cv_detect_grid(gray)
occupied = cv_detect_occupied(gray, h_pos, v_pos, spacing)
print(f'Occupied: {len(occupied)} intersections')
for ci, ri, _ in occupied:
    print(f'  ({ci},{ri})')
# Expected: at least 8 positions matching B(2,4)(3,9)(3,15)(4,3)(5,3) W(3,2)(4,2)(6,2)
"
```

- [ ] **Step 1.4: Commit**

```bash
git add scripts/recognize_boards_v2.py
git commit -m "refactor(recognition): replace cv_detect_stones with cv_detect_occupied (no classification)"
```

---

### Chunk 2: Contact Sheet Generation

- [ ] **Step 2.1: Implement `build_contact_sheet()`**

**File:** `scripts/recognize_boards_v2.py`

```python
from math import ceil

def build_contact_sheet(occupied_patches, spacing, cols_per_row=8):
    """Arrange occupied intersection patches into a labeled contact sheet image.

    Args:
        occupied_patches: list of (col_idx, row_idx, patch_image)
        spacing: grid spacing in pixels (determines patch size)
        cols_per_row: number of patches per row in the sheet

    Returns:
        (sheet_image, label_map) where label_map is {"A": (col_idx, row_idx), ...}
    """
    if not occupied_patches:
        return None, {}

    patch_size = int(spacing * 1.0)
    margin = 4
    label_h = 16  # height for text label below each patch
    cell_w = patch_size + margin * 2
    cell_h = patch_size + margin * 2 + label_h

    n = len(occupied_patches)
    rows = ceil(n / cols_per_row)
    sheet_w = cols_per_row * cell_w
    sheet_h = rows * cell_h

    sheet = np.ones((sheet_h, sheet_w), dtype=np.uint8) * 240  # light gray background
    label_map = {}

    for idx, (ci, ri, patch) in enumerate(occupied_patches):
        row_i = idx // cols_per_row
        col_i = idx % cols_per_row
        x_off = col_i * cell_w + margin
        y_off = row_i * cell_h + margin

        # Resize patch to standard size
        resized = cv2.resize(patch, (patch_size, patch_size), interpolation=cv2.INTER_AREA)

        # Place patch
        sheet[y_off:y_off + patch_size, x_off:x_off + patch_size] = resized

        # Draw border
        cv2.rectangle(sheet, (x_off - 1, y_off - 1),
                      (x_off + patch_size, y_off + patch_size), 0, 1)

        # Label: A, B, C, ... AA, AB, ...
        if idx < 26:
            label = chr(65 + idx)
        else:
            label = chr(65 + idx // 26 - 1) + chr(65 + idx % 26)

        label_map[label] = (ci, ri)

        # Draw label text
        cv2.putText(sheet, f"{label}:({ci},{ri})", (x_off, y_off + patch_size + label_h - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, 0, 1)

    return sheet, label_map
```

- [ ] **Step 2.2: Add `--save-sheets` CLI mode**

```python
# In main():
parser.add_argument("--save-sheets", type=str,
                    help="Save contact sheets to this directory (no DB write)")

# When --save-sheets is given:
# 1. Run CV pipeline (A1-A5)
# 2. Build contact sheet (B1)
# 3. Save sheet image + label_map JSON to output directory
# 4. No VLLM call, no DB write
```

- [ ] **Step 2.3: Test contact sheet on section 1**

```bash
python scripts/recognize_boards_v2.py --section-id 1 --save-sheets /tmp/sheets/
ls /tmp/sheets/  # should have 图1.png ... 图10.png + 图1.json ... 图10.json
```

- [ ] **Step 2.4: Commit**

```bash
git add scripts/recognize_boards_v2.py
git commit -m "feat(recognition): add contact sheet generation for VLLM batch classification"
```

---

### Chunk 3: VLLM Classification via Subagent

- [ ] **Step 3.1: Implement `classification_to_payload()`**

**File:** `scripts/recognize_boards_v2.py`

```python
def classification_to_payload(classifications, label_map, col_start=0, row_start=0):
    """Convert VLLM classification results to board_payload format.

    Args:
        classifications: dict like {"A": "black+1", "B": "white+8", "C": "triangle_white", ...}
        label_map: dict like {"A": (col_idx, row_idx), ...}
        col_start: offset to map local col to full 19×19 col
        row_start: offset to map local row to full 19×19 row

    Categories:
        "black"           → B stone, no label
        "white"           → W stone, no label
        "black+N"         → B stone with move number N
        "white+N"         → W stone with move number N
        "triangle_black"  → B stone with triangle marker
        "triangle_white"  → W stone with triangle marker
        "letter_X"        → letter annotation X at empty intersection
        "empty"           → false positive, ignore
    """
    black, white = [], []
    labels, letters, shapes = {}, {}, {}

    for lbl, cls in classifications.items():
        if cls == "empty" or lbl not in label_map:
            continue
        ci, ri = label_map[lbl]
        col = col_start + ci
        row = row_start + ri
        key = f"{col},{row}"

        if cls.startswith("black"):
            black.append([col, row])
            if "+" in cls:
                labels[key] = cls.split("+")[1]
        elif cls.startswith("white"):
            white.append([col, row])
            if "+" in cls:
                labels[key] = cls.split("+")[1]
        elif cls.startswith("triangle"):
            color = cls.split("_")[1]
            (black if color == "black" else white).append([col, row])
            shapes[key] = "triangle"
        elif cls.startswith("letter"):
            letter_val = cls.split("_")[1]
            letters[key] = letter_val

    return {
        "size": 19,
        "stones": {"B": black, "W": white},
        "labels": labels,
        "letters": letters,
        "shapes": shapes,
        "highlights": [],
    }
```

- [ ] **Step 3.2: Add `--apply-classifications` CLI mode**

```python
parser.add_argument("--apply-classifications", type=str,
                    help="Apply VLLM classification results from JSON file to DB")

# JSON format:
# {
#   "图1": {"classifications": {"A": "black+1", ...}, "col_start": 0, "row_start": 0},
#   "图2": {...},
#   ...
# }
```

- [ ] **Step 3.3: Define VLLM subagent prompt template**

The subagent prompt for classifying a contact sheet:

```
You are classifying Go board intersection patches from a textbook diagram.
The contact sheet image shows cropped patches labeled A, B, C, etc.
Each patch is a ~40×40px crop centered on a grid intersection.

Classify each labeled patch into EXACTLY ONE category:
- "black": solid black stone without a number
- "white": outlined white stone without a number
- "black+N": black stone with move number N (read the number carefully)
- "white+N": white stone with move number N (read the number carefully)
- "triangle_black": black stone marked with a triangle △
- "triangle_white": white stone marked with a triangle △
- "letter_X": letter X (A, B, C...) marked on an empty intersection
- "empty": no stone or marking (false positive from CV)

Return JSON only, no explanation:
{"A": "black+1", "B": "white+8", "C": "black", "D": "letter_A", ...}
```

- [ ] **Step 3.4: Test full pipeline on section 1 图4 (reference validation)**

```bash
# Generate sheets
python scripts/recognize_boards_v2.py --section-id 1 --save-sheets /tmp/sheets/

# Manually verify 图4 contact sheet has all 8 occupied intersections
# Then run subagent on 图4 sheet → get classifications
# Apply and verify against reference:
# Expected: B(2,4)①, W(4,2)②, B(5,3)③, W(6,2)④, B(3,9)⑤, W(3,2) (no label), B(3,15) (no label)
```

- [ ] **Step 3.5: Run subagents in parallel for all 10 figures**

Launch 5 subagents (one per page), each:
1. Reads 2 contact sheet images
2. Classifies all patches
3. Returns JSON

Each subagent only needs to classify one simple image → fast (~10-20 seconds).

- [ ] **Step 3.6: Commit**

```bash
git add scripts/recognize_boards_v2.py
git commit -m "feat(recognition): add VLLM classification mapping and --apply-classifications mode"
```

---

### Chunk 4: Auto-Save Training Data

Every time the pipeline runs, automatically save labeled patches for future model training.

- [ ] **Step 4.1: Save patches + manifest.jsonl with full provenance**

> Per Codex review: save ALL patches including `empty` (needed for Phase 2), and include full provenance metadata.

```python
TRAINING_DIR = Path("data/training_patches")

def save_training_patch(patch, classification, book_slug, page, figure_label,
                        local_col, local_row, global_col, global_row, source):
    """Save a single classified patch with full provenance to manifest.jsonl."""
    patch_id = f"{book_slug}_{figure_label}_{local_col}_{local_row}"

    # Save image (organized by base_type for browsing)
    base_type = classification.base_type  # "black", "white", "empty", "unknown"
    class_dir = TRAINING_DIR / "images" / base_type
    class_dir.mkdir(parents=True, exist_ok=True)
    img_path = class_dir / f"{patch_id}.png"
    cv2.imwrite(str(img_path), patch)

    # Append to manifest.jsonl
    record = {
        "patch_id": patch_id,
        "image_path": str(img_path.relative_to(TRAINING_DIR)),
        "book": book_slug,
        "page": page,
        "figure": figure_label,
        "local_col": local_col, "local_row": local_row,
        "global_col": global_col, "global_row": global_row,
        "base_type": base_type,
        "text": classification.text,          # "1", "A", null
        "shape": classification.shape,        # "triangle", null
        "confidence": classification.confidence,
        "source": source,                     # "cv", "vllm", "human"
        "review_status": "raw_auto",          # raw_auto → reviewed → gold
        "timestamp": datetime.utcnow().isoformat(),
    }
    manifest_path = TRAINING_DIR / "manifest.jsonl"
    with open(manifest_path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

Key changes from original:
- **Saves `empty` patches** (Codex fix: Phase 2 needs negative samples)
- **manifest.jsonl** with full provenance (book, page, figure, coordinates, source, confidence, review_status)
- **Three-tier review**: `raw_auto` → `reviewed` → `gold` (prevents VLLM error propagation)

- [ ] **Step 4.2: Add to `.gitignore`**

```
data/training_patches/
models/
```

- [ ] **Step 4.3: Commit**

```bash
git add katrain/web/tutorials/vision/ .gitignore
git commit -m "feat(recognition): training data with manifest.jsonl and full provenance"
```

---

### Chunk 5: Multi-Evidence Region Calibration

> Per Gemini/Codex review: star-point-only calibration is fragile (stars can be covered by stones, mid-board diagrams may have no visible stars). Replace with multi-evidence hypothesis search.

- [ ] **Step 5.1: Implement `calibrate_region()` in `region_calibrator.py`**

**File:** `katrain/web/tutorials/vision/region_calibrator.py`

Evidence sources (each produces a score for candidate offsets):

```python
def calibrate_region(gray, h_positions, v_positions, spacing, occupied):
    """Multi-evidence inference of col_start/row_start.

    Evidence sources:
    1. Border detection: thick lines at edges → board boundary → col/row = 0 or 18
    2. Star point matching: small dots at unoccupied intersections → known 19×19 positions
    3. Line count constraint: num_visible_cols + col_start <= 19
    4. Occupied range: stones should map to valid 19×19 coordinates

    Returns (col_start, row_start, confidence, evidence_details).
    """
    KNOWN_STARS = {(3,3),(9,3),(15,3),(3,9),(9,9),(15,9),(3,15),(9,15),(15,15)}
    num_cols, num_rows = len(v_positions), len(h_positions)

    candidates = []
    for col_off in range(max(0, 19 - num_cols) + 1):
        for row_off in range(max(0, 19 - num_rows) + 1):
            score = 0.0
            evidence = []

            # Evidence 1: border lines (thick first/last lines → board edge)
            if _is_border_line(gray, v_positions[0], axis='v'):
                if col_off == 0: score += 2.0; evidence.append("left_border")
            if _is_border_line(gray, v_positions[-1], axis='v'):
                if col_off + num_cols == 19: score += 2.0; evidence.append("right_border")
            if _is_border_line(gray, h_positions[0], axis='h'):
                if row_off == 0: score += 2.0; evidence.append("top_border")
            if _is_border_line(gray, h_positions[-1], axis='h'):
                if row_off + num_rows == 19: score += 2.0; evidence.append("bottom_border")

            # Evidence 2: star point matching
            star_matches = _count_star_matches(gray, h_positions, v_positions,
                                                spacing, occupied, col_off, row_off, KNOWN_STARS)
            score += star_matches * 1.5
            if star_matches > 0: evidence.append(f"stars={star_matches}")

            # Evidence 3: typical layout bias (most book diagrams start from col=0)
            if col_off == 0: score += 0.5

            candidates.append((col_off, row_off, score, evidence))

    best = max(candidates, key=lambda x: x[2])
    confidence = best[2] / (max(c[2] for c in candidates) + 1e-6) if candidates else 0
    return best[0], best[1], confidence, best[3]
```

- [ ] **Step 5.2: Fallback to VLLM if confidence < 0.6**

Low-confidence figures enter `needs_review` status. If VLLM is available, ask it to confirm.

- [ ] **Step 5.3: Commit**

```bash
git add katrain/web/tutorials/vision/region_calibrator.py
git commit -m "feat(recognition): multi-evidence region calibration (border+star+layout)"
```

---

## Phase 2: Lightweight EfficientNet-B0 Classifier

> Prerequisites: ~2000 labeled patches accumulated from Phase 1 processing (~2-3 books).

### Chunk 6: Training Script

- [ ] **Step 6.1: Create `scripts/train_classifier.py`**

```python
"""Train a lightweight EfficientNet-B0 classifier for Go intersection patches.

Classes:
  0: empty           (false positive from CV)
  1: black            (solid black stone, no number)
  2: white            (outlined white stone, no number)
  3: black_numbered   (black stone with move number)
  4: white_numbered   (white stone with move number)
  5: triangle_black   (black stone with △ marker)
  6: triangle_white   (white stone with △ marker)
  7: letter           (letter annotation on empty intersection)

For classes 3/4 (numbered), a separate digit recognition head outputs 0-99.

Usage:
    python scripts/train_classifier.py --data-dir data/training_patches/ --epochs 50
"""

import torch
import torch.nn as nn
from torchvision import transforms, models
from torch.utils.data import DataLoader, Dataset
from pathlib import Path

CLASS_NAMES = ["empty", "black", "white", "black_numbered", "white_numbered",
               "triangle_black", "triangle_white", "letter"]

# Data augmentation
train_transforms = transforms.Compose([
    transforms.Resize((64, 64)),
    transforms.RandomRotation(5),
    transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
    transforms.ColorJitter(brightness=0.3, contrast=0.3),
    transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

# Model
class StoneClassifier(nn.Module):
    def __init__(self, num_classes=8, num_digits=100):
        super().__init__()
        self.backbone = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
        # Freeze early layers
        for i, param in enumerate(self.backbone.parameters()):
            if i < len(list(self.backbone.parameters())) * 0.8:
                param.requires_grad = False
        # Classification head
        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Identity()
        self.class_head = nn.Sequential(nn.Linear(in_features, 256), nn.ReLU(), nn.Dropout(0.5), nn.Linear(256, num_classes))
        # Digit recognition head (only used for numbered classes)
        self.digit_head = nn.Sequential(nn.Linear(in_features, 128), nn.ReLU(), nn.Dropout(0.3), nn.Linear(128, num_digits))

    def forward(self, x):
        features = self.backbone(x)
        class_logits = self.class_head(features)
        digit_logits = self.digit_head(features)
        return class_logits, digit_logits

# Training: AdamW, CosineAnnealing, 50 epochs, batch_size=32
```

- [ ] **Step 6.2: Add `--use-model` mode to `recognize_boards_v2.py`**

When `--use-model models/stone_classifier.pt` is given, use the trained model instead of VLLM for classification. Falls back to VLLM if model confidence < 0.8.

- [ ] **Step 6.3: Commit**

```bash
git add scripts/train_classifier.py scripts/recognize_boards_v2.py
git commit -m "feat(recognition): add EfficientNet-B0 training script and --use-model mode"
```

---

## Phase 3: Active Learning & Continuous Improvement

### Chunk 7: Active Learning Loop

- [ ] **Step 7.1: Confidence-based VLLM fallback**

When using the trained model, if confidence < threshold:
1. Save the low-confidence patch to `data/training_patches/uncertain/`
2. Fall back to VLLM for classification
3. Add VLLM result to training set
4. Periodically retrain model with expanded dataset

- [ ] **Step 7.2: Cross-book generalization testing**

Process books with different printing styles:
- Different publishers (varying line thickness, stone rendering)
- Different scan qualities (DPI, contrast, noise)
- Collect hard examples and retrain

- [ ] **Step 7.3: Digit recognition refinement**

If digit accuracy is low:
- Option A: Tesseract OCR with preprocessing (CLAHE + threshold + PSM=8)
- Option B: Dedicated CRNN digit recognizer trained on extracted patches
- Option C: Template matching against rendered digit images

---

## Verification Plan

### Phase 1 Verification

```bash
# 1. Generate contact sheets (instant, local)
python scripts/recognize_boards_v2.py --section-id 1 --save-sheets /tmp/sheets/

# 2. Verify contact sheets visually
open /tmp/sheets/  # should show clear labeled patches for each figure

# 3. Run VLLM classification (via subagents)
# → produces /tmp/classifications.json

# 4. Apply to DB
python scripts/recognize_boards_v2.py --section-id 1 --apply-classifications /tmp/classifications.json

# 5. Browser validation
open http://localhost:8002/galaxy/tutorials/section/1
# Navigate 图1-10, verify:
#   - Stone positions correct
#   - Black/white correctly classified
#   - Move numbers displayed
#   - Letter annotations (A, B) shown where applicable

# 6. Reference validation (图4)
# Expected: B(2,4)①, W(4,2)②, B(5,3)③, W(6,2)④, B(3,9)⑤, W(3,2), B(3,15)
```

### Phase 2 Verification

```bash
# Train
python scripts/train_classifier.py --data-dir data/training_patches/ --epochs 50 --output models/stone_classifier.pt

# Test accuracy
python scripts/train_classifier.py --evaluate --model models/stone_classifier.pt --data-dir data/training_patches/
# Target: >95% classification accuracy, >90% digit accuracy

# Compare model vs VLLM
python scripts/recognize_boards_v2.py --section-id 1 --use-model models/stone_classifier.pt --dry-run
# Compare output against Phase 1 VLLM results
```

---

## Acceptance Metrics (per Codex review)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Grid line exact-match rate | ≥ 95% | Compare detected line count with manual count on golden set |
| Occupied recall | ≥ 99% | All stones/marks must be detected (漏检不可接受) |
| Occupied false-positive rate | ≤ 15% | Extra detections filtered by VLLM `empty` class |
| Black/white classification accuracy | ≥ 95% | Against golden set with manual labels |
| Numbered stone OCR accuracy | ≥ 90% | Correct number on correct stone |
| Annotation accuracy (△/letter) | ≥ 90% | Correct type + correct position |
| End-to-end board_payload exact match | ≥ 80% | Full payload matches manual reference |
| `needs_review` ratio | ≤ 20% | Figures needing human review |

Golden set: Section 1 图1-图10 (10 figures, manually verified).

---

## Implementation Priority

| Priority | Task | Effort | Dependency |
|----------|------|--------|------------|
| P0 | Module split (grid_detector, occupied_detector, etc.) | 30 min | None |
| P0 | Chunk 1: `cv_detect_occupied()` + CV pre-classification | 30 min | Module split |
| P0 | Chunk 2: `build_contact_sheet()` with CLAHE preprocessing | 30 min | Chunk 1 |
| P0 | Chunk 3: `classification_to_payload()` + structured schema | 1 hour | Chunk 2 |
| P0 | Chunk 5: Multi-evidence region calibration | 30 min | Chunk 1 |
| P1 | Chunk 4: Training data with manifest.jsonl | 20 min | Chunk 3 |
| P1 | DB write fix: call compute_viewport() | 15 min | Chunk 3 |
| P1 | Per-figure status tracking + summary report | 20 min | Chunk 3 |
| P2 | Chunk 6: EfficientNet-B0 training | 2 hours | ~2000 patches from Chunk 4 |
| P3 | Chunk 7: Active learning loop | 1 hour | Chunk 6 |
