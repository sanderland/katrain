from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Enum, CheckConstraint, Boolean, UniqueConstraint, Index, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from katrain.web.core.db import Base
import enum
import uuid as uuid_module


class MatchSourceEnum(str, enum.Enum):
    """Data source for live matches."""
    XINGZHEN = "xingzhen"
    YIKE = "yike"
    PANDANET = "pandanet"


class MatchStatusEnum(str, enum.Enum):
    """Status of a live match."""
    LIVE = "live"
    FINISHED = "finished"


class AnalysisStatusEnum(str, enum.Enum):
    """Status of analysis task."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, index=True, default=lambda: uuid_module.uuid4().hex)  # Unique UUID assigned at registration
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    rank = Column(String, default="20k")
    net_wins = Column(Integer, default=0)
    elo_points = Column(Integer, default=0)
    credits = Column(Float, default=10000.00)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    followers = relationship("Relationship", foreign_keys="[Relationship.following_id]", back_populates="following")
    following = relationship("Relationship", foreign_keys="[Relationship.follower_id]", back_populates="follower")
    tsumego_progress = relationship("UserTsumegoProgress", back_populates="user")

class Relationship(Base):
    __tablename__ = "relationships"

    follower_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    following_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    following = relationship("User", foreign_keys=[following_id], back_populates="followers")

class RatingHistory(Base):
    __tablename__ = "rating_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    old_rank = Column(String)
    new_rank = Column(String)
    elo_change = Column(Integer, default=0)
    game_id = Column(String(32), ForeignKey("user_games.id"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    game = relationship("UserGame")
    user = relationship("User")


class LiveMatchDB(Base):
    """Database model for live/historical matches from external sources."""
    __tablename__ = "live_matches"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String(64), unique=True, nullable=False, index=True)  # Format: {source}_{source_id}
    source = Column(String(20), nullable=False)  # xingzhen / yike
    source_id = Column(String(64), nullable=False)
    tournament = Column(String(256), nullable=False)
    round_name = Column(String(128), nullable=True)
    match_date = Column(DateTime(timezone=True), nullable=True)
    player_black = Column(String(128), nullable=False)
    player_white = Column(String(128), nullable=False)
    black_rank = Column(String(16), nullable=True)
    white_rank = Column(String(16), nullable=True)
    status = Column(String(16), nullable=False, default="live")  # live / finished
    result = Column(String(64), nullable=True)
    move_count = Column(Integer, default=0)
    sgf_content = Column(Text, nullable=True)
    moves = Column(JSON, nullable=True)  # ["Q16", "D4", ...]
    current_winrate = Column(Float, default=0.5)  # From XingZhen API
    current_score = Column(Float, default=0.0)    # From XingZhen API
    katago_winrate = Column(Float, nullable=True)  # From local KataGo (latest move)
    katago_score = Column(Float, nullable=True)    # From local KataGo (latest move)
    # Game rules and komi
    board_size = Column(Integer, default=19)  # Board size (9, 13, 19)
    komi = Column(Float, default=7.5)  # Komi (compensation points for white)
    rules = Column(String(32), default="chinese")  # Rules: chinese, japanese, korean, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship to analysis records
    analysis_records = relationship("LiveAnalysisDB", back_populates="match", cascade="all, delete-orphan")


class LiveAnalysisDB(Base):
    """Database model for move-by-move analysis data."""
    __tablename__ = "live_analysis"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String(64), ForeignKey("live_matches.match_id"), nullable=False, index=True)
    move_number = Column(Integer, nullable=False)  # 0 = empty board, 1 = after first move
    status = Column(String(16), nullable=False, default="pending")  # pending / running / success / failed
    priority = Column(Integer, default=10)  # Higher = more urgent (live matches get higher priority)

    # Analysis results (populated when status=success)
    winrate = Column(Float, nullable=True)  # Black's winrate 0-1
    score_lead = Column(Float, nullable=True)  # Black's lead in points
    top_moves = Column(JSON, nullable=True)  # [{move, visits, winrate, score_lead, prior, pv}, ...]
    ownership = Column(JSON, nullable=True)  # 2D array of ownership values (-1 to 1, positive=Black)

    # Move classification
    actual_move = Column(String(8), nullable=True)  # The move that was played
    actual_player = Column(String(1), nullable=True)  # 'B' or 'W'
    delta_score = Column(Float, nullable=True)  # Score change from previous position
    delta_winrate = Column(Float, nullable=True)  # Winrate change from previous position
    is_brilliant = Column(Boolean, default=False)
    is_mistake = Column(Boolean, default=False)
    is_questionable = Column(Boolean, default=False)

    # Error tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    analyzed_at = Column(DateTime(timezone=True), nullable=True)

    # Unique constraint for (match_id, move_number)
    __table_args__ = (
        UniqueConstraint('match_id', 'move_number', name='uq_match_move'),
    )

    # Relationship to match
    match = relationship("LiveMatchDB", back_populates="analysis_records")


class LiveCommentDB(Base):
    """Database model for comments on live matches."""
    __tablename__ = "live_comments"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String(64), ForeignKey("live_matches.match_id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    match = relationship("LiveMatchDB", backref="comments")
    user = relationship("User", backref="live_comments")


class TranslationSourceEnum(str, enum.Enum):
    """Source of translation data."""
    STATIC = "static"      # From JSON files
    MANUAL = "manual"      # Manually entered by user
    LLM = "llm"            # Generated by LLM
    WIKIPEDIA = "wikipedia"  # From Wikipedia lookup


class PlayerTranslationDB(Base):
    """Database model for player name translations."""
    __tablename__ = "player_translations"

    id = Column(Integer, primary_key=True, index=True)
    canonical_name = Column(String(128), unique=True, nullable=False, index=True)  # Original name (e.g., "王立诚")
    country = Column(String(4), nullable=True)  # CN, JP, KR, TW
    en = Column(String(128), nullable=True)  # English translation
    cn = Column(String(128), nullable=True)  # Simplified Chinese
    tw = Column(String(128), nullable=True)  # Traditional Chinese
    jp = Column(String(128), nullable=True)  # Japanese (kanji/katakana)
    ko = Column(String(128), nullable=True)  # Korean (hangul)
    aliases = Column(JSON, nullable=True)  # List of alternative names
    source = Column(String(16), nullable=False, default="manual")  # static/manual/llm/wikipedia
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TournamentTranslationDB(Base):
    """Database model for tournament name translations."""
    __tablename__ = "tournament_translations"

    id = Column(Integer, primary_key=True, index=True)
    original = Column(String(256), unique=True, nullable=False, index=True)  # Original tournament name
    en = Column(String(256), nullable=True)  # English translation
    cn = Column(String(256), nullable=True)  # Simplified Chinese
    tw = Column(String(256), nullable=True)  # Traditional Chinese
    jp = Column(String(256), nullable=True)  # Japanese
    ko = Column(String(256), nullable=True)  # Korean
    source = Column(String(16), nullable=False, default="manual")  # static/manual/llm/wikipedia
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SystemConfigDB(Base):
    """Database model for system configuration.

    Stores runtime-configurable settings. Sensitive values like API keys
    should still be stored in environment variables for security.
    """
    __tablename__ = "system_config"

    key = Column(String(64), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============ Tsumego Models ============

class TsumegoProblem(Base):
    """Individual tsumego problem."""
    __tablename__ = "tsumego_problems"

    id = Column(String(32), primary_key=True)  # Problem number, e.g. "1014"
    level = Column(String(8), nullable=False, index=True)  # "3d", "4d"
    category = Column(String(32), nullable=False, index=True)  # "life-death", "tesuji"
    hint = Column(String(16), nullable=False)  # "黑先", "白先"
    board_size = Column(Integer, default=19)
    initial_black = Column(JSON)  # ["pa", "rd", ...]
    initial_white = Column(JSON)  # ["nc", "qf", ...]
    sgf_content = Column(Text)  # Full SGF for solving
    source = Column(String(256))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_tsumego_level_category", "level", "category"),
    )


class UserTsumegoProgress(Base):
    """User's progress on a specific problem."""
    __tablename__ = "user_tsumego_progress"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    problem_id = Column(String(32), ForeignKey("tsumego_problems.id"), primary_key=True)
    completed = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    first_completed_at = Column(DateTime(timezone=True))
    last_attempt_at = Column(DateTime(timezone=True))
    last_duration = Column(Integer)  # Seconds to complete last time

    user = relationship("User", back_populates="tsumego_progress")
    problem = relationship("TsumegoProblem")


# ============ Tutorial Models ============

class UserTutorialProgress(Base):
    # DEPRECATED in V2 — kept for data preservation. Will be replaced in Phase 3.
    """User's progress on a specific tutorial example."""
    __tablename__ = "user_tutorial_progress"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    example_id = Column(String(64), primary_key=True)
    topic_id = Column(String(64), nullable=False, index=True)
    last_step_id = Column(String(64), nullable=True)
    completed = Column(Boolean, default=False)
    last_played_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="tutorial_progress")


# ============ Tutorial V2 Models ============

class TutorialBook(Base):
    """A Go tutorial book imported from book.json."""
    __tablename__ = "tutorial_books"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(32), nullable=False, index=True)      # 入门/布局/中盘/官子
    subcategory = Column(String(64), nullable=False, default="棋书")
    title = Column(String(256), nullable=False)
    author = Column(String(128), nullable=True)
    translator = Column(String(128), nullable=True)
    slug = Column(String(128), nullable=False, unique=True, index=True)
    asset_dir = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    chapters = relationship("TutorialChapter", back_populates="book", cascade="all, delete-orphan",
                            order_by="TutorialChapter.order")

    __table_args__ = (
        CheckConstraint("category IN ('入门', '布局', '中盘', '官子')", name="ck_book_category"),
    )


class TutorialChapter(Base):
    """A chapter within a tutorial book."""
    __tablename__ = "tutorial_chapters"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("tutorial_books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_number = Column(String(32), nullable=False)
    title = Column(String(256), nullable=False)
    order = Column(Integer, nullable=False)

    book = relationship("TutorialBook", back_populates="chapters")
    sections = relationship("TutorialSection", back_populates="chapter", cascade="all, delete-orphan",
                            order_by="TutorialSection.order")

    __table_args__ = (
        UniqueConstraint("book_id", "order", name="uq_chapter_book_order"),
    )


class TutorialSection(Base):
    """A section within a chapter (= one Example in the UI)."""
    __tablename__ = "tutorial_sections"

    id = Column(Integer, primary_key=True, index=True)
    chapter_id = Column(Integer, ForeignKey("tutorial_chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    section_number = Column(String(32), nullable=False)
    title = Column(String(256), nullable=False)
    order = Column(Integer, nullable=False)

    chapter = relationship("TutorialChapter", back_populates="sections")
    figures = relationship("TutorialFigure", back_populates="section", cascade="all, delete-orphan",
                           order_by="TutorialFigure.order")

    __table_args__ = (
        UniqueConstraint("chapter_id", "order", name="uq_section_chapter_order"),
    )


class TutorialFigure(Base):
    """A single board diagram (= one Variation in the UI). Core content unit."""
    __tablename__ = "tutorial_figures"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("tutorial_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=False)
    figure_label = Column(String(32), nullable=False)
    book_text = Column(Text, nullable=True)
    page_context_text = Column(Text, nullable=True)
    bbox = Column(JSON, nullable=True)
    page_image_path = Column(String(512), nullable=True)
    board_payload = Column(JSON, nullable=True)
    recognition_debug = Column(JSON, nullable=True)
    narration = Column(Text, nullable=True)
    audio_asset = Column(String(512), nullable=True)
    video_asset = Column(String(512), nullable=True)
    video_duration_ms = Column(Integer, nullable=True)
    video_size_bytes = Column(Integer, nullable=True)
    order = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    section = relationship("TutorialSection", back_populates="figures")

    __table_args__ = (
        UniqueConstraint("section_id", "order", name="uq_figure_section_order"),
    )


class TrainingSample(Base):
    """Individual patch sample for EfficientNet-B0 stone classifier training.

    Populated from human-verified figures via scripts/export_training_data.py.
    Each row = one CV-cropped intersection patch with ground-truth label.
    """
    __tablename__ = "training_samples"

    id = Column(Integer, primary_key=True, index=True)
    figure_id = Column(Integer, ForeignKey("tutorial_figures.id", ondelete="CASCADE"), nullable=False, index=True)
    patch_label = Column(String(4), nullable=False)       # "A", "B", "AA"
    local_col = Column(Integer, nullable=False)
    local_row = Column(Integer, nullable=False)
    global_col = Column(Integer, nullable=False)
    global_row = Column(Integer, nullable=False)
    patch_image_path = Column(String(512), nullable=False)  # relative to data/
    base_type = Column(String(16), nullable=False)          # black/white/empty
    move_number = Column(Integer, nullable=True)            # 1-99 or null
    shape = Column(String(16), nullable=True)               # triangle/square/circle or null
    letter = Column(String(4), nullable=True)               # A/B/C or null
    source = Column(String(16), nullable=False, server_default="human")
    book_slug = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    figure = relationship("TutorialFigure")


class KifuAlbum(Base):
    """Database model for tournament game records (大赛棋谱)."""
    __tablename__ = "kifu_albums"

    id = Column(Integer, primary_key=True, index=True)
    player_black = Column(String(512), nullable=False, index=True)
    player_white = Column(String(512), nullable=False, index=True)
    black_rank = Column(String(64), nullable=True)
    white_rank = Column(String(64), nullable=True)
    event = Column(String(256), nullable=True, index=True)
    result = Column(String(64), nullable=True)
    date_played = Column(String(32), nullable=True)  # Raw SGF date string for display ("1926", "1928-09-04,05")
    date_sort = Column(String(10), nullable=True, index=True)  # Normalized ISO prefix for sorting ("1926-00-00", "1928-09-04")
    place = Column(String(256), nullable=True)
    komi = Column(Float, nullable=True)
    handicap = Column(Integer, default=0)
    board_size = Column(Integer, default=19)
    rules = Column(String(32), nullable=True)
    round_name = Column(String(128), nullable=True)
    source = Column(String(256), nullable=True)
    move_count = Column(Integer, default=0)
    sgf_content = Column(Text, nullable=False)
    source_path = Column(String(512), unique=True, nullable=False, index=True)  # Prevents duplicate imports
    search_text = Column(Text, nullable=True)  # Lowercased concatenated searchable fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserGame(Base):
    """Personal game library: play records, imported SGFs, research positions."""
    __tablename__ = "user_games"

    id = Column(String(32), primary_key=True, default=lambda: uuid_module.uuid4().hex)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    sgf_content = Column(Text, nullable=True)
    player_black = Column(String(100), nullable=True)
    player_white = Column(String(100), nullable=True)
    result = Column(String(50), nullable=True)
    board_size = Column(Integer, default=19)
    rules = Column(String(64), default="chinese")
    komi = Column(Float, default=7.5)
    move_count = Column(Integer, default=0)
    source = Column(String(50), nullable=False)  # play_ai / play_human / import / research
    category = Column(String(50), default="game")  # game / position
    game_type = Column(String(50), nullable=True)  # free / rated / null
    sgf_hash = Column(String(64), nullable=True, index=True)
    event = Column(String(255), nullable=True)
    game_date = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="user_games")
    analysis_records = relationship("UserGameAnalysis", back_populates="game", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_user_games_user_category", "user_id", "category"),
        Index("ix_user_games_user_source", "user_id", "source"),
        Index("ix_user_games_created", "created_at"),
    )


class UserGameAnalysis(Base):
    """Move-by-move analysis data for user games (research module)."""
    __tablename__ = "user_game_analysis"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String(32), ForeignKey("user_games.id"), nullable=False, index=True)
    move_number = Column(Integer, nullable=False)
    status = Column(String(16), default="pending")  # pending / running / success / failed
    priority = Column(Integer, default=10)
    winrate = Column(Float, nullable=True)
    score_lead = Column(Float, nullable=True)
    visits = Column(Integer, nullable=True)
    top_moves = Column(JSON, nullable=True)
    ownership = Column(JSON, nullable=True)
    move = Column(String(8), nullable=True)  # actual move played (e.g. "Q16")
    actual_player = Column(String(1), nullable=True)  # B / W
    delta_score = Column(Float, nullable=True)
    delta_winrate = Column(Float, nullable=True)
    is_brilliant = Column(Boolean, default=False)
    is_mistake = Column(Boolean, default=False)
    is_questionable = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    game = relationship("UserGame", back_populates="analysis_records")

    __table_args__ = (
        UniqueConstraint('game_id', 'move_number', name='uq_user_game_analysis_move'),
        Index("ix_user_game_analysis_status", "status", "priority"),
    )


class SyncQueueEntry(Base):
    """Offline sync queue for board mode. See design.md Section 4.5.1."""
    __tablename__ = "sync_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    idempotency_key = Column(String(64), unique=True, nullable=False, index=True)
    operation = Column(String(64), nullable=False)  # create_user_game / update_tsumego_progress
    endpoint = Column(String(256), nullable=False)  # Remote API path
    method = Column(String(8), nullable=False)  # POST / PUT
    payload = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)  # pending/in_progress/completed/failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    locked_at = Column(DateTime(timezone=True), nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=5)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    last_http_status = Column(Integer, nullable=True)
    last_error = Column(Text, nullable=True)
    user_id = Column(String(64), nullable=True)
    device_id = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_sync_queue_status_retry", "status", "next_retry_at"),
    )


class DeviceHeartbeatDB(Base):
    """Server-side device tracking. See design.md Section 4.15.2."""
    __tablename__ = "device_heartbeats"

    device_id = Column(String(64), primary_key=True)
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    queue_depth = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    oldest_unsynced_age_sec = Column(Integer, default=0)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(64), nullable=True)
    app_version = Column(String(32), nullable=True)


class UpcomingMatchDB(Base):
    """Upcoming/scheduled matches from various sources (populated by katrain-cron)."""
    __tablename__ = "live_upcoming"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(128), unique=True, nullable=False, index=True)
    tournament = Column(String(256), nullable=False)
    round_name = Column(String(128), nullable=True)
    scheduled_time = Column(DateTime(timezone=True), nullable=False, index=True)
    player_black = Column(String(128), nullable=True)
    player_white = Column(String(128), nullable=True)
    source = Column(String(32), nullable=False)  # foxwq, nihonkiin, etc.
    source_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============ Cross-Platform Play Models ============


class PlatformGameDB(Base):
    """Cross-platform game records — games played on external platforms (OGS, Fox, etc.) via KaTrain."""

    __tablename__ = "platform_games"

    id = Column(String(64), primary_key=True)  # KaTrain game UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String(20), nullable=False, index=True)  # "ogs", "fox", "golaxy", "kgs"
    platform_game_id = Column(String(128), nullable=False)  # ID on the remote platform
    opponent_name = Column(String(128), nullable=True)
    opponent_rank = Column(String(16), nullable=True)
    my_color = Column(String(1), nullable=True)  # "B" or "W"
    result = Column(String(64), nullable=True)  # "B+5.5", "W+R", etc.
    board_size = Column(Integer, default=19)
    sgf_content = Column(Text, nullable=True)
    played_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="platform_games")

    __table_args__ = (UniqueConstraint("platform", "platform_game_id", name="uq_platform_game"),)
