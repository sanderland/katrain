PROGRAM_NAME = "KaTrain"
VERSION = "2.0.0"
HOMEPAGE = "https://github.com/sanderland/katrain"
CONFIG_MIN_VERSION = "2.0.0"  # keep config files from this version
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
PRIORITY_EXTRA_ANALYSIS = 100
PRIORITY_DEFAULT = 1000  # new move, high pri
PRIORITY_EXTRA_AI_QUERY = 10_000

PLAYER_HUMAN, PLAYER_AI = "player:human", "player:ai"
PLAYER_TYPES = [PLAYER_HUMAN, PLAYER_AI]

PLAYING_NORMAL, PLAYING_TEACHING = "game:normal", "game:teach"
GAME_TYPES = [PLAYING_NORMAL, PLAYING_TEACHING]

MODE_PLAY, MODE_ANALYZE = "play", "analyze"

AI_DEFAULT = "ai:default"
AI_HUMAN = "ai:human"

AI_CONFIG_DEFAULT = AI_DEFAULT

AI_STRATEGIES = [AI_DEFAULT, AI_HUMAN]
AI_STRATEGIES_RECOMMENDED_ORDER = [AI_DEFAULT, AI_HUMAN]

# Used by the AI config UI to float the most important keys to the top.
AI_KEY_PROPERTIES = {
    "profile",
    "human_kyu_rank",
    "modern_style",
    "pro_year",
}


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
