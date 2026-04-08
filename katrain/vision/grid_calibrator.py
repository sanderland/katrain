"""Grid calibration via Hough line detection.

Detects the 19x19 grid lines on a perspective-corrected (warped) board image
and computes precise pixel offsets and spacing.  Run once at game start when
the board has few/no stones for best results.  The calibration is cached and
reused until the board physically moves.

Algorithm (proven in prototype /tmp/hough_grid_detect.py):
  1. CLAHE + adaptive threshold
  2. Directional morphological filtering (H and V separately)
  3. HoughLinesP on each directional mask (+ full binary supplementary)
  4. Weighted histogram clustering into distinct line positions
  5. RANSAC-style regular grid fitting with least-squares refinement
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass
class GridCalibration:
    """Result of grid calibration."""

    h_offset: float  # y-position of first horizontal line (pixels)
    h_spacing: float  # horizontal line spacing (pixels)
    v_offset: float  # x-position of first vertical line (pixels)
    v_spacing: float  # vertical line spacing (pixels)
    confidence: float  # 0-1 quality metric


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------


class GridCalibrator:
    """Detects 19x19 grid lines via Hough transform and computes calibration."""

    def __init__(self, grid_size: int = 19):
        self.grid_size = grid_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calibrate(self, warped: np.ndarray) -> GridCalibration | None:
        """Detect grid lines and return calibration, or None if detection failed.

        Parameters
        ----------
        warped:
            Perspective-corrected board image (BGR or grayscale).
        """
        h, w = warped.shape[:2]

        h_positions, v_positions = self._detect_lines(warped)

        h_fit = self._fit_regular_grid(h_positions, self.grid_size, h)
        v_fit = self._fit_regular_grid(v_positions, self.grid_size, w)

        if h_fit is None or v_fit is None:
            logger.warning(
                "Grid calibration failed: could not fit %d lines (H=%d peaks, V=%d peaks)",
                self.grid_size,
                len(h_positions),
                len(v_positions),
            )
            return None

        h_offset, h_spacing = h_fit
        v_offset, v_spacing = v_fit

        # Confidence: ratio of detected peaks to expected grid lines, capped at 1.0
        confidence = min(len(h_positions), len(v_positions)) / self.grid_size
        confidence = min(1.0, confidence)

        logger.info(
            "Grid calibration: H(offset=%.1f, spacing=%.1f) V(offset=%.1f, spacing=%.1f) conf=%.2f",
            h_offset,
            h_spacing,
            v_offset,
            v_spacing,
            confidence,
        )

        return GridCalibration(
            h_offset=h_offset,
            h_spacing=h_spacing,
            v_offset=v_offset,
            v_spacing=v_spacing,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Line detection pipeline
    # ------------------------------------------------------------------

    def _detect_lines(self, warped: np.ndarray) -> tuple[list[float], list[float]]:
        """Full Hough pipeline: preprocess -> morph filter -> detect -> cluster.

        Returns (h_positions, v_positions) sorted lists of line pixel positions.
        """
        h, w = warped.shape[:2]

        # 1. Preprocess
        gray, binary = self._preprocess(warped)

        # 2. Directional morphological masks
        h_mask, v_mask = self._make_directional_masks(binary, h, w)

        # 3. Detect Hough segments on directional masks
        min_line_len_h = max(10, int(w * 0.10))
        min_line_len_v = max(10, int(h * 0.10))
        max_gap = max(5, int(min(w, h) * 0.04))

        h_segments = self._detect_hough_segments(h_mask, min_line_len_h, max_gap, threshold=30)
        h_segments = self._filter_by_angle(h_segments, target_angle_deg=0, tolerance_deg=15)

        v_segments = self._detect_hough_segments(v_mask, min_line_len_v, max_gap, threshold=30)
        v_segments = self._filter_by_angle(v_segments, target_angle_deg=90, tolerance_deg=15)

        # 4. Supplementary detection on full binary
        full_segments = self._detect_hough_segments(
            binary, min(min_line_len_h, min_line_len_v), max_gap, threshold=50
        )
        full_h = self._filter_by_angle(full_segments, 0, 15)
        full_v = self._filter_by_angle(full_segments, 90, 15)

        all_h = h_segments + full_h
        all_v = v_segments + full_v

        # 5. Cluster into distinct positions
        h_peaks = self._cluster_to_positions(all_h, axis="y", img_size=h)
        v_peaks = self._cluster_to_positions(all_v, axis="x", img_size=w)

        h_positions = [p for p, _w in h_peaks]
        v_positions = [p for p, _w in v_peaks]

        logger.debug(
            "Line detection: %d H segments -> %d peaks, %d V segments -> %d peaks",
            len(all_h),
            len(h_positions),
            len(all_v),
            len(v_positions),
        )

        return h_positions, v_positions

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess(warped: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Convert to grayscale, CLAHE, adaptive threshold."""
        if len(warped.shape) == 3:
            gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        else:
            gray = warped.copy()

        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        binary = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=15,
            C=8,
        )
        return gray, binary

    @staticmethod
    def _make_directional_masks(
        binary: np.ndarray, h_img: int, w_img: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Separate H and V features via directional morphological opening."""
        # Horizontal: keep long horizontal structures
        h_kernel_len = max(15, w_img // 30)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
        h_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
        h_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        h_mask = cv2.dilate(h_mask, h_dilate, iterations=1)

        # Vertical: keep long vertical structures
        v_kernel_len = max(15, h_img // 30)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_len))
        v_mask = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        v_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        v_mask = cv2.dilate(v_mask, v_dilate, iterations=1)

        return h_mask, v_mask

    # ------------------------------------------------------------------
    # Hough segment detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_hough_segments(
        binary: np.ndarray, min_line_length: int, max_line_gap: int, threshold: int = 40
    ) -> list[tuple[int, int, int, int]]:
        """Run HoughLinesP and return raw segments as (x1, y1, x2, y2) tuples."""
        lines = cv2.HoughLinesP(
            binary,
            rho=1,
            theta=np.pi / 180,
            threshold=threshold,
            minLineLength=min_line_length,
            maxLineGap=max_line_gap,
        )
        if lines is None:
            return []
        return [(int(seg[0][0]), int(seg[0][1]), int(seg[0][2]), int(seg[0][3])) for seg in lines]

    @staticmethod
    def _filter_by_angle(
        segments: list[tuple[int, int, int, int]],
        target_angle_deg: int,
        tolerance_deg: int = 20,
    ) -> list[tuple[int, int, int, int]]:
        """Keep segments within angle tolerance of the target (0=horizontal, 90=vertical)."""
        result = []
        for x1, y1, x2, y2 in segments:
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if target_angle_deg == 0:
                if angle < tolerance_deg or angle > (180 - tolerance_deg):
                    result.append((x1, y1, x2, y2))
            elif target_angle_deg == 90:
                if abs(angle - 90) < tolerance_deg:
                    result.append((x1, y1, x2, y2))
        return result

    # ------------------------------------------------------------------
    # Clustering
    # ------------------------------------------------------------------

    @staticmethod
    def _segment_position(seg: tuple[int, int, int, int], axis: str) -> float:
        """Representative position: average y for H lines, average x for V lines."""
        x1, y1, x2, y2 = seg
        return (y1 + y2) / 2.0 if axis == "y" else (x1 + x2) / 2.0

    @staticmethod
    def _segment_length(seg: tuple[int, int, int, int]) -> float:
        x1, y1, x2, y2 = seg
        return float(np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))

    @classmethod
    def _cluster_to_positions(
        cls,
        segments: list[tuple[int, int, int, int]],
        axis: str,
        img_size: int,
    ) -> list[tuple[float, float]]:
        """Cluster segments into distinct line positions using weighted histogram peaks.

        Returns sorted list of (position, weight) tuples.
        """
        if not segments:
            return []

        positions = np.array([cls._segment_position(s, axis) for s in segments])
        weights = np.array([cls._segment_length(s) for s in segments])

        # Weighted histogram
        n_bins = max(img_size, 400)
        hist = np.zeros(n_bins)
        for p, w in zip(positions, weights):
            bin_idx = int(np.clip(p / img_size * (n_bins - 1), 0, n_bins - 1))
            hist[bin_idx] += w

        # Smooth
        kernel_size = max(3, n_bins // 120)
        if kernel_size % 2 == 0:
            kernel_size += 1
        smoothed = np.convolve(hist, np.ones(kernel_size) / kernel_size, mode="same")

        # Find peaks
        threshold = max(smoothed) * 0.05 if max(smoothed) > 0 else 0
        peaks: list[tuple[float, float]] = []
        for i in range(1, len(smoothed) - 1):
            if smoothed[i] > threshold and smoothed[i] >= smoothed[i - 1] and smoothed[i] >= smoothed[i + 1]:
                window = 5
                lo = max(0, i - window)
                hi = min(len(smoothed), i + window + 1)
                idx_range = np.arange(lo, hi)
                w_range = smoothed[lo:hi]
                if w_range.sum() > 0:
                    refined_bin = float(np.average(idx_range, weights=w_range))
                    peak_pos = refined_bin / (n_bins - 1) * img_size
                else:
                    peak_pos = i / (n_bins - 1) * img_size
                peaks.append((peak_pos, float(smoothed[i])))

        # Merge close peaks (< img_size / 40)
        min_gap = img_size / 40
        merged: list[tuple[float, float]] = []
        for pos, wt in peaks:
            if merged and abs(pos - merged[-1][0]) < min_gap:
                p0, w0 = merged[-1]
                merged[-1] = ((p0 * w0 + pos * wt) / (w0 + wt), w0 + wt)
            else:
                merged.append((pos, wt))

        return merged

    # ------------------------------------------------------------------
    # Grid fitting (RANSAC-style)
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_regular_grid(
        peak_positions: list[float],
        n_target: int,
        img_size: int,
    ) -> tuple[float, float] | None:
        """Fit an evenly-spaced grid to detected peak positions.

        Returns (offset_of_first_line, spacing) or None if fit fails.

        Uses RANSAC-like approach: enumerate (offset, spacing) hypotheses from
        pairs of detected peaks, count inliers, refine the best via least-squares.
        """
        peaks = np.array(sorted(peak_positions))
        n = len(peaks)

        if n < max(3, int(n_target * 0.3)):
            logger.debug("Too few peaks (%d) for %d-line grid", n, n_target)
            return None

        # Build spacing candidates from pairwise differences
        diffs: list[float] = []
        spacing_lo = img_size / (n_target + 5)
        spacing_hi = img_size / max(1, n_target - 8)

        for i in range(n):
            for j in range(i + 1, min(i + 5, n)):
                d = peaks[j] - peaks[i]
                for k in range(1, 4):
                    candidate = d / k
                    if spacing_lo < candidate < spacing_hi:
                        diffs.append(candidate)

        if not diffs:
            # Fallback: assume peaks span the full grid
            spacing_est = (peaks[-1] - peaks[0]) / max(n - 1, 1)
            if spacing_lo < spacing_est < spacing_hi:
                diffs = [spacing_est]
            else:
                return None

        # RANSAC: try each spacing with various anchor assignments
        best_score = -1.0
        best_params: tuple[float, float, int] | None = None

        for spacing_candidate in diffs:
            for anchor_idx in range(n):
                for grid_idx_guess in range(n_target):
                    offset = peaks[anchor_idx] - grid_idx_guess * spacing_candidate

                    # Bounds check
                    first_line = offset
                    last_line = offset + (n_target - 1) * spacing_candidate
                    if first_line < -img_size * 0.1 or last_line > img_size * 1.1:
                        continue

                    # Count inliers
                    tolerance = spacing_candidate * 0.25
                    inlier_count = 0
                    total_error = 0.0
                    for p in peaks:
                        grid_pos = (p - offset) / spacing_candidate
                        nearest_int = round(grid_pos)
                        if 0 <= nearest_int < n_target:
                            residual = abs(grid_pos - nearest_int) * spacing_candidate
                            if residual < tolerance:
                                inlier_count += 1
                                total_error += residual**2

                    if inlier_count >= 3:
                        score = inlier_count * 1000 - total_error
                        if score > best_score:
                            best_score = score
                            best_params = (offset, spacing_candidate, inlier_count)

        if best_params is None:
            return None

        offset, spacing, n_inliers = best_params

        if n_inliers < max(3, int(n_target * 0.3)):
            logger.debug("Best fit only has %d inliers (need %d)", n_inliers, int(n_target * 0.3))
            return None

        # Refine via least-squares on inliers
        tolerance = spacing * 0.25
        inlier_positions: list[float] = []
        inlier_indices: list[int] = []
        for p in peaks:
            grid_pos = (p - offset) / spacing
            nearest_int = round(grid_pos)
            if 0 <= nearest_int < n_target:
                residual = abs(grid_pos - nearest_int) * spacing
                if residual < tolerance:
                    inlier_positions.append(p)
                    inlier_indices.append(nearest_int)

        if len(inlier_positions) >= 2 and len(set(inlier_indices)) >= 2:
            A = np.vstack([np.array(inlier_indices, dtype=float), np.ones(len(inlier_indices))]).T
            result = np.linalg.lstsq(A, np.array(inlier_positions), rcond=None)
            spacing_fit, offset_fit = result[0]
        else:
            spacing_fit, offset_fit = spacing, offset

        # Sanity: spacing must be positive
        if spacing_fit <= 0:
            return None

        return (float(offset_fit), float(spacing_fit))


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def pixel_to_grid_calibrated(
    x_px: float,
    y_px: float,
    cal: GridCalibration,
    grid_size: int = 19,
) -> tuple[int, int]:
    """Map pixel coordinates to grid position using calibration.

    Parameters
    ----------
    x_px, y_px:
        Pixel coordinates in the warped board image.
    cal:
        Grid calibration result from :class:`GridCalibrator`.
    grid_size:
        Number of lines per side (default 19).

    Returns
    -------
    (col, row) grid indices clamped to [0, grid_size-1].
    """
    col = round((x_px - cal.v_offset) / cal.v_spacing)
    row = round((y_px - cal.h_offset) / cal.h_spacing)
    gs = grid_size - 1
    return max(0, min(gs, col)), max(0, min(gs, row))
