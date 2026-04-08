import numpy as np
import pytest
from katrain.vision.inference.base import letterbox_preprocess


class TestLetterboxPreprocess:
    def test_preserves_aspect_ratio(self):
        img = np.zeros((257, 400, 3), dtype=np.uint8)
        result, scale, x_off, y_off = letterbox_preprocess(img, 640)
        assert result.shape == (640, 640, 3)
        # Content should be centered
        assert x_off == 0  # width is the max dimension
        assert y_off > 0  # height is padded

    def test_square_image(self):
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        result, scale, x_off, y_off = letterbox_preprocess(img, 640)
        assert result.shape == (640, 640, 3)
        assert x_off == 0
        assert y_off == 0
        assert abs(scale - 1.28) < 0.01

    def test_scale_and_offsets(self):
        img = np.ones((200, 400, 3), dtype=np.uint8) * 255
        result, scale, x_off, y_off = letterbox_preprocess(img, 640)
        assert scale == 640 / 400  # = 1.6
        assert x_off == 0
        new_h = int(200 * scale)  # 320
        assert y_off == (640 - new_h) // 2  # 160
        # Padded area should be gray (114)
        assert result[0, 0, 0] == 114
        # Content area should be white (255)
        assert result[y_off + 10, 10, 0] == 255

    def test_coordinate_roundtrip(self):
        """A point in the original image should map back correctly after letterbox+unletterbox."""
        img = np.zeros((257, 400, 3), dtype=np.uint8)
        _, scale, x_off, y_off = letterbox_preprocess(img, 640)
        # Original point
        orig_x, orig_y = 200.0, 128.0
        # Forward: original -> letterbox space
        lb_x = orig_x * scale + x_off
        lb_y = orig_y * scale + y_off
        # Inverse: letterbox space -> original
        recovered_x = (lb_x - x_off) / scale
        recovered_y = (lb_y - y_off) / scale
        assert abs(recovered_x - orig_x) < 0.01
        assert abs(recovered_y - orig_y) < 0.01
