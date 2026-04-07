"""Server-side viewport calculation for read-only board display.

Computes the minimal viewport (quarter, half, or full board) that contains
all stones, labels, letters, and shapes. The viewport boundary always includes
the star points (hoshi) at the edge for visual context.
"""

from typing import Dict, Optional, Set, Tuple


def _occupied_positions(payload: Dict) -> Set[Tuple[int, int]]:
    """Extract all occupied positions from a board_payload."""
    positions: Set[Tuple[int, int]] = set()
    stones = payload.get("stones", {})
    for coords in stones.values():
        for col, row in coords:
            positions.add((col, row))
    for key in ("labels", "letters", "shapes"):
        mapping = payload.get(key, {})
        if mapping:
            for coord_str in mapping:
                parts = coord_str.split(",")
                if len(parts) == 2:
                    positions.add((int(parts[0]), int(parts[1])))
    highlights = payload.get("highlights") or []
    for col, row in highlights:
        positions.add((col, row))
    return positions


def compute_viewport(payload: Dict) -> Optional[Dict]:
    """Compute the optimal viewport for a board_payload.

    Returns a viewport dict or None for full board.
    Quarter: {col, row, size} (10x10)
    Half: {col, row, cols, rows} (rectangular)
    Full: None
    """
    size = payload.get("size", 19)
    if size != 19:
        return None  # non-19x19 boards: show full

    positions = _occupied_positions(payload)
    if not positions:
        return None  # empty board: show full

    mid = 9  # center of 19x19

    # Determine which quadrants are occupied
    has_tl = any(c <= mid and r <= mid for c, r in positions)
    has_tr = any(c >= mid and r <= mid for c, r in positions)
    has_bl = any(c <= mid and r >= mid for c, r in positions)
    has_br = any(c >= mid and r >= mid for c, r in positions)

    quadrant_count = sum([has_tl, has_tr, has_bl, has_br])

    # Quarter board: only one quadrant occupied
    if quadrant_count == 1:
        if has_tl:
            return {"col": 0, "row": 0, "size": 10}
        if has_tr:
            return {"col": 9, "row": 0, "size": 10}
        if has_bl:
            return {"col": 0, "row": 9, "size": 10}
        if has_br:
            return {"col": 9, "row": 9, "size": 10}

    # Half board: two adjacent quadrants — use rectangular viewport
    if quadrant_count == 2:
        if has_tl and has_tr and not has_bl and not has_br:
            return {"col": 0, "row": 0, "cols": 19, "rows": 10}   # top half
        if has_bl and has_br and not has_tl and not has_tr:
            return {"col": 0, "row": 9, "cols": 19, "rows": 10}   # bottom half
        if has_tl and has_bl and not has_tr and not has_br:
            return {"col": 0, "row": 0, "cols": 10, "rows": 19}   # left half
        if has_tr and has_br and not has_tl and not has_bl:
            return {"col": 9, "row": 0, "cols": 10, "rows": 19}   # right half

    # 3 or 4 quadrants, or diagonal: full board
    return None
