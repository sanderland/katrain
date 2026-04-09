# Cross-Platform Online Play — Implementation Plan

> **Revision 2** (2026-04-08) — Updated based on Codex and Gemini review feedback.
> See `review-evaluation.md` for detailed evaluation of each review suggestion.

**Goal:** Turn the KaTrain RK3588 smart board into a cross-platform Go hub that connects to OGS, 野狐围棋, 星阵围棋, and potentially 弈城围棋, enabling users to play against opponents on any platform through their physical board. ~~KGS removed from scope (2026-04-09).~~

**Strategy:** OGS first (validate architecture with official API) → 野狐 (largest China user base) → 星阵 → others. ~~KGS skipped (2026-04-09).~~

**Target:** Board/kiosk mode first. Web version can reuse backend but will have different UI.

**Output directory:** `katrain/web/platforms/`

---

## Phase 0: Platform Adapter Infrastructure

**Purpose:** Build the abstraction layer that all platform integrations share. This is the foundation — no platform-specific code yet.

### Step 0.1: Data Models (`katrain/web/platforms/models.py`)

Define shared data models used across all platform adapters:

```python
# Key models to implement:

class GamePhase(str, Enum):
    """Shared game phase model across all platforms."""
    PLAYING = "playing"
    PAUSED = "paused"
    SCORING = "scoring"       # OGS stone removal, etc.
    FINISHED = "finished"

@dataclass
class PlatformCredentials:
    platform: str           # "ogs", "fox", "golaxy", "kgs", "tygem"
    username: str
    # Per-platform auth fields stored as JSON blob
    auth_data: dict         # e.g. {"access_token": "...", "refresh_token": "..."}

@dataclass
class OnlineUser:
    platform: str
    user_id: str            # Platform-specific user ID (string for cross-platform compat)
    username: str
    rank: str               # Normalized display rank, e.g. "3d", "5k"
    rank_numeric: float     # Normalized numeric rank for sorting (higher = stronger)
    status: str             # "idle", "playing", "away"

@dataclass
class PlatformChallenge:
    platform: str
    challenge_id: str
    from_user: OnlineUser
    board_size: int
    time_control: TimeControl
    rules: str              # "chinese", "japanese", "korean", "aga"
    ranked: bool
    handicap: int
    komi: float | None      # None = automatic

@dataclass
class TimeControl:
    system: str             # "byoyomi", "fischer", "canadian", "absolute", "simple"
    main_time: int          # seconds
    # Byo-yomi
    period_time: int | None
    periods: int | None
    # Fischer
    time_increment: int | None
    max_time: int | None
    # Canadian
    stones_per_period: int | None

@dataclass
class ClockState:
    black_time: dict        # Platform-normalized time remaining
    white_time: dict
    current_player: str     # "B" or "W"
    paused: bool

@dataclass
class PlatformMove:
    col: int                # 0-indexed from left
    row: int                # 0-indexed from top
    color: str              # "B" or "W"
    move_number: int

@dataclass
class PlatformGameSession:
    platform: str
    game_id: str
    board_size: int
    my_color: str           # "B" or "W"
    opponent: OnlineUser
    time_control: TimeControl
    rules: str              # "chinese", "japanese", "korean", "aga"
    ranked: bool
    handicap: int
    komi: float

@dataclass
class PlatformGameContext:
    """Tracks the bridge state between a platform game and a local KaTrain session.
    This is the authoritative state for platform games — remote platform is source of truth."""
    session_id: str                     # Local KaTrain session ID
    platform: str
    remote_game_id: str
    game_phase: GamePhase
    last_confirmed_move: int            # Move number of last ACK'd move
    pending_action: str | None          # "move", "pass", "resign", None
    pending_action_timestamp: float | None
    remote_clock_version: int           # Monotonic counter for clock dedup
    needs_resync: bool                  # True if we missed events and need full state fetch
    my_color: str                       # "B" or "W"

    def recover_from_snapshot(self, snapshot: dict) -> None:
        """Reset local state from a full game snapshot fetched after reconnection."""
        ...
```

### Step 0.2: Abstract Adapter Interface (`katrain/web/platforms/base.py`)

```python
class PlatformAdapter(ABC):
    """Base class for all platform adapters."""

    platform_name: str
    supported_board_sizes: list[int]

    # --- Capability declarations ---
    # Subclasses override to declare what they support.
    # Avoids `if platform == ...` in shared code.
    supports_live_play: bool = False
    supports_scoring: bool = False        # Interactive stone removal phase
    supports_automatch: bool = False
    supports_rooms: bool = False          # Room-based lobby (Fox, KGS)
    supports_seek_graph: bool = False     # Open challenge board (OGS)

    # --- Connection lifecycle ---
    async def connect(self, credentials: PlatformCredentials) -> bool
    async def disconnect(self) -> None
    @property
    def is_connected(self) -> bool

    # --- Lobby ---
    async def get_online_users(self, room: str | None = None) -> list[OnlineUser]
    async def get_rooms(self) -> list[dict]        # Platform-specific room structure
    async def get_open_challenges(self) -> list[PlatformChallenge]

    # --- Challenge ---
    async def send_challenge(self, user_id: str, settings: dict) -> str  # returns challenge_id
    async def accept_challenge(self, challenge_id: str) -> PlatformGameSession
    async def decline_challenge(self, challenge_id: str) -> None
    async def create_open_challenge(self, settings: dict) -> str
    async def cancel_challenge(self, challenge_id: str) -> None
    async def start_automatch(self, preferences: dict) -> None
    async def cancel_automatch(self) -> None

    # --- In-game ---
    async def submit_move(self, game_id: str, col: int, row: int) -> bool
    async def submit_pass(self, game_id: str) -> bool
    async def resign(self, game_id: str) -> None
    async def request_undo(self, game_id: str) -> None
    async def accept_undo(self, game_id: str) -> None
    async def fetch_game_snapshot(self, game_id: str) -> dict:
        """Fetch full game state from platform. Used for reconnection state recovery."""
        ...
    async def submit_scoring_action(self, game_id: str, action: dict) -> bool:
        """Platform-specific scoring phase actions (mark dead stones, accept score, etc.)."""
        ...

    # --- Event stream (server-sent events via callbacks) ---
    def on_opponent_move(self, callback: Callable[[PlatformMove], Awaitable[None]]) -> None
    def on_clock_update(self, callback: Callable[[ClockState], Awaitable[None]]) -> None
    def on_challenge_received(self, callback: Callable[[PlatformChallenge], Awaitable[None]]) -> None
    def on_game_started(self, callback: Callable[[PlatformGameSession], Awaitable[None]]) -> None
    def on_game_ended(self, callback: Callable[[str, str, str], Awaitable[None]]) -> None  # game_id, result, winner
    def on_game_phase_changed(self, callback: Callable[[str, GamePhase], Awaitable[None]]) -> None
    def on_automatch_found(self, callback: Callable[[PlatformGameSession], Awaitable[None]]) -> None
    def on_connection_lost(self, callback: Callable[[], Awaitable[None]]) -> None
    def on_reconnected(self, callback: Callable[[], Awaitable[None]]) -> None
    def on_auth_expired(self, callback: Callable[[], Awaitable[None]]) -> None
    def on_token_refreshed(self, callback: Callable[[dict], Awaitable[None]]) -> None
        # ↑ Notifies PlatformManager to persist updated tokens to credential store
```

### Step 0.3: Credential Storage (`katrain/web/platforms/credentials.py`)

Local encrypted credential storage, keyed to the KaTrain user.

**Mandatory encryption — no fallback to plaintext.** Third-party credentials must fail closed
(unlike the existing `katrain/web/core/credentials.py` which degrades when `cryptography` is missing).

- **Storage location:** `~/.katrain/platform_credentials.db` (SQLite)
- **Encryption:** AES-256-GCM via `cryptography.fernet`
- **Key derivation:**
  - **Server mode:** Key derived from KaTrain user password via PBKDF2
  - **Board mode:** Key derived from hardware-bound identifier (RK3588 CPU serial from `/proc/cpuinfo`) + local salt. Prevents credential DB from being decrypted if copied to another device.
- **Schema:**
  ```sql
  CREATE TABLE platform_credentials (
      user_id INTEGER NOT NULL,       -- KaTrain user ID
      platform TEXT NOT NULL,          -- "ogs", "fox", "golaxy", "kgs"
      username TEXT NOT NULL,          -- Platform username
      auth_data_encrypted BLOB NOT NULL, -- Encrypted JSON blob (tokens, NOT passwords)
      created_at TIMESTAMP,
      updated_at TIMESTAMP,
      PRIMARY KEY (user_id, platform)
  );
  ```
- **API:** `save_credentials()`, `load_credentials()`, `delete_credentials()`, `list_platforms(user_id)`
- **Token refresh hook:** When `PlatformAdapter.on_token_refreshed` fires, `PlatformManager` calls `save_credentials()` to persist the new tokens. User does not need to re-login after restart.
- **Unlink UX:** Each platform card has a "断开连接" button that calls `delete_credentials()` and clears all local tokens.

### Step 0.4: Platform Manager (`katrain/web/platforms/manager.py`)

Orchestrates all adapters and bridges them to the existing KaTrain session system:

```python
class PlatformManager:
    """Singleton managing all platform connections for a user."""

    def __init__(self, session_manager: SessionManager):
        self._adapters: dict[str, PlatformAdapter] = {}
        self._session_manager = session_manager
        self._active_games: dict[str, PlatformGameContext] = {}  # game_id -> context

    async def connect_platform(self, platform: str, credentials: PlatformCredentials) -> bool
    async def disconnect_platform(self, platform: str) -> None
    def get_adapter(self, platform: str) -> PlatformAdapter | None
    def list_connected_platforms(self) -> list[str]

    # Bridge: platform game → KaTrain session
    async def start_platform_game(self, platform: str, game_session: PlatformGameSession) -> str:
        """Creates a KaTrain session backed by a platform game. Returns session_id."""
        # 1. Create KaTrain multiplayer session (local user vs. virtual opponent)
        # 2. Set up callbacks: opponent moves → katrain.play(), vision moves → adapter.submit_move()
        # 3. Return session_id for UI to connect

    async def _on_opponent_move(self, game_id: str, move: PlatformMove):
        """Callback: platform opponent played a move → inject into KaTrain game."""
        # 1. Get the KaTrain session for this game
        # 2. Call session.katrain("play", coords) with the opponent's move
        # 3. Broadcast state update to connected WebSockets
        # 4. Update vision expected board state

    async def _on_vision_move(self, game_id: str, col: int, row: int):
        """Bridge: vision detected our move → submit to platform."""
        # 1. Validate it's our turn
        # 2. Call adapter.submit_move(game_id, col, row)
        # 3. On success, play locally too
```

### Step 0.5: Platform Command Gateway (`katrain/web/platforms/gateway.py`)

> **[NEW — from Codex review]** This is the most critical architectural addition.

**Problem:** Currently `/api/move` directly calls `session.katrain("play", coords)`, and
`/api/resign` directly ends the game. In a platform game, these local-first actions cause
state divergence — the local board changes before the remote platform confirms.

**Solution:** A command gateway that intercepts ALL game-modifying actions during platform
games and routes them through the adapter first.

```python
class PlatformCommandGateway:
    """Intercepts game commands for platform-backed sessions.

    For platform games: submit to remote platform → wait for ACK → apply locally.
    For local games: pass through to KaTrain directly (existing behavior).
    """

    def __init__(self, platform_manager: PlatformManager, session_manager: SessionManager):
        self._pm = platform_manager
        self._sm = session_manager

    async def play_move(self, session_id: str, col: int, row: int, user_id: int) -> dict:
        ctx = self._pm.get_game_context(session_id)
        if ctx is None:
            # Not a platform game — pass through to existing logic
            return await self._local_play(session_id, col, row)

        # Platform game — remote first
        ctx.pending_action = "move"
        ctx.pending_action_timestamp = time.time()
        self._broadcast_pending(session_id)  # UI shows "确认中..."

        adapter = self._pm.get_adapter(ctx.platform)
        success = await adapter.submit_move(ctx.remote_game_id, col, row)

        if success:
            ctx.pending_action = None
            ctx.last_confirmed_move += 1
            result = await self._local_play(session_id, col, row)
            return result
        else:
            ctx.pending_action = None
            self._broadcast_rejected(session_id)  # UI shows rejection
            raise PlatformMoveRejectedError()

    async def pass_move(self, session_id: str, user_id: int) -> dict:
        """Same pattern: remote ACK first, then local."""
        ...

    async def resign(self, session_id: str, user_id: int) -> dict:
        """Same pattern: remote resign first, then local."""
        ...

    async def request_count(self, session_id: str, user_id: int) -> dict:
        """Route to platform scoring phase if supported."""
        ...
```

**Integration with existing server.py:**

The existing `/api/move`, `/api/resign`, `/api/pass` endpoints are modified to check if the
session has an active `PlatformGameContext`. If yes, they delegate to the gateway instead
of calling `session.katrain()` directly. This is a minimal change to `server.py`:

```python
# Before (server.py /api/move):
session.katrain("play", coords)

# After:
if app.state.platform_manager.is_platform_game(session_id):
    result = await app.state.gateway.play_move(session_id, col, row, user_id)
else:
    session.katrain("play", coords)  # existing behavior unchanged
```

**Vision move poller integration:**

The `_vision_move_poller` also routes through the gateway for platform games:
```python
# Before:
vision_move_to_katrain(col, row, color)
session.katrain("play", move.coords)

# After:
if platform_manager.is_platform_game(session_id):
    await gateway.play_move(session_id, col, row, user_id)
else:
    session.katrain("play", move.coords)
```

### Step 0.6: REST API Endpoints (`katrain/web/api/v1/endpoints/platforms.py`)

New endpoints for the frontend:

```
# Credential management
POST   /api/v1/platforms/{platform}/login     — Login to a platform
DELETE /api/v1/platforms/{platform}/logout     — Logout from a platform
GET    /api/v1/platforms/status                — List all platforms + connection status

# Lobby
GET    /api/v1/platforms/{platform}/users      — Online user list
GET    /api/v1/platforms/{platform}/rooms       — Room/channel list
GET    /api/v1/platforms/{platform}/challenges  — Open challenges

# Challenge flow
POST   /api/v1/platforms/{platform}/challenge          — Send challenge to a user
POST   /api/v1/platforms/{platform}/challenge/accept    — Accept incoming challenge
POST   /api/v1/platforms/{platform}/challenge/decline   — Decline incoming challenge
POST   /api/v1/platforms/{platform}/automatch/start     — Start automatch
POST   /api/v1/platforms/{platform}/automatch/cancel    — Cancel automatch

# In-game (uses existing /api/move, /api/resign, etc. with platform bridge)
```

### Step 0.7: WebSocket Extensions

Extend the existing `/ws/lobby` and `/ws/{session_id}` protocols with platform events:

```json
// === Lobby events (Server → Client) ===

// Happy path
{"type": "platform_challenge", "platform": "ogs", "challenge": {...}}
{"type": "platform_challenge_withdrawn", "platform": "ogs", "challenge_id": "..."}
{"type": "platform_game_started", "platform": "ogs", "session_id": "...", "game": {...}}
{"type": "platform_game_ended", "platform": "ogs", "game_id": "...", "result": "B+5.5"}
{"type": "platform_status", "platform": "ogs", "connected": true}
{"type": "platform_automatch_found", "platform": "ogs", "session_id": "...", "game": {...}}

// Error / degraded states [NEW — from Codex review]
{"type": "platform_auth_expired", "platform": "ogs"}
{"type": "platform_connection_degraded", "platform": "ogs", "reason": "high_latency"}

// === In-game events (Server → Client on /ws/{session_id}) ===

// Move lifecycle [NEW — from Codex review]
{"type": "platform_move_pending", "col": 3, "row": 15}
{"type": "platform_move_confirmed", "col": 3, "row": 15, "move_number": 42}
{"type": "platform_move_rejected", "reason": "not_your_turn"}

// State recovery [NEW — from Codex review]
{"type": "platform_resync_required", "reason": "missed_events"}
{"type": "platform_resync_complete", "moves_recovered": 2}

// Game phase [NEW — from reviews]
{"type": "platform_phase_changed", "phase": "scoring"}

// Clock
{"type": "clock_update", "black_time": {...}, "white_time": {...}, "current_player": "B"}
```

### Step 0.8: Database Schema Addition

New table for cross-platform game records:

```sql
CREATE TABLE platform_games (
    id TEXT PRIMARY KEY,                -- KaTrain game UUID
    user_id INTEGER NOT NULL REFERENCES users(id),
    platform TEXT NOT NULL,             -- "ogs", "fox", etc.
    platform_game_id TEXT NOT NULL,     -- ID on the remote platform
    opponent_name TEXT,
    opponent_rank TEXT,
    my_color TEXT,                      -- "B" or "W"
    result TEXT,                        -- "B+5.5", "W+R", etc.
    board_size INTEGER DEFAULT 19,
    sgf_content TEXT,
    played_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_game_id)
);
```

---

## Phase 1: OGS Integration

**Purpose:** First working platform adapter. Validates the entire architecture end-to-end.

### Step 1.0: OGS Protocol Spike (1-2 days) [NEW — from Codex review]

> **Before writing the adapter, verify the current state of OGS APIs.**
> OGS is actively migrating from socket.io to native WebSocket. The plan must be based on
> verified facts, not assumptions from potentially stale documentation.

**Spike deliverables:**
1. Verify which auth methods currently work: OAuth2 (password grant? PKCE?), session login, bot API key
2. Verify which real-time protocol works: socket.io (`/socket.io/`) vs native WebSocket (`wss://ggs.online-go.com`)
3. Write a minimal Python script that: authenticates → connects WebSocket → joins a game → receives a move event
4. Document the verified protocol in `katrain/web/platforms/ogs/PROTOCOL.md`

**References:**
- [OGS API docs](https://docs.online-go.com/)
- [OGS OAuth2 docs](https://docs.online-go.com/oauth2.html)
- [OGS realtime protocol](https://docs.online-go.com/goban/modules/protocol.html)
- [goban library source](https://github.com/online-go/goban) — authoritative protocol definitions
- [gtp2ogs source](https://github.com/online-go/gtp2ogs) — working bot implementation

**Freeze the adapter design only after the spike confirms the viable protocol path.**

### Step 1.1: OGS Adapter (`katrain/web/platforms/ogs/adapter.py`)

Implement `PlatformAdapter` for OGS.

**Dependencies:** `websockets` (for native WS) or `python-socketio[asyncio_client]` (fallback), `httpx` (already in project)

**Authentication flow (to be confirmed by spike):**

**Primary path — native WebSocket + JWT:**
1. Session login: `POST /api/v0/login` with `{username, password}`
2. Fetch JWT from `GET /api/v1/ui/config` → get `user_jwt`, `chat_auth`, `notification_auth`
3. Connect native WebSocket to `wss://ggs.online-go.com` (or `wss://online-go.com/socket.io/` as fallback)
4. Authenticate with JWT via `["authenticate", {"jwt": "...", ...}]`
5. Store JWT + refresh mechanism in credentials DB
6. `on_token_refreshed` callback updates stored credentials

**Fallback path — socket.io (if native WS not yet stable):**
1. Same auth, but connect via `python-socketio` to `https://online-go.com/socket.io/`
2. Messages wrapped in socket.io framing (`42["event", data]`)

### Step 1.2: OGS Realtime Client (`katrain/web/platforms/ogs/realtime_client.py`)

Core real-time communication. **Prefer native WebSocket; fall back to socket.io.**

```python
class OGSRealtimeClient:
    """Manages WebSocket connection to OGS.

    Supports two transports (determined by protocol spike):
    - Native WebSocket: wss://ggs.online-go.com (preferred, forward-looking)
    - Socket.io: https://online-go.com/socket.io/ (fallback if native not stable)

    Wire format (native WS):
      Client→Server: [command, data, optional_request_id]
      Server→Client: [event_name, data] or [request_id, data, error]
    """

    def __init__(self, base_url="https://online-go.com", transport="native"):
        self._transport = transport  # "native" or "socketio"
        self._ws = None              # websockets.WebSocketClientProtocol (native)
        self._sio = None             # socketio.AsyncClient (fallback)
        self._authenticated = asyncio.Event()
        self._callbacks: dict[str, list[Callable]] = {}
        self._request_id = 0
        self._latency = 0
        self._drift = 0

    async def connect(self, jwt: str, user_id: int, username: str):
        if self._transport == "native":
            self._ws = await websockets.connect("wss://ggs.online-go.com")
            await self._send("authenticate", {
                "jwt": jwt,
                "player_id": user_id,
                "username": username,
                "device_id": str(uuid.uuid4()),
                "client": "KaTrain-SmartBoard",
                "client_version": "0.1"
            })
            asyncio.create_task(self._receive_loop())
        else:
            # socket.io fallback
            self._sio = socketio.AsyncClient(reconnection=True)
            await self._sio.connect(f"{self._base_url}/socket.io/", transports=["websocket"])
            await self._sio.emit("authenticate", {...})
        asyncio.create_task(self._ping_loop())

    async def _send(self, command: str, data: dict, request_id: int | None = None):
        msg = [command, data] if request_id is None else [command, data, request_id]
        await self._ws.send(json.dumps(msg))

    async def _receive_loop(self):
        async for raw in self._ws:
            msg = json.loads(raw)
            if isinstance(msg[0], str):
                event, data = msg[0], msg[1] if len(msg) > 1 else {}
                await self._dispatch(event, data)
            elif isinstance(msg[0], int):
                request_id, data, error = msg[0], msg[1], msg[2] if len(msg) > 2 else None
                await self._resolve_request(request_id, data, error)

    async def game_connect(self, game_id: int):
        await self._send("game/connect", {"game_id": game_id, "chat": False})

    async def game_move(self, game_id: int, col: int, row: int, board_size: int = 19):
        sgf_move = chr(ord('a') + col) + chr(ord('a') + row)
        await self._send("game/move", {"game_id": game_id, "move": sgf_move})

    async def game_pass(self, game_id: int):
        await self._send("game/move", {"game_id": game_id, "move": ".."})

    async def game_resign(self, game_id: int):
        await self._send("game/resign", {"game_id": game_id})

    async def seek_graph_connect(self):
        await self._send("seek_graph/connect", {"channel": "global"})

    async def automatch_find(self, uuid: str, preferences: dict):
        await self._send("automatch/find_match", {"uuid": uuid, **preferences})

    async def automatch_cancel(self, uuid: str):
        await self._send("automatch/cancel", {"uuid": uuid})

    def on(self, event: str, handler: Callable): ...

    async def _ping_loop(self):
        while self._connected:
            await self._send("net/ping", {
                "client": int(time.time() * 1000),
                "drift": self._drift,
                "latency": self._latency
            })
            await asyncio.sleep(15)
```

**Key event mappings:**

| OGS Event | Handler | Action |
|-----------|---------|--------|
| `game/{id}/gamedata` | `_on_gamedata` | Initialize game state, determine turns |
| `game/{id}/move` | `_on_move` | Callback `on_opponent_move` |
| `game/{id}/clock` | `_on_clock` | Callback `on_clock_update` |
| `game/{id}/phase` | `_on_phase` | Handle stone removal / game end |
| `active_game` | `_on_active_game` | Track active games |
| `notification` | `_on_notification` | Route challenges |
| `seekgraph/global` | `_on_seekgraph` | Update open challenges list |
| `automatch/start` | `_on_automatch` | Callback `on_automatch_found` |
| `net/pong` | `_on_pong` | Update latency/drift |

### Step 1.3: OGS REST Client (`katrain/web/platforms/ogs/rest_client.py`)

```python
class OGSRestClient:
    BASE_URL = "https://online-go.com"

    async def login(self, username: str, password: str) -> dict:
        """Session login → fetch JWT from ui/config."""

    async def get_user_info(self) -> dict:
        """GET /api/v1/me/"""

    async def search_players(self, query: str) -> list[dict]:
        """GET /api/v1/players/?username__startswith=query"""

    async def challenge_player(self, player_id: int, settings: dict) -> tuple[int, int]:
        """POST /api/v1/players/{id}/challenge/ → (challenge_id, game_id)"""

    async def accept_challenge(self, challenge_id: int) -> dict:
        """POST /api/v1/me/challenges/{id}/accept"""

    async def decline_challenge(self, challenge_id: int) -> None:
        """POST /api/v1/me/challenges/{id} with {delete: true}"""

    async def get_game_sgf(self, game_id: int) -> str:
        """GET /api/v1/games/{id}/sgf"""

    async def get_active_games(self) -> list[dict]:
        """GET /api/v1/ui/overview → active games"""
```

### Step 1.4: Coordinate Translation Utilities (`katrain/web/platforms/coords.py`)

```python
def katrain_to_sgf(col: int, row: int) -> str:
    """KaTrain 0-indexed (col, row) from top-left → SGF 'ab' format."""
    return chr(ord('a') + col) + chr(ord('a') + row)

def sgf_to_katrain(sgf_move: str) -> tuple[int, int]:
    """SGF 'ab' → KaTrain (col, row)."""
    return (ord(sgf_move[0]) - ord('a'), ord(sgf_move[1]) - ord('a'))

def katrain_to_gtp(col: int, row: int, board_size: int = 19) -> str:
    """KaTrain (col, row) → GTP 'D4' format (skip I, row from bottom)."""
    gtp_col = chr(ord('A') + col + (1 if col >= 8 else 0))  # Skip 'I'
    gtp_row = board_size - row
    return f"{gtp_col}{gtp_row}"

def gtp_to_katrain(gtp_move: str, board_size: int = 19) -> tuple[int, int]:
    """GTP 'D4' → KaTrain (col, row)."""
    col_char = gtp_move[0].upper()
    col = ord(col_char) - ord('A') - (1 if col_char > 'I' else 0)
    row = board_size - int(gtp_move[1:])
    return (col, row)
```

### Step 1.5: Integration with Vision Move Poller

Modify the existing `_vision_move_poller` in `server.py` to route through the command gateway:

```python
# Current flow:
#   vision detects move → katrain.play(coords) → broadcast

# New flow for platform games:
#   vision detects move → gateway.play_move() →
#     1. Broadcast "platform_move_pending" to UI (shows "确认中..." overlay)
#     2. Lock further vision moves (reject new detections until ACK/reject)
#     3. Submit to remote platform
#     4. On ACK: apply locally + broadcast "platform_move_confirmed"
#     5. On reject: broadcast "platform_move_rejected" + unlock
#     6. On timeout (5s): broadcast rejection + unlock + log warning
#   For local games: katrain.play(coords) directly (existing behavior unchanged)
```

**Move confirmation UX** [NEW — from both reviews]:

The 100-500ms gap between vision detection and platform ACK is critical. Users may:
- Try to adjust the stone they just placed
- Place the next stone before the previous one is confirmed

**Solution:**
1. **Immediate UI feedback:** Broadcast `platform_move_pending` the instant vision confirms a move.
   Frontend shows a pulsing "确认中..." overlay on the stone position.
2. **Input lock:** Vision move poller ignores new detections while `pending_action is not None`.
   Screen touch moves are also blocked by the command gateway.
3. **Audio feedback:** Play a distinct "submitting" sound, different from the normal stone click.
4. **Timeout:** If no ACK within 5 seconds, treat as failure. Show error, unlock inputs.

### Step 1.6: Timer Display Integration

OGS clock events need to be forwarded to the frontend:

- Parse OGS `ClockState` into normalized `ClockState` model
- Broadcast clock updates via the game session WebSocket:
  ```json
  {"type": "clock_update", "black_time": {...}, "white_time": {...}, "current_player": "B"}
  ```
- Frontend displays countdown timer (new React component)

### Step 1.7: Testing Strategy [REVISED — from both reviews]

**Three layers of automated testing:**

**Layer 1: Adapter Contract Tests** (`tests/platforms/test_adapter_contract.py`)
- Verify all PlatformAdapter subclasses implement the required interface correctly
- Test capability flag declarations match actual method implementations
- Test coordinate translation roundtrips (katrain↔sgf↔gtp)

**Layer 2: Record/Replay Transport Tests** (`tests/platforms/ogs/test_ogs_replay.py`)
- Capture real OGS WebSocket transcripts (auth → game connect → moves → finish)
- Save as JSON fixtures in `tests/data/ogs_transcripts/`
- Replay against OGSRealtimeClient with a mock WebSocket server
- Test: message parsing, event dispatch, clock state tracking, reconnection recovery
- Test edge cases: duplicate events, out-of-order moves, ACK timeout

**Layer 3: PlatformManager Bridge Tests** (`tests/platforms/test_gateway.py`)
- Test PlatformCommandGateway with a mock adapter:
  - Move submission: pending → confirmed → local apply
  - Move rejection: pending → rejected → unlock
  - Timeout: pending → 5s → auto-reject → unlock
  - Resign flow: remote resign ACK → local game end
- Test PlatformGameContext state transitions:
  - Normal play → scoring → finished
  - Disconnection → needs_resync → recover_from_snapshot
  - Auth expired → re-login → resume

**Manual E2E Checklist** (run against live OGS with test account):

1. [ ] Login to OGS from KaTrain UI → credentials saved locally
2. [ ] View online users / seek graph
3. [ ] Send challenge to an OGS user → opponent sees challenge on OGS
4. [ ] Accept incoming challenge → game session created
5. [ ] Place stone on physical board → "确认中" shown → move appears on OGS
6. [ ] Opponent plays on OGS → audio cue + move displayed on KaTrain screen
7. [ ] Timer counts down correctly on both sides
8. [ ] Pass → stone removal → game ends correctly
9. [ ] Resign works
10. [ ] SGF saved locally after game ends
11. [ ] Reconnection after network interruption (kill WiFi for 10s, reconnect)
12. [ ] Multiple consecutive games without re-login
13. [ ] Token refresh after restart (no re-login needed)

---

## Phase 2: 野狐围棋 (Fox Weiqi) Integration

**Purpose:** Cover the largest Chinese Go community. Uses reverse-engineered protocol.

### Step 2.0: Fox Research Spike (2-3 days) [REVISED — from Codex review]

> **Do NOT start building the adapter before validating feasibility.**
> The old plan of "start with read-only proxy, then add live play" is wrong — the proxy
> doesn't cover the hard parts (login persistence, real-time events, move ACK, reconnection).

**Spike objectives:**
1. Clone `ale64bit/WeiqiHub` (Flutter/Dart, BSD-3), study the protobuf definitions and connection flow
2. Attempt to authenticate to Fox servers using a test account from Python (port the minimal auth flow)
3. Assess: Can we reliably establish and maintain a TCP connection? How often does the protocol change?
4. Check WalrusWQ (walruswq.com) and MiniFox for additional reverse-engineering notes
5. Document findings in `katrain/web/platforms/fox/PROTOCOL.md`

**Spike deliverables — one of:**
- **GO:** "Live play is feasible, here's the minimal working auth + move flow in Python" → proceed to Step 2.1
- **NO-GO:** "Protocol is too unstable / account gets banned / can't maintain connection" → defer Fox, move to Phase 3

**References:**
- [WeiqiHub](https://github.com/ale64bit/WeiqiHub) — Flutter client with full Fox protocol (BSD-3)
- [openfoxwq API](https://github.com/openfoxwq/api) — Community REST proxy (read-only)
- [WalrusWQ](https://walruswq.com) — Web client by the same developer

### Step 2.1: Fox Adapter (`katrain/web/platforms/fox/adapter.py`)

**Only proceed here if the spike produces a GO decision.**

Port the WeiqiHub protocol to Python:

```python
class FoxProtocolClient:
    """Low-level protobuf TCP client for Fox Weiqi."""

    async def connect(self, host: str, port: int): ...
    async def authenticate(self, username: str, password_md5: str): ...
    async def enter_room(self, room_id: int): ...
    async def get_room_users(self, room_id: int) -> list: ...
    async def send_challenge(self, user_id: int, settings: dict): ...
    async def play_move(self, game_id: int, col: int, row: int): ...
```

**Key differences from OGS:**
- Binary protobuf over TCP instead of JSON over WebSocket
- MD5 password hashing (not plain text)
- Room-based lobby structure (users join specific rooms by rank)
- Different coordinate system (needs translation layer)
- No official documentation — rely entirely on WeiqiHub source

**Capability flags:** `supports_rooms=True`, `supports_live_play=True`, `supports_automatch=False` (Fox uses room-based matching)

### Step 2.2: Risk Mitigation

- Protocol may change without notice → version detection + graceful degradation
- Account ban risk → use dedicated test accounts, not primary accounts
- Legal: experimental feature only, not for commercial release without official partnership

---

## Phase 3: 星阵围棋 (Golaxy / 19x19.com) Integration

**Purpose:** Second Chinese platform. Web-based protocols (REST + real-time WebSocket).

### Step 3.0: Golaxy Discovery Spike (2-3 days) [REVISED — from Codex review]

> **Don't assume STOMP/SockJS until verified by traffic capture.**
> The JS bundle hints at STOMP, but the actual live-play protocol may differ.
> SockJS session establishment, heartbeat, and fallback transport add hidden complexity.

**Spike objectives:**
1. Register a test account on 19x19.com (requires +86 phone number)
2. Use browser DevTools to capture the complete API traffic during:
   - Login flow (verify OAuth2 token endpoint and parameters)
   - Entering a game room / matchmaking
   - Playing a full game (move submission, opponent move reception, clock updates)
   - Game ending / scoring
3. Verify: Is the real-time channel actually STOMP? Or plain WebSocket? Or something else?
4. Document all discovered endpoints, message formats, and auth headers

**Spike deliverables:**
- `katrain/web/platforms/golaxy/PROTOCOL.md` — Fact table:
  - Verified auth flow (OAuth2 endpoint, grant type, client credentials)
  - REST endpoints for game/social/matchmaking
  - Real-time protocol: transport (WebSocket/SockJS/STOMP), message format, subscription model
  - GO/NO-GO decision for live play implementation

### Step 3.1: Golaxy Adapter (`katrain/web/platforms/golaxy/adapter.py`)

**Only proceed after discovery spike confirms the protocol.**

**Known auth flow (from JS bundle analysis):**
1. `POST /api/auth/oauth/token` with Basic Auth header `golaxy_web:xingzhen0730`
2. Body: `grant_type=password&username=PHONE&password=PWD` (phone number login)
3. Response: `{access_token, refresh_token, token_type, expires_in}`
4. Use Bearer token for all subsequent REST calls

**Known endpoints (from JS bundle, to be verified by spike):**
- `/api/social/...` — Matchmaking, game rooms, user lists
- `/api/game/...` — Game creation, move submission, game records
- `/api/engine/dcnn/genmove` — AI moves (not needed for our use case)

### Step 3.2: Golaxy Realtime Client

Implementation depends on spike findings. Possible outcomes:

**If STOMP over SockJS (as suggested by JS bundle):**
```python
class GolaxyStompClient:
    async def connect(self, token: str): ...
    async def subscribe(self, destination: str, callback: Callable): ...
    async def send(self, destination: str, body: dict): ...
```
Dependencies: `stomp.py` or `aiostomp`

**If plain WebSocket:**
```python
class GolaxyWebSocketClient:
    async def connect(self, url: str, token: str): ...
    # Similar pattern to OGS realtime client
```
Dependencies: `websockets`

**Limitation:** Golaxy requires +86 phone number for registration. International users cannot use this platform.

---

## ~~Phase 4: KGS Integration~~ — SKIPPED

> **Decision (2026-04-09):** KGS registration is problematic and the platform's user base is declining.
> Deprioritized indefinitely. The existing `katrain/web/platforms/kgs/` skeleton can be removed or left as-is.
> If revisited later, the `PlatformAdapter` infrastructure supports adding it back.

---

## Phase 5: Frontend UI

**Purpose:** React components for platform selection, lobby browsing, and in-game overlay.

**Entry point:** 方案 A — "跨平台对弈" 作为 PlayPage "人人对弈" 分组下的第三张 ModeCard。

### Step 5.0: PlayPage Card Layout Adjustment

Current PlayPage has 4 ModeCards (AI×2 + PvP×2) that are too large — adding a 5th card
would require scrolling on the 1024×600 / 1280×800 kiosk touchscreen.

**Changes to `kiosk/pages/PlayPage.tsx`:**
1. Reduce ModeCard sizes so all 5 cards (AI free, AI ranked, local PvP, online lobby, **cross-platform**) fit on one screen without scrolling
2. Add "跨平台对弈" card under "人人对弈" section:
   - Icon: globe/network icon
   - Title: "跨平台对弈"
   - Subtitle: "连接 OGS、野狐等平台"
   - Route: `/kiosk/play/cross-platform`

**Navigation flow:**
```
PlayPage "跨平台对弈" card
  → /kiosk/play/cross-platform (PlatformConnectPage)
    → 选择/登录平台
      → /kiosk/play/cross-platform/lobby (PlatformLobbyPage)
        → 挑战/接受对局
          → /kiosk/play/pvp/room/:sessionId (reuse existing GamePage)
```

### Step 5.1: Platform Connection Page (`kiosk/pages/PlatformConnectPage.tsx`)

- Grid of platform cards (OGS, 野狐, 星阵, KGS)
- Each card shows: platform logo, connection status (connected/disconnected), username if connected
- Click to login/manage credentials
- Login modal per platform with platform-specific fields
- Connected platforms have "进入大厅" button → navigates to lobby with that platform pre-selected

### Step 5.2: Platform Lobby Page (`kiosk/pages/PlatformLobbyPage.tsx`)

- Tab bar: one tab per connected platform
- Each tab shows that platform's online user list:
  - User avatar/rank/status
  - "Challenge" button per user
  - Search/filter by rank range
- Open challenges section (seek graph for OGS)
- Automatch button with preferences (board size, time control, rank range)
- Incoming challenge notifications (toast/modal)

### Step 5.3: Platform Game Page (extend existing `GamePage.tsx`)

Reuse the existing game board component, adding:
- **Opponent move indicator:** Highlighted intersection showing where opponent played (flash animation)
- **Opponent move audio cue** [NEW]: Distinct sound when remote opponent plays. Critical because user may be looking at the physical board, not the screen.
- **Move pending overlay** [NEW]: "确认中..." pulsing overlay on the stone position while waiting for platform ACK. Blocks further input.
- **Clock display:** Two timers (black/white) showing remaining time in platform's time control format
- **Platform badge:** Small indicator showing which platform this game is on
- **Connection status:** Green/yellow/red dot for platform connection health
- **Error states** [NEW]: Banners for "platform_move_rejected", "platform_resync_required", "platform_auth_expired"

### Step 5.4: Timer Component (`PlatformTimer.tsx`)

```typescript
interface TimerProps {
  blackTime: ClockState;
  whiteTime: ClockState;
  currentPlayer: "B" | "W";
  timeControl: TimeControl;
}

// Renders:
// - Main time countdown (mm:ss or hh:mm:ss)
// - Byo-yomi: periods remaining (e.g., "3 × 30s") as visual dots
// - Fischer: increment indicator (e.g., "+10s")
// - Canadian: remaining stones in period (e.g., "剩余 8 手 / 5分钟")
// - Absolute: simple countdown
// - Visual urgency (color change when < 30s, flash when < 10s)
// - Sound alert at 10s, 5s, 1s
```

**Touch target requirements** [from both reviews]:
- All interactive elements ≥ 44×44px (Apple HIG / Material Design standard)
- Timer buttons, challenge accept/decline, resign button, lobby user rows
- On 1024×600 screen: compact layout with bottom sheet for lobby sidebar on small screens

### Step 5.5: API Client Extensions (`api.ts`)

```typescript
// New API calls
export const PlatformAPI = {
  login: (platform: string, credentials: object) => post(`/api/v1/platforms/${platform}/login`, credentials),
  logout: (platform: string) => del(`/api/v1/platforms/${platform}/logout`),
  getStatus: () => get('/api/v1/platforms/status'),
  getUsers: (platform: string) => get(`/api/v1/platforms/${platform}/users`),
  getRooms: (platform: string) => get(`/api/v1/platforms/${platform}/rooms`),
  getChallenges: (platform: string) => get(`/api/v1/platforms/${platform}/challenges`),
  sendChallenge: (platform: string, data: object) => post(`/api/v1/platforms/${platform}/challenge`, data),
  acceptChallenge: (platform: string, data: object) => post(`/api/v1/platforms/${platform}/challenge/accept`, data),
  startAutomatch: (platform: string, prefs: object) => post(`/api/v1/platforms/${platform}/automatch/start`, prefs),
  cancelAutomatch: (platform: string) => post(`/api/v1/platforms/${platform}/automatch/cancel`),
}
```

### Step 5.6: WebSocket Hook Extensions (`usePlatformEvents.ts`)

```typescript
// Extend useGameSession or create new hook
function usePlatformEvents(lobbySocket: WebSocket) {
  // Listen for platform-specific lobby events:
  // - platform_challenge → show incoming challenge modal
  // - platform_game_started → navigate to game page
  // - platform_game_ended → show result
  // - platform_status → update connection indicators
  // - platform_automatch_found → navigate to game page
}
```

---

## File Structure Summary

```
katrain/web/platforms/
├── __init__.py
├── base.py              # PlatformAdapter ABC + capability declarations
├── models.py            # Shared data models (GamePhase, PlatformGameContext, etc.)
├── coords.py            # Coordinate translation utilities
├── credentials.py       # Encrypted credential storage (fail-closed, hardware-bound key)
├── manager.py           # PlatformManager orchestrator
├── gateway.py           # PlatformCommandGateway [NEW] — intercepts all game commands
├── ogs/
│   ├── __init__.py
│   ├── adapter.py        # OGSAdapter(PlatformAdapter)
│   ├── realtime_client.py # Native WebSocket client (socket.io fallback)
│   ├── rest_client.py    # HTTP client
│   └── PROTOCOL.md       # Verified protocol docs (from spike)
├── fox/
│   ├── __init__.py
│   ├── adapter.py        # FoxAdapter(PlatformAdapter)
│   ├── protocol.py       # Protobuf TCP client
│   └── PROTOCOL.md       # Reverse-engineering docs (from spike)
├── golaxy/
│   ├── __init__.py
│   ├── adapter.py        # GolaxyAdapter(PlatformAdapter)
│   ├── realtime_client.py # Transport TBD by discovery spike
│   ├── rest_client.py    # HTTP client
│   └── PROTOCOL.md       # Discovery docs (from spike)
└── kgs/
    ├── __init__.py
    ├── adapter.py        # KGSAdapter(PlatformAdapter)
    └── json_client.py    # HTTP polling client

katrain/web/api/v1/endpoints/
└── platforms.py          # New REST endpoints

katrain/web/ui/src/
├── kiosk/pages/                # Board-first: cross-platform UI lives in kiosk mode
│   ├── PlatformConnectPage.tsx    # Platform login/management
│   └── PlatformLobbyPage.tsx      # Per-platform lobby
├── components/
│   ├── PlatformTimer.tsx           # Clock display (byo-yomi, fischer, canadian)
│   ├── PlatformBadge.tsx           # Platform indicator
│   ├── OpponentMoveIndicator.tsx   # Move highlight overlay + audio cue
│   └── MovePendingOverlay.tsx      # [NEW] "确认中..." overlay during platform ACK wait
├── hooks/
│   └── usePlatformEvents.ts        # WebSocket event hook (incl. error/degraded states)
└── api.ts                          # Extended API client

tests/platforms/
├── test_adapter_contract.py        # [NEW] Contract tests for all adapters
├── test_gateway.py                 # [NEW] Command gateway state machine tests
├── test_coords.py                  # Coordinate translation roundtrip tests
├── ogs/
│   ├── test_ogs_replay.py          # [NEW] Record/replay transport tests
│   └── fixtures/                   # Captured WebSocket transcripts
└── data/                           # Shared test fixtures
```

---

## Dependencies to Add

```
# Python (add to requirements-web.txt)
websockets>=12.0                       # OGS native WebSocket (primary)
python-socketio[asyncio_client]>=5.0   # OGS socket.io (fallback, may not be needed)
# stomp.py — add only if Golaxy spike confirms STOMP
protobuf>=4.0                           # Fox Weiqi protocol (add only after Fox spike GO)
cryptography>=41.0                      # Credential encryption (mandatory, no fallback)

# Frontend (add to katrain/web/ui/package.json)
# No new dependencies expected — existing WebSocket + fetch sufficient
```

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| OGS changes socket.io → native WebSocket | Medium | Medium (in progress) | Support both transports, monitor goban repo |
| Fox protocol changes | High | Medium | Version detection, WeiqiHub community tracks changes |
| Golaxy API undocumented, may change | High | Medium | Pin to known working endpoints, browser-based monitoring |
| KGS JSON API stale docs | Low | High | Test against live server, ShinKGS as reference |
| Account bans on non-official clients | Medium | Low (Fox/Golaxy) | Dedicated test accounts, user warnings in UI |
| Network latency on RK3588 (WiFi) | Medium | Medium | Async I/O, connection health monitoring, auto-reconnect |
| Vision move + platform move race condition | High | Medium | Submit to platform FIRST, play locally only on ACK |

---

## Milestones & Checkpoints

| Milestone | Deliverable | Checkpoint Criteria |
|-----------|-------------|-------------------|
| **M0** | Platform infrastructure | `PlatformAdapter` + `PlatformCommandGateway` + `PlatformGameContext` + credential storage + contract tests pass |
| **M1-spike** | OGS protocol spike | Verified auth + realtime protocol, minimal Python script connects and receives events |
| **M1a** | OGS auth + lobby | Can login, see online users, see seek graph |
| **M1b** | OGS live play | Can play a complete game: challenge → moves → resign/finish (screen only) |
| **M1c** | OGS + vision + gateway | Physical board moves go through gateway → OGS ACK → local apply, with "确认中" UX |
| **M1d** | OGS + timer + audio | Clock displays correctly, opponent move audio cue, low-time warning |
| **M1e** | OGS reconnection | Network drop → reconnect → resync state → resume game |
| **M2-spike** | Fox research spike | GO/NO-GO decision with evidence: working auth in Python, or documented blocker |
| **M2a** | Fox auth + lobby | Can login, enter room, see users (if GO) |
| **M2b** | Fox live play | Can play a complete game (if GO) |
| **M3-spike** | Golaxy discovery spike | Protocol fact table: verified auth, REST endpoints, real-time transport and message format |
| **M3a** | Golaxy auth + lobby | Can login, see users (if GO) |
| **M3b** | Golaxy live play | Can play a complete game (if GO) |
| ~~**M4**~~ | ~~KGS integration~~ | ~~SKIPPED — registration issues, declining user base~~ |
| **M5** | UI polish | Platform selection, lobby tabs, timer, move indicators, touch targets ≥ 44px |

---

## Open Questions

1. **OGS OAuth2 app registration:** Need to register our app at `online-go.com/oauth2/applications/` — do we use a shared KaTrain client_id, or per-device?
   - **Recommendation:** Single shared client_id for all KaTrain boards, stored in config.

2. **Fox account registration:** WeiqiHub uses phone number registration — how do we handle this in the KaTrain UI?
   - **Recommendation:** User registers on Fox mobile app first, then enters credentials in KaTrain.

3. **Golaxy phone-only auth:** Golaxy requires +86 phone number — international users can't use it.
   - **Recommendation:** Note this limitation in UI. Focus on Chinese users for Golaxy.

4. **Stone removal phase:** OGS has a stone removal scoring phase — do we support this on the physical board?
   - **Recommendation:** Phase 1 handle via screen UI only (tap to mark dead stones). Physical board stone removal later. `GamePhase.SCORING` is now part of the shared model.

5. **Simultaneous platform games:** Can a user play on two platforms at once?
   - **Recommendation:** No, one active platform game at a time for MVP. Physical board can only track one game.

6. **Frontend placement: kiosk vs galaxy?** [NEW — from Codex review]
   - The codebase has two UI modes: `kiosk/` (board mode) and `galaxy/` (web mode).
   - Cross-platform play is primarily a board/kiosk feature.
   - **Decision: `kiosk/pages/`** — board-first. Galaxy/web shares backend APIs but gets its own UI later.

7. **Screen vs physical board input for platform games?** [NEW — from Codex review]
   - Both screen touch and physical board (vision) are allowed as input methods.
   - Both go through the PlatformCommandGateway — same remote-first flow.
