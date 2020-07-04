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
    "weaken_fac": [x/20 for x in range(10,3*20+1)],
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

CALIBRATED_RANK_ELO =[(39.36921298625589, 18),
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
                      (1700,-4)]
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
