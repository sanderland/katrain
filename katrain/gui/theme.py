
def to_hexcol(kivycol):
    return "#" + "".join(f"{round(c * 255):02x}" for c in kivycol[:3])

# Modern Dark Palette (Dracula/Catppuccin hybrid)
BACKGROUND = [30/255, 30/255, 46/255, 1]       # Mocha Base
SURFACE = [49/255, 50/255, 68/255, 1]          # Surface0
SURFACE_LIGHT = [69/255, 71/255, 90/255, 1]    # Surface1
TEXT_MAIN = [205/255, 214/255, 244/255, 1]     # Text
TEXT_SUB = [166/255, 173/255, 200/255, 1]      # Subtext0

ACCENT_PRIMARY = [137/255, 180/255, 250/255, 1]   # Blue
ACCENT_SECONDARY = [166/255, 227/255, 161/255, 1] # Green
ACCENT_WARN = [249/255, 226/255, 175/255, 1]      # Yellow
ACCENT_ERROR = [243/255, 139/255, 168/255, 1]     # Red
ACCENT_INFO = [180/255, 190/255, 254/255, 1]      # Lavender

BLACK_COL = [0.1, 0.1, 0.1, 1]
WHITE_COL = [0.95, 0.95, 0.95, 1]

# Compatibility Aliases
WHITE = WHITE_COL
BLACK = BLACK_COL
LIGHT_GREY = TEXT_SUB
LIGHTER_GREY = TEXT_MAIN # or SURFACE_LIGHT? Let's use TEXT_MAIN for high contrast elements if they were background
GREY = TEXT_SUB


class Theme:
    # font
    DEFAULT_FONT = "NotoSansCJKsc-Regular.otf"
    INPUT_FONT_SIZE = 20  # sp
    DESC_FONT_SIZE = 18  # sp
    NOTES_FONT_SIZE = 16  # sp

    ACCENT_PRIMARY = ACCENT_PRIMARY
    ACCENT_SECONDARY = ACCENT_SECONDARY
    ACCENT_WARN = ACCENT_WARN
    ACCENT_ERROR = ACCENT_ERROR
    ACCENT_INFO = ACCENT_INFO
    TEXT_SUB = TEXT_SUB
    TEXT_MAIN = TEXT_MAIN
    SURFACE_LIGHT = SURFACE_LIGHT
    SURFACE = SURFACE
    BACKGROUND = BACKGROUND

    # gui colors
    BACKGROUND_COLOR = BACKGROUND
    BOX_BACKGROUND_COLOR = SURFACE
    LIGHTER_BACKGROUND_COLOR = SURFACE_LIGHT
    
    SCROLLBAR_COLOR = SURFACE_LIGHT
    TEXT_COLOR = TEXT_MAIN
    INPUT_FONT_COLOR = TEXT_MAIN
    
    SCORE_COLOR = ACCENT_PRIMARY
    WINRATE_COLOR = ACCENT_SECONDARY
    POINTLOSS_COLOR = ACCENT_WARN
    
    BUTTON_INACTIVE_COLOR = SURFACE_LIGHT
    BUTTON_BORDER_COLOR = ACCENT_PRIMARY
    BUTTON_TEXT_COLOR = TEXT_MAIN
    
    PAUSE_ACTIVE_COLOR = ACCENT_WARN
    TIMER_TEXT_COLOR = ACCENT_SECONDARY
    TIMER_TEXT_TIMEOUT_COLOR = ACCENT_ERROR
    
    CIRCLE_TEXT_COLORS = {"W": BLACK_COL, "B": WHITE_COL}
    
    NOTES_TAB_FONT_COLOR = ACCENT_WARN
    INFO_TAB_FONT_COLOR = TEXT_MAIN
    
    ERROR_BORDER_COLOR = ACCENT_ERROR
    
    MENU_ITEM_FONT_COLOR = TEXT_MAIN
    MENU_ITEM_SHORTCUT_COLOR = TEXT_SUB
    
    PLAY_ANALYZE_TAB_COLOR = ACCENT_WARN
    
    CHECKBOX_COLOR = ACCENT_PRIMARY
    PRIMARY_BUTTON_COLOR = ACCENT_PRIMARY
    MISTAKE_BUTTON_COLOR = ACCENT_ERROR
    
    STAT_WORSE_COLOR = ACCENT_ERROR
    STAT_BETTER_COLOR = ACCENT_SECONDARY

    # gui spacing - Increased for modern feel
    RIGHT_PANEL_ASPECT_RATIO = 0.45  # Slightly wider
    CONTROLS_PANEL_ASPECT_RATIO = 12.0 
    CONTROLS_PANEL_MIN_HEIGHT = 60
    CONTROLS_PANEL_MAX_HEIGHT = 90
    
    CP_SPACING = 8
    CP_SMALL_SPACING = 4
    CP_PADDING = 10

    # textures
    STONE_TEXTURE = {"B": "B_stone.png", "W": "W_stone.png"}
    EVAL_DOT_TEXTURE = "dot.png"
    LAST_MOVE_TEXTURE = "inner.png"
    TOP_MOVE_TEXTURE = "topmove.png"
    BOARD_TEXTURE = "board.png"
    GRAPH_TEXTURE = "graph_bg.png"
    
    # sounds
    STONE_SOUNDS = [f"stone{i}.wav" for i in [1, 2, 3, 4, 5]]
    CAPTURING_SOUND = "capturing.wav"
    COUNTDOWN_SOUND = "countdownbeep.wav"
    MINIMUM_TIME_PASSED_SOUND = "boing.wav"
    MISTAKE_SOUNDS = []

    # eval dots - Updated to match palette
    EVAL_COLORS = {
        "theme:normal": [
            [0.58, 0.4, 0.9, 1],   # Purple
            ACCENT_ERROR,          # Red
            [0.96, 0.6, 0.25, 1],  # Orange
            ACCENT_WARN,           # Yellow
            [0.7, 0.9, 0.3, 1],    # Lime
            ACCENT_SECONDARY,      # Green
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
    APPROX_BOARD_COLOR = [0.95, 0.75, 0.47, 1]
    BOARD_COLOR_TINT = [1, 1, 1, 1]

    HINT_TEXT_COLOR = BLACK_COL

    PASS_CIRCLE_COLOR = [0.45, 0.05, 0.45, 0.7]
    PASS_CIRCLE_TEXT_COLOR = [0.85, 0.85, 0.85]

    STONE_COLORS = {"B": BLACK_COL, "W": WHITE_COL}
    NUMBER_COLOR = [0.85, 0.68, 0.40, 0.8]

    NEXT_MOVE_DASH_CONTRAST_COLORS = {"B": SURFACE_LIGHT, "W": [0.5, 0.5, 0.5, 1]}
    OUTLINE_COLORS = {"B": [0.3, 0.3, 0.3, 0.5], "W": [0.7, 0.7, 0.7, 0.5]}
    PV_TEXT_COLORS = {"W": BLACK_COL, "B": WHITE_COL}

    # board
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
    TOP_MOVE_BORDER_COLOR = ACCENT_PRIMARY
    CHILD_SCALE = 0.95
    HINT_SCALE = 0.98
    UNCERTAIN_HINT_SCALE = 0.7

    # ponder light
    ENGINE_DOWN_COLOR = ACCENT_ERROR
    ENGINE_BUSY_COLOR = [0.96, 0.6, 0.25, 1] # Orange
    ENGINE_READY_COLOR = ACCENT_SECONDARY
    ENGINE_PONDERING_COLOR = ACCENT_WARN

    # info PV link
    INFO_PV_COLOR = to_hexcol(ACCENT_WARN)

    # graph
    GRAPH_DOT_COLOR = ACCENT_ERROR
    WINRATE_MARKER_COLOR = ACCENT_SECONDARY
    SCORE_MARKER_COLOR = ACCENT_PRIMARY
    POINTLOSS_MARKER_COLOR = ACCENT_WARN

    # move tree
    MOVE_TREE_LINE = TEXT_SUB
    MOVE_TREE_CURRENT = ACCENT_WARN
    MOVE_TREE_SELECTED = ACCENT_ERROR
    MOVE_TREE_COLLAPSED = SURFACE_LIGHT
    MOVE_TREE_STONE_OUTLINE_COLORS = {"W": BLACK_COL, "B": WHITE_COL}

    # keyboard shortcuts - Kept same
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
