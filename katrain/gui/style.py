def to_hexcol(kivycol):
    return "#" + "".join(f"{round(c * 255):02x}" for c in kivycol[:3])


# basic color definitions
RED = [0.8, 0.1, 0.1, 1]
WHITE = [0.95,0.95,0.95,1]

# eval dots
EVAL_COLORS = [
    [0.447, 0.129, 0.42, 1],
    [0.8, 0, 0, 1],
    [0.9, 0.4, 0.1, 1],
    [0.85, 0.89, 0.3, 1],
    [0.67, 0.9, 0.18, 1.0],
    [0.117, 0.588, 0, 1.0],
]
EVAL_DOT_MAX_SIZE = 0.5
EVAL_DOT_MIN_SIZE = 0.25

# board
LINE_COLOR = [0, 0, 0]
POLICY_COLOR = [0.9, 0.2, 0.8]
STARPOINT_SIZE = 0.1
BOARD_COLOR = [0.85, 0.68, 0.40, 1]
STONE_SIZE = 0.475
VISITS_FRAC_SMALL = 0.1
STONE_COLORS = {"B": [0.05, 0.05, 0.05], "W": [0.95, 0.95, 0.95]}
OUTLINE_COLORS = {"B": [0.3, 0.3, 0.3, 0.5], "W": [0.7, 0.7, 0.7, 0.5]}
GHOST_ALPHA = 0.5
TOP_MOVE_ALPHA = 0.4
CHILD_SCALE = 0.95

# ponder light
ENGINE_DOWN_COL = [0.8, 0, 0, 1]
ENGINE_BUSY_COL = [0.9, 0.4, 0.1, 1]
ENGINE_READY_COL = [0.117, 0.588, 0, 1]

# info
PV_COLOR = to_hexcol(RED)
