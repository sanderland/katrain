#!/usr/bin/env python3
"""Hybrid CV+VLLM Go board recognition from book page images.

Pipeline:
  Step 0: CV detects diagram bounding boxes on the page (VLLM fallback)
  Step 1: VLLM identifies which part of the 19x19 board is shown (col_start/row_start)
  Step 2: CV detects grid lines precisely (no counting errors)
  Step 3: CV detects occupied intersections + pre-classifies obvious B/W
  Step 4: VLLM classifies ambiguous patches via contact sheet
  Step 5: Merge CV+VLLM → board_payload → DB + training data

Division of labor:
  CV  handles WHERE: grid lines, intersection positions, patch cropping
  VLLM handles WHAT: stone color, move numbers, annotations, board region

Usage:
    # Generate contact sheets (CV only, fast)
    python scripts/recognize_boards_v2.py --section-id 1 --save-sheets /tmp/sheets/

    # Apply subagent classifications to DB
    python scripts/recognize_boards_v2.py --section-id 1 --apply-classifications FILE.json --force

    # Full auto pipeline (requires working VLLM)
    python scripts/recognize_boards_v2.py --section-id 1 --force [--dry-run]

    # Test CV pipeline only
    python scripts/recognize_boards_v2.py --test-cv PAGE_IMAGE
"""

import argparse
import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from PIL import Image

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from katrain.web.core.config import settings
from katrain.web.tutorials import db_queries
from katrain.web.tutorials.vision.region_calibrator import calibrate_region

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ASSET_BASE = Path("data")
MODEL_DIR = Path(__file__).resolve().parent.parent / "katrain" / "models" / "book-kifu"


# ── Structured classification schema ─────────────────────────────────────────

@dataclass
class PatchClassification:
    """Classification result for a single intersection patch."""
    label: str                            # contact sheet label: "A", "B", ...
    local_col: int                        # grid index in cropped diagram
    local_row: int
    base_type: str                        # "black" | "white" | "empty" | "unknown"
    text: Optional[str] = None            # move number "1"-"99+" or letter "A"-"Z" or None
    shape: Optional[str] = None           # "triangle" | "square" | "circle" | None
    confidence: float = 1.0               # 0.0-1.0; <0.8 → needs_review
    source: str = "cv"                    # "cv" | "vllm" | "model" | "human"


@dataclass
class FigureResult:
    """Per-figure processing result for batch status tracking."""
    label: str
    figure_id: int
    status: str  # "success" | "needs_review" | "failed_cv" | "failed_semantic" | "skipped"
    detail: str = ""
    stone_count: int = 0
    label_count: int = 0
    calibration_confidence: float = 0.0


@dataclass
class CVParams:
    """Per-book CV parameters for the recognition pipeline.

    Defaults match the 布局 books (good scan quality). For books with lighter
    grid lines or different scan characteristics, create a cv_params.json in
    data/tutorial_assets/{slug}/ with overridden values.
    """
    # S0: bbox detection
    bbox_binary_threshold: int = 160
    # S2: grid detection
    grid_binary_threshold: int = 160
    grid_min_line_len_ratio: float = 0.125       # min(h,w) * ratio
    grid_peak_threshold_ratio: float = 0.3       # of max projection value
    # S3: occupied detection
    occupied_dark_pixel_threshold: int = 100
    occupied_anomaly_sigma: float = 2.0
    # S3b: pre-classification
    preclass_black_dark_ratio: float = 0.55
    preclass_black_mean_max: float = 80.0
    preclass_white_mean_min: float = 180.0
    preclass_white_dark_ratio_max: float = 0.05
    # Deskew
    deskew_binary_threshold: int = 160

    @classmethod
    def from_file(cls, path):
        """Load from JSON file. Unknown keys are ignored, missing keys use defaults."""
        path = Path(path)
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        valid_names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid_names})

    def to_file(self, path):
        """Save to JSON file with a description header."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"_description": "Per-book CV parameters. Edit to tune recognition for this book's scan quality."}
        for f in fields(self):
            data[f.name] = getattr(self, f.name)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_cv_params(book_slug):
    """Load per-book CV params, auto-creating defaults if missing."""
    cv_path = ASSET_BASE / "tutorial_assets" / book_slug / "cv_params.json"
    if cv_path.exists():
        params = CVParams.from_file(cv_path)
        log.info("Loaded CV params from %s", cv_path)
    else:
        params = CVParams()
        params.to_file(cv_path)
        log.info("Created default CV params at %s", cv_path)
    return params


def print_summary_report(results):
    """Print a summary report of figure processing results."""
    log.info("\n═══ Processing Summary ═══")
    status_counts = defaultdict(int)
    for r in results:
        status_counts[r.status] += 1
        icon = {"success": "✓", "needs_review": "?", "skipped": "—"}.get(r.status, "✗")
        log.info("  %s %s (id=%d): %s %s",
                 icon, r.label, r.figure_id, r.status, r.detail)

    log.info("──────────────────────────")
    for status, count in sorted(status_counts.items()):
        log.info("  %s: %d", status, count)
    log.info("  total: %d", len(results))


def parse_classification(label, cls_str, local_col, local_row, source="vllm"):
    """Parse a VLLM classification string into a PatchClassification."""
    base_type = "unknown"
    text = None
    shape = None

    if cls_str == "empty":
        return PatchClassification(label, local_col, local_row, "empty", source=source)

    if cls_str.startswith("black"):
        base_type = "black"
        if "+" in cls_str:
            text = cls_str.split("+", 1)[1]
    elif cls_str.startswith("white"):
        base_type = "white"
        if "+" in cls_str:
            text = cls_str.split("+", 1)[1]
    elif cls_str in ("triangle", "square", "circle", "cross"):
        shape = cls_str
        base_type = "empty"  # bare shape on empty intersection
    elif cls_str.startswith(("triangle_", "square_", "circle_", "cross_")):
        parts = cls_str.split("_", 1)
        shape = parts[0]
        base_type = parts[1] if len(parts) > 1 else "empty"
    elif cls_str.startswith("letter_"):
        base_type = "empty"
        text = cls_str.split("_", 1)[1]

    return PatchClassification(label, local_col, local_row, base_type,
                               text=text, shape=shape, source=source)


def classification_to_payload(classifications, label_map, col_start=0, row_start=0):
    """Convert classification results to board_payload format.

    Args:
        classifications: dict like {"A": "black+1", "B": "white+8", ...}
            OR list of PatchClassification objects
        label_map: dict like {"A": (col_idx, row_idx), ...}
        col_start: offset to map local col to full 19×19 col
        row_start: offset to map local row to full 19×19 row
    """
    black, white = [], []
    labels, letters, shapes = {}, {}, {}

    # Normalize to PatchClassification objects
    if isinstance(classifications, dict):
        parsed = []
        for lbl, cls_str in classifications.items():
            if lbl in label_map:
                ci, ri = label_map[lbl]
                parsed.append(parse_classification(lbl, cls_str, ci, ri))
        items = parsed
    else:
        items = classifications

    for pc in items:
        if pc.base_type == "empty" and pc.text and pc.text.isalpha():
            # Letter annotation on empty intersection
            ci, ri = pc.local_col, pc.local_row
            col = col_start + ci
            row = row_start + ri
            key = f"{col},{row}"
            letters[key] = pc.text
            continue

        if pc.base_type == "empty" and pc.shape:
            # Shape mark on empty intersection (e.g. triangle without stone)
            ci, ri = pc.local_col, pc.local_row
            col = col_start + ci
            row = row_start + ri
            shapes[f"{col},{row}"] = pc.shape
            continue

        if pc.base_type in ("empty", "unknown"):
            continue

        ci, ri = pc.local_col, pc.local_row
        col = col_start + ci
        row = row_start + ri
        key = f"{col},{row}"

        if pc.base_type == "black":
            black.append([col, row])
        elif pc.base_type == "white":
            white.append([col, row])

        if pc.text and pc.text.isdigit():
            labels[key] = pc.text

        if pc.shape:
            shapes[key] = pc.shape

    return {
        "size": 19,
        "stones": {"B": black, "W": white},
        "labels": labels,
        "letters": letters,
        "shapes": shapes,
        "highlights": [],
    }


# ── Debug image generation ────────────────────────────────────────────────────

def generate_bbox_debug_image(page_img, bboxes, figure_labels):
    """Draw bounding boxes on page image. Returns annotated image."""
    debug = page_img.copy()
    colors = [(0, 200, 0), (200, 0, 0), (0, 0, 200), (200, 200, 0)]
    for i, (label, bbox) in enumerate(zip(figure_labels, bboxes)):
        if bbox is None:
            continue
        x1, y1, x2, y2 = [int(c) for c in bbox]
        color = colors[i % len(colors)]
        cv2.rectangle(debug, (x1, y1), (x2, y2), color, 3)
        cv2.putText(debug, label, (x1 + 5, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
    return debug


def generate_grid_debug_image(crop, h_pos, v_pos, spacing, occupied, confident, ambiguous):
    """Draw grid lines and occupied patches on crop. Returns annotated image."""
    debug = crop.copy()
    if len(debug.shape) == 2:
        debug = cv2.cvtColor(debug, cv2.COLOR_GRAY2BGR)

    # Draw grid lines
    for y in h_pos:
        cv2.line(debug, (0, int(y)), (debug.shape[1], int(y)), (0, 0, 200), 1)
    for x in v_pos:
        cv2.line(debug, (int(x), 0), (int(x), debug.shape[0]), (200, 0, 0), 1)

    r = int(spacing * 0.4) if spacing > 0 else 8

    # Draw occupied intersections
    confident_set = {(ci, ri) for ci, ri, _, _ in confident}
    for ci, ri, _ in occupied:
        vx, hy = int(v_pos[ci]), int(h_pos[ri])
        if (ci, ri) in confident_set:
            cv2.circle(debug, (vx, hy), r, (0, 220, 0), 2)  # green = confident
        else:
            cv2.circle(debug, (vx, hy), r, (0, 220, 220), 2)  # yellow = ambiguous

    # Label indices
    for ci, ri, _ in occupied:
        vx, hy = int(v_pos[ci]), int(h_pos[ri])
        cv2.putText(debug, f"{ci},{ri}", (vx + r + 2, hy + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

    return debug


def generate_deskew_debug_image(original_crop, h_pos, v_pos, deskew_angle):
    """Draw detected grid lines projected back onto the original (pre-deskew) crop.

    Grid lines are detected on the deskewed image. This function applies the
    inverse rotation to project them back onto the original image, so the user
    can visually verify both deskew accuracy and grid alignment.

    Returns annotated BGR image.
    """
    debug = original_crop.copy()
    if len(debug.shape) == 2:
        debug = cv2.cvtColor(debug, cv2.COLOR_GRAY2BGR)
    h_img, w_img = debug.shape[:2]

    if abs(deskew_angle) < 0.1:
        # No deskew — just draw straight grid lines (same as grid_debug)
        for y in h_pos:
            cv2.line(debug, (0, int(y)), (w_img, int(y)), (0, 180, 0), 1)
        for x in v_pos:
            cv2.line(debug, (int(x), 0), (int(x), h_img), (0, 180, 0), 1)
        return debug

    # Inverse rotation matrix: rotate by -deskew_angle around image center
    center = (w_img / 2, h_img / 2)
    M_inv = cv2.getRotationMatrix2D(center, -deskew_angle, 1.0)

    def transform_point(x, y):
        """Apply inverse rotation to a point."""
        pt = np.array([x, y, 1.0])
        result = M_inv @ pt
        return int(round(result[0])), int(round(result[1]))

    # Draw horizontal grid lines (projected back to original space)
    for y in h_pos:
        y_int = int(round(y))
        p1 = transform_point(0, y_int)
        p2 = transform_point(w_img, y_int)
        cv2.line(debug, p1, p2, (0, 180, 0), 1)

    # Draw vertical grid lines (projected back to original space)
    for x in v_pos:
        x_int = int(round(x))
        p1 = transform_point(x_int, 0)
        p2 = transform_point(x_int, h_img)
        cv2.line(debug, p1, p2, (0, 180, 0), 1)

    # Add deskew angle annotation
    cv2.putText(debug, f"deskew: {deskew_angle:+.2f}deg", (5, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    return debug


def save_debug_images(page_img, crop, h_pos, v_pos, spacing, occupied, confident, ambiguous,
                      bboxes_dict, figure_labels, label, book_slug,
                      original_crop=None, deskew_angle=0.0):
    """Save all debug images and return their relative paths."""
    debug_dir = ASSET_BASE / "tutorial_assets" / book_slug / "debug" / label
    debug_dir.mkdir(parents=True, exist_ok=True)

    paths = {}

    # 1. Bbox debug image (page with rectangles)
    bbox_list = [bboxes_dict.get(l) for l in figure_labels]
    bbox_debug = generate_bbox_debug_image(page_img, bbox_list, figure_labels)
    bbox_path = debug_dir / "bbox_debug.png"
    cv2.imwrite(str(bbox_path), bbox_debug)
    paths["bbox_debug"] = str(bbox_path.relative_to(ASSET_BASE))

    # 2. Grid + occupied debug image (on deskewed crop)
    grid_debug = generate_grid_debug_image(crop, h_pos, v_pos, spacing, occupied, confident, ambiguous)
    grid_path = debug_dir / "grid_debug.png"
    cv2.imwrite(str(grid_path), grid_debug)
    paths["grid_debug"] = str(grid_path.relative_to(ASSET_BASE))

    # 3. Deskew debug image (grid lines projected back onto original crop)
    if original_crop is not None:
        deskew_debug = generate_deskew_debug_image(original_crop, h_pos, v_pos, deskew_angle)
        deskew_path = debug_dir / "deskew_debug.png"
        cv2.imwrite(str(deskew_path), deskew_debug)
        paths["deskew_debug"] = str(deskew_path.relative_to(ASSET_BASE))

    # 4. Crop image
    crop_path = debug_dir / "crop.png"
    cv2.imwrite(str(crop_path), crop)
    paths["crop"] = str(crop_path.relative_to(ASSET_BASE))

    return paths


# ── Training data collection ──────────────────────────────────────────────────

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
        "local_col": local_col,
        "local_row": local_row,
        "global_col": global_col,
        "global_row": global_row,
        "base_type": base_type,
        "text": classification.text,
        "shape": classification.shape,
        "confidence": classification.confidence,
        "source": source,
        "review_status": "raw_auto",  # raw_auto → reviewed → gold
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = TRAINING_DIR / "manifest.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return patch_id


def save_all_training_patches(occupied_patches, classifications, label_map,
                              col_start, row_start, book_slug, page, figure_label,
                              classification_source="vllm"):
    """Save all patches (including empty) for a figure with full provenance."""
    saved = 0
    patch_lookup = {(ci, ri): patch for ci, ri, patch in occupied_patches}

    for lbl, (ci, ri) in label_map.items():
        patch = patch_lookup.get((ci, ri))
        if patch is None:
            continue

        # Get classification for this label
        if isinstance(classifications, dict):
            cls_str = classifications.get(lbl, "empty")
            pc = parse_classification(lbl, cls_str, ci, ri, source=classification_source)
        elif isinstance(classifications, list):
            pc = next((c for c in classifications if c.label == lbl), None)
            if pc is None:
                pc = PatchClassification(lbl, ci, ri, "empty", source="cv")
        else:
            continue

        save_training_patch(
            patch, pc, book_slug, page, figure_label,
            ci, ri, col_start + ci, row_start + ri, pc.source
        )
        saved += 1

    log.info("  Saved %d training patches for %s", saved, figure_label)
    return saved


# ── Step 2: OpenCV grid detection ─────────────────────────────────────────────

def _find_peaks(arr, min_val, min_dist):
    """Simple 1D peak finder without scipy dependency."""
    peaks = []
    for i in range(1, len(arr) - 1):
        if arr[i] >= min_val and arr[i] >= arr[i - 1] and arr[i] >= arr[i + 1]:
            if not peaks or i - peaks[-1] >= min_dist:
                peaks.append(i)
    return np.array(peaks)


def _refine_positions(line_image, positions, axis, window=15):
    """Refine grid line positions to sub-pixel accuracy using weighted centroid.

    Uses the morphological line image (where only H or V lines remain) as weights.
    For each detected peak, computes the center-of-mass in a window around it.
    """
    h_img, w_img = line_image.shape
    refined = []
    for pos in positions:
        idx = int(pos)
        if axis == "h":
            y1 = max(0, idx - window)
            y2 = min(h_img, idx + window + 1)
            weights = np.sum(line_image[y1:y2, :], axis=1).astype(float)
        else:
            x1 = max(0, idx - window)
            x2 = min(w_img, idx + window + 1)
            weights = np.sum(line_image[:, x1:x2], axis=0).astype(float)
        if np.sum(weights) > 0:
            centroid = np.average(np.arange(len(weights)), weights=weights)
            refined.append((y1 if axis == "h" else x1) + centroid)
        else:
            refined.append(float(pos))
    return np.array(refined)


def cv_detect_grid(gray, cv_params=None):
    """Detect grid line positions from a grayscale board image.

    Returns (h_positions, v_positions, spacing) where positions are pixel
    coordinates of each horizontal/vertical grid line.
    """
    if cv_params is None:
        cv_params = CVParams()
    h_img, w_img = gray.shape

    _, binary = cv2.threshold(gray, cv_params.grid_binary_threshold, 255, cv2.THRESH_BINARY_INV)

    # Morphological isolation of horizontal and vertical lines
    min_line_len = int(min(h_img, w_img) * cv_params.grid_min_line_len_ratio)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_line_len, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_line_len))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

    # Project to 1D
    h_proj = np.sum(h_lines, axis=1) // 255
    v_proj = np.sum(v_lines, axis=0) // 255

    h_thresh = max(10, int(np.max(h_proj) * cv_params.grid_peak_threshold_ratio))
    v_thresh = max(10, int(np.max(v_proj) * cv_params.grid_peak_threshold_ratio))

    # Estimate minimum distance between lines (~60% of expected spacing)
    est_spacing = min(h_img, w_img) / 20
    min_dist = max(10, int(est_spacing * 0.6))

    h_positions = _find_peaks(h_proj, h_thresh, min_dist)
    v_positions = _find_peaks(v_proj, v_thresh, min_dist)

    if len(h_positions) < 2 or len(v_positions) < 2:
        return h_positions, v_positions, 0.0

    h_spacing = float(np.median(np.diff(h_positions)))
    v_spacing = float(np.median(np.diff(v_positions)))
    spacing = (h_spacing + v_spacing) / 2

    # Fill gaps where stones occlude grid lines (gap ≈ 2× spacing → missing line)
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

    # Sub-pixel refinement: use weighted centroid on the morphological line image
    window = max(3, int(spacing * 0.4))
    h_positions = _refine_positions(h_lines, h_positions, axis="h", window=window)
    v_positions = _refine_positions(v_lines, v_positions, axis="v", window=window)

    return h_positions, v_positions, spacing


# ── Step 3a: OpenCV occupied intersection detection ──────────────────────────

def cv_detect_occupied(gray, h_positions, v_positions, spacing, cv_params=None):
    """Detect all non-empty intersections using multi-feature anomaly detection.

    Returns list of (col_idx, row_idx, patch) where patch is the cropped grayscale image.
    Does NOT classify color — that's VLLM's job.
    """
    if cv_params is None:
        cv_params = CVParams()
    h_img, w_img = gray.shape
    r = int(spacing * 0.5)  # slightly larger for better patch quality
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
            dark_ratio = float(np.sum(roi < cv_params.occupied_dark_pixel_threshold) / roi.size)
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

    dark_med, dark_std = float(np.median(darks)), float(np.std(darks))
    edge_med, edge_std = float(np.median(edges_arr)), float(np.std(edges_arr))
    std_med, std_std = float(np.median(stds)), float(np.std(stds))

    # Mark as occupied if ANY feature is anomalous (wide net, minimal false negatives)
    occupied = []
    occupied_set = set()
    for ci, ri, vx, hy, dark, edge, std_v, circ, roi in features:
        is_occupied = (
            dark > dark_med + cv_params.occupied_anomaly_sigma * dark_std
            or edge > edge_med + cv_params.occupied_anomaly_sigma * edge_std
            or std_v > std_med + cv_params.occupied_anomaly_sigma * std_std
            or circ < -15  # white stone signature (light center)
            or dark > 0.28  # absolute threshold for numbered stones
        )
        if is_occupied:
            occupied.append((ci, ri, roi))
            occupied_set.add((ci, ri))

    # Second pass: detect letter annotations (A, B, C...) at unoccupied intersections.
    # Strategy: for each patch, mask out the grid cross pattern, count remaining dark pixels.
    # Letters have strokes OUTSIDE the grid lines; empty intersections don't.
    cross_w = max(3, int(spacing * 0.08))  # grid line thickness
    for ci, ri, vx, hy, dark, edge, std_v, circ, roi in features:
        if (ci, ri) in occupied_set:
            continue
        # Skip border rows/columns (thick border lines are noisy)
        if ci == 0 or ci == len(v_positions) - 1:
            continue
        if ri == 0 or ri == len(h_positions) - 1:
            continue
        # Mask out the grid cross (horizontal + vertical line through center)
        h_roi, w_roi = roi.shape
        mask = np.ones_like(roi, dtype=np.uint8) * 255
        cy, cx = h_roi // 2, w_roi // 2
        mask[cy - cross_w:cy + cross_w + 1, :] = 0  # horizontal line
        mask[:, cx - cross_w:cx + cross_w + 1] = 0   # vertical line
        # Count dark pixels OUTSIDE the grid cross
        outside_dark = np.sum((roi < 120) & (mask > 0))
        outside_total = np.sum(mask > 0)
        if outside_total == 0:
            continue
        outside_ratio = float(outside_dark) / outside_total
        # Real letters have outside_ratio > 0.12 (e.g. "A"=0.156)
        # Noise from grid/text residue is typically 0.02-0.10
        if outside_ratio > 0.12:
            occupied.append((ci, ri, roi))
            occupied_set.add((ci, ri))
            log.debug("  Letter candidate at (%d,%d): outside_ratio=%.3f", ci, ri, outside_ratio)

    return occupied


def cv_preclass_confident(occupied_patches, spacing, cv_params=None):
    """Pre-classify high-confidence patches using simple CV heuristics.

    Returns (confident, ambiguous) where:
      confident: list of (col_idx, row_idx, patch, base_type) for obvious B/W
      ambiguous: list of (col_idx, row_idx, patch) needing VLLM classification
    """
    if cv_params is None:
        cv_params = CVParams()
    confident = []
    ambiguous = []

    for ci, ri, patch in occupied_patches:
        dark_ratio = float(np.sum(patch < cv_params.occupied_dark_pixel_threshold) / patch.size)
        mean_val = float(np.mean(patch))

        # Very dark → almost certainly black stone
        if dark_ratio > cv_params.preclass_black_dark_ratio and mean_val < cv_params.preclass_black_mean_max:
            confident.append((ci, ri, patch, "black"))
        # Very light center → almost certainly white stone (no number)
        elif mean_val > cv_params.preclass_white_mean_min and dark_ratio < cv_params.preclass_white_dark_ratio_max:
            confident.append((ci, ri, patch, "white"))
        else:
            ambiguous.append((ci, ri, patch))

    return confident, ambiguous


# ── Annotated crop for debug visualization ───────────────────────────────────

def build_annotated_crop(crop, h_positions, v_positions, occupied_patches, spacing):
    """Draw letter labels at occupied intersections on the full crop image.

    Unlike build_contact_sheet (isolated patches), this gives VLLM full context:
    complete stone shapes, surrounding board lines, and neighboring stones.

    Returns (annotated_image, label_map) where label_map is {"A": (col_idx, row_idx), ...}
    """
    annotated = crop.copy()
    if len(annotated.shape) == 2:
        annotated = cv2.cvtColor(annotated, cv2.COLOR_GRAY2BGR)

    label_map = {}
    r = max(8, int(spacing * 0.25))  # label circle radius

    for idx, (ci, ri, _) in enumerate(occupied_patches):
        if idx < 26:
            label = chr(65 + idx)
        else:
            label = chr(65 + idx // 26 - 1) + chr(65 + idx % 26)
        label_map[label] = (ci, ri)

        vx = int(v_positions[ci])
        hy = int(h_positions[ri])

        # Draw a white circle background with magenta border for the label
        cv2.circle(annotated, (vx, hy), r, (255, 255, 255), -1)  # white fill
        cv2.circle(annotated, (vx, hy), r, (200, 0, 200), 2)     # magenta border

        # Draw the letter label centered
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4 if len(label) == 1 else 0.3
        (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
        cv2.putText(annotated, label, (vx - tw // 2, hy + th // 2),
                    font, font_scale, (200, 0, 200), 1, cv2.LINE_AA)

    return annotated, label_map


# ── Step 3b: OpenCV stone detection (legacy) ─────────────────────────────────

def cv_detect_stones_legacy(gray, h_positions, v_positions, spacing):
    """Detect stones at grid intersections using dark-ratio + edge analysis.

    Legacy version that classifies B/W. Kept for --test-cv comparison.
    Returns list of (col_idx, row_idx, color) where color is 'B' or 'W'.
    """
    h_img, w_img = gray.shape
    r = int(spacing * 0.45)
    if r < 3:
        return []

    # Compute features for every intersection
    features = []
    for ci, vx in enumerate(v_positions):
        for ri, hy in enumerate(h_positions):
            y1, y2 = max(0, hy - r), min(h_img, hy + r)
            x1, x2 = max(0, vx - r), min(w_img, vx + r)
            roi = gray[y1:y2, x1:x2]
            if roi.size == 0:
                continue
            edges = cv2.Canny(roi, 50, 150)
            dark_ratio = float(np.sum(roi < 100) / roi.size)
            edge_ratio = float(np.sum(edges > 0) / edges.size)
            features.append((ci, ri, int(vx), int(hy), dark_ratio, edge_ratio))

    if not features:
        return []

    # Fixed thresholds derived from empirical analysis of Go book scans:
    #   Black stone:  dark_ratio > 0.45 (solid filled circle)
    #   White+number: dark_ratio > 0.28 AND std > 105 (circle outline + number text)
    #   White plain:  circ_contrast < -15 (light center, dark outline ring)
    BLACK_DARK = 0.45
    WHITE_NUMBERED_DARK = 0.28
    WHITE_NUMBERED_STD = 105
    WHITE_PLAIN_CONTRAST = -15

    stones = []
    for ci, ri, vx, hy, dark, edge in features:
        if dark > BLACK_DARK:
            stones.append((ci, ri, "B"))
            continue

        # White stone with number: moderate dark + high std (number adds texture)
        y1, y2 = max(0, hy - r), min(h_img, hy + r)
        x1, x2 = max(0, vx - r), min(w_img, vx + r)
        roi = gray[y1:y2, x1:x2]
        std_val = float(np.std(roi.astype(float)))

        if dark > WHITE_NUMBERED_DARK and std_val > WHITE_NUMBERED_STD:
            stones.append((ci, ri, "W"))
            continue

        # White stone without number: circle outline makes edges darker than center
        if roi.size > 0:
            mask = np.zeros_like(roi, dtype=np.uint8)
            cr = roi.shape[0] // 2
            cv2.circle(mask, (cr, cr), max(1, cr - 2), 255, -1)
            inside = roi[mask > 0]
            outside = roi[mask == 0]
            if inside.size > 0 and outside.size > 0:
                circ_contrast = float(np.mean(outside)) - float(np.mean(inside))
                if circ_contrast < WHITE_PLAIN_CONTRAST:
                    stones.append((ci, ri, "W"))

    return stones


# ── Step 4: Haiku per-patch classification ────────────────────────────────────

HAIKU_CLASSIFY_PROMPT = """This is a small cropped patch from a Go (围棋) textbook diagram, centered on one grid intersection.

Classify what is at this intersection. Use EXACTLY one of these formats:
- black+N  — black stone (dark filled circle) with move number N (where N is 1-999)
- white+N  — white stone (open circle with thick dark border) with move number N (where N is 1-999)
- black    — black stone without any number (solid dark circle)
- white    — white stone without any number (open circle with thick dark border, light/empty inside)
- letter_X — a letter annotation (A-Z or a-z) on an empty intersection, e.g. letter_A, letter_b
- triangle_black — a triangle mark (△) on a BLACK stone
- triangle_white — a triangle mark (△) on a WHITE stone
- triangle — a triangle mark (△) on an empty intersection (no stone)
- cross_black — a cross mark (✕) on a BLACK stone
- cross_white — a cross mark (✕) on a WHITE stone
- cross — a cross mark (✕) on an empty intersection (no stone)
- empty    — just thin grid lines crossing, nothing else

IMPORTANT distinctions:
- White stones have a THICK circular border. Empty intersections only have THIN crossing grid lines.
- Numbers on stones (1, 2, 3... up to 3 digits) are MOVE numbers, NOT letters. A "2" on a white stone = white+2, NOT letter_2.
- Letters are ONLY alphabetic (A-Z or a-z), never numeric. They appear on empty intersections without any stone.

Answer with just one classification, nothing else."""


def haiku_classify_patch(patch_image_path, max_retries=3):
    """Classify a single Go intersection patch using Claude Haiku via Anthropic SDK.

    Uses ANTHROPIC_API_KEY directly (no claude CLI overhead).
    Retries on 429 rate limit errors with exponential backoff.
    Returns classification string like "black+1", "white", "letter_A", "empty".
    """
    import time
    import anthropic

    img_bytes = Path(patch_image_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode()

    use_thinking = os.environ.get("HAIKU_THINKING", "").lower() in ("1", "true", "yes")
    client = anthropic.Anthropic()
    for attempt in range(max_retries):
        try:
            kwargs = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2048 if use_thinking else 20,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                        {"type": "text", "text": HAIKU_CLASSIFY_PROMPT},
                    ],
                }],
            }
            if use_thinking:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": 1024}
            response = client.messages.create(**kwargs)
            break
        except anthropic.RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** attempt + 1  # 2s, 3s, 5s
                log.info("    Rate limited, waiting %ds before retry...", wait)
                time.sleep(wait)
            else:
                raise
        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            if attempt < max_retries - 1:
                wait = 3 * (attempt + 1)  # 3s, 6s, 9s
                log.info("    Connection error, waiting %ds before retry...", wait)
                time.sleep(wait)
            else:
                raise

    # With thinking, response has [thinking_block, text_block]; without, just [text_block]
    text = next(b.text for b in response.content if b.type == "text").strip()
    text = text.split("\n")[0].strip().strip('"').strip("'").rstrip(".")
    # Normalize prefix to lowercase but preserve letter case in letter_X
    if text.lower().startswith("letter_"):
        return "letter_" + text[7:]  # keep original case of the letter
    return text.lower()


def qwen_classify_patch(patch_image_path, max_retries=3):
    """Classify a single Go intersection patch using Qwen VL via DashScope API.

    Uses DASHSCOPE_API_KEY from environment. Compatible with OpenAI SDK format.
    Retries on rate limit errors with exponential backoff.
    Returns classification string like "black+1", "white", "letter_A", "empty".
    """
    import time
    from openai import OpenAI

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY not set — add it to .zshrc or export it")

    img_bytes = Path(patch_image_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode()

    client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="qwen3-vl-plus",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                        {"type": "text", "text": HAIKU_CLASSIFY_PROMPT},
                    ],
                }],
                max_tokens=256,
                extra_body={"enable_thinking": True, "thinking_budget": 200},
            )
            break
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str or "throttl" in err_str:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt + 1
                    log.info("    Rate limited, waiting %ds before retry...", wait)
                    time.sleep(wait)
                else:
                    raise
            elif "connect" in err_str or "timeout" in err_str:
                if attempt < max_retries - 1:
                    wait = 3 * (attempt + 1)
                    log.info("    Connection error, waiting %ds before retry...", wait)
                    time.sleep(wait)
                else:
                    raise
            else:
                raise

    text = response.choices[0].message.content.strip()
    text = text.split("\n")[0].strip().strip('"').strip("'").rstrip(".")
    if text.lower().startswith("letter_"):
        return "letter_" + text[7:]
    return text.lower()


def gemini_classify_patch(patch_image_path, max_retries=3):
    """Classify a single Go intersection patch using Gemini via Google GenAI SDK.

    Uses GEMINI_API_KEY from environment. Uses native SDK to disable thinking.
    Returns classification string like "black+1", "white", "letter_A", "empty".
    """
    import time
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set — get one at https://aistudio.google.com/apikey")

    img_bytes = Path(patch_image_path).read_bytes()
    client = genai.Client(api_key=api_key)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    HAIKU_CLASSIFY_PROMPT,
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=20,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            break
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str or "resource" in err_str:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt + 1
                    log.info("    Rate limited, waiting %ds before retry...", wait)
                    time.sleep(wait)
                else:
                    raise
            elif "connect" in err_str or "timeout" in err_str:
                if attempt < max_retries - 1:
                    wait = 3 * (attempt + 1)
                    log.info("    Connection error, waiting %ds before retry...", wait)
                    time.sleep(wait)
                else:
                    raise
            else:
                raise

    raw = response.text
    if raw is None:
        raise RuntimeError("Gemini returned empty response (thinking consumed all tokens)")
    text = raw.strip()
    text = text.strip("`").strip()
    text = text.split("\n")[0].strip().strip('"').strip("'").rstrip(".")
    if text.lower().startswith("letter_"):
        return "letter_" + text[7:]
    return text.lower()



def _coarse_to_compound(coarse: str, patch: np.ndarray, ocr) -> str:
    """Convert EfficientNet coarse class + OCR into pipeline compound format.

    Fallback when OCR fails: numbered → bare color, letter → empty, marked → bare color.
    """
    if coarse in ("black", "white", "empty"):
        return coarse
    if coarse == "black_numbered":
        num = ocr.read_number(patch, "black")
        return f"black+{num}" if num else "black"
    if coarse == "white_numbered":
        num = ocr.read_number(patch, "white")
        return f"white+{num}" if num else "white"
    if coarse == "letter":
        letter = ocr.read_letter(patch)
        return f"letter_{letter}" if letter else "empty"
    if coarse == "marked_black":
        shape = ocr.read_shape(patch, "black")
        return f"{shape}_black" if shape else "black"
    if coarse == "marked_white":
        shape = ocr.read_shape(patch, "white")
        return f"{shape}_white" if shape else "white"
    return "empty"


def local_classify_patch(patch_image_path, max_retries=3):
    """Classify a single Go intersection patch using local EfficientNet-B0 + OCR.

    Same signature as haiku_classify_patch. Combines coarse EfficientNet class
    with PatchOCR to produce compound strings matching the pipeline format.
    """
    from katrain.web.tutorials.vision.patch_classifier import PatchClassifier
    from katrain.web.tutorials.vision.patch_ocr import PatchOCR

    patch = cv2.imread(str(patch_image_path), cv2.IMREAD_GRAYSCALE)
    if patch is None:
        return "empty"
    classifier = PatchClassifier.get_instance(MODEL_DIR)
    ocr = PatchOCR()
    coarse, conf = classifier.classify_single(patch)
    return _coarse_to_compound(coarse, patch, ocr)


def cv_detect_bboxes(page_image_path, cv_params=None):
    """Step 0: Detect bounding boxes for each board diagram on the page using OpenCV.

    Uses morphological line detection to find regions with dense grid patterns.
    Returns list of (x1, y1, x2, y2) tuples sorted top-to-bottom, left-to-right.
    """
    if cv_params is None:
        cv_params = CVParams()
    gray = cv2.imread(str(page_image_path), cv2.IMREAD_GRAYSCALE)
    h, w = gray.shape

    _, binary = cv2.threshold(gray, cv_params.bbox_binary_threshold, 255, cv2.THRESH_BINARY_INV)

    # Detect horizontal and vertical lines
    min_line_len = min(h, w) // 10
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_line_len, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, min_line_len))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

    # Areas with both H and V lines = board regions
    combined = cv2.bitwise_or(h_lines, v_lines)
    dilate_k = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 30))
    dilated = cv2.dilate(combined, dilate_k, iterations=3)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter small regions, sort by position (top-to-bottom, left-to-right)
    min_area = (min(h, w) // 8) ** 2
    boxes = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw * bh > min_area:
            boxes.append((x, y, x + bw, y + bh))

    boxes.sort(key=lambda b: (b[1] // 200, b[0]))
    return boxes


# ── Step 5: Build board_payload ───────────────────────────────────────────────

def build_payload(stones, labels_data, col_start, row_start):
    """Combine CV stone detection + VLLM label recognition into board_payload."""
    black, white = [], []
    labels = {}
    letters = {}

    for ci, ri, color in stones:
        full_col = col_start + ci
        full_row = row_start + ri
        if color == "B":
            black.append([full_col, full_row])
        else:
            white.append([full_col, full_row])

    # Add labels from VLLM
    if labels_data:
        for key, val in labels_data.get("labels", {}).items():
            if val is None:
                continue
            ci, ri = map(int, key.split(","))
            full_col = col_start + ci
            full_row = row_start + ri
            labels[f"{full_col},{full_row}"] = str(int(val))

        for key, val in labels_data.get("letters", {}).items():
            if not val:
                continue
            ci, ri = map(int, key.split(","))
            full_col = col_start + ci
            full_row = row_start + ri
            letters[f"{full_col},{full_row}"] = str(val)

    return {
        "size": 19,
        "stones": {"B": black, "W": white},
        "labels": labels,
        "letters": letters,
        "shapes": {},
        "highlights": [],
    }


# ── Deskew: straighten tilted scanned board images ───────────────────────────

def deskew_board(gray, debug=False, cv_params=None):
    """Detect and correct rotation in a scanned Go board diagram.

    Uses HoughLinesP to detect grid lines, computes median angle, and rotates
    the image to straighten it. Only corrects small angles (< 5°).

    Returns (corrected_gray, angle_degrees). If no correction needed, returns
    the original image with angle=0.
    """
    if cv_params is None:
        cv_params = CVParams()
    h_img, w_img = gray.shape

    # Detect lines using probabilistic Hough transform
    _, binary = cv2.threshold(gray, cv_params.deskew_binary_threshold, 255, cv2.THRESH_BINARY_INV)
    min_line_len = min(h_img, w_img) // 3  # only long lines for reliable angle
    lines = cv2.HoughLinesP(binary, 1, np.pi / 1800, threshold=100,
                            minLineLength=min_line_len, maxLineGap=10)

    if lines is None or len(lines) < 4:
        return gray, 0.0

    # Compute angle of each line, separate into ~horizontal and ~vertical
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Near-horizontal lines (angle close to 0°)
        if abs(angle) < 10:
            angles.append(angle)
        # Near-vertical lines (angle close to ±90°)
        elif abs(abs(angle) - 90) < 10:
            angles.append(angle - 90 if angle > 0 else angle + 90)

    if len(angles) < 4:
        return gray, 0.0

    # Use trimmed mean (remove outlier 20%) for robustness
    sorted_angles = sorted(angles)
    trim = max(1, len(sorted_angles) // 5)
    trimmed = sorted_angles[trim:-trim] if len(sorted_angles) > 2 * trim else sorted_angles
    median_angle = float(np.mean(trimmed))

    # Only correct small tilts (< 5°), larger angles suggest a different issue
    if abs(median_angle) < 0.1 or abs(median_angle) > 5.0:
        return gray, 0.0

    # Rotate image to correct the skew
    center = (w_img / 2, h_img / 2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    corrected = cv2.warpAffine(gray, M, (w_img, h_img),
                               flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT,
                               borderValue=255)

    if debug:
        log.info("  Deskew: corrected %.2f° rotation (%d lines detected)", median_angle, len(angles))

    return corrected, median_angle


def deskew_board_color(img, gray, angle):
    """Apply the same deskew rotation to a color image."""
    if abs(angle) < 0.1:
        return img
    h_img, w_img = gray.shape
    center = (w_img / 2, h_img / 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w_img, h_img),
                          flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=(255, 255, 255))


# ── Page-level crop detection (CV fallback for VLLM bbox) ────────────────────

def cv_detect_diagram_bboxes(page_gray):
    """Fallback: detect board diagram regions using CV projection analysis.

    Returns list of (y_start, y_end) for each diagram on the page (left portion).
    """
    h_img, w_img = page_gray.shape

    # Board diagrams are in the left ~50% of the page
    left_half = page_gray[:, : w_img // 2]
    row_dark = np.sum(left_half < 100, axis=1)

    # Find rows with significant dark content (board lines)
    threshold = np.max(row_dark) * 0.15
    board_rows = np.where(row_dark > threshold)[0]

    if len(board_rows) == 0:
        return []

    # Split into groups (diagrams) by large gaps
    groups = []
    current_start = board_rows[0]
    prev = board_rows[0]
    for r in board_rows[1:]:
        if r - prev > 50:
            groups.append((int(current_start), int(prev)))
            current_start = r
        prev = r
    groups.append((int(current_start), int(prev)))

    # Filter: only keep groups with reasonable height (at least 100px)
    # Add generous padding to avoid clipping board edge lines
    pad = 40
    return [(max(0, y1 - pad), min(h_img, y2 + pad)) for y1, y2 in groups if y2 - y1 > 100]


def crop_diagram(page_img, page_gray, y_start, y_end, padding=15):
    """Crop a single board diagram from the page, finding its horizontal extent."""
    h_img, w_img = page_gray.shape

    y1 = max(0, y_start - padding)
    y2 = min(h_img, y_end + padding)

    # Find horizontal extent within this row range
    strip = page_gray[y1:y2, :]
    col_dark = np.sum(strip < 100, axis=0)
    dark_cols = np.where(col_dark > 5)[0]

    if len(dark_cols) == 0:
        return None

    x1 = max(0, int(dark_cols[0]) - padding)
    x2 = min(w_img, int(dark_cols[-1]) + padding)

    return page_img[y1:y2, x1:x2]


# ── Full pipeline ─────────────────────────────────────────────────────────────

def process_page(page_image_path, figure_ids, dry_run=False, db=None, force=False, vllm="haiku",
                  db_bboxes=None, cv_params=None):
    """Process all diagrams on a single page.

    figure_ids: list of (figure_label, figure_db_id) e.g. [("图1", 1), ("图2", 2)]
    vllm: VLLM backend for S4 — "haiku" (Claude) or "qwen" (DashScope).
    db_bboxes: optional dict mapping figure_label → DB bbox dict (relative coords from book.json).
    Returns list of FigureResult for per-figure status tracking.
    """
    results = []
    page_img = cv2.imread(str(page_image_path))
    if page_img is None:
        log.error("Cannot read image: %s", page_image_path)
        for label, fig_id in figure_ids:
            results.append(FigureResult(label, fig_id, "failed_cv", "cannot read page image"))
        return results
    page_gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
    h_img, w_img = page_gray.shape[:2]

    # Step 0: detect diagram bounding boxes (pure CV — fast and accurate)
    log.info("[Step 0      ] detecting diagram bboxes on %s", page_image_path.name)
    if cv_params is None:
        cv_params = CVParams()
    cv_boxes = cv_detect_bboxes(page_image_path, cv_params)
    log.info("  CV detected %d diagram regions", len(cv_boxes))

    # Build bboxes: prefer DB bboxes (from book.json) when available, fall back to CV
    bboxes = {}
    if db_bboxes:
        for label, _ in figure_ids:
            db_bb = db_bboxes.get(label)
            if not db_bb:
                continue
            # Convert relative {x_min, y_min, x_max, y_max} (0-1) to pixel coords
            if isinstance(db_bb, dict) and "x_min" in db_bb:
                x1 = int(db_bb["x_min"] * w_img)
                y1 = int(db_bb["y_min"] * h_img)
                x2 = int(db_bb["x_max"] * w_img)
                y2 = int(db_bb["y_max"] * h_img)
                bboxes[label] = [x1, y1, x2, y2]
                log.info("  %s: using DB bbox (%.2f,%.2f)-(%.2f,%.2f) → [%d,%d,%d,%d]",
                         label, db_bb["x_min"], db_bb["y_min"], db_bb["x_max"], db_bb["y_max"],
                         x1, y1, x2, y2)

    # Fall back to CV-detected bboxes for figures without DB bbox
    for i, (label, _) in enumerate(figure_ids):
        if label not in bboxes and i < len(cv_boxes):
            x1, y1, x2, y2 = cv_boxes[i]
            bboxes[label] = [x1, y1, x2, y2]

    # Process each figure
    for label, fig_id in figure_ids:
        log.info("Processing %s (id=%d)", label, fig_id)

        bbox = bboxes.get(label)
        if bbox is None:
            log.warning("  No bbox found — skipping")
            results.append(FigureResult(label, fig_id, "failed_cv", "no bbox detected"))
            continue

        # Crop diagram
        x1, y1, x2, y2 = [int(c) for c in bbox]
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(page_img.shape[1], x2)
        y2 = min(page_img.shape[0], y2)
        crop = page_img[y1:y2, x1:x2]
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # Deskew: straighten tilted scans before grid detection
        original_crop = crop.copy()  # keep pre-deskew copy for debug overlay
        crop_gray, deskew_angle = deskew_board(crop_gray, debug=True, cv_params=cv_params)
        if abs(deskew_angle) >= 0.1:
            crop = deskew_board_color(crop, crop_gray, deskew_angle)

        # Save crop for VLLM steps
        crop_path = Path(tempfile.mktemp(suffix=".png", prefix=f"board_{label}_"))
        cv2.imwrite(str(crop_path), crop)
        log.info("  Cropped: %dx%d → %s", crop.shape[1], crop.shape[0], crop_path.name)

        # Step 2: CV grid detection
        h_pos, v_pos, spacing = cv_detect_grid(crop_gray, cv_params)
        log.info("  Step 2: %d rows × %d cols, spacing=%.1fpx", len(h_pos), len(v_pos), spacing)

        # Generate grid debug image: deskewed crop with detected grid lines overlay
        grid_debug = crop.copy() if len(crop.shape) == 3 else cv2.cvtColor(crop_gray, cv2.COLOR_GRAY2BGR)
        for hy in h_pos:
            y = int(round(hy))
            cv2.line(grid_debug, (0, y), (grid_debug.shape[1], y), (0, 180, 0), 1)
        for vx in v_pos:
            x = int(round(vx))
            cv2.line(grid_debug, (x, 0), (x, grid_debug.shape[0]), (0, 180, 0), 1)

        if len(h_pos) < 3 or len(v_pos) < 3:
            log.warning("  Too few grid lines — skipping")
            crop_path.unlink(missing_ok=True)
            results.append(FigureResult(label, fig_id, "failed_cv", f"too few grid lines ({len(h_pos)}×{len(v_pos)})"))
            continue

        # Step 3: CV occupied intersection detection
        occupied = cv_detect_occupied(crop_gray, h_pos, v_pos, spacing, cv_params)
        confident, ambiguous = cv_preclass_confident(occupied, spacing, cv_params)
        log.info("  Step 3: %d occupied (%d confident, %d ambiguous)",
                 len(occupied), len(confident), len(ambiguous))

        # Step 1: Region calibration (pure CV — border detection + star points)
        occupied_set = {(ci, ri) for ci, ri, _ in occupied}
        col_start, row_start, cal_conf, cal_evidence = calibrate_region(
            crop_gray, h_pos, v_pos, spacing, occupied_set
        )
        log.info("  Step 1: col_start=%d, row_start=%d, confidence=%.2f, evidence=%s",
                 col_start, row_start, cal_conf, cal_evidence)

        # Step 4: VLLM classification via annotated crop (full context)
        # Build annotated crop with letter labels at ALL occupied positions
        annotated, full_label_map = build_annotated_crop(
            crop, h_pos, v_pos, occupied, spacing
        )
        log.info("  Step 4: built annotated crop with %d labeled positions", len(full_label_map))

        # Save individual patches to debug dir (for training data export)
        book_slug_dir = page_image_path.parent.parent.name
        fig_debug_dir = ASSET_BASE / "tutorial_assets" / book_slug_dir / "debug" / f"{fig_id}_{label}"
        fig_debug_dir.mkdir(parents=True, exist_ok=True)
        patches_dir = fig_debug_dir / "patches"
        patches_dir.mkdir(exist_ok=True)
        patch_lookup = {(ci, ri): patch for ci, ri, patch in occupied}
        for lbl, (ci, ri) in full_label_map.items():
            patch = patch_lookup.get((ci, ri))
            if patch is not None:
                cv2.imwrite(str(patches_dir / f"{lbl}_{ci}_{ri}.png"), patch)
        log.info("  Saved %d patches to %s", len(full_label_map), patches_dir)

        # Build CV pre-classification for ALL patches (for debug display)
        confident_set = {(ci, ri): bt for ci, ri, _, bt in confident}
        cv_preclass = {}  # label → CV result for every patch
        merged_classifications = {}
        for lbl, (ci, ri) in full_label_map.items():
            if (ci, ri) in confident_set:
                cv_preclass[lbl] = confident_set[(ci, ri)]
                merged_classifications[lbl] = confident_set[(ci, ri)]
            else:
                cv_preclass[lbl] = "ambiguous"

        # Step 4: VLLM per-patch classification for ambiguous positions (concurrent)
        classify_fn = {"haiku": haiku_classify_patch, "qwen": qwen_classify_patch, "gemini": gemini_classify_patch, "local": local_classify_patch}[vllm]
        classification_source = vllm
        ambiguous_labels = [lbl for lbl in full_label_map if lbl not in merged_classifications]
        if ambiguous_labels:
            log.info("  Step 4: classifying %d ambiguous patches with %s (concurrent)", len(ambiguous_labels), vllm)
            # Build tasks: (label, patch_path) pairs
            vllm_tasks = []
            for lbl in ambiguous_labels:
                ci, ri = full_label_map[lbl]
                patch_path = patches_dir / f"{lbl}_{ci}_{ri}.png"
                if not patch_path.exists():
                    log.warning("    Patch %s not found, skipping", patch_path)
                    continue
                vllm_tasks.append((lbl, patch_path))

            if vllm == "local":
                # Batch fast-path: single forward pass over all ambiguous patches
                from katrain.web.tutorials.vision.patch_classifier import PatchClassifier
                from katrain.web.tutorials.vision.patch_ocr import PatchOCR

                classifier = PatchClassifier.get_instance(MODEL_DIR)
                ocr = PatchOCR()
                patches_np = []
                for lbl, pp in vllm_tasks:
                    patch = cv2.imread(str(pp), cv2.IMREAD_GRAYSCALE)
                    patches_np.append(patch if patch is not None else np.zeros((40, 40), dtype=np.uint8))
                batch_results = classifier.classify_batch(patches_np)
                for (lbl, pp), (coarse, conf), patch in zip(vllm_tasks, batch_results, patches_np):
                    cls_str = _coarse_to_compound(coarse, patch, ocr)
                    merged_classifications[lbl] = cls_str
                    log.info("    %s → %s (conf=%.2f)", lbl, cls_str, conf)
            else:
                # Run VLLM calls concurrently (max 4 threads to respect rate limits)
                with ThreadPoolExecutor(max_workers=min(4, len(vllm_tasks))) as executor:
                    futures = {
                        executor.submit(classify_fn, pp): lbl
                        for lbl, pp in vllm_tasks
                    }
                    for future in as_completed(futures):
                        lbl = futures[future]
                        try:
                            cls_str = future.result()
                            merged_classifications[lbl] = cls_str
                            log.info("    %s → %s", lbl, cls_str)
                        except Exception as e:
                            log.warning("    VLLM failed for %s: %s", lbl, e)

        log.info("  Classifications: %d total", len(merged_classifications))

        # Step 5: Build payload via classification_to_payload
        payload = classification_to_payload(merged_classifications, full_label_map, col_start, row_start)
        log.info("  Payload: B=%d W=%d labels=%d letters=%d",
                 len(payload["stones"]["B"]), len(payload["stones"]["W"]),
                 len(payload["labels"]), len(payload["letters"]))

        # Save training data
        # Extract page number from image path for training data provenance
        page_num_str = page_image_path.stem.replace("page_", "")
        book_slug = page_image_path.parent.parent.name  # e.g. "曹薰铉布局技巧-上册-曹薰铉-1997"
        save_all_training_patches(
            occupied, merged_classifications, full_label_map,
            col_start, row_start, book_slug, page_num_str, label,
            classification_source=classification_source,
        )

        stone_count = len(payload["stones"]["B"]) + len(payload["stones"]["W"])
        label_count_total = len(payload.get("labels", {}))

        # Determine per-figure status
        missing_count = len(full_label_map) - len(merged_classifications)
        if missing_count > 0:
            status = "failed_vllm"
            detail = f"{missing_count}/{len(full_label_map)} patches failed classification ({vllm})"
        elif stone_count == 0:
            status = "failed_cv"
            detail = "no stones detected"
        elif cal_conf < 0.3:
            status = "needs_review"
            detail = f"low calibration confidence ({cal_conf:.2f})"
        else:
            status = "success"
            detail = f"{stone_count} stones, {label_count_total} labels"

        if dry_run:
            print(f"\n=== {label} (id={fig_id}) [{status}] ===")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif status == "failed_vllm":
            log.warning("  ✗ Skipping DB save for %s: %s", label, detail)
        elif db is not None:
            figure = db_queries.get_figure(db, fig_id)
            if figure:
                if figure.board_payload and not force:
                    log.info("  Skipping %s (already has payload, use --force to overwrite)", label)
                    status = "skipped"
                    detail = "already has payload"
                else:
                    db_queries.update_figure_board(db, figure, payload)
                    # Write recognition_debug with bbox, region, patches, classification
                    # Save annotated crop and bbox debug to debug dir
                    cv2.imwrite(str(fig_debug_dir / "annotated_crop.png"), annotated)
                    cv2.imwrite(str(fig_debug_dir / "crop.png"), crop)
                    cv2.imwrite(str(fig_debug_dir / "grid_debug.png"), grid_debug)
                    # Generate deskew debug image (grid lines on original crop)
                    deskew_debug = generate_deskew_debug_image(original_crop, h_pos, v_pos, deskew_angle)
                    cv2.imwrite(str(fig_debug_dir / "deskew_debug.png"), deskew_debug)
                    # Generate bbox debug image
                    bbox_vis = page_img.copy()
                    for bl, bb in bboxes.items():
                        bx1, by1, bx2, by2 = [int(c) for c in bb]
                        cv2.rectangle(bbox_vis, (bx1, by1), (bx2, by2), (0, 200, 0), 3)
                        cv2.putText(bbox_vis, bl, (bx1+5, by1+30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,200,0), 3)
                    cv2.imwrite(str(fig_debug_dir / "bbox_debug.png"), bbox_vis)

                    rel = lambda p: str(p.relative_to(ASSET_BASE))
                    # Build patch paths map
                    patch_paths = {}
                    for lbl, (ci, ri) in full_label_map.items():
                        pp = patches_dir / f"{lbl}_{ci}_{ri}.png"
                        if pp.exists():
                            patch_paths[lbl] = rel(pp)

                    recognition_debug = {
                        "deskew": {
                            "angle": round(deskew_angle, 3),
                            "debug_image": rel(fig_debug_dir / "deskew_debug.png"),
                            "grid_image": rel(fig_debug_dir / "grid_debug.png"),
                        },
                        "bbox": {
                            "method": "cv",
                            "bbox": list(bboxes.get(label, [])),
                            "debug_image": rel(fig_debug_dir / "bbox_debug.png"),
                        },
                        "region": {
                            "method": "cv",
                            "col_start": col_start,
                            "row_start": row_start,
                            "confidence": cal_conf,
                            "evidence": cal_evidence,
                            "grid_rows": len(h_pos),
                            "grid_cols": len(v_pos),
                        },
                        "cv_detection": {
                            "spacing": spacing,
                            "total_occupied": len(occupied),
                            "confident_count": len(confident),
                            "ambiguous_count": len(ambiguous),
                            "debug_image": rel(fig_debug_dir / "annotated_crop.png"),
                        },
                        "classification": {
                            "label_map": {k: list(v) for k, v in full_label_map.items()},
                            "cv_preclass": cv_preclass,
                            "classifications": merged_classifications,
                            "source": classification_source,
                            "patch_images": patch_paths,
                        },
                        "crop_image": rel(fig_debug_dir / "crop.png"),
                    }
                    db_queries.update_figure_recognition_debug(db, figure, recognition_debug)
                    log.info("  ✓ Saved to DB")
            else:
                log.error("  Figure id=%d not found in DB", fig_id)
                status = "failed_semantic"
                detail = "figure not found in DB"

        results.append(FigureResult(
            label, fig_id, status, detail,
            stone_count=stone_count, label_count=label_count_total,
            calibration_confidence=cal_conf,
        ))

        # Cleanup temp file
        crop_path.unlink(missing_ok=True)

    return results


# ── Test CV pipeline ──────────────────────────────────────────────────────────

def test_cv(page_image_path, cv_params=None):
    """Test the CV pipeline (Steps 2-3 only) on a page image."""
    page_img = cv2.imread(str(page_image_path))
    page_gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)

    regions = cv_detect_diagram_bboxes(page_gray)
    log.info("Found %d diagram regions", len(regions))

    for i, (y_start, y_end) in enumerate(regions):
        crop = crop_diagram(page_img, page_gray, y_start, y_end)
        if crop is None:
            continue
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        h_pos, v_pos, spacing = cv_detect_grid(crop_gray, cv_params)

        # New: occupied detection (no color classification)
        occupied = cv_detect_occupied(crop_gray, h_pos, v_pos, spacing, cv_params)
        confident, ambiguous = cv_preclass_confident(occupied, spacing, cv_params)
        log.info("Diagram %d: %d×%d grid, spacing=%.1fpx, %d occupied (%d confident, %d ambiguous)",
                 i + 1, len(v_pos), len(h_pos), spacing, len(occupied),
                 len(confident), len(ambiguous))
        for ci, ri, _, base_type in confident:
            log.info("  CV-confident: %s at local(%d,%d)", base_type, ci, ri)
        for ci, ri, _ in ambiguous:
            log.info("  Ambiguous: local(%d,%d)", ci, ri)

        # Legacy comparison
        stones = cv_detect_stones_legacy(crop_gray, h_pos, v_pos, spacing)
        log.info("  Legacy: %d stones (B=%d, W=%d)", len(stones),
                 sum(1 for _, _, c in stones if c == "B"),
                 sum(1 for _, _, c in stones if c == "W"))

        # Save debug image
        r = int(spacing * 0.45) if spacing > 0 else 10
        debug = crop.copy()
        for y in h_pos:
            cv2.line(debug, (0, y), (crop.shape[1], y), (0, 0, 255), 1)
        for x in v_pos:
            cv2.line(debug, (x, 0), (x, crop.shape[0]), (255, 0, 0), 1)
        for ci, ri, patch in occupied:
            vx, hy = int(v_pos[ci]), int(h_pos[ri])
            cv2.circle(debug, (vx, hy), r, (0, 255, 255), 2)
            cv2.putText(debug, f"({ci},{ri})", (vx + r + 2, hy + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
        # Mark confident patches in green (black) / orange (white)
        for ci, ri, _, base_type in confident:
            vx, hy = int(v_pos[ci]), int(h_pos[ri])
            c = (0, 255, 0) if base_type == "black" else (255, 128, 0)
            cv2.circle(debug, (vx, hy), r + 3, c, 2)
        out = Path(f"/tmp/cv_debug_diagram_{i + 1}.png")
        cv2.imwrite(str(out), debug)
        log.info("  Debug image: %s", out)

        # Save crop for contact sheet testing
        crop_out = Path(f"/tmp/cv_crop_diagram_{i + 1}.png")
        cv2.imwrite(str(crop_out), crop)
        log.info("  Crop: %s", crop_out)


# ── Main ──────────────────────────────────────────────────────────────────────

def apply_classifications_from_file(db, section_id, json_path, force=False):
    """Apply VLLM classification results from a JSON file to DB.

    JSON format (col_start/row_start determined by VLLM/subagent, NOT CV):
    {
      "图1": {"classifications": {"A": "black+1", ...}, "col_start": 0, "row_start": 0},
      "图2": {...},
      ...
    }

    If patches directory exists alongside the JSON file (from --save-sheets),
    training data is automatically saved.
    """
    from katrain.web.tutorials.viewport import compute_viewport

    with open(json_path) as f:
        data = json.load(f)

    section = db_queries.get_section(db, section_id)
    if section is None:
        log.error("Section %d not found", section_id)
        return

    # Build figure lookup
    fig_by_label = {fig.figure_label: fig for fig in section.figures}

    results = []  # (label, status, detail)

    for label, entry in data.items():
        figure = fig_by_label.get(label)
        if figure is None:
            log.warning("  %s: not found in section — skipping", label)
            results.append((label, "failed_semantic", "figure not found in section"))
            continue

        if figure.board_payload and figure.board_payload.get("stones", {}).get("B") and not force:
            log.info("  %s: already has board_payload — skipping (use --force to overwrite)", label)
            results.append((label, "skipped", "already has payload"))
            continue

        classifications = entry.get("classifications", {})
        col_start = entry.get("col_start", 0)
        row_start = entry.get("row_start", 0)

        # Load label_map from the contact sheet metadata if available
        label_map = entry.get("label_map", {})
        if not label_map:
            log.warning("  %s: no label_map in JSON — skipping", label)
            results.append((label, "failed_semantic", "missing label_map"))
            continue

        # Convert label_map values from lists to tuples
        label_map = {k: tuple(v) for k, v in label_map.items()}

        try:
            payload = classification_to_payload(classifications, label_map, col_start, row_start)

            # Compute viewport before DB write (Codex fix)
            viewport = compute_viewport(payload)
            payload["viewport"] = viewport

            db_queries.update_figure_board(db, figure, payload)
            stone_count = len(payload["stones"]["B"]) + len(payload["stones"]["W"])
            log.info("  %s: applied (%d stones, %d labels) ✓",
                     label, stone_count, len(payload.get("labels", {})))

            # Update recognition_debug with classification results + final region
            # Deep copy to avoid SQLAlchemy in-place mutation detection issue
            existing_debug = json.loads(json.dumps(figure.recognition_debug or {}))
            existing_debug.setdefault("classification", {})["classifications"] = classifications
            existing_debug.setdefault("region", {})["col_start"] = col_start
            existing_debug["region"]["row_start"] = row_start
            existing_debug["region"]["method"] = "vllm"
            db_queries.update_figure_recognition_debug(db, figure, existing_debug)

            # Save training data if patches directory exists
            json_dir = Path(json_path).parent
            patches_dir = json_dir / "patches" / label
            if patches_dir.exists():
                occupied_patches = []
                for lbl, (ci, ri) in label_map.items():
                    patch_path = patches_dir / f"{lbl}_{ci}_{ri}.png"
                    if patch_path.exists():
                        patch = cv2.imread(str(patch_path), cv2.IMREAD_GRAYSCALE)
                        if patch is not None:
                            occupied_patches.append((ci, ri, patch))
                if occupied_patches:
                    book_slug = entry.get("book_slug", "unknown")
                    page = entry.get("page", 0)
                    save_all_training_patches(
                        occupied_patches, classifications, label_map,
                        col_start, row_start, book_slug, page, label
                    )

            results.append((label, "success", f"{stone_count} stones"))
        except Exception as e:
            log.error("  %s: failed — %s", label, e)
            results.append((label, "failed_semantic", str(e)))

    # Summary
    success = sum(1 for _, s, _ in results if s == "success")
    failed = sum(1 for _, s, _ in results if s.startswith("failed"))
    skipped = sum(1 for _, s, _ in results if s == "skipped")
    log.info("\nSummary: %d success, %d failed, %d skipped (total %d)",
             success, failed, skipped, len(results))


def save_sheets_for_section(db, section_id, output_dir, cv_params=None):
    """Generate and save contact sheets for all figures in a section.

    Runs CV pipeline only (Steps 0-3), builds contact sheets, saves to output_dir.
    No VLLM calls, no DB writes.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    section = db_queries.get_section(db, section_id)
    if section is None:
        log.error("Section %d not found", section_id)
        return

    log.info("Section %d: %s (%d figures)", section.id, section.title, len(section.figures))

    pages = defaultdict(list)
    for fig in section.figures:
        pages[fig.page].append((fig.figure_label, fig.id))

    for page_num in sorted(pages.keys()):
        figure_ids = pages[page_num]
        fig0 = next(f for f in section.figures if f.page == page_num)
        if not fig0.page_image_path:
            log.warning("Page %d: no image path — skipping", page_num)
            continue
        image_path = ASSET_BASE / fig0.page_image_path
        if not image_path.exists():
            log.warning("Page %d: image not found at %s — skipping", page_num, image_path)
            continue

        page_img = cv2.imread(str(image_path))
        if page_img is None:
            log.error("Cannot read image: %s", image_path)
            continue
        page_gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)

        # Step 0: detect diagram bboxes (CV only — no VLLM)
        cv_regions = cv_detect_diagram_bboxes(page_gray)
        log.info("Page %d: CV detected %d diagram regions for %d figures",
                 page_num, len(cv_regions), len(figure_ids))

        bboxes = {}
        for i, (label, _) in enumerate(figure_ids):
            if i < len(cv_regions):
                y1, y2 = cv_regions[i]
                strip = page_gray[y1:y2, :]
                col_dark = np.sum(strip < 100, axis=0)
                dark_cols = np.where(col_dark > 5)[0]
                if len(dark_cols) > 0:
                    x1, x2 = int(dark_cols[0]) - 10, int(dark_cols[-1]) + 10
                    bboxes[label] = [x1, y1 - 10, x2, y2 + 10]

        for label, fig_id in figure_ids:
            bbox = bboxes.get(label)
            if bbox is None:
                log.warning("  %s: no bbox — skipping", label)
                continue

            x1, y1, x2, y2 = [max(0, int(c)) for c in bbox]
            x2 = min(page_img.shape[1], x2)
            y2 = min(page_img.shape[0], y2)
            crop = page_img[y1:y2, x1:x2]
            crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            # Deskew: straighten tilted scans before grid detection
            original_crop = crop.copy()
            crop_gray, deskew_angle = deskew_board(crop_gray, debug=True, cv_params=cv_params)
            if abs(deskew_angle) >= 0.1:
                crop = deskew_board_color(crop, crop_gray, deskew_angle)

            # Step 2: grid detection
            h_pos, v_pos, spacing = cv_detect_grid(crop_gray, cv_params)
            if len(h_pos) < 3 or len(v_pos) < 3:
                log.warning("  %s: too few grid lines — skipping", label)
                continue

            # Step 3: occupied detection
            occupied = cv_detect_occupied(crop_gray, h_pos, v_pos, spacing, cv_params)
            confident, ambiguous = cv_preclass_confident(occupied, spacing, cv_params)
            log.info("  %s: %d×%d grid, %d occupied (%d confident, %d ambiguous)",
                     label, len(v_pos), len(h_pos), len(occupied),
                     len(confident), len(ambiguous))

            if not occupied:
                log.warning("  %s: no occupied intersections — skipping", label)
                continue

            # Region calibration
            occupied_set = {(ci, ri) for ci, ri, _ in occupied}
            col_start, row_start, cal_conf, cal_evidence = calibrate_region(
                crop_gray, h_pos, v_pos, spacing, occupied_set
            )
            log.info("  %s: region col_start=%d, row_start=%d (conf=%.2f)",
                     label, col_start, row_start, cal_conf)

            # Build annotated crop (primary VLLM input) + contact sheet (for display)
            annotated, label_map = build_annotated_crop(
                crop, h_pos, v_pos, occupied, spacing
            )
            sheet, _ = build_contact_sheet(occupied, spacing)

            # Save both
            annotated_path = output_dir / f"{label}_annotated.png"
            cv2.imwrite(str(annotated_path), annotated)
            sheet_path = output_dir / f"{label}.png"
            if sheet is not None:
                cv2.imwrite(str(sheet_path), sheet)

            # Build confident map
            confident_set = {(ci, ri): bt for ci, ri, _, bt in confident}
            conf_map = {}
            for lbl, (ci, ri) in label_map.items():
                if (ci, ri) in confident_set:
                    conf_map[lbl] = confident_set[(ci, ri)]

            region_needs_vllm = cal_conf < 0.5

            # Generate and save debug images to data/ dir
            book_slug = image_path.parent.parent.name
            figure_labels = [l for l, _ in figure_ids]
            debug_paths = save_debug_images(
                page_img, crop, h_pos, v_pos, spacing,
                occupied, confident, ambiguous,
                bboxes, figure_labels, label, book_slug,
                original_crop=original_crop, deskew_angle=deskew_angle,
            )

            # Save annotated crop + contact sheet to debug dir
            debug_dir = ASSET_BASE / "tutorial_assets" / book_slug / "debug" / label
            debug_annotated_path = debug_dir / "annotated_crop.png"
            cv2.imwrite(str(debug_annotated_path), annotated)
            debug_paths["annotated_crop"] = str(debug_annotated_path.relative_to(ASSET_BASE))
            if sheet is not None:
                debug_sheet_path = debug_dir / "contact_sheet.png"
                cv2.imwrite(str(debug_sheet_path), sheet)
                debug_paths["contact_sheet"] = str(debug_sheet_path.relative_to(ASSET_BASE))

            # Build recognition_debug metadata for DB
            recognition_debug = {
                "deskew": {
                    "angle": round(deskew_angle, 3),
                    "debug_image": debug_paths.get("deskew_debug"),
                    "grid_image": debug_paths.get("grid_debug"),
                },
                "bbox": {
                    "method": "cv",
                    "bbox": bboxes.get(label),
                    "debug_image": debug_paths.get("bbox_debug"),
                },
                "region": {
                    "method": "cv_hint",
                    "col_start": col_start,
                    "row_start": row_start,
                    "confidence": cal_conf,
                    "evidence": cal_evidence,
                    "grid_rows": len(h_pos),
                    "grid_cols": len(v_pos),
                    "needs_vllm": region_needs_vllm,
                },
                "cv_detection": {
                    "debug_image": debug_paths.get("grid_debug"),
                    "spacing": spacing,
                    "total_occupied": len(occupied),
                    "confident_count": len(confident),
                    "ambiguous_count": len(ambiguous),
                },
                "classification": {
                    "annotated_crop": debug_paths.get("annotated_crop"),
                    "contact_sheet": debug_paths.get("contact_sheet"),
                    "label_map": {k: list(v) for k, v in label_map.items()},
                    "confident_cv": conf_map,
                    "classifications": None,  # filled after VLLM step
                },
                "crop_image": debug_paths.get("crop"),
            }

            # Save recognition_debug to DB
            figure = db_queries.get_figure(db, fig_id)
            if figure:
                db_queries.update_figure_recognition_debug(db, figure, recognition_debug)

            # Save metadata to output dir (for --apply-classifications)
            meta = {
                "figure_label": label,
                "figure_id": fig_id,
                "grid_rows": len(h_pos),
                "grid_cols": len(v_pos),
                "spacing": spacing,
                "col_start": col_start,
                "row_start": row_start,
                "region_needs_vllm": region_needs_vllm,
                "calibration_confidence": cal_conf,
                "calibration_evidence": cal_evidence,
                "total_occupied": len(occupied),
                "confident_count": len(confident),
                "ambiguous_count": len(ambiguous),
                "label_map": {k: list(v) for k, v in label_map.items()},
                "confident": conf_map,
            }
            meta_path = output_dir / f"{label}.json"
            with open(meta_path, "w") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            # Save individual patches
            patches_dir = output_dir / "patches" / label
            patches_dir.mkdir(parents=True, exist_ok=True)
            patch_lookup = {(ci, ri): patch for ci, ri, patch in occupied}
            for lbl, (ci, ri) in label_map.items():
                patch = patch_lookup.get((ci, ri))
                if patch is not None:
                    patch_path = patches_dir / f"{lbl}_{ci}_{ri}.png"
                    cv2.imwrite(str(patch_path), patch)

            crop_path = output_dir / f"{label}_crop.png"
            cv2.imwrite(str(crop_path), crop)

            log.info("  %s: saved sheet + debug images → %s", label, debug_dir)

    log.info("Contact sheets saved to %s", output_dir)


def main():
    parser = argparse.ArgumentParser(description="Hybrid VLLM+CV board recognition")
    parser.add_argument("--section-id", type=int, help="Process all figures in this section")
    parser.add_argument("--test-cv", type=str, help="Test CV pipeline on a page image")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without DB write")
    parser.add_argument("--force", action="store_true", help="Overwrite existing board_payload")
    parser.add_argument("--save-sheets", type=str,
                        help="Save contact sheets to this directory (no DB write)")
    parser.add_argument("--apply-classifications", type=str,
                        help="Apply VLLM classification results from JSON file to DB")
    parser.add_argument("--vllm", choices=["haiku", "qwen", "gemini", "local"], default="gemini",
                        help="Backend for S4 patch classification: API (gemini/haiku/qwen) or local EfficientNet-B0 (default: gemini)")
    args = parser.parse_args()

    if args.test_cv:
        test_cv(Path(args.test_cv))
        return

    if not args.section_id:
        parser.error("--section-id or --test-cv required")

    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Mode: save contact sheets (CV only, no VLLM, no DB write)
        if args.save_sheets:
            section = db_queries.get_section(db, args.section_id)
            cv_params = load_cv_params(section.chapter.book.slug) if section else CVParams()
            save_sheets_for_section(db, args.section_id, args.save_sheets, cv_params=cv_params)
            return

        # Mode: apply VLLM classifications from JSON file
        if args.apply_classifications:
            apply_classifications_from_file(db, args.section_id, args.apply_classifications, force=args.force)
            return

        # Default mode: full pipeline
        section = db_queries.get_section(db, args.section_id)
        if section is None:
            log.error("Section %d not found", args.section_id)
            return

        # Load per-book CV parameters
        book_slug = section.chapter.book.slug
        cv_params = load_cv_params(book_slug)

        log.info("Section %d: %s (%d figures)", section.id, section.title, len(section.figures))

        # Group figures by page, collect DB bboxes for fallback
        pages = defaultdict(list)
        fig_bboxes = {}
        for fig in section.figures:
            pages[fig.page].append((fig.figure_label, fig.id))
            if fig.bbox:
                fig_bboxes[fig.figure_label] = fig.bbox

        all_results = []
        for page_num in sorted(pages.keys()):
            figure_ids = pages[page_num]
            # Find page image path from the first figure
            fig0 = next(f for f in section.figures if f.page == page_num)
            if not fig0.page_image_path:
                log.warning("Page %d: no image path — skipping", page_num)
                continue
            image_path = ASSET_BASE / fig0.page_image_path

            if not image_path.exists():
                log.warning("Page %d: image not found at %s — skipping", page_num, image_path)
                continue

            # Collect DB bboxes for figures on this page
            page_db_bboxes = {label: fig_bboxes[label] for label, _ in figure_ids if label in fig_bboxes}

            log.info("\n── Page %d (%s) ── %d figure(s)", page_num, image_path.name, len(figure_ids))
            page_results = process_page(image_path, figure_ids, dry_run=args.dry_run, db=db, force=args.force,
                                        vllm=args.vllm, db_bboxes=page_db_bboxes, cv_params=cv_params)
            if page_results:
                all_results.extend(page_results)

        # Print summary report
        if all_results:
            print_summary_report(all_results)

    finally:
        db.close()


if __name__ == "__main__":
    main()
