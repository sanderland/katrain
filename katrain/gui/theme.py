def to_hexcol(kivycol):
    return "#" + "".join(f"{round(c * 255):02x}" for c in kivycol[:3])


# basic colors
WHITE = [0.95, 0.95, 0.95, 1]
BLACK = [0.05, 0.05, 0.05, 1]
LIGHT_GREY = [0.7, 0.7, 0.7, 1]
GREY = [0.5, 0.5, 0.5, 1]
LIGHTER_GREY = [0.85, 0.85, 0.85, 1]
RED = [0.8, 0.1, 0.1, 1]
GREEN = [0.1, 0.8, 0.1, 1]
YELLOW = [0.8, 0.8, 0.1, 1]
ORANGE = [242 / 255, 96 / 255, 34 / 255, 1]
LIGHT_ORANGE = [1, 0.5, 0.25, 1]
BLUE = [0.3, 0.7, 0.9, 1]


class Theme:
    # font
    DEFAULT_FONT = "NotoSansCJKsc-Regular.otf"
    INPUT_FONT_SIZE = 25  # sp
    DESC_FONT_SIZE = 20  # sp
    NOTES_FONT_SIZE = 18  # sp

    # gui colors
    BACKGROUND_COLOR = [36 / 255, 48 / 255, 62 / 255, 1]
    BOX_BACKGROUND_COLOR = [46 / 255, 65 / 255, 88 / 255, 1]
    LIGHTER_BACKGROUND_COLOR = [64 / 255, 85 / 255, 110 / 255, 1]
    SCROLLBAR_COLOR = LIGHT_GREY
    TEXT_COLOR = WHITE
    SCORE_COLOR = BLUE  # blue
    WINRATE_COLOR = GREEN  # green
    POINTLOSS_COLOR = YELLOW  # yellow
    BUTTON_INACTIVE_COLOR = LIGHT_GREY
    BUTTON_BORDER_COLOR = WHITE
    BUTTON_TEXT_COLOR = WHITE
    PAUSE_ACTIVE_COLOR = ORANGE
    TIMER_TEXT_COLOR = GREEN
    TIMER_TEXT_TIMEOUT_COLOR = ORANGE
    CIRCLE_TEXT_COLORS = {"W": BLACK, "B": WHITE}
    NOTES_TAB_FONT_COLOR = YELLOW
    INFO_TAB_FONT_COLOR = WHITE
    ERROR_BORDER_COLOR = RED
    MENU_ITEM_FONT_COLOR = WHITE
    MENU_ITEM_SHORTCUT_COLOR = LIGHT_GREY
    PLAY_ANALYZE_TAB_COLOR = YELLOW
    INPUT_FONT_COLOR = WHITE
    MISTAKE_BUTTON_COLOR = [0.79, 0.06, 0.06, 1]

    # gui spacing
    RIGHT_PANEL_ASPECT_RATIO = 0.4  # W/H
    CONTROLS_PANEL_ASPECT_RATIO = 13.5  # W/H
    CONTROLS_PANEL_MIN_HEIGHT = 50
    CONTROLS_PANEL_MAX_HEIGHT = 75  # dp
    CP_SPACING = 6
    CP_SMALL_SPACING = 3
    CP_PADDING = 6

    # textures
    STONE_TEXTURE = {"B": "B_stone.png", "W": "W_stone.png"}
    EVAL_DOT_TEXTURE = "dot.png"
    LAST_MOVE_TEXTURE = "inner.png"
    TOP_MOVE_TEXTURE = "topmove.png"
    BOARD_TEXTURE = "board.png"
    GRAPH_TEXTURE = "graph_bg.png"
    # sounds
    STONE_SOUNDS = [f"stone{i}.wav" for i in [1, 2, 3, 4, 5]]
    COUNTDOWN_SOUND = "countdownbeep.wav"
    MINIMUM_TIME_PASSED_SOUND = "boing.wav"

    # eval dots
    EVAL_COLORS = {
        "theme:normal": [
            [0.447, 0.129, 0.42, 1],
            [0.8, 0, 0, 1],
            [0.9, 0.4, 0.1, 1],
            [0.95, 0.95, 0, 1],
            [0.67, 0.9, 0.18, 1],
            [0.117, 0.588, 0, 1],
        ],
        "theme:red-green-colourblind": [
            [1, 0, 1, 1],
            [1, 0, 0, 1],
            [1, 0.5, 0, 1],
            [1, 1, 0, 1],
            [0, 1, 1, 1],
            [0, 0, 1, 1],
        ],
    }

    EVAL_DOT_MAX_SIZE = 0.5
    EVAL_DOT_MIN_SIZE = 0.25

    # board theme
    APPROX_BOARD_COLOR = [0.95, 0.75, 0.47, 1]  # for drawing on top of / hiding what's under it
    BOARD_COLOR_TINT = [1, 0.95, 0.8, 1]  # multiplied by texture

    HINT_TEXT_COLOR = BLACK

    REGION_BORDER_COLOR = LIGHTER_BACKGROUND_COLOR
    INSERT_BOARD_COLOR_TINT = [1, 1, 1, 0.75]
    PASS_CIRCLE_COLOR = [0.45, 0.05, 0.45, 0.7]
    PASS_CIRCLE_TEXT_COLOR = [0.85, 0.85, 0.85]

    STONE_COLORS = {"B": BLACK, "W": WHITE}
    NEXT_MOVE_DASH_CONTRAST_COLORS = {"B": LIGHTER_GREY, "W": GREY}
    OUTLINE_COLORS = {"B": [0.3, 0.3, 0.3, 0.5], "W": [0.7, 0.7, 0.7, 0.5]}
    PV_TEXT_COLORS = {"W": BLACK, "B": WHITE}  # numbers in PV

    # board
    LINE_COLOR = [0, 0, 0]
    STARPOINT_SIZE = 0.1
    BOARD_COLOR = [0.85, 0.68, 0.40, 1]
    STONE_SIZE = 0.505  # texture edge is transparent

    GHOST_ALPHA = 0.6
    POLICY_ALPHA = 0.5

    HINTS_LO_ALPHA = 0.6
    HINTS_ALPHA = 0.8
    TOP_MOVE_BORDER_COLOR = [10 / 255, 200 / 255, 250 / 255, 1.0]
    CHILD_SCALE = 0.95
    HINT_SCALE = 0.98
    UNCERTAIN_HINT_SCALE = 0.7

    # ponder light
    ENGINE_DOWN_COLOR = EVAL_COLORS["theme:normal"][1]
    ENGINE_BUSY_COLOR = EVAL_COLORS["theme:normal"][2]
    ENGINE_READY_COLOR = EVAL_COLORS["theme:normal"][-1]
    ENGINE_PONDERING_COLOR = YELLOW

    # info PV link
    INFO_PV_COLOR = to_hexcol(YELLOW)

    # graph
    GRAPH_DOT_COLOR = [0.85, 0.3, 0.3, 1]
    WINRATE_MARKER_COLOR = [0.05, 0.7, 0.05, 1]
    SCORE_MARKER_COLOR = [0.2, 0.6, 0.8, 1]

    # move tree
    MOVE_TREE_LINE = LIGHT_GREY
    MOVE_TREE_CURRENT = YELLOW
    MOVE_TREE_SELECTED = RED
    MOVE_TREE_INSERT_NODE_PARENT = GREEN
    MOVE_TREE_INSERT_CURRENT = ORANGE
    MOVE_TREE_INSERT_OTHER = LIGHT_ORANGE
    MOVE_TREE_COLLAPSED = LIGHT_GREY
    MOVE_TREE_STONE_OUTLINE_COLORS = {"W": BLACK, "B": WHITE}
