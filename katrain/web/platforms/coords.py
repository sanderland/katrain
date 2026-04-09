"""Coordinate translation utilities for cross-platform play.

KaTrain uses 0-indexed (col, row) from top-left.
SGF uses 'ab' letter pairs (a=0, b=1, ...).
GTP uses 'D4' notation (skips I, row counted from bottom).
OGS uses same encoding as SGF (a=0, b=1, ..., does NOT skip 'i').
"""


def katrain_to_sgf(col: int, row: int) -> str:
    """KaTrain 0-indexed (col, row) from top-left -> SGF 'ab' format."""
    return chr(ord("a") + col) + chr(ord("a") + row)


def sgf_to_katrain(sgf_move: str) -> tuple[int, int]:
    """SGF 'ab' -> KaTrain (col, row)."""
    return (ord(sgf_move[0]) - ord("a"), ord(sgf_move[1]) - ord("a"))


def katrain_to_gtp(col: int, row: int, board_size: int = 19) -> str:
    """KaTrain (col, row) -> GTP 'D4' format (skip I, row from bottom)."""
    gtp_col = chr(ord("A") + col + (1 if col >= 8 else 0))
    gtp_row = board_size - row
    return f"{gtp_col}{gtp_row}"


def gtp_to_katrain(gtp_move: str, board_size: int = 19) -> tuple[int, int]:
    """GTP 'D4' -> KaTrain (col, row)."""
    col_char = gtp_move[0].upper()
    col = ord(col_char) - ord("A") - (1 if col_char > "I" else 0)
    row = board_size - int(gtp_move[1:])
    return (col, row)
