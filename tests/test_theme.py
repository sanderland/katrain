from katrain.gui.theme import Theme


def test_move_numbers_contrast_with_the_stone_color():
    assert Theme.MOVE_NUMBER_COLORS == {"B": [1, 1, 1, 1], "W": [0, 0, 0, 1]}
