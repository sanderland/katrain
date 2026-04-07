# S4 Classification: Replace VLLM with EfficientNet-B0 + OCR

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the VLLM-based S4 classification step (15-20s, often 120s timeout, high token cost) with a local two-step approach: EfficientNet-B0 coarse classifier + pre-trained OCR, reducing S4 to <100ms with zero API cost.

**Architecture:**
```
Occupied patches (from S3)
    │
    ├─► CV pre-classification (confident black/white) ──► direct output
    │
    └─► EfficientNet-B0 batch (ambiguous patches)
            │
            ├─ black / white / empty ──► direct output
            ├─ black_numbered / white_numbered ──► pytesseract digit ──► "black+N"
            ├─ letter ──► pytesseract letter ──► "letter_X"
            └─ marked_black / marked_white ──► template match ──► "triangle_black"
```

**Current Data (360 unique patches from 1 book):**
| Class | Count | Notes |
|-------|-------|-------|
| empty | 231 | Sufficient |
| black | 43 | OK with augmentation |
| black_numbered | 36 | OK with augmentation |
| white_numbered | 34 | OK with augmentation |
| white | 9 | Need more data |
| marked_white | 5 | Very low |
| marked_black | 1 | Insufficient |
| letter | 1 | Insufficient |

Patch sizes: mostly 38x38 or 40x40 grayscale. Numbers seen: 1-13.

**Key Files:**
| Existing File | Role |
|---------------|------|
| `scripts/recognize_boards_v2.py` | Main pipeline (S0-S4), ~1737 lines |
| `katrain/web/tutorials/training_export.py` | Human-verified patch export |
| `katrain/web/core/models_db.py:367` | `TrainingSample` DB schema |
| `data/training_patches/manifest.jsonl` | 1036 entries (360 unique), VLLM-labeled |
| `data/training_patches/images/{black,white,empty}/` | 471 patch PNGs (3-class only) |
| `data/training_patches/examples/` | 6 few-shot reference patches |

**Reusable Code:**
| Code | Location | How to reuse |
|------|----------|-------------|
| `PatchClassification` dataclass | `recognize_boards_v2.py:66` | Already has `confidence`, `source` fields — use directly |
| `parse_classification()` | `recognize_boards_v2.py:133` | Handles all compound strings — model output feeds into this |
| `classification_to_payload()` | `recognize_boards_v2.py:162` | Converts to BoardPayload — unchanged |
| `cv_preclass_confident()` | `recognize_boards_v2.py:574` | CV pre-filter for confident black/white — stays as-is |
| `save_all_training_patches()` | `recognize_boards_v2.py:371` | Saves patches after classification — unchanged |
| `export_figure_training_samples()` | `training_export.py` | Human-verified export for active learning — unchanged |

---

## Task 1: Dependencies

**Files:**
- Modify: `pyproject.toml`

**Rationale:** EfficientNet-B0 needs PyTorch + torchvision. Digit OCR needs pytesseract (lightest pre-trained option). Keep as optional group so base install is unaffected.

**Step 1: Add `classifier` optional dependency group to `pyproject.toml`**

Under `[project.optional-dependencies]` add:

```toml
classifier = [
    "torch>=2.0",
    "torchvision>=0.15",
    "pytesseract>=0.3.10",
]
```

Note: pytesseract requires the Tesseract binary: `brew install tesseract` on macOS.

**Step 2: Install and verify**

```bash
uv sync --extra classifier --extra vision
uv run python -c "import torch; print(f'torch {torch.__version__}, MPS: {torch.backends.mps.is_available()}')"
uv run python -c "import torchvision; print(f'torchvision {torchvision.__version__}')"
uv run python -c "import pytesseract; print('pytesseract OK')"
tesseract --version
```

---

## Task 2: Training Data Preparation

**Files:**
- Create: `scripts/prepare_training_data.py`
- Output: `data/training_patches/prepared/{8 class dirs}/`

**Rationale:** Current patches are organized into only 3 directories (black/white/empty). Need to reorganize into 8 fine-grained classes by parsing `text` and `shape` fields from `manifest.jsonl`. This enables standard PyTorch `ImageFolder` dataset loading.

**Step 1: Write `scripts/prepare_training_data.py`**

Logic:
1. Read `data/training_patches/manifest.jsonl`, deduplicate by `patch_id` (keep latest)
2. Derive 8-class label for each patch:
   - `base_type=black`, `text=null`, `shape=null` → `black`
   - `base_type=white`, `text=null`, `shape=null` → `white`
   - `base_type=black`, `text` is digit → `black_numbered`
   - `base_type=white`, `text` is digit → `white_numbered`
   - `base_type=black`, `shape` not null → `marked_black`
   - `base_type=white`, `shape` not null → `marked_white`
   - `base_type=empty`, `text` is alpha → `letter`
   - `base_type=empty`, `text=null` → `empty`
3. Create `data/training_patches/prepared/{class}/` directories
4. Copy (not symlink) patch images into class directories
5. Generate `data/training_patches/prepared/splits.json`:
   ```json
   {
     "train": ["black/patch_001.png", ...],
     "val": ["black/patch_042.png", ...],
     "class_counts": {"black": 43, ...},
     "class_weights": {"black": 5.37, ...}
   }
   ```
   Use stratified 80/20 split. Compute inverse-frequency class weights.
6. Print distribution report to stdout

**Step 2: Run and verify**

```bash
python scripts/prepare_training_data.py
# Should print: 8 classes, total N patches, train/val split counts
ls data/training_patches/prepared/
# Should show: black/ white/ black_numbered/ white_numbered/ marked_black/ marked_white/ letter/ empty/
```

---

## Task 3: EfficientNet-B0 Training Script

**Files:**
- Create: `scripts/train_patch_classifier.py`
- Output: `data/models/patch_classifier/model.pt`, `class_map.json`, `training_report.json`

**Rationale:** Transfer learning from ImageNet-pretrained EfficientNet-B0. The model is small (5.3M params, ~16MB weights) and well-suited for small image classification. With heavy augmentation, can work from ~50-100 samples per class.

**Step 1: Write training script**

Model setup:
- `torchvision.models.efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)`
- Modify first conv: sum RGB pretrained weights → 1-channel input (grayscale)
- Replace classifier head: `nn.Linear(1280, 8)`
- Input: grayscale patch → resize to 224x224 → normalize (ImageNet mean/std adapted for grayscale)

Data augmentation (training only):
- `RandomRotation(10)`
- `ColorJitter(brightness=0.3, contrast=0.3)`
- `GaussianBlur(kernel_size=3, sigma=(0.1, 1.0))`
- `RandomAffine(degrees=0, translate=(0.05, 0.05), scale=(0.9, 1.1))`
- `RandomHorizontalFlip(p=0.5)`
- `RandomErasing(p=0.1)` (simulates grid line occlusion)

Training configuration:
- Loss: `CrossEntropyLoss(weight=class_weights)` — from `splits.json`
- Optimizer: `AdamW(lr=1e-3, weight_decay=1e-4)` for head, `1e-5` for backbone
- Schedule: cosine annealing over total epochs
- Epochs: up to 50, early stopping patience=10 on val loss
- Phase 1 (epochs 1-5): freeze backbone, train head only
- Phase 2 (epochs 6+): unfreeze all, differential LR
- Device: auto-detect MPS > CUDA > CPU
- Batch size: 32 (adjustable)

Output artifacts:
- `data/models/patch_classifier/model.pt` — `state_dict` only
- `data/models/patch_classifier/class_map.json` — `{"0": "black", "1": "white", ...}`
- `data/models/patch_classifier/training_report.json` — per-class F1, confusion matrix, hyperparams, timestamp

CLI interface:
```bash
python scripts/train_patch_classifier.py \
    --data-dir data/training_patches/prepared \
    --output-dir data/models/patch_classifier \
    --epochs 50 --batch-size 32 --patience 10
```

**Step 2: Create output directory and run**

```bash
mkdir -p data/models/patch_classifier
python scripts/train_patch_classifier.py --data-dir data/training_patches/prepared --output-dir data/models/patch_classifier
```

**Acceptance criteria:** Val accuracy >80% on classes with >20 samples. Per-class metrics logged.

---

## Task 4: Inference Wrapper

**Files:**
- Create: `katrain/web/tutorials/vision/patch_classifier.py`

**Rationale:** Singleton pattern for model loading (load once, reuse across figures). Batch inference for all patches in a figure in one forward pass.

**Step 1: Write `PatchClassifier` class**

```python
class PatchClassifier:
    """EfficientNet-B0 based Go intersection patch classifier."""

    _instance: Optional["PatchClassifier"] = None
    DEFAULT_MODEL_PATH = "data/models/patch_classifier"

    @classmethod
    def get_instance(cls, model_dir: str = None) -> "PatchClassifier":
        """Lazy singleton — loads model on first call."""

    def __init__(self, model_dir: str):
        """Load model.pt and class_map.json, set eval mode."""

    def classify_batch(self, patches: list[np.ndarray]) -> list[tuple[str, float]]:
        """Classify a batch of grayscale patches.

        Args:
            patches: list of grayscale numpy arrays (variable size, typically 38x38 or 40x40)

        Returns:
            list of (class_label, confidence) tuples
            class_label: one of 8 classes
            confidence: softmax probability of predicted class
        """
        # 1. Preprocess each patch: resize to 224x224, normalize
        # 2. Stack into batch tensor
        # 3. Single forward pass (no_grad)
        # 4. Softmax → argmax → class label + confidence
```

Key design decisions:
- Accept variable-size numpy arrays (resize internally)
- Return raw class names from `class_map.json`, not compound strings
- Caller (`model_classify_figure`) handles composition with OCR results
- Thread-safe via `torch.no_grad()` and eval mode

**Step 2: Verify**

```python
from katrain.web.tutorials.vision.patch_classifier import PatchClassifier
import cv2
clf = PatchClassifier.get_instance()
patch = cv2.imread("data/training_patches/examples/black_plain.png", cv2.IMREAD_GRAYSCALE)
result = clf.classify_batch([patch])
print(result)  # [("black", 0.95)]
```

---

## Task 5: OCR Module (Digit/Letter/Shape)

**Files:**
- Create: `katrain/web/tutorials/vision/patch_ocr.py`
- Create: `data/training_patches/templates/` (3 shape template images)

**Rationale:** Step 2 of the two-step approach. Only invoked on patches classified as numbered/letter/marked by EfficientNet-B0. Uses pre-trained OCR (pytesseract) for digits and letters, template matching for shapes. No custom training required.

**Step 1: Write digit preprocessing pipeline**

For **black numbered** stones (white digits on dark background):
1. Create circular mask: `r = min(h, w) // 2 - 2`, center of patch
2. Apply mask to isolate stone interior
3. Invert: `255 - patch` (white digits → dark on light bg)
4. Adaptive threshold: `cv2.adaptiveThreshold(GAUSSIAN_C, blockSize=11, C=2)`
5. Find contours, filter by area (`20 < area < patch_area * 0.5`)
6. Bounding box of largest contour cluster → digit region
7. Pad to square, resize to 96x96 (upscale for OCR)

For **white numbered** stones (dark digits on light background):
1. Create smaller circular mask: `r = min(h, w) // 2 - 4` (avoid border outline)
2. Apply mask
3. Adaptive threshold (no inversion needed — digits already dark)
4. Same contour extraction + upscale

**Step 2: Write pytesseract integration**

```python
def read_number(self, patch: np.ndarray, stone_color: str) -> Optional[int]:
    digit_region = self._extract_digit_region(patch, stone_color)
    if digit_region is None:
        return None
    # pytesseract with digit whitelist
    text = pytesseract.image_to_string(
        digit_region,
        config="--psm 7 -c tessedit_char_whitelist=0123456789"
    ).strip()
    if text.isdigit() and 1 <= int(text) <= 200:
        return int(text)
    return None

def read_letter(self, patch: np.ndarray) -> Optional[str]:
    letter_region = self._extract_letter_region(patch)
    if letter_region is None:
        return None
    text = pytesseract.image_to_string(
        letter_region,
        config="--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    ).strip()
    return text[0] if text and text[0].isalpha() else None
```

**Step 3: Write shape template matching**

Create 3 template images (triangle, square, circle) at ~20x20px in `data/training_patches/templates/`.

```python
def read_shape(self, patch: np.ndarray, stone_color: str) -> Optional[str]:
    # Preprocess: remove stone fill, isolate shape mark
    # Match against 3 templates using cv2.matchTemplate(TM_CCOEFF_NORMED)
    # Return shape with highest score if > 0.5, else None
```

**Step 4: Verify on known patches**

```python
ocr = PatchOCR()
# Test on a known black+5 patch
patch = cv2.imread("data/tutorial_assets/.../debug/.../patches/A_2_2.png", 0)
print(ocr.read_number(patch, "black"))  # Should print: 5
```

---

## Task 6: Pipeline Integration

**Files:**
- Modify: `scripts/recognize_boards_v2.py`

**Rationale:** Add model-based classification as an alternative path alongside existing VLLM, with `--method` CLI flag. Keep all existing code intact — no removal of VLLM path.

**Step 1: Add CLI argument (~line 1662 in `main()`)**

```python
parser.add_argument(
    "--method", choices=["vllm", "model", "auto"], default="auto",
    help="Classification method: vllm (existing), model (EfficientNet+OCR), auto (model with vllm fallback)"
)
```

**Step 2: Add `model_classify_figure()` function (~insert before line 870)**

```python
def model_classify_figure(
    occupied_patches: list[tuple[int, int, np.ndarray]],
    spacing: float,
    label_map: dict[str, tuple[int, int]],
) -> dict[str, str]:
    """Classify patches using local EfficientNet-B0 + OCR.

    Returns dict of {label: classification_string} compatible with
    parse_classification() and classification_to_payload().
    """
    from katrain.web.tutorials.vision.patch_classifier import PatchClassifier
    from katrain.web.tutorials.vision.patch_ocr import PatchOCR

    classifier = PatchClassifier.get_instance()
    ocr = PatchOCR()

    patches = [patch for ci, ri, patch in occupied_patches]
    coarse_results = classifier.classify_batch(patches)

    classifications = {}
    for idx, (ci, ri, patch) in enumerate(occupied_patches):
        # Find the label for this (ci, ri) from label_map
        label = next(lbl for lbl, (c, r) in label_map.items() if c == ci and r == ri)
        coarse_class, confidence = coarse_results[idx]

        if coarse_class in ("black_numbered", "white_numbered"):
            stone_color = coarse_class.replace("_numbered", "")
            number = ocr.read_number(patch, stone_color)
            cls_str = f"{stone_color}+{number}" if number else stone_color
        elif coarse_class == "letter":
            letter = ocr.read_letter(patch)
            cls_str = f"letter_{letter}" if letter else "empty"
        elif coarse_class in ("marked_black", "marked_white"):
            stone_color = coarse_class.replace("marked_", "")
            shape = ocr.read_shape(patch, stone_color)
            cls_str = f"{shape}_{stone_color}" if shape else stone_color
        else:
            cls_str = coarse_class  # "black", "white", "empty"

        classifications[label] = cls_str

    return classifications
```

**Step 3: Modify `process_page()` classification dispatch (~line 1191)**

Replace the VLLM classification block with method dispatch:

```python
if method in ("model", "auto"):
    try:
        model_result = model_classify_figure(occupied, spacing, full_label_map)
        for lbl, cls_str in model_result.items():
            merged_classifications[lbl] = cls_str
        classification_source = "model"
    except Exception as e:
        if method == "model":
            raise
        log.warning("Model failed (%s), falling back to VLLM", e)
        # ... existing VLLM code block ...
        classification_source = "vllm"
else:  # method == "vllm"
    # ... existing VLLM code block (unchanged) ...
    classification_source = "vllm"
```

**Step 4: Update PatchClassification source**

When building PatchClassification objects from model results, set `source="model"` and `confidence` from the softmax output.

**Step 5: Verify**

```bash
# Dry run with model classification
python scripts/recognize_boards_v2.py --section-id <ID> --method model --dry-run

# Compare with VLLM
python scripts/recognize_boards_v2.py --section-id <ID> --method vllm --dry-run

# Auto mode (model with VLLM fallback)
python scripts/recognize_boards_v2.py --section-id <ID> --method auto --dry-run
```

---

## Task 7: Evaluation & A/B Comparison

**Files:**
- Create: `scripts/compare_classification_methods.py`

**Rationale:** Need to measure model accuracy against VLLM baseline and human-verified ground truth before trusting model for production use.

**Step 1: Write comparison script**

Logic:
1. Query all figures that have existing VLLM classifications in `recognition_debug`
2. For each figure: re-run model classification on the same patches
3. Compare model vs VLLM output per-patch
4. Report: agreement rate, disagreements by class, confusion matrix
5. If human-verified `board_payload` exists: also compare both methods against ground truth

**Step 2: Run and analyze**

```bash
python scripts/compare_classification_methods.py --section-id <ID>
```

Target: >90% agreement with VLLM on confident predictions. Where they disagree, manually check which is correct.

---

## Task 8: Active Learning Loop (Ongoing)

**No new files — leverages existing infrastructure.**

**Rationale:** With only 360 patches (and severe imbalance for 3 classes), the model needs iterative improvement through human-in-the-loop review. The existing web UI verification flow + training export pipeline already supports this.

**Workflow:**
1. Run pipeline with `--method auto` on new sections
2. Model-classified patches get `confidence` scores
3. Figures with low-confidence patches → `needs_review` status in DB
4. Human reviews in web UI → clicks "确认审核"
5. `export_figure_training_samples()` auto-exports to `training_samples` table
6. Periodically: export patches → retrain model → deploy improved weights

**Rare class strategy** (marked, letter — <10 samples):
- Keep VLLM fallback for these via `--method auto` until sufficient data
- Optionally: create synthetic training patches by rendering Go diagrams with known labels
- When ~50+ samples per rare class: retrain with all 8 classes

**Data accumulation target before first meaningful training:**
- Process 5-10 more sections with `--method vllm` first
- Target: ~100+ unique patches per major class (black, white, black_numbered, white_numbered, empty)
- Rare classes (marked, letter) can start with VLLM fallback

---

## Execution Order & Dependencies

```
Task 1 (deps) ──────────────────────────► prerequisite for all
Task 2 (data prep) ────────────────────► prerequisite for Task 3
Task 3 (training script) ──────────────► prerequisite for Task 4
Task 4 (inference wrapper) ────────────► prerequisite for Task 6
Task 5 (OCR module) ───────────────────► prerequisite for Task 6 (can parallel with 3-4)
Task 6 (integration) ──────────────────► requires Task 4 + Task 5
Task 7 (evaluation) ───────────────────► requires Task 6
Task 8 (active learning) ─────────────► ongoing after Task 6
```

Parallelizable: Task 5 can be developed in parallel with Tasks 3-4.

---

## Verification Checklist

- [ ] `uv sync --extra classifier` installs torch + torchvision + pytesseract
- [ ] `prepare_training_data.py` produces 8-class directory with correct counts
- [ ] `train_patch_classifier.py` trains successfully on MPS, val accuracy >80% for major classes
- [ ] `PatchClassifier.classify_batch()` returns correct class for all 6 example patches
- [ ] `PatchOCR.read_number()` reads digits from known numbered patches (at least 1-13)
- [ ] `PatchOCR.read_letter()` reads "A" from known letter patch
- [ ] `recognize_boards_v2.py --method model --dry-run` produces BoardPayload
- [ ] Pipeline speed: <500ms per figure with model (vs 15-20s with VLLM)
- [ ] `--method auto` falls back to VLLM when model confidence < 0.5
- [ ] A/B comparison: >90% agreement with VLLM on confident predictions
