"""
Show the 19x19 grid overlay on a live camera feed to verify board detection + coordinate mapping.

Usage:
    python -m katrain.vision.tools.show_grid --camera 0
    python -m katrain.vision.tools.show_grid --camera 0 --marker-ids 0 1 2 3
    python -m katrain.vision.tools.show_grid --camera 0 --debug --marker-ids 0 1 2 3

No YOLO model needed — this only tests BoardFinder + coordinate mapping.

Controls:  Q = quit | C = toggle CLAHE | S = save screenshot | D = toggle debug
"""

import argparse

import cv2
import numpy as np

from katrain.vision.board_finder import BoardFinder
from katrain.vision.config import BoardConfig
from katrain.vision.coordinates import grid_to_pixel
from katrain.vision.stone_detector import Detection


def draw_grid(image: np.ndarray, config: BoardConfig) -> np.ndarray:
    """Draw all 361 intersection points and grid lines on the warped board image."""
    display = image.copy()
    h, w = display.shape[:2]
    gs = config.grid_size

    # Draw grid lines
    for i in range(gs):
        # Horizontal lines
        x0, y = grid_to_pixel(0, i, w, h, config)
        x1, _ = grid_to_pixel(gs - 1, i, w, h, config)
        cv2.line(display, (x0, y), (x1, y), (0, 0, 255), 1)
        # Vertical lines
        x, y0 = grid_to_pixel(i, 0, w, h, config)
        _, y1 = grid_to_pixel(i, gs - 1, w, h, config)
        cv2.line(display, (x, y0), (x, y1), (0, 0, 255), 1)

    # Draw intersection dots
    for row in range(gs):
        for col in range(gs):
            px, py = grid_to_pixel(col, row, w, h, config)
            cv2.circle(display, (px, py), 3, (0, 255, 0), -1)

    # Highlight star points (for 19x19)
    if gs == 19:
        for r in (3, 9, 15):
            for c in (3, 9, 15):
                px, py = grid_to_pixel(c, r, w, h, config)
                cv2.circle(display, (px, py), 5, (0, 255, 255), -1)

    # Label corners
    for col, row, label in [(0, 0, "A19"), (18, 0, "T19"), (0, 18, "A1"), (18, 18, "T1"), (9, 9, "K10")]:
        px, py = grid_to_pixel(col, row, w, h, config)
        cv2.putText(display, label, (px + 6, py - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

    return display


def draw_detections_overlay(
    image: np.ndarray, detections: list[Detection], config: BoardConfig, font_scale: float = 0.45
) -> np.ndarray:
    """Draw YOLO-style bbox + label + confidence on warped board image.

    Args:
        image: warped board BGR image
        detections: list of Detection objects (with bbox coordinates in warped image space)
        config: BoardConfig (unused currently, reserved for future grid-snapping)
        font_scale: font size for labels (default 0.45)

    Returns:
        Image with bounding boxes, class labels, and confidence scores drawn.
    """
    display = image.copy()
    # black stones: green box, white stones: orange box
    colors = {0: (0, 200, 0), 1: (0, 140, 255)}

    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det.bbox]
        color = colors.get(det.class_id, (128, 128, 128))
        cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)

        label = f"{det.class_name} {det.confidence:.2f}"
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        # Draw label background
        cv2.rectangle(display, (x1, y1 - th - baseline - 4), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            display, label, (x1 + 2, y1 - baseline - 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1
        )

    return display


def draw_detection_overlay(
    frame: np.ndarray,
    corners: list[tuple[int, int]],
    transform_matrix: np.ndarray,
    warp_size: tuple[int, int],
    config: BoardConfig,
) -> np.ndarray:
    """Draw detection boundary + projected grid points on the original camera image.

    Args:
        frame: original BGR image
        corners: detected corners from _sort_corner [TL, TR, BR, BL]
        transform_matrix: perspective transform M (warped = M * raw)
        warp_size: (width, height) of the warped image
        config: BoardConfig
    """
    display = frame.copy()

    # Draw cyan quadrilateral boundary
    pts = np.array(corners, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(display, [pts], isClosed=True, color=(255, 255, 0), thickness=2)

    # Label corners
    labels = ["TL", "TR", "BR", "BL"]
    for i, (cx, cy) in enumerate(corners):
        cv2.putText(display, labels[i], (cx + 10, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # Back-project grid points from warped space to raw image space
    if transform_matrix is not None and warp_size is not None:
        w, h = warp_size
        M_inv = np.linalg.inv(transform_matrix)

        gs = config.grid_size
        warped_pts = []
        for row in range(gs):
            for col in range(gs):
                px, py = grid_to_pixel(col, row, w, h, config)
                warped_pts.append([px, py])

        warped_pts = np.array(warped_pts, dtype=np.float32).reshape(-1, 1, 2)
        raw_pts = cv2.perspectiveTransform(warped_pts, M_inv)

        for pt in raw_pts:
            x, y = int(pt[0][0]), int(pt[0][1])
            cv2.circle(display, (x, y), 3, (0, 255, 0), -1)

    return display


def draw_camera_inference_overlay(
    frame: np.ndarray,
    corners: list[tuple[int, int]],
    transform_matrix: np.ndarray,
    warp_size: tuple[int, int],
    detections: list[Detection],
    config: BoardConfig,
    font_scale: float = 0.3,
) -> np.ndarray:
    """Draw board boundary, grid, and back-projected stone detections on original camera frame.

    Args:
        frame: original BGR camera image
        corners: detected corners in camera space [TR, TL, BL, BR]
        transform_matrix: perspective transform M (warped = M * raw)
        warp_size: (width, height) of the warped image
        detections: YOLO detections with coordinates in warped image space
        config: BoardConfig
        font_scale: font size for labels (default 0.3)
    """
    display = frame.copy()
    colors = {0: (0, 200, 0), 1: (0, 140, 255)}  # black→green, white→orange

    # Draw cyan quadrilateral boundary
    pts = np.array(corners, dtype=np.int32).reshape((-1, 1, 2))
    cv2.polylines(display, [pts], isClosed=True, color=(255, 255, 0), thickness=2)

    if transform_matrix is not None and warp_size is not None:
        w, h = warp_size
        M_inv = np.linalg.inv(transform_matrix)

        # Back-project grid intersections
        gs = config.grid_size
        warped_pts = []
        for row in range(gs):
            for col in range(gs):
                px, py = grid_to_pixel(col, row, w, h, config)
                warped_pts.append([px, py])
        warped_pts = np.array(warped_pts, dtype=np.float32).reshape(-1, 1, 2)
        raw_pts = cv2.perspectiveTransform(warped_pts, M_inv)
        for pt in raw_pts:
            x, y = int(pt[0][0]), int(pt[0][1])
            cv2.circle(display, (x, y), 2, (0, 255, 0), -1)

        # Back-project stone detections
        if detections:
            det_pts = np.array([[det.x_center, det.y_center] for det in detections], dtype=np.float32).reshape(-1, 1, 2)
            raw_det_pts = cv2.perspectiveTransform(det_pts, M_inv)

            for i, det in enumerate(detections):
                rx, ry = int(raw_det_pts[i][0][0]), int(raw_det_pts[i][0][1])
                color = colors.get(det.class_id, (128, 128, 128))
                cv2.circle(display, (rx, ry), 8, color, -1)
                cv2.circle(display, (rx, ry), 8, (0, 0, 0), 1)  # outline

                abbrev = "B" if det.class_id == 0 else "W"
                label = f"{abbrev} .{int(det.confidence * 100):02d}"
                cv2.putText(display, label, (rx + 10, ry - 5), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1)

    # Stone counts top-left
    black_count = sum(1 for d in detections if d.class_id == 0)
    white_count = sum(1 for d in detections if d.class_id == 1)
    cv2.putText(display, f"B:{black_count} W:{white_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    return display


def draw_debug_overlay(frame: np.ndarray, finder: BoardFinder, use_clahe: bool, min_threshold: int) -> np.ndarray:
    """Draw debug visualization on the raw camera frame."""
    display = frame.copy()
    h, w = display.shape[:2]

    # Preprocessing (same as find_focus)
    processed = display.copy()
    if use_clahe:
        lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        lab = cv2.merge([l_ch, a_ch, b_ch])
        processed = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

    method = "None"

    # ArUco detection overlay
    if finder.marker_ids is not None and finder.aruco_dict is not None:
        detector = cv2.aruco.ArucoDetector(finder.aruco_dict, finder.aruco_params)
        marker_corners, marker_ids, _ = detector.detectMarkers(gray)
        if marker_ids is not None and len(marker_ids) > 0:
            cv2.aruco.drawDetectedMarkers(display, marker_corners, marker_ids)
            # Check if all required markers found
            found_ids = set(marker_ids.flatten())
            required_ids = set(finder.marker_ids)
            if required_ids.issubset(found_ids):
                method = "ArUco"
                # Draw inner corners
                corners = finder._detect_aruco(gray)
                if corners is not None:
                    for i, (cx, cy) in enumerate(corners):
                        cv2.circle(display, (cx, cy), 8, (0, 0, 255), 2)
                        cv2.putText(
                            display,
                            f"C{i}",
                            (cx + 10, cy - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 0, 255),
                            1,
                        )

    # Canny contour overlay (always show for debug)
    blurred = cv2.GaussianBlur(processed, (3, 3), 0, 0)
    canny = cv2.Canny(blurred, min_threshold, 250)
    k = np.ones((3, 3), np.uint8)
    canny = cv2.morphologyEx(canny, cv2.MORPH_CLOSE, k)
    contours, _ = cv2.findContours(canny, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    for i, contour in enumerate(contours):
        color = (0, 255, 0) if i == 0 else (0, 180, 0)
        cv2.drawContours(display, [contour], -1, color, 2)
        perimeter = cv2.arcLength(contour, True)
        epsilon = 0.02 * perimeter
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) == 4 and method == "None":
            method = "Canny"
            for pt in approx:
                cv2.circle(display, (pt[0][0], pt[0][1]), 8, (0, 0, 255), 2)

    # Status text
    stable = not finder.is_first
    cv2.putText(display, f"Method: {method}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(
        display, f"Stable: {'Yes' if stable else 'Init'}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2
    )
    cv2.putText(
        display, f"CLAHE: {'ON' if use_clahe else 'OFF'}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2
    )

    return display


def main():
    parser = argparse.ArgumentParser(description="Show 19x19 grid overlay on detected board")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--use-clahe", action="store_true")
    parser.add_argument("--canny-min", type=int, default=20)
    parser.add_argument("--calibration", type=str, default=None)
    parser.add_argument("--marker-ids", type=int, nargs=4, default=None, help="4 ArUco marker IDs: TL TR BR BL")
    parser.add_argument("--debug", action="store_true", help="Show debug overlay with contours and markers")
    args = parser.parse_args()

    camera_config = None
    if args.calibration:
        from katrain.vision.config import CameraConfig

        data = np.load(args.calibration)
        camera_config = CameraConfig(camera_matrix=data["camera_matrix"], dist_coeffs=data["dist_coeffs"])

    config = BoardConfig()
    finder = BoardFinder(camera_config=camera_config, marker_ids=args.marker_ids)
    use_clahe = args.use_clahe
    debug = args.debug

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"Error: cannot open camera {args.camera}")
        return

    print("Q = quit | C = toggle CLAHE | S = save screenshot | D = toggle debug")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        warped, found = finder.find_focus(frame, min_threshold=args.canny_min, use_clahe=use_clahe)

        if found and warped is not None:
            grid_img = draw_grid(warped, config)
            h, w = grid_img.shape[:2]
            cv2.putText(grid_img, f"{w}x{h}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("Grid Overlay", grid_img)
        else:
            cv2.putText(frame, "Board not detected", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        if debug:
            debug_frame = draw_debug_overlay(frame, finder, use_clahe, args.canny_min)
            cv2.imshow("Debug", debug_frame)
        elif found and finder.last_transform_matrix is not None:
            detection_frame = draw_detection_overlay(
                frame, finder.pre_corner_point, finder.last_transform_matrix, finder.last_warp_size, config
            )
            cv2.imshow("Camera", detection_frame)
        else:
            cv2.imshow("Camera", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("c"):
            use_clahe = not use_clahe
            print(f"CLAHE: {'ON' if use_clahe else 'OFF'}")
        elif key == ord("d"):
            debug = not debug
            print(f"Debug: {'ON' if debug else 'OFF'}")
            if not debug:
                cv2.destroyWindow("Debug")
            else:
                cv2.destroyWindow("Camera")
        elif key == ord("s") and found and warped is not None:
            cv2.imwrite("grid_screenshot.jpg", draw_grid(warped, config))
            print("Saved grid_screenshot.jpg")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
