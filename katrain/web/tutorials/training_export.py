"""Auto-export training samples when a figure is human-verified.

Called from the verify_figure endpoint. Uses OpenCV grid detection to crop
precise patches from the crop image, then inserts TrainingSample rows.
"""

import logging
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from katrain.web.core.models_db import TrainingSample, TutorialFigure

log = logging.getLogger("katrain_web")

ASSET_BASE = Path("data")


def _cv_detect_grid(gray):
    """Detect grid line positions (copied core logic from recognize_boards_v2)."""
    h_img, w_img = gray.shape
    _, binary = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY_INV)

    min_line_len = min(h_img, w_img) // 8
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_line_len, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_line_len))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

    h_proj = np.sum(h_lines, axis=1) // 255
    v_proj = np.sum(v_lines, axis=0) // 255

    h_thresh = max(10, int(np.max(h_proj) * 0.3))
    v_thresh = max(10, int(np.max(v_proj) * 0.3))

    est_spacing = min(h_img, w_img) / 20
    min_dist = max(10, int(est_spacing * 0.6))

    h_positions = _find_peaks(h_proj, h_thresh, min_dist)
    v_positions = _find_peaks(v_proj, v_thresh, min_dist)

    if len(h_positions) < 2 or len(v_positions) < 2:
        return h_positions, v_positions, 0.0

    h_spacing = float(np.median(np.diff(h_positions)))
    v_spacing = float(np.median(np.diff(v_positions)))
    spacing = (h_spacing + v_spacing) / 2

    def _fill_gaps(positions, sp):
        if len(positions) < 2:
            return positions
        result = [positions[0]]
        for i in range(1, len(positions)):
            gap = positions[i] - positions[i - 1]
            if gap > sp * 1.6:
                n_missing = round(gap / sp) - 1
                for j in range(1, n_missing + 1):
                    result.append(int(positions[i - 1] + j * gap / (n_missing + 1)))
            result.append(positions[i])
        return np.array(result)

    h_positions = _fill_gaps(h_positions, h_spacing)
    v_positions = _fill_gaps(v_positions, v_spacing)

    return h_positions, v_positions, spacing


def _find_peaks(arr, threshold, min_dist):
    """Find peak positions in a 1D array."""
    above = np.where(arr > threshold)[0]
    if len(above) == 0:
        return np.array([])
    peaks = [above[0]]
    for idx in above[1:]:
        if idx - peaks[-1] >= min_dist:
            peaks.append(idx)
        elif arr[idx] > arr[peaks[-1]]:
            peaks[-1] = idx
    return np.array(peaks)


def _classify_position(board_payload, global_col, global_row):
    """Determine ground-truth classification from board_payload."""
    key = f"{global_col},{global_row}"
    is_black = any(c == global_col and r == global_row for c, r in board_payload.get("stones", {}).get("B", []))
    is_white = any(c == global_col and r == global_row for c, r in board_payload.get("stones", {}).get("W", []))
    base_type = "black" if is_black else "white" if is_white else "empty"

    move_number = None
    labels = board_payload.get("labels", {})
    if key in labels:
        try:
            move_number = int(labels[key])
        except (ValueError, TypeError):
            pass

    shape = board_payload.get("shapes", {}).get(key)
    letter = board_payload.get("letters", {}).get(key)

    return base_type, move_number, shape, letter


def export_figure_training_samples(db: Session, figure: TutorialFigure) -> int:
    """Export patches for a verified figure to training_samples table.

    Uses OpenCV grid detection to crop precise patches from the crop image.
    Returns count of samples exported.
    """
    debug = figure.recognition_debug or {}
    payload = figure.board_payload or {}

    if not debug.get("human_verified"):
        return 0

    classification = debug.get("classification", {})
    label_map = classification.get("label_map", {})
    if not label_map:
        log.warning("Figure %d: no label_map — skipping training export", figure.id)
        return 0

    region = debug.get("region", {})
    col_start = region.get("col_start", 0)
    row_start = region.get("row_start", 0)

    # Skip if already exported
    existing = db.query(TrainingSample).filter_by(figure_id=figure.id).count()
    if existing > 0:
        log.info("Figure %d: already exported (%d samples)", figure.id, existing)
        return 0

    # Derive book slug from page_image_path
    book_slug = ""
    if figure.page_image_path:
        parts = Path(figure.page_image_path).parts
        if len(parts) >= 2:
            book_slug = parts[1]

    # Load crop image and detect grid
    crop_path = ASSET_BASE / "tutorial_assets" / book_slug / "debug" / figure.figure_label / "crop.png"
    if not crop_path.exists():
        log.warning("Figure %d: crop not found at %s", figure.id, crop_path)
        return 0

    gray = cv2.imread(str(crop_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        log.warning("Figure %d: cannot read crop image", figure.id)
        return 0

    h_positions, v_positions, spacing = _cv_detect_grid(gray)
    if spacing == 0:
        log.warning("Figure %d: grid detection failed", figure.id)
        return 0

    r = int(spacing * 0.5)
    h_img, w_img = gray.shape

    # Ensure patches dir exists, save patches if not already there
    patches_dir = crop_path.parent / "patches"
    patches_dir.mkdir(exist_ok=True)

    samples = []
    for label, coords in label_map.items():
        local_col, local_row = coords[0], coords[1]
        global_col = col_start + local_col
        global_row = row_start + local_row

        if local_col >= len(v_positions) or local_row >= len(h_positions):
            continue

        # Crop patch using precise grid positions
        cx = int(v_positions[local_col])
        cy = int(h_positions[local_row])
        x1, y1 = max(0, cx - r), max(0, cy - r)
        x2, y2 = min(w_img, cx + r), min(h_img, cy + r)
        patch = gray[y1:y2, x1:x2]

        # Save patch to disk
        patch_filename = f"{label}_{local_col}_{local_row}.png"
        patch_path = patches_dir / patch_filename
        if not patch_path.exists():
            cv2.imwrite(str(patch_path), patch)

        # Classify from ground truth
        base_type, move_number, shape, letter = _classify_position(payload, global_col, global_row)
        relative_path = str(patch_path.relative_to(ASSET_BASE))

        sample = TrainingSample(
            figure_id=figure.id,
            patch_label=label,
            local_col=local_col,
            local_row=local_row,
            global_col=global_col,
            global_row=global_row,
            patch_image_path=relative_path,
            base_type=base_type,
            move_number=move_number,
            shape=shape,
            letter=letter,
            source="human",
            book_slug=book_slug,
        )
        samples.append(sample)

    if samples:
        db.add_all(samples)
        db.commit()

    log.info("Figure %d: exported %d training samples", figure.id, len(samples))
    return len(samples)
