"""Tests for the Hough-based grid calibration module."""

import cv2
import numpy as np
import pytest

from katrain.vision.grid_calibrator import (
    GridCalibration,
    GridCalibrator,
    pixel_to_grid_calibrated,
)


def make_grid_image(
    width: int = 640,
    height: int = 640,
    grid_size: int = 19,
    border: int = 30,
    line_thickness: int = 1,
) -> tuple[np.ndarray, float, float, float]:
    """Create a synthetic board image with known grid lines.

    Returns (image, border, spacing_x, spacing_y).
    """
    img = np.ones((height, width, 3), dtype=np.uint8) * 200  # light background
    spacing_x = (width - 2 * border) / (grid_size - 1)
    spacing_y = (height - 2 * border) / (grid_size - 1)
    for i in range(grid_size):
        y = int(border + i * spacing_y)
        cv2.line(img, (border, y), (width - border, y), (50, 50, 50), line_thickness)
        x = int(border + i * spacing_x)
        cv2.line(img, (x, border), (x, height - border), (50, 50, 50), line_thickness)
    return img, float(border), spacing_x, spacing_y


class TestGridCalibrator:
    """Tests for GridCalibrator.calibrate()."""

    def test_synthetic_grid(self):
        """Calibration on a clean synthetic 19x19 board should match known geometry."""
        img, expected_border, expected_sx, expected_sy = make_grid_image()
        cal = GridCalibrator().calibrate(img)
        assert cal is not None, "Calibration returned None on a clean synthetic grid"
        assert abs(cal.v_offset - expected_border) < expected_sx * 0.2, (
            f"v_offset {cal.v_offset:.1f} too far from expected {expected_border:.1f}"
        )
        assert abs(cal.h_offset - expected_border) < expected_sy * 0.2, (
            f"h_offset {cal.h_offset:.1f} too far from expected {expected_border:.1f}"
        )
        assert abs(cal.v_spacing - expected_sx) < expected_sx * 0.1, (
            f"v_spacing {cal.v_spacing:.2f} too far from expected {expected_sx:.2f}"
        )
        assert abs(cal.h_spacing - expected_sy) < expected_sy * 0.1, (
            f"h_spacing {cal.h_spacing:.2f} too far from expected {expected_sy:.2f}"
        )
        assert cal.confidence > 0.5

    def test_synthetic_grid_larger_image(self):
        """Calibration works on larger images with wider borders."""
        img, expected_border, expected_sx, expected_sy = make_grid_image(
            width=800, height=800, border=60, line_thickness=2
        )
        cal = GridCalibrator().calibrate(img)
        assert cal is not None
        assert abs(cal.v_spacing - expected_sx) < expected_sx * 0.1
        assert abs(cal.h_spacing - expected_sy) < expected_sy * 0.1

    def test_returns_none_for_blank_image(self):
        """A blank image with no lines should return None."""
        img = np.ones((400, 400, 3), dtype=np.uint8) * 200
        cal = GridCalibrator().calibrate(img)
        assert cal is None

    def test_returns_none_for_noise_image(self):
        """An image of pure random noise should return None."""
        rng = np.random.RandomState(42)
        img = rng.randint(0, 256, (400, 400, 3), dtype=np.uint8)
        cal = GridCalibrator().calibrate(img)
        assert cal is None

    def test_grayscale_input(self):
        """Calibrator accepts grayscale input as well as BGR."""
        img_bgr, expected_border, expected_sx, expected_sy = make_grid_image()
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        cal = GridCalibrator().calibrate(img_gray)
        assert cal is not None
        assert abs(cal.v_spacing - expected_sx) < expected_sx * 0.15

    def test_9x9_grid(self):
        """Calibrator supports non-19 grid sizes."""
        img, expected_border, expected_sx, expected_sy = make_grid_image(
            width=400, height=400, grid_size=9, border=30, line_thickness=1
        )
        cal = GridCalibrator(grid_size=9).calibrate(img)
        assert cal is not None
        assert abs(cal.v_spacing - expected_sx) < expected_sx * 0.15
        assert abs(cal.h_spacing - expected_sy) < expected_sy * 0.15


class TestPixelToGridCalibrated:
    """Tests for the pixel_to_grid_calibrated convenience function."""

    @pytest.fixture()
    def cal(self) -> GridCalibration:
        return GridCalibration(
            h_offset=30.0, h_spacing=32.0, v_offset=30.0, v_spacing=32.0, confidence=0.9
        )

    def test_origin(self, cal: GridCalibration):
        assert pixel_to_grid_calibrated(30, 30, cal) == (0, 0)

    def test_far_corner(self, cal: GridCalibration):
        assert pixel_to_grid_calibrated(30 + 18 * 32, 30 + 18 * 32, cal) == (18, 18)

    def test_center_with_offset(self, cal: GridCalibration):
        # Slight sub-cell offset should still snap to (9, 9)
        assert pixel_to_grid_calibrated(30 + 9 * 32 + 5, 30 + 9 * 32 - 3, cal) == (9, 9)

    def test_clamping_negative(self, cal: GridCalibration):
        assert pixel_to_grid_calibrated(-100, -100, cal) == (0, 0)

    def test_clamping_overflow(self, cal: GridCalibration):
        assert pixel_to_grid_calibrated(9999, 9999, cal) == (18, 18)

    def test_non_default_grid_size(self, cal: GridCalibration):
        # With grid_size=9, max index is 8
        assert pixel_to_grid_calibrated(9999, 9999, cal, grid_size=9) == (8, 8)


class TestFitRegularGrid:
    """Unit tests for the internal _fit_regular_grid method."""

    def test_perfect_19_positions(self):
        """Given exactly 19 evenly-spaced positions, fitting should be exact."""
        spacing = 30.0
        offset = 25.0
        positions = [offset + i * spacing for i in range(19)]
        result = GridCalibrator._fit_regular_grid(positions, 19, 640)
        assert result is not None
        fit_offset, fit_spacing = result
        assert abs(fit_offset - offset) < 1.0
        assert abs(fit_spacing - spacing) < 0.5

    def test_partial_positions(self):
        """Fitting should succeed with a subset of the 19 lines detected."""
        spacing = 30.0
        offset = 25.0
        # Drop some lines (simulating stone occlusion)
        indices = [0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 17, 18]
        positions = [offset + i * spacing for i in indices]
        result = GridCalibrator._fit_regular_grid(positions, 19, 640)
        assert result is not None
        fit_offset, fit_spacing = result
        assert abs(fit_offset - offset) < 2.0
        assert abs(fit_spacing - spacing) < 1.0

    def test_too_few_positions_returns_none(self):
        """With fewer than 30% of expected lines, fitting should fail."""
        result = GridCalibrator._fit_regular_grid([10.0, 40.0], 19, 640)
        assert result is None


class TestClusterToPositions:
    """Unit tests for the internal _cluster_to_positions method."""

    def test_clusters_nearby_segments(self):
        """Multiple segments at similar y should cluster into one position."""
        # Three horizontal segments near y=100
        segments = [
            (10, 99, 300, 101),
            (50, 100, 350, 100),
            (20, 98, 320, 102),
        ]
        peaks = GridCalibrator._cluster_to_positions(segments, axis="y", img_size=400)
        # Should produce exactly one cluster near y=100
        assert len(peaks) == 1
        pos, _weight = peaks[0]
        assert abs(pos - 100) < 10

    def test_empty_segments(self):
        assert GridCalibrator._cluster_to_positions([], axis="y", img_size=400) == []
