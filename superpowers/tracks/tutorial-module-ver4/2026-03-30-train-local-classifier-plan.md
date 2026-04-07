# Plan: Train EfficientNet-B0 Classifier & Replace VLLM in Recognition Pipeline

**Date**: 2026-03-30

## Context

The user has manually annotated (human-verified) board figures for Sections 1-6 of the Go textbook "曹薰铉布局技巧（上）". Training samples were auto-exported to the `training_samples` DB table when each figure was verified. The goal is to train a local EfficientNet-B0 classifier to replace the expensive VLLM API calls (Haiku/Qwen/Gemini) in the board recognition pipeline's Step 4 (patch classification).

**Current state**: An earlier model exists at `data/models/patch_classifier/` with only 360 samples and 36% val accuracy (unusable). The DB should now have ~1,100+ human-verified samples from sections 1-6.

## Step 1: Verify Training Data in DB

Run a read-only SQL query to confirm training_samples exist for sections 1-6:
```bash
python3 -c "
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from katrain.web.core.config import settings
engine = create_engine(settings.DATABASE_URL)
db = sessionmaker(bind=engine)()
result = db.execute(text('''
    SELECT ts.base_type, ts.move_number IS NOT NULL as has_number,
           ts.shape IS NOT NULL as has_shape, ts.letter IS NOT NULL as has_letter,
           COUNT(*) as cnt
    FROM training_samples ts
    JOIN tutorial_figures tf ON ts.figure_id = tf.id
    JOIN tutorial_sections s ON tf.section_id = s.id
    WHERE s.chapter_id = 1
    GROUP BY ts.base_type, has_number, has_shape, has_letter
    ORDER BY cnt DESC
'''))
for row in result:
    print(row)
db.close()
"
```

If data is missing, run `python scripts/export_training_data.py --all` to batch-export.

## Step 2: Add `--from-db` Flag to `prepare_training_data.py`

**File**: `scripts/prepare_training_data.py`

The script currently reads from `data/training_patches/manifest.jsonl` (VLLM auto-labels, noisy). Add a `--from-db` flag to read directly from the `training_samples` table (human-verified, gold standard).

Changes:
- Add `--from-db` argparse flag
- Add `load_entries_from_db()` function that queries `training_samples` and returns entries in the same dict format as manifest entries (`base_type`, `text`, `shape`, `image_path`)
- The `patch_image_path` in the DB is relative to `data/` — resolve image paths accordingly (use `--image-base data/` or hardcode the `ASSET_BASE`)
- Reuse existing `derive_class()` logic unchanged
- Copy patches from their debug locations into `prepared/{class}/` subdirectories as before

Key mapping from DB fields to manifest fields:
```python
text = str(s.move_number) if s.move_number else (s.letter if s.letter else None)
shape = s.shape
base_type = s.base_type
image_path = s.patch_image_path  # relative to data/
```

## Step 3: Prepare Training Data & Train

```bash
# Prepare 8-class splits from DB data
python scripts/prepare_training_data.py --from-db --val-ratio 0.2

# Train with output to katrain/models/book-kifu/
python scripts/train_patch_classifier.py \
    --data-dir data/training_patches/prepared \
    --output-dir katrain/models/book-kifu \
    --epochs 50 --batch-size 32 --patience 10
```

No changes needed to `train_patch_classifier.py` — it already supports `--output-dir`.

Output artifacts:
- `katrain/models/book-kifu/model.pt`
- `katrain/models/book-kifu/class_map.json`
- `katrain/models/book-kifu/training_report.json`

## Step 4: Add `--vllm local` to Recognition Pipeline

**File**: `scripts/recognize_boards_v2.py`

### 4a. Add `local_classify_patch()` function

Same signature as `haiku_classify_patch(patch_image_path, max_retries=3) -> str`. Combines EfficientNet coarse class + PatchOCR to produce compound strings matching the pipeline format:

| EfficientNet output | + OCR | Pipeline format |
|---|---|---|
| `black` | — | `"black"` |
| `white` | — | `"white"` |
| `black_numbered` | `read_number()` → 3 | `"black+3"` |
| `white_numbered` | `read_number()` → 15 | `"white+15"` |
| `letter` | `read_letter()` → A | `"letter_A"` |
| `marked_black` | `read_shape()` → triangle | `"triangle_black"` |
| `marked_white` | `read_shape()` → square | `"square_white"` |
| `empty` | — | `"empty"` |

Fallback when OCR fails: `black_numbered` → `"black"`, `letter` → `"empty"`, `marked_*` → bare stone color.

```python
def local_classify_patch(patch_image_path, max_retries=3):
    patch = cv2.imread(str(patch_image_path), cv2.IMREAD_GRAYSCALE)
    if patch is None:
        return "empty"
    classifier = PatchClassifier.get_instance(MODEL_DIR)
    ocr = PatchOCR()
    coarse, conf = classifier.classify_single(patch)
    return _coarse_to_compound(coarse, patch, ocr)
```

### 4b. Add batch fast-path for local model

Replace the `ThreadPoolExecutor` block (lines 1316-1329) with a conditional:
- `vllm == "local"`: Use `classifier.classify_batch()` for a single forward pass over all ambiguous patches, then OCR each one
- Otherwise: existing ThreadPoolExecutor code for API backends

### 4c. Register in argument parser

- Line 1862: Add `"local"` to `choices=["haiku", "qwen", "gemini", "local"]`
- Line 1300: Add `"local": local_classify_patch` to dispatch dict (used only for single-patch fallback; batch path handles the main flow)

### 4d. Model path constant

Add near top of file:
```python
MODEL_DIR = Path(__file__).resolve().parent.parent / "katrain" / "models" / "book-kifu"
```

## Step 5: Test on Section 7

```bash
# Dry run — print payloads without writing to DB
python scripts/recognize_boards_v2.py --section-id 7 --vllm local --dry-run

# If results look good, write to DB
python scripts/recognize_boards_v2.py --section-id 7 --vllm local --force
```

## Files to Modify

| File | Change |
|---|---|
| `scripts/prepare_training_data.py` | Add `--from-db` flag + `load_entries_from_db()` |
| `scripts/recognize_boards_v2.py` | Add `local_classify_patch()`, batch fast-path, `"local"` choice |

## Files to Read (no changes)

| File | Purpose |
|---|---|
| `katrain/web/tutorials/vision/patch_classifier.py` | Inference singleton (reuse as-is) |
| `katrain/web/tutorials/vision/patch_ocr.py` | OCR module (reuse as-is) |
| `scripts/train_patch_classifier.py` | Training script (run as-is with `--output-dir`) |
| `scripts/export_training_data.py` | May need to run if data missing |

## Verification

1. **Training data**: Confirm 1,000+ samples across 8 classes after Step 2
2. **Training quality**: Expect >75% val accuracy with 1,100+ samples (vs. 36% with 360)
3. **Section 7 dry-run**: Compare local model results against expected board layouts
4. **Speed**: Local model should classify all patches in <100ms vs. 2-5s for VLLM API
