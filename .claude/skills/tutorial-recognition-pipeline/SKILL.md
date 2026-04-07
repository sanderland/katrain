---
name: tutorial-recognition-pipeline
description: >
  Go board recognition pipeline for tutorial book digitization. Use when processing
  tutorial book pages into structured board data: running the 5-step pipeline
  (recognize_boards_v2.py), managing the figure editing/verification UI, exporting
  training samples, or debugging recognition results. Triggers on: board recognition,
  棋谱识别, tutorial processing, figure verification, patch classification, training data export.
---

# Tutorial Board Recognition Pipeline

Digitize Go textbook diagrams into structured `BoardPayload` JSON via a hybrid CV + VLLM pipeline.
S0-S3 are pure OpenCV (millisecond-level). S4 uses CV pre-classification + Gemini 3 Flash per-patch (default).

## Architecture

```
Book PDF → Page Images → [S0] CV BBox → [Deskew] Rotation Correction
→ [S1] CV Region Calibration → [S2] CV Grid Detection
→ [S3] CV Occupied Detection
→ [S4] CV pre-classify + Gemini per-patch → BoardPayload
→ Human Verification → Training Samples Export
```

## Pipeline Execution Order

This skill is part of a 3-skill tutorial digitization pipeline. **Check prerequisites before running.**

| Order | Skill | Script | Prerequisite Check |
|-------|-------|--------|--------------------|
| 0 (first) | `tutorial-book-import` | `import_book.py` | book.json + pages exist in book-dir |
| 1 (after 0) | **`tutorial-recognition-pipeline`** | `recognize_boards_v2.py` | Figures exist in DB with `page_image_path` and `bbox` |
| 2 (after 0) | `tutorial-voice-pipeline` | `generate_voice.py` | Figures exist in DB with `book_text` |

Steps 1 and 2 are independent — can run in any order or in parallel. Both require step 0.

**Before running this skill, verify:**
- Section has figures in the database with `page_image_path` and `bbox` populated.
- If prerequisites are not met, inform the user to run `tutorial-book-import` (`scripts/import_book.py`) first.

## Key Files

| Component | Path |
|-----------|------|
| Pipeline script | `scripts/recognize_boards_v2.py` |
| Region calibrator | `katrain/web/tutorials/vision/region_calibrator.py` |
| Training export | `katrain/web/tutorials/training_export.py` |
| Verify endpoint | `katrain/web/api/v1/endpoints/tutorials.py` |
| DB models | `katrain/web/core/models_db.py` (TutorialFigure, TrainingSample) |
| Debug panel UI | `katrain/web/ui/src/galaxy/components/tutorials/RecognitionDebugPanel.tsx` |
| Editor UI | `katrain/web/ui/src/galaxy/pages/tutorials/TutorialFigurePage.tsx` |
| TS types | `katrain/web/ui/src/galaxy/types/tutorial.ts` (RecognitionDebug) |
| Debug output | `data/tutorial_assets/{book_slug}/debug/{figure_label}/` |

## Running the Pipeline

```bash
# Full pipeline for a section (default: Gemini 3 Flash for S4)
python scripts/recognize_boards_v2.py --section-id <ID>

# Use local EfficientNet-B0 model (fast, lower accuracy)
python scripts/recognize_boards_v2.py --section-id <ID> --vllm local

# Other backends (only use if user explicitly requests):
# python scripts/recognize_boards_v2.py --section-id <ID> --vllm haiku
# python scripts/recognize_boards_v2.py --section-id <ID> --vllm qwen

# Dry run (print results without DB write)
python scripts/recognize_boards_v2.py --section-id <ID> --dry-run

# Force re-process (overwrite existing board_payload)
python scripts/recognize_boards_v2.py --section-id <ID> --force

# CV-only test on a single page image
python scripts/recognize_boards_v2.py --test-cv data/tutorial_assets/.../pages/page_016.png
```

## Pipeline Steps

See [references/pipeline-steps.md](references/pipeline-steps.md) for detailed step descriptions.

**Summary (all times per figure):**
- **S0** (<100ms): Detect diagram bounding boxes on page — pure CV morphological line detection
- **Deskew** (<50ms): Straighten tilted scans — HoughLinesP angle detection + warpAffine rotation
- **S1** (<30ms): Determine which portion of 19x19 board is shown — pure CV border extension analysis + star point matching
- **S2** (<50ms): OpenCV morphological grid line detection + sub-pixel centroid refinement
- **S3** (<50ms): Multi-feature anomaly detection for occupied intersections + letter annotations
- **S4** (~2-5s): CV pre-classify confident B/W → VLLM per-patch for ambiguous positions

## S4 Classification: CV + VLLM

Two-tier approach:
1. **CV pre-classification** (`cv_preclass_confident()`): fast, handles obvious cases
   - `dark_ratio > 0.55 && mean < 80` → "black" (confident)
   - `mean > 180 && dark_ratio < 0.05` → "white" (confident)
   - Everything else → ambiguous, send to VLLM

2. **VLLM per-patch**: each ambiguous patch sent individually with simple prompt. Four backends available via `--vllm`:

   **Gemini 3 Flash** (`--vllm gemini`, default — always use this):
   - Model: `gemini-3-flash-preview` (thinking model) via Google GenAI SDK
   - Auth: `GEMINI_API_KEY` environment variable
   - Calls run concurrently via ThreadPoolExecutor (max 4 threads)
   - Good accuracy, preferred backend
   - **On transient errors (503, SSL):** wait and retry with Gemini. Do NOT auto-switch to another backend.

   **Local EfficientNet-B0** (`--vllm local`):
   - Model: `katrain/models/book-kifu/model.pt`
   - No API key needed, runs on CPU/MPS/CUDA
   - Fastest option, but lower accuracy (needs more training data)

   **Other backends** (only use if user explicitly requests):
   - **Claude Haiku** (`--vllm haiku`): `claude-haiku-4-5-20251001`, `ANTHROPIC_API_KEY`
   - **Qwen VL** (`--vllm qwen`): `qwen-vl-plus` via DashScope, `DASHSCOPE_API_KEY`

   All API backends accurately read move numbers (1-999), detect letters (A-Z, a-z), shapes. Same prompt used for all.

**Classification prompt (used by all VLLM backends):**
```
This is a small cropped patch from a Go (围棋) textbook diagram, centered on one grid intersection.

Classify what is at this intersection. Use EXACTLY one of these formats:
- black+N  — black stone (dark filled circle) with move number N (where N is 1-999)
- white+N  — white stone (open circle with thick dark border) with move number N (where N is 1-999)
- black    — black stone without any number (solid dark circle)
- white    — white stone without any number (open circle with thick dark border, light/empty inside)
- letter_X — a letter annotation (A-Z or a-z) on an empty intersection, e.g. letter_A, letter_b
- triangle_black — a triangle mark (△) on a BLACK stone
- triangle_white — a triangle mark (△) on a WHITE stone
- triangle — a triangle mark (△) on an empty intersection (no stone)
- empty    — just thin grid lines crossing, nothing else

IMPORTANT distinctions:
- White stones have a THICK circular border. Empty intersections only have THIN crossing grid lines.
- Numbers on stones (1, 2, 3... up to 3 digits) are MOVE numbers, NOT letters. A "2" on a white stone = white+2, NOT letter_2.
- Letters are ONLY alphabetic (A-Z or a-z), never numeric. They appear on empty intersections without any stone.

Answer with just one classification, nothing else.
```

**Debug data stored in `recognition_debug.classification`:**
- `cv_preclass`: dict mapping every label → CV result ("black"/"white" for confident, "ambiguous" for VLLM-bound)
- `classifications`: dict mapping every label → final result (CV or VLLM)
- `patch_images`: dict mapping every label → relative path to patch PNG
- `label_map`: dict mapping label → `[col_idx, row_idx]`

**Debug UI** (`RecognitionDebugPanel.tsx`): Each patch shows thumbnail image + CV pre-classification + final classification chip. CV-confident results shown in green, ambiguous in grey.

**Authentication:**
- **Gemini** (default): `GEMINI_API_KEY` environment variable (Google GenAI SDK)
- **Local**: no API key needed
- **Haiku**: `ANTHROPIC_API_KEY` (only if explicitly requested)
- **Qwen**: `DASHSCOPE_API_KEY` (only if explicitly requested)

## Data Model

See [references/data-model.md](references/data-model.md) for complete schemas.

**BoardPayload** (stored in `tutorial_figures.board_payload`):
```json
{
  "size": 19,
  "stones": {"B": [[col,row],...], "W": [[col,row],...]},
  "labels": {"col,row": "1"},
  "letters": {"col,row": "A"},
  "shapes": {"col,row": "triangle"},
  "viewport": {"col": 0, "row": 0, "cols": 12, "rows": 19}
}
```

## Human Verification Flow

1. Open tutorial figure page in web UI (`/galaxy/tutorials/section/{id}`)
2. Edit board with toolbar (stone/letter/shape/eraser tools)
3. Click "保存" to save board_payload
4. Click "确认审核" to mark as verified
5. Verify endpoint auto-exports training samples to `training_samples` table

## Training Data Export

Auto-triggered on verify. Can also run manually:

```bash
python scripts/export_training_data.py --all          # Export all verified
python scripts/export_training_data.py --section-id <ID>  # Specific section
python scripts/export_training_data.py --all --dry-run     # Preview only
```

**Patch structure:** ~40x40px grayscale, centered on intersection using precise OpenCV grid positions.

## Debug Output

Each processed figure generates debug images in `data/tutorial_assets/{book}/debug/{figure}/`:
- `crop.png` — deskewed cropped diagram from page
- `deskew_debug.png` — detected grid lines projected back onto original (pre-deskew) crop for verifying deskew + grid alignment
- `grid_debug.png` — detected grid lines overlay on deskewed crop for verifying grid accuracy
- `annotated_crop.png` — crop with labeled occupied positions
- `patches/` — individual intersection patches (`{label}_{col}_{row}.png`)

## Finding Section IDs

```python
from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import TutorialSection, TutorialFigure
db = SessionLocal()
for s in db.query(TutorialSection).all():
    figs = db.query(TutorialFigure).filter_by(section_id=s.id).all()
    unprocessed = [f for f in figs if not (f.recognition_debug or {}).get('classification')]
    print(f"Section {s.id}: {s.title} — {len(figs)} figs ({len(unprocessed)} unprocessed)")
```
