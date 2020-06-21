VERSION = "1.3.0"
HOMEPAGE = "https://github.com/sanderland/katrain"
CONFIG_MIN_VERSION = "1.2.0"  # keep config files from this version

OUTPUT_ERROR = -1
OUTPUT_KATAGO_STDERR = -0.5
OUTPUT_INFO = 0
OUTPUT_DEBUG = 1
OUTPUT_EXTRA_DEBUG = 2

PLAYER_HUMAN, PLAYER_AI = "player:human", "player:ai"
PLAYER_TYPES = [PLAYER_HUMAN, PLAYER_AI]

PLAYING_NORMAL, PLAYING_TEACHING = "game:normal", "game:teach"
GAME_TYPES = [PLAYING_NORMAL, PLAYING_TEACHING]

MODE_PLAY, MODE_ANALYZE = "play", "analyze"

AI_DEFAULT = "ai:default"
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

AI_STRATEGIES_ENGINE = [AI_DEFAULT, AI_SCORELOSS, AI_JIGO]
AI_STRATEGIES_PICK = [AI_PICK, AI_LOCAL, AI_TENUKI, AI_INFLUENCE, AI_TERRITORY, AI_RANK]
AI_STRATEGIES_POLICY = [AI_WEIGHTED, AI_POLICY] + AI_STRATEGIES_PICK
AI_STRATEGIES = AI_STRATEGIES_ENGINE + AI_STRATEGIES_POLICY
AI_STRATEGIES_RECOMMENDED_ORDER = [
    AI_DEFAULT,
    AI_RANK,
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


AI_STRENGTH = {  # not used
    AI_DEFAULT: "9d",
    AI_POLICY: "4d",
    AI_JIGO: "?d",
    AI_SCORELOSS: "5k",
    AI_WEIGHTED: "5k",
    AI_PICK: "8k",
    AI_LOCAL: "5k",
    AI_TENUKI: "8k",
    AI_INFLUENCE: "8k",
    AI_TERRITORY: "5k",
    AI_RANK: "15k - 3d",
}

AI_OPTION_VALUES = {
    "kyu_rank": [(k, f"{k}[strength:kyu]") for k in range(15, 0, -1)]
    + [(k, f"{1-k}[strength:dan]") for k in range(0, -3, -1)],
    "strength": [0.25, 0.5, 1, 2, 4],
    "opening_moves": range(0, 51),
    "pick_override": [0, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1],
    "lower_bound": [(v, f"{v:.2%}") for v in [0, 0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05]],
    "weaken_fac": [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 4],
    "endgame": [x / 100 for x in range(10, 80, 5)],
    "pick_frac": [x / 100 for x in range(0, 101, 5)],
    "pick_n": range(0, 26),
    "stddev": [x / 2 for x in range(21)],
    "line_weight": range(0, 11),
    "threshold": [2, 2.5, 3, 3.5, 4, 4.5],
}
