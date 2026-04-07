from katrain.web.tutorials.viewport import compute_viewport


def test_empty_board_returns_none():
    payload = {"size": 19, "stones": {"B": [], "W": []}}
    assert compute_viewport(payload) is None


def test_single_corner_tl():
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[2, 4]]}, "labels": {"3,3": "1", "2,4": "2"}}
    vp = compute_viewport(payload)
    assert vp is not None
    assert vp["col"] == 0 and vp["row"] == 0 and vp["size"] == 10


def test_single_corner_br():
    payload = {"size": 19, "stones": {"B": [[15, 15]], "W": [[16, 14]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp is not None
    assert vp["col"] == 9 and vp["row"] == 9 and vp["size"] == 10


def test_all_quadrants_returns_none():
    payload = {"size": 19, "stones": {"B": [[3, 3], [15, 15]], "W": [[3, 15], [15, 3]]}, "labels": {}}
    assert compute_viewport(payload) is None


def test_includes_letters_and_shapes():
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": []},
               "letters": {"5,5": "A"}, "shapes": {"4,4": "triangle"}}
    vp = compute_viewport(payload)
    assert vp is not None
    assert vp["col"] == 0 and vp["row"] == 0  # all in TL


def test_non_19_returns_none():
    payload = {"size": 13, "stones": {"B": [[3, 3]], "W": []}}
    assert compute_viewport(payload) is None


def test_top_half():
    """Stones in TL and TR → top half (19 wide, 10 tall)."""
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[15, 3]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 0, "row": 0, "cols": 19, "rows": 10}


def test_bottom_half():
    payload = {"size": 19, "stones": {"B": [[3, 15]], "W": [[15, 15]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 0, "row": 9, "cols": 19, "rows": 10}


def test_left_half():
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[3, 15]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 0, "row": 0, "cols": 10, "rows": 19}


def test_right_half():
    payload = {"size": 19, "stones": {"B": [[15, 3]], "W": [[15, 15]]}, "labels": {}}
    vp = compute_viewport(payload)
    assert vp == {"col": 9, "row": 0, "cols": 10, "rows": 19}


def test_diagonal_returns_none():
    """Stones in TL and BR (diagonal) → full board."""
    payload = {"size": 19, "stones": {"B": [[3, 3]], "W": [[15, 15]]}, "labels": {}}
    assert compute_viewport(payload) is None
