import cv2
import numpy as np
import pytest
from katrain.vision.board_finder import BoardFinder
from katrain.vision.config import CameraConfig


@pytest.fixture
def finder():
    return BoardFinder()


def make_board_image(width=640, height=480, board_rect=(100, 50, 440, 380)):
    """Create a synthetic image with a rectangular 'board' region."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (200, 200, 200)
    x1, y1, x2, y2 = board_rect
    cv2.rectangle(img, (x1, y1), (x2, y2), (80, 155, 200), -1)  # warm wood tone (HSV H≈19)
    cv2.rectangle(img, (x1, y1), (x2, y2), (50, 50, 50), 3)
    return img


def make_aruco_image(marker_ids=(0, 1, 2, 3), width=800, height=800, marker_size=60, margin=40):
    """Create a synthetic image with 4 ArUco markers at the corners of a board region."""
    img = np.ones((height, width, 3), dtype=np.uint8) * 200
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    # Draw board area
    bx1, by1 = margin + marker_size, margin + marker_size
    bx2, by2 = width - margin - marker_size, height - margin - marker_size
    cv2.rectangle(img, (bx1, by1), (bx2, by2), (139, 119, 101), -1)

    # Place markers at corners (outside the board area)
    positions = [
        (margin, margin),  # top-left
        (width - margin - marker_size, margin),  # top-right
        (width - margin - marker_size, height - margin - marker_size),  # bottom-right
        (margin, height - margin - marker_size),  # bottom-left
    ]

    for mid, (px, py) in zip(marker_ids, positions):
        marker = cv2.aruco.generateImageMarker(aruco_dict, mid, marker_size)
        marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        img[py : py + marker_size, px : px + marker_size] = marker_bgr

    return img


class TestBoardFinderInit:
    def test_init_defaults(self):
        finder = BoardFinder()
        assert finder.allowed_moving_length == 10
        assert finder.marker_ids is None
        assert finder.aruco_dict is None
        assert finder.aruco_params is None
        assert not hasattr(finder, "allowed_moving_girth")

    def test_init_with_marker_ids(self):
        finder = BoardFinder(marker_ids=[0, 1, 2, 3])
        assert finder.marker_ids == [0, 1, 2, 3]
        assert finder.aruco_dict is not None
        assert finder.aruco_params is not None
        assert finder.aruco_params.cornerRefinementMethod == cv2.aruco.CORNER_REFINE_SUBPIX

    def test_accepts_camera_config(self):
        cam = CameraConfig()
        finder = BoardFinder(camera_config=cam)
        assert finder.camera_config is cam


class TestBoardFinderCanny:
    def test_finds_board_in_synthetic_image(self, finder):
        img = make_board_image()
        warped, found = finder.find_focus(img)
        assert found is True
        assert warped is not None
        assert warped.shape[0] > 0

    def test_returns_false_for_blank_image(self, finder):
        img = np.ones((480, 640, 3), dtype=np.uint8) * 128
        warped, found = finder.find_focus(img)
        assert found is False

    def test_clahe_preprocessing(self, finder):
        img = np.ones((480, 640, 3), dtype=np.uint8) * 160
        x1, y1, x2, y2 = 100, 50, 440, 380
        cv2.rectangle(img, (x1, y1), (x2, y2), (150, 140, 130), -1)
        cv2.rectangle(img, (x1, y1), (x2, y2), (130, 120, 110), 3)
        warped, found = finder.find_focus(img, use_clahe=True)
        assert isinstance(found, bool)

    def test_detect_canny_aspect_ratio_filter(self):
        """Non-square contour (very wide rectangle) should be rejected."""
        finder = BoardFinder()
        # Create image with very elongated rectangle (aspect > 1.4)
        img = np.ones((480, 640, 3), dtype=np.uint8) * 200
        cv2.rectangle(img, (20, 180), (620, 300), (50, 50, 50), 3)  # 600x120 → aspect ~5.0
        warped, found = finder.find_focus(img)
        assert found is False

    def test_detect_canny_convexity_filter(self):
        """Non-convex contour should be rejected by _detect_canny."""
        finder = BoardFinder()
        gray = np.ones((480, 640), dtype=np.uint8) * 200
        processed = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        # L-shape (non-convex)
        points = np.array(
            [
                [[100, 100]],
                [[400, 100]],
                [[400, 300]],
                [[250, 300]],
                [[250, 200]],
                [[100, 200]],
            ],
            dtype=np.int32,
        )
        cv2.drawContours(processed, [points], -1, (50, 50, 50), 3)
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        result = finder._detect_canny(processed, gray, 30, 250)
        assert result is None


class TestBoardFinderAruco:
    def test_detect_aruco_all_found(self):
        """When all 4 markers present, _detect_aruco returns 4 corners."""
        finder = BoardFinder(marker_ids=[0, 1, 2, 3])
        img = make_aruco_image(marker_ids=(0, 1, 2, 3))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = finder._detect_aruco(gray)
        assert corners is not None
        assert len(corners) == 4
        for c in corners:
            assert len(c) == 2
            assert isinstance(c[0], int)
            assert isinstance(c[1], int)

    def test_detect_aruco_partial(self):
        """When only some markers present, returns None."""
        finder = BoardFinder(marker_ids=[0, 1, 2, 3])
        # Only place markers 0 and 1, missing 2 and 3
        img = make_aruco_image(marker_ids=(0, 1, 10, 11))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners = finder._detect_aruco(gray)
        assert corners is None

    def test_detect_aruco_none_without_config(self):
        """Without marker_ids, _detect_aruco returns None."""
        finder = BoardFinder()
        gray = np.ones((480, 640), dtype=np.uint8) * 128
        assert finder._detect_aruco(gray) is None

    def test_find_focus_with_aruco(self):
        """Full pipeline with ArUco markers produces a warped image."""
        finder = BoardFinder(marker_ids=[0, 1, 2, 3])
        img = make_aruco_image(marker_ids=(0, 1, 2, 3))
        warped, found = finder.find_focus(img)
        assert found is True
        assert warped is not None
        assert warped.shape[0] > 0
        assert warped.shape[1] > 0


class TestStabilityFilter:
    def test_stability_filter_rejects_large_jumps(self, finder):
        img = make_board_image()
        _, found1 = finder.find_focus(img)
        assert found1 is True
        img2 = make_board_image(board_rect=(200, 150, 540, 430))
        _, found2 = finder.find_focus(img2)
        assert found2 is False

    def test_stability_no_baseline_reset(self):
        """Verify baseline is NOT updated when a frame is rejected."""
        finder = BoardFinder()
        img1 = make_board_image()
        _, found1 = finder.find_focus(img1)
        assert found1 is True
        baseline_after_accept = list(finder.pre_corner_point)

        # Large jump — should be rejected
        img2 = make_board_image(board_rect=(200, 150, 540, 430))
        _, found2 = finder.find_focus(img2)
        assert found2 is False
        # Baseline should NOT have changed
        assert finder.pre_corner_point == baseline_after_accept

    def test_fallback_uses_last_transform(self, finder):
        """When detection fails but board is stable, reuse last transform matrix."""
        img = make_board_image()
        warped1, found1 = finder.find_focus(img)
        assert found1 is True
        # Blank image — detection fails, but last_transform_matrix should exist
        blank = np.ones((480, 640, 3), dtype=np.uint8) * 128
        warped2, found2 = finder.find_focus(blank)
        assert isinstance(found2, bool)
        assert finder.last_transform_matrix is not None  # Saved from successful detection
