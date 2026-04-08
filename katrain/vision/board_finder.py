"""
Board detection and perspective correction.

Hybrid detection: ArUco markers (primary, reliable) + improved Canny (fallback).

ArUco mode: Place 4 printed ArUco markers at the board corners.
Canny mode: Detects the board outline via edge detection (original approach, improved).

Ported from Fe-Fool/code/robot/image_find_focus.py (FocusFinder class).
Enhanced with:
- ArUco marker detection (primary method when configured)
- Improved Canny pipeline with aspect ratio / convexity / area filters
- Fixed stability filter (no baseline reset on rejection)
- CLAHE preprocessing for low-contrast wood boards
- cv2.undistort when camera calibration is available
- Fallback to last known transform matrix on detection failure
"""

import cv2
import numpy as np

from katrain.vision.config import CameraConfig


class BoardFinder:
    def __init__(
        self,
        scale: float = 1.0,
        marker_ids: list[int] | None = None,
        allowed_moving_length: int = 50,
        min_perimeter: int = 600,
        camera_config: CameraConfig | None = None,
    ):
        self.scale = scale
        self.marker_ids = marker_ids  # [top-left, top-right, bottom-right, bottom-left]
        self.allowed_moving_length = allowed_moving_length
        self.min_perimeter = min_perimeter
        self.camera_config = camera_config
        self.pre_corner_point = [(0, 0), (0, 0), (0, 0), (0, 0)]
        self.is_first = True
        self.last_transform_matrix: np.ndarray | None = None
        self.last_warp_size: tuple[int, int] | None = None

        # ArUco setup
        if marker_ids is not None:
            self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            self.aruco_params = cv2.aruco.DetectorParameters()
            self.aruco_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        else:
            self.aruco_dict = None
            self.aruco_params = None

    def find_focus(
        self, img: np.ndarray, min_threshold: int = 30, max_threshold: int = 250, use_clahe: bool = False
    ) -> tuple[np.ndarray | None, bool]:
        """
        Detect board outline and apply perspective transform.

        Returns:
            (warped_image, success) — warped_image is None if detection failed
        """
        source_img = img.copy()

        # Undistort if calibration available
        if self.camera_config and self.camera_config.is_calibrated:
            source_img = cv2.undistort(source_img, self.camera_config.camera_matrix, self.camera_config.dist_coeffs)

        # CLAHE preprocessing
        if use_clahe:
            processed = source_img.copy()
            lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            l_ch = clahe.apply(l_ch)
            lab = cv2.merge([l_ch, a_ch, b_ch])
            processed = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            processed = source_img

        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

        # Try ArUco detection first
        corners = None
        if self.marker_ids is not None:
            corners = self._detect_aruco(gray)

        # Canny fallback
        if corners is None:
            corners = self._detect_canny(processed, gray, min_threshold, max_threshold)

        if corners is None:
            return None, False

        sort_corner = self._sort_corner(corners)

        # Stability filter
        if self.is_first:
            self.pre_corner_point = sort_corner
            self.is_first = False
        elif np.max(abs(np.array(sort_corner) - np.array(self.pre_corner_point))) > self.allowed_moving_length:
            # Don't update baseline on rejection — keep old baseline
            return None, False

        # Accepted — update baseline
        self.pre_corner_point = sort_corner

        h, w = self._calc_size(sort_corner)
        if h <= 0 or w <= 0:
            return None, False

        dst = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        src = np.float32(sort_corner)
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(source_img, M, (int(w), int(h)))

        # Save transform for fallback
        self.last_transform_matrix = M
        self.last_warp_size = (int(w), int(h))

        return warped, True

    def _detect_aruco(self, gray: np.ndarray) -> list[tuple[int, int]] | None:
        """
        Detect 4 ArUco markers and return inner corner points.

        For each marker, uses the corner closest to the board center:
        - top-left marker → bottom-right corner (index 2)
        - top-right marker → bottom-left corner (index 3)
        - bottom-right marker → top-left corner (index 0)
        - bottom-left marker → top-right corner (index 1)

        Returns:
            List of 4 (x, y) corners ordered [TL, TR, BR, BL], or None.
        """
        if self.aruco_dict is None or self.marker_ids is None:
            return None

        detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        marker_corners, marker_ids, _ = detector.detectMarkers(gray)

        if marker_ids is None or len(marker_ids) == 0:
            return None

        # Build ID → corners mapping
        id_to_corners = {}
        for i, mid in enumerate(marker_ids.flatten()):
            id_to_corners[int(mid)] = marker_corners[i][0]  # shape (4, 2)

        # Check all 4 required markers are found
        for mid in self.marker_ids:
            if mid not in id_to_corners:
                return None

        # Extract inner corners: the corner of each marker closest to board center
        # marker_ids order: [top-left, top-right, bottom-right, bottom-left]
        # ArUco corner order: [top-left=0, top-right=1, bottom-right=2, bottom-left=3]
        inner_corner_indices = [2, 3, 0, 1]

        result = []
        for marker_idx, mid in enumerate(self.marker_ids):
            mc = id_to_corners[mid]
            corner_idx = inner_corner_indices[marker_idx]
            x, y = mc[corner_idx]
            result.append((int(round(x)), int(round(y))))

        return result

    def _detect_canny(
        self, processed: np.ndarray, gray: np.ndarray, min_threshold: int, max_threshold: int
    ) -> list[tuple[int, int]] | None:
        """
        Detect board via Canny edge detection with improved filtering.

        Improvements over original:
        - Progressive approxPolyDP epsilon (0.02 → 0.04 → 0.06)
        - Aspect ratio filter (0.7–1.4)
        - Convexity check
        - Area filter (10%–80% of frame to reject background surfaces)
        - Direct use of approxPolyDP 4-point result
        """
        blurred = cv2.GaussianBlur(processed, (5, 5), 0, 0)
        canny = cv2.Canny(blurred, min_threshold, max_threshold)
        k = np.ones((3, 3), np.uint8)
        canny = cv2.morphologyEx(canny, cv2.MORPH_CLOSE, k)

        contours, _ = cv2.findContours(canny, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        frame_area = gray.shape[0] * gray.shape[1]

        # Progressive epsilon: try tighter first, relax if needed.
        # Real-world boards (grid lines, oblique angles) often need 0.04–0.06.
        for eps_factor in (0.02, 0.04, 0.06):
            result = self._try_canny_with_epsilon(contours, frame_area, eps_factor, processed)
            if result is not None:
                return result

        return None

    def _try_canny_with_epsilon(
        self, contours, frame_area: int, eps_factor: float, image_bgr: np.ndarray
    ) -> list[tuple[int, int]] | None:
        """Try to find a valid board quadrilateral at a given epsilon factor."""
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            if perimeter < self.min_perimeter:
                break  # sorted by area, so remaining are smaller

            epsilon = eps_factor * perimeter
            approx = cv2.approxPolyDP(contour, epsilon, True)

            if len(approx) != 4:
                continue

            # Convexity check
            if not cv2.isContourConvex(approx):
                continue

            # Area filter: must fill 10%–80% of frame
            # Upper bound rejects background surfaces (table/paper) that are
            # larger than the board itself.
            area = cv2.contourArea(approx)
            if area < 0.10 * frame_area or area > 0.80 * frame_area:
                continue

            # Aspect ratio filter
            rect = cv2.boundingRect(approx)
            _, _, rw, rh = rect
            if rh == 0:
                continue
            aspect = rw / rh
            if aspect < 0.7 or aspect > 1.4:
                continue

            # Color validation: interior must be predominantly wood-colored,
            # not white paper or dark background.
            if not self._is_wood_colored(image_bgr, approx):
                continue

            # Use the 4 points directly
            points = [(int(p[0][0]), int(p[0][1])) for p in approx]
            return points

        return None

    @staticmethod
    def _is_wood_colored(image_bgr: np.ndarray, approx: np.ndarray) -> bool:
        """Check if the interior of a quadrilateral is predominantly wood-colored.

        Go boards are typically warm-toned wood (yellow/orange/brown in HSV).
        White paper or dark backgrounds will fail this check.
        """
        mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [approx], 255)

        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        # Wood color: hue 10-40 (yellow-orange-brown), moderate saturation, medium-high value
        wood_mask = cv2.inRange(hsv, np.array([10, 20, 80]), np.array([40, 200, 255]))

        interior_pixels = cv2.countNonZero(mask)
        if interior_pixels == 0:
            return False
        wood_pixels = cv2.countNonZero(cv2.bitwise_and(wood_mask, mask))
        return (wood_pixels / interior_pixels) > 0.25

    def _calc_size(self, corners):
        # corners = [TL, TR, BR, BL]
        h = max(corners[3][1] - corners[0][1], corners[2][1] - corners[1][1]) * self.scale
        w = max(corners[1][0] - corners[0][0], corners[2][0] - corners[3][0]) * self.scale
        return h, w

    def _sort_corner(self, pts):
        # Sort by y to split top/bottom, then by x within each pair.
        # Returns [TL, TR, BR, BL] matching dst [[0,0], [w,0], [w,h], [0,h]].
        pts = sorted(pts, key=lambda p: p[1])
        top = sorted(pts[:2], key=lambda p: p[0])  # ascending x: [left, right]
        bot = sorted(pts[2:], key=lambda p: p[0])  # ascending x: [left, right]
        return [top[0], top[1], bot[1], bot[0]]  # [TL, TR, BR, BL]
