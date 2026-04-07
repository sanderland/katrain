"""OCR module for reading digits, letters, and shapes from Go board intersection patches.

Step 2 of the two-step classification pipeline:
  Step 1 (EfficientNet-B0, separate module) classifies patches into coarse categories:
         black, white, black_numbered, white_numbered, marked_black, marked_white, letter, empty
  Step 2 (THIS MODULE) reads the actual content from patches that carry information:
         move numbers (1-200), letter annotations (A-Z), shape marks (triangle/square/circle)

Patches are small (~38-40px) grayscale crops of individual Go board intersections.
"""

import logging
from typing import Optional

import cv2
import numpy as np

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class PatchOCR:
    """Reads digits, letters, and shape marks from small grayscale Go board patches.

    All public methods accept a single-channel (grayscale) uint8 numpy array
    and return the decoded value or ``None`` when recognition fails.
    """

    # ── Number reading ───────────────────────────────────────────────────

    def read_number(self, patch: np.ndarray, stone_color: str) -> Optional[int]:
        """Read a move number (1-200) from a numbered stone patch.

        Args:
            patch: Grayscale uint8 image of the intersection crop.
            stone_color: ``"black"`` (white digits on dark bg) or ``"white"``
                         (dark digits on light bg).

        Returns:
            Integer move number in [1, 200], or ``None`` on failure.
        """
        if pytesseract is None:
            log.warning("pytesseract is not installed -- cannot read numbers")
            return None

        digit_region = self._extract_digit_region(patch, stone_color)
        if digit_region is None:
            return None

        text = pytesseract.image_to_string(
            digit_region,
            config="--psm 8 -c tessedit_char_whitelist=0123456789",
        ).strip()

        if text.isdigit():
            value = int(text)
            if 1 <= value <= 200:
                return value
        return None

    # ── Letter reading ───────────────────────────────────────────────────

    def read_letter(self, patch: np.ndarray) -> Optional[str]:
        """Read a letter annotation (A-Z) from an empty intersection patch.

        Letters sit at intersections on an otherwise empty board, so the
        grid cross-lines running through the center must be masked out
        before thresholding.

        Args:
            patch: Grayscale uint8 image of the intersection crop.

        Returns:
            Single uppercase letter A-Z, or ``None`` on failure.
        """
        if pytesseract is None:
            log.warning("pytesseract is not installed -- cannot read letters")
            return None

        letter_region = self._extract_letter_region(patch)
        if letter_region is None:
            return None

        text = pytesseract.image_to_string(
            letter_region,
            config="--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        ).strip()

        if text and text[0].isalpha():
            return text[0].upper()
        return None

    # ── Shape reading ────────────────────────────────────────────────────

    def read_shape(self, patch: np.ndarray, stone_color: str) -> Optional[str]:
        """Detect a shape mark (triangle, square, circle) on a marked stone.

        Uses contour analysis and polygon approximation rather than OCR.

        Args:
            patch: Grayscale uint8 image of the intersection crop.
            stone_color: ``"black"`` or ``"white"``.

        Returns:
            One of ``"triangle"``, ``"square"``, ``"circle"``, or ``None``.
        """
        h, w = patch.shape[:2]
        if h < 8 or w < 8:
            return None

        # ── isolate the shape mark inside the stone ─────────────────────
        r = min(h, w) // 2 - 2
        if stone_color == "white":
            r = max(r - 2, min(h, w) // 4)  # tighter mask to avoid dark border outline
        cy, cx = h // 2, w // 2

        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(mask, (cx, cy), max(r, 1), 255, -1)

        masked = cv2.bitwise_and(patch, patch, mask=mask)

        if stone_color == "black":
            # White/bright shape marks on dark stone -- invert so marks become dark
            processed = 255 - masked
        else:
            processed = masked.copy()

        thresh = cv2.adaptiveThreshold(
            processed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, blockSize=11, C=2
        )
        # Zero anything outside the circular mask
        thresh = cv2.bitwise_and(thresh, thresh, mask=mask)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        patch_area = h * w
        best_shape: Optional[str] = None
        best_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 20 or area > patch_area * 0.5:
                continue
            if area <= best_area:
                continue

            perimeter = cv2.arcLength(cnt, True)
            if perimeter < 1e-6:
                continue

            approx = cv2.approxPolyDP(cnt, 0.04 * perimeter, True)
            num_vertices = len(approx)

            circularity = (4.0 * np.pi * area) / (perimeter * perimeter)

            if num_vertices == 3:
                best_shape = "triangle"
                best_area = area
            elif num_vertices == 4:
                best_shape = "square"
                best_area = area
            elif num_vertices > 6 and circularity > 0.6:
                best_shape = "circle"
                best_area = area

        return best_shape

    # ── Internal helpers ─────────────────────────────────────────────────

    def _extract_digit_region(self, patch: np.ndarray, stone_color: str) -> Optional[np.ndarray]:
        """Pre-process a numbered stone patch and return a clean digit image.

        Strategy differs by stone colour:
        - **Black**: circle mask → invert → Otsu → morphological opening to
          remove arc-edge noise → connected-component area filter.
        - **White**: detect circle via ``minEnclosingCircle``, force everything
          outside the circle to white, erase the border ring (70-100% radius
          annulus), then Otsu on the interior.

        Both paths upscale to 384 px first and produce a binary image with
        dark text on a white background, padded for OCR.
        """
        h, w = patch.shape[:2]
        if h < 8 or w < 8:
            return None

        scale = 384
        up = cv2.resize(patch, (scale, scale), interpolation=cv2.INTER_CUBIC)

        if stone_color == "black":
            return self._extract_digit_black(up, scale)
        return self._extract_digit_white(up, scale)

    def _extract_digit_black(self, up: np.ndarray, scale: int) -> Optional[np.ndarray]:
        """Extract digits from a black numbered stone (white digits on dark fill)."""
        # Detect the stone circle
        _, stone_mask = cv2.threshold(up, 100, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(stone_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        largest = max(contours, key=cv2.contourArea)
        (cx, cy), radius = cv2.minEnclosingCircle(largest)

        # Tight circle mask (78 %) to cut off edge artifacts
        mask = np.zeros((scale, scale), dtype=np.uint8)
        cv2.circle(mask, (int(cx), int(cy)), int(radius * 0.78), 255, -1)

        # Invert: white digits → dark on white
        inverted = 255 - up
        inverted[mask == 0] = 255

        # Otsu binarisation
        _, binary = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        binary[mask == 0] = 255

        # Morphological opening removes thin arc-edge noise while
        # preserving thicker digit strokes
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg = 255 - binary  # foreground = white for morphology
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel)
        binary = 255 - fg

        # Remove small connected components (< 5 % of total foreground)
        fg_inv = 255 - binary
        n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(fg_inv, connectivity=8)
        total_fg = np.sum(stats[1:, cv2.CC_STAT_AREA]) if n_labels > 1 else 1
        min_area = max(50, int(total_fg * 0.05))
        for i in range(1, n_labels):
            if stats[i, cv2.CC_STAT_AREA] < min_area:
                binary[labels == i] = 255

        return cv2.copyMakeBorder(binary, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)

    def _extract_digit_white(self, up: np.ndarray, scale: int) -> Optional[np.ndarray]:
        """Extract digits from a white numbered stone (dark digits on light fill)."""
        # Detect the outer stone circle via its dark border
        _, dark_mask = cv2.threshold(up, 128, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(dark_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        largest = max(contours, key=cv2.contourArea)
        (cx, cy), outer_r = cv2.minEnclosingCircle(largest)
        cx_i, cy_i = int(cx), int(cy)

        # Full circle mask — everything outside → white
        circle_mask = np.zeros((scale, scale), dtype=np.uint8)
        cv2.circle(circle_mask, (cx_i, cy_i), int(outer_r), 255, -1)

        result = up.copy()
        result[circle_mask == 0] = 255

        # Erase the border ring (70-100 % radius annulus) → white
        inner_r = int(outer_r * 0.70)
        ring_inner = np.zeros((scale, scale), dtype=np.uint8)
        cv2.circle(ring_inner, (cx_i, cy_i), inner_r, 255, -1)
        ring_only = cv2.bitwise_and(circle_mask, cv2.bitwise_not(ring_inner))
        result[ring_only > 0] = 255

        # Otsu binarisation on the cleaned interior
        _, binary = cv2.threshold(result, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Polarity check — digits must be dark-on-white.  If the inner
        # region is majority dark after Otsu, the threshold inverted it.
        inner_pixels = binary[ring_inner > 0]
        if inner_pixels.size > 0 and np.mean(inner_pixels < 128) > 0.5:
            binary = 255 - binary

        binary[circle_mask == 0] = 255

        return cv2.copyMakeBorder(binary, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)

    def _extract_letter_region(self, patch: np.ndarray) -> Optional[np.ndarray]:
        """Pre-process a letter-annotated intersection and return a clean letter image.

        Grid cross-lines (horizontal + vertical through center) are masked
        out so they do not confuse OCR.
        """
        h, w = patch.shape[:2]
        if h < 8 or w < 8:
            return None

        working = patch.copy()

        # ── mask out grid cross-lines through the center (~3px wide) ────
        cy, cx = h // 2, w // 2
        line_half_width = max(1, min(h, w) // 12)  # ~1-2px each side of center
        # Horizontal line
        working[max(0, cy - line_half_width) : min(h, cy + line_half_width + 1), :] = 255
        # Vertical line
        working[:, max(0, cx - line_half_width) : min(w, cx + line_half_width + 1)] = 255

        # ── adaptive threshold ───────────────────────────────────────
        thresh = cv2.adaptiveThreshold(
            working, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, blockSize=11, C=2
        )

        # ── find letter contours ─────────────────────────────────────
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        patch_area = h * w
        valid_contours = [c for c in contours if 20 < cv2.contourArea(c) < patch_area * 0.5]
        if not valid_contours:
            return None

        all_points = np.concatenate(valid_contours)
        x, y, bw, bh = cv2.boundingRect(all_points)

        pad = max(2, int(0.1 * max(bw, bh)))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + bw + pad)
        y2 = min(h, y + bh + pad)

        letter_crop = thresh[y1:y2, x1:x2]
        if letter_crop.size == 0:
            return None

        return self._pad_and_resize(letter_crop, target_size=96)

    @staticmethod
    def _pad_and_resize(binary_crop: np.ndarray, target_size: int = 96) -> np.ndarray:
        """Pad a binary image to a square and resize to ``target_size x target_size``.

        The padding colour is black (0) which matches the background of the
        BINARY_INV threshold output (foreground = white, background = black).
        After resizing the image is inverted so the result has dark text on a
        white background -- the format pytesseract expects.
        """
        ch, cw = binary_crop.shape[:2]
        side = max(ch, cw)
        # Add generous border so characters are not flush against the edge
        border = max(4, side // 4)
        canvas_size = side + 2 * border
        canvas = np.zeros((canvas_size, canvas_size), dtype=np.uint8)

        y_off = (canvas_size - ch) // 2
        x_off = (canvas_size - cw) // 2
        canvas[y_off : y_off + ch, x_off : x_off + cw] = binary_crop

        resized = cv2.resize(canvas, (target_size, target_size), interpolation=cv2.INTER_LINEAR)

        # Invert: pytesseract expects dark text on white background
        return 255 - resized
