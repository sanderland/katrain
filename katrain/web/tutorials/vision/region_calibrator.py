"""Multi-evidence region calibration for Go board diagrams.

Infers col_start/row_start (which part of the 19×19 board is shown)
using multiple evidence sources: border lines, star points, line count,
and layout bias. Replaces fragile star-point-only calibration.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)

KNOWN_STARS_19 = {(3, 3), (9, 3), (15, 3), (3, 9), (9, 9), (15, 9), (3, 15), (9, 15), (15, 15)}


def _measure_line_thickness(gray, position, axis):
    """Measure the thickness (consecutive dark pixel rows/cols) of a grid line."""
    h_img, w_img = gray.shape
    if axis == "h":
        y = int(position)
        y1, y2 = max(0, y - 6), min(h_img, y + 7)
        strip = gray[y1:y2, :]
        dark_per_row = np.sum(strip < 120, axis=1)
        return int(np.sum(dark_per_row > w_img * 0.3))
    else:
        x = int(position)
        x1, x2 = max(0, x - 6), min(w_img, x + 7)
        strip = gray[:, x1:x2]
        dark_per_col = np.sum(strip < 120, axis=0)
        return int(np.sum(dark_per_col > h_img * 0.3))


def _count_extending_lines(gray, line_positions, edge_pos, axis, is_start, spacing=None):
    """Count how many grid lines extend past the edge line toward the image boundary.

    If many lines extend → this edge is NOT a board border (board continues beyond crop).
    If few/no lines extend → this edge IS a board border (board ends here).

    Uses projection (sum along the extension direction) to detect a line-like dark
    feature in a tolerance band around each grid line position. This handles printed
    lines that aren't perfectly aligned with the detected grid.
    """
    _, binary = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY_INV)
    h_img, w_img = gray.shape
    tol = max(4, int((spacing or 40) * 0.25))
    min_ext_len = max(8, int((spacing or 40) * 0.4))  # line must extend at least ~40% of spacing
    count = 0

    for pos in line_positions:
        p = int(pos)
        if axis == "h":
            # Extract band around this h-line, in the extension zone past the edge
            y1, y2 = max(0, p - tol), min(h_img, p + tol + 1)
            if is_start:
                x2 = max(1, int(edge_pos) - 2)
                x1 = max(0, x2 - min_ext_len)
            else:
                x1 = int(edge_pos) + 2
                x2 = min(w_img, x1 + min_ext_len)
            strip = binary[y1:y2, x1:x2]
            if strip.size == 0:
                continue
            # Project along x-axis: for each row in band, count dark pixels along extension
            # If any row has a continuous dark run → line extends
            row_dark = np.sum(strip > 0, axis=1)  # dark pixel count per row
            if np.max(row_dark) >= min(strip.shape[1], min_ext_len) * 0.5:
                count += 1
        else:
            # Extract band around this v-line, in the extension zone past the edge
            x1, x2 = max(0, p - tol), min(w_img, p + tol + 1)
            if is_start:
                y2 = max(1, int(edge_pos) - 2)
                y1 = max(0, y2 - min_ext_len)
            else:
                y1 = int(edge_pos) + 2
                y2 = min(h_img, y1 + min_ext_len)
            strip = binary[y1:y2, x1:x2]
            if strip.size == 0:
                continue
            col_dark = np.sum(strip > 0, axis=0)  # dark pixel count per column
            if np.max(col_dark) >= min(strip.shape[0], min_ext_len) * 0.5:
                count += 1
    return count


def _detect_borders(gray, h_positions, v_positions, spacing):
    """Detect which edges are board borders using line extension analysis.

    Key insight: on a real board border, grid lines STOP at the edge.
    On a non-border edge (crop boundary), grid lines EXTEND beyond the last line.

    Returns dict with keys 'left', 'right', 'top', 'bottom' → bool.
    """
    threshold = 0.08  # if ANY lines extend (>~1), it's NOT a border

    if len(v_positions) >= 19:
        left, right = True, True
    elif len(v_positions) > 0 and len(h_positions) > 0:
        l_ext = _count_extending_lines(gray, h_positions, v_positions[0], "h", True, spacing)
        r_ext = _count_extending_lines(gray, h_positions, v_positions[-1], "h", False, spacing)
        left = l_ext / len(h_positions) < threshold
        right = r_ext / len(h_positions) < threshold
    else:
        left, right = False, False

    if len(h_positions) >= 19:
        top, bottom = True, True
    elif len(h_positions) > 0 and len(v_positions) > 0:
        t_ext = _count_extending_lines(gray, v_positions, h_positions[0], "v", True, spacing)
        b_ext = _count_extending_lines(gray, v_positions, h_positions[-1], "v", False, spacing)
        top = t_ext / len(v_positions) < threshold
        bottom = b_ext / len(v_positions) < threshold
    else:
        top, bottom = False, False

    return {"left": left, "right": right, "top": top, "bottom": bottom}


def _count_star_matches(gray, h_positions, v_positions, spacing, occupied_set,
                        col_off, row_off, known_stars):
    """Count how many unoccupied intersections match expected star point positions.

    Star points appear as small dots (~3-5px) at specific intersections.
    Only checks unoccupied intersections (stones cover star points).
    """
    matches = 0
    r = max(3, int(spacing * 0.15))  # small radius for star point detection

    for ci, vx in enumerate(v_positions):
        for ri, hy in enumerate(h_positions):
            global_pos = (col_off + ci, row_off + ri)
            if global_pos not in known_stars:
                continue
            if (ci, ri) in occupied_set:
                continue  # stone covers star point

            # Check for a small dark dot at this intersection
            h_img, w_img = gray.shape
            y1 = max(0, int(hy) - r)
            y2 = min(h_img, int(hy) + r)
            x1 = max(0, int(vx) - r)
            x2 = min(w_img, int(vx) + r)
            roi = gray[y1:y2, x1:x2]

            if roi.size == 0:
                continue

            # Star points are small dark clusters at the center of the ROI
            dark_ratio = float(np.sum(roi < 120) / roi.size)
            if dark_ratio > 0.15:  # has a visible mark
                matches += 1

    return matches


def calibrate_region(gray, h_positions, v_positions, spacing, occupied=None):
    """Multi-evidence inference of col_start/row_start.

    Evidence sources:
    1. Border detection: thick lines at edges → board boundary → col/row = 0 or 18
    2. Star point matching: small dots at unoccupied intersections → known 19×19 positions
    3. Line count constraint: num_visible_cols + col_start <= 19
    4. Typical layout bias: most book diagrams start from corner

    Args:
        gray: grayscale image of the cropped diagram
        h_positions: detected horizontal line positions (pixel coords)
        v_positions: detected vertical line positions (pixel coords)
        spacing: average grid spacing in pixels
        occupied: set of (col_idx, row_idx) occupied intersections (optional)

    Returns:
        (col_start, row_start, confidence, evidence_details)
    """
    num_cols = len(v_positions)
    num_rows = len(h_positions)
    occupied_set = occupied or set()

    # Pre-compute which edges are board borders
    borders = _detect_borders(gray, h_positions, v_positions, spacing)
    has_left = borders.get("left", False)
    has_right = borders.get("right", False)
    has_top = borders.get("top", False)
    has_bottom = borders.get("bottom", False)

    candidates = []
    for col_off in range(max(0, 19 - num_cols) + 1):
        for row_off in range(max(0, 19 - num_rows) + 1):
            score = 0.0
            evidence = []

            # Evidence 1: border detection (hard constraints + scoring)
            # Rule: if lines extend past an edge → NOT a border → hard-reject candidates
            # that place the board edge there.
            # Conversely, if an edge IS a border → the candidate must align with it.

            # Hard constraint: non-border edge CANNOT be a board edge
            if not has_left and col_off == 0:
                score -= 100
                evidence.append("left_not_border")
            if not has_right and col_off + num_cols == 19:
                score -= 100
                evidence.append("right_not_border")
            if not has_top and row_off == 0:
                score -= 100
                evidence.append("top_not_border")
            if not has_bottom and row_off + num_rows == 19:
                score -= 100
                evidence.append("bottom_not_border")

            # Positive: border edge aligns with board edge
            # Negative: border detected but candidate doesn't place board edge there
            if has_left:
                if col_off == 0:
                    score += 5.0
                    evidence.append("left_border")
                else:
                    score -= 5.0
            if has_right:
                if col_off + num_cols == 19:
                    score += 5.0
                    evidence.append("right_border")
                else:
                    score -= 5.0
            if has_top:
                if row_off == 0:
                    score += 5.0
                    evidence.append("top_border")
                else:
                    score -= 5.0
            if has_bottom:
                if row_off + num_rows == 19:
                    score += 5.0
                    evidence.append("bottom_border")
                else:
                    score -= 5.0

            # Evidence 2: star point matching
            star_matches = _count_star_matches(
                gray, h_positions, v_positions, spacing,
                occupied_set, col_off, row_off, KNOWN_STARS_19
            )
            score += star_matches * 1.5
            if star_matches > 0:
                evidence.append(f"stars={star_matches}")

            # Evidence 3: typical layout bias (most book diagrams start from col=0, row=0)
            if col_off == 0:
                score += 0.5
            if row_off == 0:
                score += 0.5

            # Evidence 4: line count sanity check
            if col_off + num_cols > 19 or row_off + num_rows > 19:
                score -= 100  # impossible
                evidence.append("out_of_bounds")

            candidates.append((col_off, row_off, score, evidence))

    if not candidates:
        return 0, 0, 0.0, ["no_candidates"]

    best = max(candidates, key=lambda x: x[2])
    max_score = best[2]

    # Confidence: how much better is the best vs second-best
    sorted_candidates = sorted(candidates, key=lambda x: x[2], reverse=True)
    if len(sorted_candidates) > 1 and max_score > 0:
        second_score = sorted_candidates[1][2]
        confidence = min(1.0, (max_score - second_score) / (max_score + 1e-6))
    else:
        confidence = 1.0

    log.info("Region calibration: col_start=%d, row_start=%d, confidence=%.2f, evidence=%s",
             best[0], best[1], confidence, best[3])

    return best[0], best[1], confidence, best[3]
