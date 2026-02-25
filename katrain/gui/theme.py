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
    # --- typography ---
    DEFAULT_FONT = "NotoSansCJKsc-Regular.otf"
    FONT_SIZE_XS = 12  # shortcuts, badges
    FONT_SIZE_SM = 14  # secondary labels, stats values
    FONT_SIZE_MD = 16  # body text, form labels (base)
    FONT_SIZE_LG = 18  # section headers, player names
    FONT_SIZE_XL = 22  # popup titles, mode labels

    # legacy aliases (used throughout KV/popups)
    INPUT_FONT_SIZE = 16
    DESC_FONT_SIZE = 16
    NOTES_FONT_SIZE = 14

    # --- spacing ---
    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 12
    SPACING_LG = 16
    SPACING_XL = 24
    RADIUS_SM = 6
    RADIUS_MD = 10
    RADIUS_LG = 14

    # --- color palette (modern light) ---
    BACKGROUND_COLOR = [0.945, 0.945, 0.955, 1]  # warm off-white
    BOX_BACKGROUND_COLOR = [1.0, 1.0, 1.0, 1]  # pure white cards
    LIGHTER_BACKGROUND_COLOR = [0.96, 0.96, 0.97, 1]  # subtle light fill

    TEXT_COLOR = [0.12, 0.12, 0.14, 1]  # near-black text
    TEXT_SECONDARY_COLOR = [0.42, 0.42, 0.46, 1]  # medium grey
    TEXT_TERTIARY_COLOR = [0.58, 0.58, 0.62, 1]  # light grey
    BORDER_COLOR = [0.0, 0.0, 0.0, 0.08]  # subtle dividers

    SCROLLBAR_COLOR = [0.55, 0.55, 0.55, 0.35]

    # semantic / accent
    SCORE_COLOR = [0.18, 0.50, 0.72, 1]  # professional blue
    WINRATE_COLOR = [0.22, 0.62, 0.35, 1]  # forest green
    POINTLOSS_COLOR = [0.78, 0.60, 0.12, 1]  # warm amber
    ERROR_COLOR = [0.78, 0.22, 0.22, 1]
    WARNING_COLOR = [0.82, 0.52, 0.18, 1]
    SUCCESS_COLOR = [0.22, 0.65, 0.35, 1]

    # buttons
    BUTTON_INACTIVE_COLOR = [0.60, 0.60, 0.62, 1]
    BUTTON_BORDER_COLOR = [0, 0, 0, 0.10]
    BUTTON_TEXT_COLOR = [0.18, 0.18, 0.20, 1]
    PRIMARY_BUTTON_COLOR = [0.20, 0.48, 0.72, 1]
    MISTAKE_BUTTON_COLOR = [0.72, 0.20, 0.20, 1]

    # interactive states
    PAUSE_ACTIVE_COLOR = ORANGE
    TIMER_TEXT_COLOR = [0.22, 0.62, 0.35, 1]
    TIMER_TEXT_TIMEOUT_COLOR = ORANGE
    CHECKBOX_COLOR = [0.22, 0.50, 0.78, 1]

    # player / circle
    CIRCLE_TEXT_COLORS = {"W": BLACK, "B": WHITE}

    # tabs and panels
    NOTES_TAB_FONT_COLOR = [0.72, 0.56, 0.08, 1]
    INFO_TAB_FONT_COLOR = [0.18, 0.18, 0.20, 1]
    ERROR_BORDER_COLOR = [0.78, 0.22, 0.22, 1]
    PLAY_ANALYZE_TAB_COLOR = [0.22, 0.50, 0.78, 1]

    # menu
    MENU_ITEM_FONT_COLOR = [0.18, 0.18, 0.22, 1]
    MENU_ITEM_SHORTCUT_COLOR = [0.52, 0.52, 0.56, 1]

    # input
    INPUT_FONT_COLOR = [0.12, 0.12, 0.14, 1]

    # stats
    STAT_WORSE_COLOR = [0.78, 0.35, 0.18, 1]
    STAT_BETTER_COLOR = [0.22, 0.60, 0.22, 1]

    # --- gui spacing ---
    RIGHT_PANEL_ASPECT_RATIO = 0.32

    # --- textures ---
    STONE_TEXTURE = {"B": "B_stone.png", "W": "W_stone.png"}
    EVAL_DOT_TEXTURE = "dot.png"
    LAST_MOVE_TEXTURE = "inner.png"
    TOP_MOVE_TEXTURE = "topmove.png"
    BOARD_TEXTURE = "board.png"
    GRAPH_TEXTURE = "graph_bg.png"

    # --- sounds ---
    STONE_SOUNDS = [f"stone{i}.wav" for i in [1, 2, 3, 4, 5]]
    CAPTURING_SOUND = "capturing.wav"

    # --- eval dots ---
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

    # --- board theme ---
    APPROX_BOARD_COLOR = [0.95, 0.75, 0.47, 1]
    BOARD_COLOR_TINT = [1, 1, 1, 1]

    HINT_TEXT_COLOR = BLACK

    PASS_CIRCLE_COLOR = [0.45, 0.05, 0.45, 0.7]
    PASS_CIRCLE_TEXT_COLOR = [0.85, 0.85, 0.85]

    STONE_COLORS = {"B": BLACK, "W": WHITE}
    NUMBER_COLOR = [0.85, 0.68, 0.40, 0.8]

    NEXT_MOVE_DASH_CONTRAST_COLORS = {"B": LIGHTER_GREY, "W": GREY}
    OUTLINE_COLORS = {"B": [0.3, 0.3, 0.3, 0.5], "W": [0.7, 0.7, 0.7, 0.5]}
    PV_TEXT_COLORS = {"W": BLACK, "B": WHITE}

    LINE_COLOR = [0, 0, 0, 1]
    STARPOINT_SIZE = 0.1
    BOARD_COLOR = [0.85, 0.68, 0.40, 1]
    STONE_SIZE = 0.505

    GHOST_ALPHA = 0.6
    POLICY_ALPHA = 0.5
    OWNERSHIP_COLORS = {"B": [0.0, 0.0, 0.10, 0.75], "W": [0.92, 0.92, 1.0, 0.800]}
    OWNERSHIP_GAMMA = 1.33
    STONE_MIN_ALPHA = 0.85

    TERRITORY_DISPLAY = "blended"
    BLOCKS_THRESHOLD = 0.3
    STONE_MARKS = "weak"
    MARK_SIZE = 0.42

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
    ENGINE_PONDERING_COLOR = [0.78, 0.60, 0.12, 1]

    # info PV link
    INFO_PV_COLOR = to_hexcol([0.18, 0.50, 0.72, 1])

    # graph
    GRAPH_DOT_COLOR = [0.72, 0.28, 0.28, 1]
    WINRATE_MARKER_COLOR = [0.22, 0.62, 0.35, 1]
    SCORE_MARKER_COLOR = [0.18, 0.50, 0.72, 1]
    POINTLOSS_MARKER_COLOR = [0.78, 0.60, 0.12, 1]

    # move tree
    MOVE_TREE_LINE = [0.62, 0.62, 0.62, 1]
    MOVE_TREE_CURRENT = [0.22, 0.50, 0.78, 1]
    MOVE_TREE_SELECTED = [0.78, 0.35, 0.30, 1]
    MOVE_TREE_COLLAPSED = [0.62, 0.62, 0.62, 1]
    MOVE_TREE_STONE_OUTLINE_COLORS = {"W": BLACK, "B": WHITE}

    # --- keyboard shortcuts ---
    KEY_AI_MOVE = ["enter", "numpadenter"]
    KEY_PASS = "p"

    KEY_TEACHER_POPUP = "f6"
    KEY_AI_POPUP = "f7"
    KEY_CONFIG_POPUP = "f8"

    KEY_NEW_GAME = "n"
    KEY_SAVE_GAME = "s"
    KEY_SAVE_GAME_AS = "d"
    KEY_LOAD_GAME = "l"
    KEY_SUBMIT_POPUP = ["enter", "numpadenter"]

    KEY_ANALYSIS_CONTROLS_SHOW_CHILDREN = "q"
    KEY_ANALYSIS_CONTROLS_EVAL = "w"
    KEY_ANALYSIS_CONTROLS_HINTS = "e"
    KEY_ANALYSIS_CONTROLS_POLICY = "r"
    KEY_ANALYSIS_CONTROLS_OWNERSHIP = "t"

    KEY_RESET_ANALYSIS = "h"
    KEY_STOP_ANALYSIS = "escape"
    KEY_TOGGLE_CONTINUOUS_ANALYSIS = "spacebar"
    KEY_TOGGLE_MOVENUM = "m"

    KEY_COPY = "c"
    KEY_PASTE = "v"

    KEY_NAV_BRANCH_DOWN = "down"
    KEY_NAV_BRANCH_UP = "up"
    KEY_NAV_NEXT = ["right", "x"]
    KEY_NAV_PREV = ["left", "z"]
    KEY_NAV_GAME_START = "home"
    KEY_NAV_GAME_END = "end"
    KEY_NAV_PREV_BRANCH = "b"
    KEY_NAV_MISTAKE = "n"
    KEY_MOVE_TREE_DELETE_SELECTED_NODE = "delete"
    KEY_MOVE_TREE_MAKE_SELECTED_NODE_MAIN_BRANCH = "pageup"

    KEY_TOGGLE_COORDINATES = "k"
