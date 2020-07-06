VERSION = "1.3.0"
HOMEPAGE = "https://github.com/sanderland/katrain"
CONFIG_MIN_VERSION = "1.3.0"  # keep config files from this version

OUTPUT_ERROR = -1
OUTPUT_KATAGO_STDERR = -0.5
OUTPUT_INFO = 0
OUTPUT_DEBUG = 1
OUTPUT_EXTRA_DEBUG = 2

STATUS_ANALYSIS = 1.0  # same priority for analysis/info
STATUS_INFO = 1.1
STATUS_TEACHING = 2.0
STATUS_ERROR = 1000.0

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
AI_POLICY = "ai:policy"
AI_PICK = "ai:p:pick"
AI_LOCAL = "ai:p:local"
AI_TENUKI = "ai:p:tenuki"
AI_INFLUENCE = "ai:p:influence"
AI_TERRITORY = "ai:p:territory"
AI_RANK = "ai:p:rank"

AI_CONFIG_DEFAULT = AI_SCORELOSS

AI_STRATEGIES_ENGINE = [AI_DEFAULT, AI_HANDICAP, AI_SCORELOSS, AI_JIGO]
AI_STRATEGIES_PICK = [AI_PICK, AI_LOCAL, AI_TENUKI, AI_INFLUENCE, AI_TERRITORY, AI_RANK]
AI_STRATEGIES_POLICY = [AI_WEIGHTED, AI_POLICY] + AI_STRATEGIES_PICK
AI_STRATEGIES = AI_STRATEGIES_ENGINE + AI_STRATEGIES_POLICY
AI_STRATEGIES_RECOMMENDED_ORDER = [
    AI_DEFAULT,
    AI_RANK,
    AI_HANDICAP,
    AI_SCORELOSS,
    AI_POLICY,
    AI_WEIGHTED,
    AI_PICK,
    AI_LOCAL,
    AI_TENUKI,
    AI_TERRITORY,
    AI_INFLUENCE,
    AI_JIGO,
]

AI_STRENGTH = {  # dan ranks
    AI_DEFAULT: 9,
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
}

AI_OPTION_VALUES = {
    "kyu_rank": [(k, f"{k}[strength:kyu]") for k in range(15, 0, -1)]
    + [(k, f"{1-k}[strength:dan]") for k in range(0, -3, -1)],
    "strength": [0.25, 0.5, 1, 2, 4],
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
}
AI_KEY_PROPERTIES = {"kyu_rank", "strength", "weaken_fac", "pick_frac", "pick_n", "automatic"}

CALIBRATED_RANK_ELO = [
    (39.36921298625589, 18),
    (96.95581072853861, 17),
    (154.54240847082144, 16),
    (212.12900621310428, 15),
    (269.7156039553871, 14),
    (327.30220169766983, 13),
    (384.88879943995266, 12),
    (442.4753971822355, 11),
    (500.06199492451833, 10),
    (557.6485926668012, 9),
    (615.235190409084, 8),
    (672.8217881513667, 7),
    (730.4083858936496, 6),
    (787.9949836359324, 5),
    (845.5815813782152, 4),
    (903.168179120498, 3),
    (960.7547768627808, 2),
    (1018.3413746050636, 1),
    (1075.9279723473464, 0),
    (1133.5145700896292, -1),
    (1191.101167831912, -2),
    (1700, -4),
]
AI_WEIGHTED_ELO = [
    (0.5, 1591.4486833932992),
    (1.0, 1266.2591850212696),
    (1.25, 1121.5661132041557),
    (1.5, 960.0966363156612),
    (1.75, 800.3124873968906),
    (2, 670.1137021076612),
    (2.5, 516.8371296455036),
    (3.0, 359.9621037249864),
]

AI_LOCAL_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [450.0, 704.0, 1190.0, 1282.0, 1520.0, 1464.0, 1617.0, 1700.0],
        [153.0, 1079.0, 1144.0, 1335.0, 1440.0, 1525.0, 1700.0, 1700.0],
        [606.0, 1185.0, 1268.0, 1484.0, 1404.0, 1544.0, 1700.0, 1700.0],
        [911.0, 1230.0, 1312.0, 1352.0, 1432.0, 1564.0, 1700.0, 1700.0],
        [1212.0, 1326.0, 1393.0, 1441.0, 1446.0, 1601.0, 1700.0, 1700.0],
        [1321.0, 1395.0, 1399.0, 1473.0, 1582.0, 1700.0, 1700.0, 1700.0],
    ],
]
AI_TENUKI_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [491.0, 394.0, 527.0, 676.0, 732.0, 959.0, 1415.0, 1700.0],
        [21.0, 456.0, 620.0, 719.0, 812.0, 1027.0, 1308.0, 1700.0],
        [306.0, 480.0, 689.0, 705.0, 925.0, 1154.0, 1397.0, 1700.0],
        [286.0, 534.0, 636.0, 796.0, 968.0, 1077.0, 1443.0, 1700.0],
        [534.0, 645.0, 665.0, 846.0, 999.0, 1134.0, 1422.0, 1700.0],
        [746.0, 719.0, 806.0, 975.0, 1048.0, 1370.0, 1505.0, 1700.0],
    ],
]
AI_TERRITORY_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [512.0, 451.0, 640.0, 686.0, 929.0, 1112.0, 1533.0, 1700.0],
        [155.0, 419.0, 614.0, 761.0, 879.0, 1118.0, 1507.0, 1700.0],
        [338.0, 449.0, 716.0, 945.0, 949.0, 1282.0, 1520.0, 1700.0],
        [400.0, 495.0, 702.0, 875.0, 950.0, 1309.0, 1520.0, 1700.0],
        [570.0, 635.0, 707.0, 981.0, 922.0, 1346.0, 1519.0, 1700.0],
        [713.0, 772.0, 839.0, 1095.0, 1217.0, 1468.0, 1700.0, 1700.0],
    ],
]
AI_INFLUENCE_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [570.0, 293.0, 536.0, 774.0, 919.0, 1236.0, 1491.0, 1518.0],
        [238.0, 461.0, 628.0, 833.0, 859.0, 1211.0, 1459.0, 1592.0],
        [323.0, 513.0, 667.0, 837.0, 941.0, 1224.0, 1504.0, 1576.0],
        [407.0, 545.0, 659.0, 899.0, 988.0, 1215.0, 1483.0, 1602.0],
        [457.0, 713.0, 785.0, 856.0, 1142.0, 1309.0, 1508.0, 1506.0],
        [774.0, 903.0, 942.0, 1098.0, 1339.0, 1449.0, 1469.0, 1495.0],
    ],
]
AI_PICK_ELO_GRID = [
    [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    [0, 5, 10, 15, 25, 50],
    [
        [106.0, 148.0, 94.0, 218.0, 606.0, 1063.0, 1426.0, 1458.0],
        [114.0, 69.0, 278.0, 385.0, 683.0, 1099.0, 1425.0, 1517.0],
        [144.0, 174.0, 186.0, 452.0, 730.0, 1153.0, 1430.0, 1447.0],
        [145.0, 105.0, 380.0, 548.0, 863.0, 1233.0, 1423.0, 1448.0],
        [202.0, 251.0, 460.0, 651.0, 919.0, 1321.0, 1554.0, 1482.0],
        [472.0, 538.0, 816.0, 971.0, 1169.0, 1422.0, 1522.0, 1491.0],
    ],
]
