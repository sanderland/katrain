"""Coordinate translation roundtrip tests."""

import pytest

from katrain.web.platforms.coords import (
    gtp_to_katrain,
    katrain_to_gtp,
    katrain_to_sgf,
    sgf_to_katrain,
)


class TestSGFConversion:
    def test_top_left(self):
        assert katrain_to_sgf(0, 0) == "aa"

    def test_bottom_right_19(self):
        assert katrain_to_sgf(18, 18) == "ss"

    def test_center_19(self):
        # tengen on 19x19: (9, 9)
        assert katrain_to_sgf(9, 9) == "jj"

    def test_roundtrip(self):
        for col in range(19):
            for row in range(19):
                sgf = katrain_to_sgf(col, row)
                c, r = sgf_to_katrain(sgf)
                assert (c, r) == (col, row), f"Roundtrip failed for ({col}, {row})"

    def test_9x9_roundtrip(self):
        for col in range(9):
            for row in range(9):
                sgf = katrain_to_sgf(col, row)
                c, r = sgf_to_katrain(sgf)
                assert (c, r) == (col, row)


class TestGTPConversion:
    def test_d4(self):
        # GTP D4 on 19x19 = col=3, row=15
        assert katrain_to_gtp(3, 15, 19) == "D4"

    def test_q16(self):
        # GTP Q16 on 19x19 = col=15, row=3
        assert katrain_to_gtp(15, 3, 19) == "Q16"

    def test_skip_i(self):
        # Column index 8 should give 'J' (skips I)
        result = katrain_to_gtp(8, 0, 19)
        assert result[0] == "J"

    def test_column_after_i(self):
        # Column index 9 should give 'K'
        result = katrain_to_gtp(9, 0, 19)
        assert result[0] == "K"

    def test_roundtrip(self):
        for col in range(19):
            for row in range(19):
                gtp = katrain_to_gtp(col, row, 19)
                c, r = gtp_to_katrain(gtp, 19)
                assert (c, r) == (col, row), f"Roundtrip failed for ({col}, {row}) -> {gtp}"

    def test_9x9_roundtrip(self):
        for col in range(9):
            for row in range(9):
                gtp = katrain_to_gtp(col, row, 9)
                c, r = gtp_to_katrain(gtp, 9)
                assert (c, r) == (col, row)

    def test_a1_bottom_left(self):
        # A1 = bottom-left = (0, 18) on 19x19
        assert katrain_to_gtp(0, 18, 19) == "A1"
        assert gtp_to_katrain("A1", 19) == (0, 18)

    def test_t19_top_right(self):
        # T19 = top-right = (18, 0) on 19x19
        assert katrain_to_gtp(18, 0, 19) == "T19"
        assert gtp_to_katrain("T19", 19) == (18, 0)


class TestCrossFormatConsistency:
    """Verify that SGF and GTP both map to the same KaTrain coordinates."""

    def test_known_point(self):
        # SGF "dd" = (3, 3) in KaTrain
        col, row = sgf_to_katrain("dd")
        assert (col, row) == (3, 3)
        # GTP equivalent for (3, 3) on 19x19 = D16
        assert katrain_to_gtp(col, row, 19) == "D16"
