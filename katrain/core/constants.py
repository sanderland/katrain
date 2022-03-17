PROGRAM_NAME = "KaTrain"
VERSION = "1.11.0"
HOMEPAGE = "https://github.com/sanderland/katrain"
CONFIG_MIN_VERSION = "1.11.0"  # keep config files from this version
ANALYSIS_FORMAT_VERSION = "1.0"
DATA_FOLDER = "~/.katrain"


OUTPUT_ERROR = -1
OUTPUT_KATAGO_STDERR = -0.5
OUTPUT_INFO = 0
OUTPUT_DEBUG = 1
OUTPUT_EXTRA_DEBUG = 2

KATAGO_EXCEPTION = "KATAGO-INTERNAL-ERROR"

STATUS_ANALYSIS = 1.0  # same priority for analysis/info
STATUS_INFO = 1.1
STATUS_TEACHING = 2.0
STATUS_ERROR = 1000.0

ADDITIONAL_MOVE_ORDER = 999

PRIORITY_GAME_ANALYSIS = -100
PRIORITY_SWEEP = -10  # sweep is live, but slow, so deprioritize
PRIORITY_ALTERNATIVES = 100  # extra analysis, live interaction
PRIORITY_EQUALIZE = 100
PRIORITY_EXTRA_ANALYSIS = 100
PRIORITY_DEFAULT = 1000  # new move, high pri
PRIORITY_EXTRA_AI_QUERY = 10_000

PLAYER_HUMAN, PLAYER_AI = "player:human", "player:ai"
PLAYER_TYPES = [PLAYER_HUMAN, PLAYER_AI]

PLAYING_NORMAL, PLAYING_TEACHING = "game:normal", "game:teach"
GAME_TYPES = [PLAYING_NORMAL, PLAYING_TEACHING]

MODE_PLAY, MODE_ANALYZE = "play", "analyze"

AI_DEFAULT = "ai:default"
AI_HANDICAP = "ai:handicap"
AI_SCORELOSS = "ai:scoreloss"
AI_WEIGHTED = "ai:p:weighted"
AI_JIGO = "ai:jigo"
AI_ANTIMIRROR = "ai:antimirror"
AI_POLICY = "ai:policy"
AI_PICK = "ai:p:pick"
AI_LOCAL = "ai:p:local"
AI_TENUKI = "ai:p:tenuki"
AI_INFLUENCE = "ai:p:influence"
AI_TERRITORY = "ai:p:territory"
AI_RANK = "ai:p:rank"
AI_SIMPLE_OWNERSHIP = "ai:simple"
AI_SETTLE_STONES = "ai:settle"

AI_CONFIG_DEFAULT = AI_RANK

AI_STRATEGIES_ENGINE = [AI_DEFAULT, AI_HANDICAP, AI_SCORELOSS, AI_SIMPLE_OWNERSHIP, AI_JIGO, AI_ANTIMIRROR]
AI_STRATEGIES_PICK = [AI_PICK, AI_LOCAL, AI_TENUKI, AI_INFLUENCE, AI_TERRITORY, AI_RANK]
AI_STRATEGIES_POLICY = [AI_WEIGHTED, AI_POLICY] + AI_STRATEGIES_PICK
AI_STRATEGIES = AI_STRATEGIES_ENGINE + AI_STRATEGIES_POLICY
AI_STRATEGIES_RECOMMENDED_ORDER = [
    AI_DEFAULT,
    AI_RANK,
    AI_HANDICAP,
    AI_SIMPLE_OWNERSHIP,
    AI_SCORELOSS,
    AI_POLICY,
    AI_WEIGHTED,
    AI_JIGO,
    AI_ANTIMIRROR,
    AI_PICK,
    AI_LOCAL,
    AI_TENUKI,
    AI_TERRITORY,
    AI_INFLUENCE,
]

AI_STRENGTH = {  # dan ranks, backup if model is missing. TODO: remove some?
    AI_DEFAULT: 9,
    AI_ANTIMIRROR: 9,
    AI_POLICY: 5,
    AI_JIGO: float("nan"),
    AI_SCORELOSS: -4,
    AI_WEIGHTED: -4,
    AI_PICK: -7,
    AI_LOCAL: -4,
    AI_TENUKI: -7,
    AI_INFLUENCE: -7,
    AI_TERRITORY: -7,
    AI_RANK: float("nan"),
    AI_SIMPLE_OWNERSHIP: 2,
    AI_SETTLE_STONES: 2,
}

AI_OPTION_VALUES = {
    "kyu_rank": [(k, f"{k}[strength:kyu]") for k in range(15, 0, -1)]
    + [(k, f"{1-k}[strength:dan]") for k in range(0, -3, -1)],
    "strength": [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 1],
    "opening_moves": range(0, 51),
    "pick_override": [0, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1],
    "lower_bound": [(v, f"{v:.2%}") for v in [0, 0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05]],
    "weaken_fac": [x / 20 for x in range(10, 3 * 20 + 1)],
    "endgame": [x / 100 for x in range(10, 80, 5)],
    "pick_frac": [x / 100 for x in range(0, 101, 5)],
    "pick_n": range(0, 26),
    "stddev": [x / 2 for x in range(21)],
    "line_weight": range(0, 11),
    "threshold": [2, 2.5, 3, 3.5, 4, 4.5],
    "automatic": "bool",
    "pda": [(x / 10, f"{'W' if x<0 else 'B'}+{abs(x/10):.1f}") for x in range(-30, 31)],
    "max_points_lost": [x / 10 for x in range(51)],
    "settled_weight": [x / 4 for x in range(0, 17)],
    "opponent_fac": [x / 10 for x in range(-20, 11)],
    "min_visits": range(1, 10),
    "attach_penalty": [x / 10 for x in range(-10, 51)],
    "tenuki_penalty": [x / 10 for x in range(-10, 51)],
}
AI_KEY_PROPERTIES = {
    "kyu_rank",
    "strength",
    "weaken_fac",
    "pick_frac",
    "pick_n",
    "automatic",
    "max_points_lost",
    "min_visits",
}


CALIBRATED_RANK_ELO = [
    (-21.679482223451032, 18),
    (42.60243194422105, 17),
    (106.88434611189314, 16),
    (171.16626027956522, 15),
    (235.44817444723742, 14),
    (299.7300886149095, 13),
    (364.0120027825817, 12),
    (428.2939169502538, 11),
    (492.5758311179259, 10),
    (556.8577452855981, 9),
    (621.1396594532702, 8),
    (685.4215736209424, 7),
    (749.7034877886144, 6),
    (813.9854019562865, 5),
    (878.2673161239586, 4),
    (942.5492302916308, 3),
    (1006.8311444593029, 2),
    (1071.113058626975, 1),
    (1135.3949727946472, 0),
    (1199.6768869623193, -1),
    (1263.9588011299913, -2),
    (1700, -4),
]


AI_WEIGHTED_ELO = [
    (0.5, 1591.5718897531551),
    (1.0, 1269.9896556526198),
    (1.25, 1042.25179764667),
    (1.5, 848.9410084463602),
    (1.75, 630.1483212024823),
    (2, 575.3637091858013),
    (2.5, 410.9747543504796),
    (3.0, 219.8667371799533),
]

AI_SCORELOSS_ELO = [
    (0.0, 539),
    (0.05, 625),
    (0.1, 859),
    (0.2, 1035),
    (0.3, 1201),
    (0.4, 1299),
    (0.5, 1346),
    (0.75, 1374),
    (1.0, 1386),
]


AI_LOCAL_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [-204.0, 791.0, 1154.0, 1372.0, 1402.0, 1473.0, 1700.0, 1700.0],
        [174.0, 1094.0, 1191.0, 1384.0, 1435.0, 1522.0, 1700.0, 1700.0],
        [619.0, 1155.0, 1323.0, 1390.0, 1450.0, 1558.0, 1700.0, 1700.0],
        [975.0, 1289.0, 1332.0, 1401.0, 1461.0, 1575.0, 1700.0, 1700.0],
        [1344.0, 1348.0, 1358.0, 1467.0, 1477.0, 1616.0, 1700.0, 1700.0],
        [1425.0, 1474.0, 1489.0, 1524.0, 1571.0, 1700.0, 1700.0, 1700.0],
    ],
]
AI_TENUKI_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [47.0, 335.0, 530.0, 678.0, 830.0, 1070.0, 1376.0, 1700.0],
        [99.0, 469.0, 546.0, 707.0, 855.0, 1090.0, 1413.0, 1700.0],
        [327.0, 513.0, 605.0, 745.0, 875.0, 1110.0, 1424.0, 1700.0],
        [429.0, 519.0, 620.0, 754.0, 900.0, 1130.0, 1435.0, 1700.0],
        [492.0, 607.0, 682.0, 797.0, 1000.0, 1208.0, 1454.0, 1700.0],
        [778.0, 830.0, 909.0, 949.0, 1169.0, 1461.0, 1483.0, 1700.0],
    ],
]
AI_TERRITORY_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [34.0, 383.0, 566.0, 748.0, 980.0, 1264.0, 1527.0, 1700.0],
        [131.0, 450.0, 586.0, 826.0, 995.0, 1280.0, 1537.0, 1700.0],
        [291.0, 517.0, 627.0, 850.0, 1010.0, 1310.0, 1547.0, 1700.0],
        [454.0, 526.0, 696.0, 870.0, 1038.0, 1340.0, 1590.0, 1700.0],
        [491.0, 603.0, 747.0, 890.0, 1050.0, 1390.0, 1635.0, 1700.0],
        [718.0, 841.0, 1039.0, 1076.0, 1332.0, 1523.0, 1700.0, 1700.0],
    ],
]
AI_INFLUENCE_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [217.0, 439.0, 572.0, 768.0, 960.0, 1227.0, 1449.0, 1521.0],
        [302.0, 551.0, 580.0, 800.0, 1028.0, 1257.0, 1470.0, 1529.0],
        [388.0, 572.0, 619.0, 839.0, 1077.0, 1305.0, 1490.0, 1561.0],
        [467.0, 591.0, 764.0, 878.0, 1097.0, 1390.0, 1530.0, 1591.0],
        [539.0, 622.0, 815.0, 953.0, 1120.0, 1420.0, 1560.0, 1601.0],
        [772.0, 912.0, 958.0, 1145.0, 1318.0, 1511.0, 1577.0, 1623.0],
    ],
]
AI_PICK_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [-533.0, -515.0, -355.0, 234.0, 650.0, 1147.0, 1546.0, 1700.0],
        [-531.0, -450.0, -69.0, 347.0, 670.0, 1182.0, 1550.0, 1700.0],
        [-450.0, -311.0, 140.0, 459.0, 693.0, 1252.0, 1555.0, 1700.0],
        [-365.0, -82.0, 265.0, 508.0, 864.0, 1301.0, 1619.0, 1700.0],
        [-113.0, 273.0, 363.0, 641.0, 983.0, 1486.0, 1700.0, 1700.0],
        [514.0, 670.0, 870.0, 1128.0, 1305.0, 1550.0, 1700.0, 1700.0],
    ],
]


TOP_MOVE_DELTA_SCORE = "top_move_delta_score"
TOP_MOVE_SCORE = "top_move_score"
TOP_MOVE_DELTA_WINRATE = "top_move_delta_winrate"
TOP_MOVE_WINRATE = "top_move_winrate"
TOP_MOVE_VISITS = "top_move_visits"
# TOP_MOVE_UTILITY = "top_move_utility"
# TOP_MOVE_UTILITYLCB = "top_move_utiltiy_lcb"
# TOP_MOVE_SCORE_STDDEV = "top_move_score_stddev"
TOP_MOVE_NOTHING = "top_move_nothing"


TOP_MOVE_OPTIONS = [
    TOP_MOVE_SCORE,
    TOP_MOVE_DELTA_SCORE,
    TOP_MOVE_WINRATE,
    TOP_MOVE_DELTA_WINRATE,
    TOP_MOVE_VISITS,
    TOP_MOVE_NOTHING,
    # TOP_MOVE_SCORE_STDDEV,
    # TOP_MOVE_UTILITY,
    # TOP_MOVE_UTILITYLCB
]
REPORT_DT = 1
PONDERING_REPORT_DT = 0.25

SGF_INTERNAL_COMMENTS_MARKER = "\u3164\u200b"
SGF_SEPARATOR_MARKER = "\u3164\u3164"
