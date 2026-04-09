"""OGS platform adapter — connects KaTrain to online-go.com."""

from __future__ import annotations

import logging
import time
from typing import Optional

from katrain.web.platforms.base import PlatformAdapter
from katrain.web.platforms.coords import katrain_to_sgf, sgf_to_katrain
from katrain.web.platforms.models import (
    ClockState,
    GamePhase,
    OnlineUser,
    PlatformChallenge,
    PlatformCredentials,
    PlatformGameSession,
    PlatformMove,
    TimeControl,
)
from katrain.web.platforms.ogs.realtime_client import OGSRealtimeClient
from katrain.web.platforms.ogs.rest_client import OGSRestClient

logger = logging.getLogger("katrain_web")


def _parse_rank(ranking: float) -> tuple[str, float]:
    """Convert OGS numeric ranking to display rank and numeric value.

    OGS ranking: 0 = 30k, 29 = 1k, 30 = 1d, 38 = 9d, 39+ = pro
    """
    if ranking < 30:
        kyu = 30 - int(ranking)
        return f"{kyu}k", ranking
    else:
        dan = int(ranking) - 29
        return f"{dan}d", ranking


def _parse_time_control(tc: dict) -> TimeControl:
    """Parse OGS time control dict into our TimeControl model."""
    system = tc.get("system", tc.get("time_control", "byoyomi"))
    return TimeControl(
        system=system,
        main_time=tc.get("main_time", 0),
        period_time=tc.get("period_time"),
        periods=tc.get("periods"),
        time_increment=tc.get("time_increment"),
        max_time=tc.get("max_time"),
        stones_per_period=tc.get("stones_per_period"),
    )


def _parse_clock(clock_data: dict, my_color: str) -> ClockState:
    """Parse OGS clock event into ClockState."""
    current_player = "B" if clock_data.get("current_player") == clock_data.get("black_player_id") else "W"
    return ClockState(
        black_time=clock_data.get("black_time", {}),
        white_time=clock_data.get("white_time", {}),
        current_player=current_player,
        paused=clock_data.get("pause", {}).get("paused", False) if isinstance(clock_data.get("pause"), dict) else False,
    )


class OGSAdapter(PlatformAdapter):
    """PlatformAdapter implementation for OGS (online-go.com)."""

    platform_name = "ogs"
    supported_board_sizes = [9, 13, 19]
    supports_live_play = True
    supports_scoring = True
    supports_automatch = True
    supports_rooms = False
    supports_seek_graph = True

    def __init__(self):
        super().__init__()
        self._rest = OGSRestClient()
        self._rt: Optional[OGSRealtimeClient] = None
        self._active_game_id: Optional[int] = None
        self._game_data: dict[int, dict] = {}  # game_id -> gamedata
        self._automatch_uuid: Optional[str] = None
        self._seek_graph: dict[str, PlatformChallenge] = {}  # challenge_id -> challenge

    # --- Connection lifecycle ---

    async def connect(self, credentials: PlatformCredentials) -> bool:
        try:
            # Try token-based reconnection first
            if "user_jwt" in credentials.auth_data and credentials.auth_data.get("user_jwt"):
                try:
                    config = await self._rest.login_with_token(credentials.auth_data)
                except Exception:
                    # Token expired, fall through to password login
                    if "password" not in credentials.auth_data:
                        return False
                    config = await self._rest.login(credentials.username, credentials.auth_data["password"])
            else:
                config = await self._rest.login(credentials.username, credentials.auth_data.get("password", ""))

            # Connect realtime
            self._rt = OGSRealtimeClient()
            await self._rt.connect(
                jwt=self._rest.user_jwt,
                user_id=self._rest.user_id,
                username=self._rest.username,
            )

            # Register event handlers
            self._register_events()
            self._connected = True

            # Subscribe to seek graph for open challenges
            await self._rt.seek_graph_connect()

            # Notify about updated tokens for storage
            await self._emit("token_refreshed", self._rest.get_auth_data_for_storage())

            return True
        except Exception as e:
            logger.error(f"OGS connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        if self._rt:
            await self._rt.disconnect()
            self._rt = None
        await self._rest.close()
        self._connected = False
        self._active_game_id = None
        self._game_data.clear()

    # --- Event registration ---

    def _register_events(self) -> None:
        """Register all OGS realtime event handlers."""
        # We register handlers for game-specific events dynamically when connecting to a game.
        # Global events:
        self._rt.on("active_game", self._on_active_game)
        self._rt.on("notification", self._on_notification)
        self._rt.on("net/pong", self._on_net_pong)
        self._rt.on("automatch/entry", self._on_automatch_entry)
        self._rt.on("automatch/start", self._on_automatch_start)
        self._rt.on("seekgraph/global", self._on_seekgraph)
        self._rt.on("_connection_lost", self._on_connection_lost_internal)
        self._rt.on("_reconnected", self._on_reconnected_internal)

    def _register_game_events(self, game_id: int) -> None:
        """Register event handlers for a specific game."""
        self._rt.on(f"game/{game_id}/gamedata", lambda data: self._on_gamedata(game_id, data))
        self._rt.on(f"game/{game_id}/move", lambda data: self._on_move(game_id, data))
        self._rt.on(f"game/{game_id}/clock", lambda data: self._on_clock(game_id, data))
        self._rt.on(f"game/{game_id}/phase", lambda data: self._on_phase(game_id, data))

    # --- Lobby ---

    async def get_open_challenges(self) -> list[PlatformChallenge]:
        """Return open challenges. Uses WebSocket seek graph cache, falls back to REST API."""
        if self._seek_graph:
            return list(self._seek_graph.values())

        # Fallback: fetch via REST when seek graph cache is empty
        try:
            raw_challenges = await self._rest.get_open_challenges(page_size=50)
            challenges = []
            for ch in raw_challenges:
                parsed = self._parse_rest_challenge(ch)
                if parsed:
                    challenges.append(parsed)
            logger.debug(f"OGS REST fallback: {len(challenges)} open challenges")
            return challenges
        except Exception as e:
            logger.warning(f"Failed to fetch OGS challenges via REST: {e}")
            return []

    def _parse_rest_challenge(self, ch: dict) -> Optional[PlatformChallenge]:
        """Parse an OGS REST /api/v1/challenges/ entry into PlatformChallenge."""
        try:
            challenger = ch.get("challenger", {})
            rank_str, rank_num = _parse_rank(challenger.get("ranking", 15))
            game = ch.get("game", {})
            tc = _parse_time_control(game.get("time_control_parameters", {}))
            return PlatformChallenge(
                platform="ogs",
                challenge_id=str(ch.get("id", "")),
                from_user=OnlineUser(
                    platform="ogs",
                    user_id=str(challenger.get("id", "")),
                    username=challenger.get("username", "?"),
                    rank=rank_str,
                    rank_numeric=rank_num,
                ),
                board_size=game.get("width", 19),
                time_control=tc,
                rules=game.get("rules", "chinese"),
                ranked=game.get("ranked", False),
                handicap=game.get("handicap", 0),
                komi=game.get("komi"),
            )
        except Exception as e:
            logger.debug(f"Failed to parse REST challenge: {e}")
            return None

    async def get_online_users(self, room: Optional[str] = None) -> list[OnlineUser]:
        """Fetch online players via OGS REST API (active game players)."""
        try:
            data = await self._rest.search_players(room or "", page_size=50)
            users = []
            for p in data:
                rank_str, rank_num = _parse_rank(p.get("ranking", 15))
                users.append(
                    OnlineUser(
                        platform="ogs",
                        user_id=str(p.get("id", "")),
                        username=p.get("username", "?"),
                        rank=rank_str,
                        rank_numeric=rank_num,
                        status="idle",
                    )
                )
            return users
        except Exception as e:
            logger.error(f"Failed to fetch OGS users: {e}")
            return []

    # --- Challenge ---

    async def send_challenge(self, user_id: str, settings: dict) -> str:
        challenge_id, game_id = await self._rest.challenge_player(int(user_id), settings)
        return str(challenge_id)

    async def accept_challenge(self, challenge_id: str) -> PlatformGameSession:
        data = await self._rest.accept_challenge(int(challenge_id))
        game_id = data.get("game") or data.get("id")
        return await self._connect_to_game(game_id)

    async def decline_challenge(self, challenge_id: str) -> None:
        await self._rest.decline_challenge(int(challenge_id))

    async def create_open_challenge(self, settings: dict) -> str:
        # OGS open challenges are created via REST API
        challenge_id, _ = await self._rest.challenge_player(0, settings)  # player_id=0 for open challenge
        return str(challenge_id)

    async def start_automatch(self, preferences: dict) -> None:
        if self._rt:
            self._automatch_uuid = await self._rt.automatch_find(preferences)

    async def cancel_automatch(self) -> None:
        if self._rt and self._automatch_uuid:
            await self._rt.automatch_cancel(self._automatch_uuid)
            self._automatch_uuid = None

    # --- In-game ---

    async def submit_move(self, game_id: str, col: int, row: int) -> bool:
        if not self._rt:
            return False
        sgf_move = katrain_to_sgf(col, row)
        await self._rt.game_move(int(game_id), sgf_move)
        # OGS doesn't send explicit ACK — if the move is invalid, we get an error event.
        # For now, assume success. The gateway timeout handles failures.
        return True

    async def submit_pass(self, game_id: str) -> bool:
        if not self._rt:
            return False
        await self._rt.game_move(int(game_id), "..")
        return True

    async def resign(self, game_id: str) -> None:
        if self._rt:
            await self._rt.game_resign(int(game_id))

    async def fetch_game_snapshot(self, game_id: str) -> dict:
        return await self._rest.get_game(int(game_id))

    async def submit_scoring_action(self, game_id: str, action: dict) -> bool:
        if not self._rt:
            return False
        if action.get("action") == "accept":
            stones = action.get("stones", "")
            await self._rt.game_removed_stones_accept(int(game_id), stones)
            return True
        return False

    # --- Internal: connect to a game ---

    async def _connect_to_game(self, game_id: int) -> PlatformGameSession:
        """Connect to an OGS game and return a PlatformGameSession."""
        self._register_game_events(game_id)
        await self._rt.game_connect(game_id)

        # Fetch game data via REST for initial state
        game_data = await self._rest.get_game(game_id)
        self._game_data[game_id] = game_data
        self._active_game_id = game_id

        # Determine our color
        players = game_data.get("players", {})
        black_id = players.get("black", {}).get("id")
        my_color = "B" if black_id == self._rest.user_id else "W"
        opponent_data = players.get("white" if my_color == "B" else "black", {})
        opp_rank, opp_rank_num = _parse_rank(opponent_data.get("ranking", 15))

        tc = _parse_time_control(game_data.get("time_control", {}))

        return PlatformGameSession(
            platform="ogs",
            game_id=str(game_id),
            board_size=game_data.get("width", 19),
            my_color=my_color,
            opponent=OnlineUser(
                platform="ogs",
                user_id=str(opponent_data.get("id", "")),
                username=opponent_data.get("username", "?"),
                rank=opp_rank,
                rank_numeric=opp_rank_num,
            ),
            time_control=tc,
            rules=game_data.get("rules", "chinese"),
            ranked=game_data.get("ranked", False),
            handicap=game_data.get("handicap", 0),
            komi=game_data.get("komi", 6.5),
        )

    # --- Event handlers ---

    async def _on_active_game(self, data) -> None:
        """Received active game notification."""
        if data and isinstance(data, dict):
            game_id = data.get("id")
            logger.debug(f"OGS active_game: {game_id}")

    async def _on_notification(self, data) -> None:
        """Received a notification (may be a challenge)."""
        if not data or not isinstance(data, dict):
            return
        ntype = data.get("type")
        if ntype == "challenge":
            await self._handle_challenge_notification(data)

    async def _handle_challenge_notification(self, data: dict) -> None:
        """Convert OGS challenge notification to PlatformChallenge."""
        challenge = data.get("challenge", data)
        challenger = challenge.get("challenger", {})
        rank_str, rank_num = _parse_rank(challenger.get("ranking", 15))
        tc = _parse_time_control(challenge.get("time_control", challenge.get("time_control_parameters", {})))

        platform_challenge = PlatformChallenge(
            platform="ogs",
            challenge_id=str(challenge.get("id", data.get("id", ""))),
            from_user=OnlineUser(
                platform="ogs",
                user_id=str(challenger.get("id", "")),
                username=challenger.get("username", "?"),
                rank=rank_str,
                rank_numeric=rank_num,
            ),
            board_size=challenge.get("width", challenge.get("game", {}).get("width", 19)),
            time_control=tc,
            rules=challenge.get("rules", "chinese"),
            ranked=challenge.get("ranked", False),
            handicap=challenge.get("handicap", 0),
            komi=challenge.get("komi"),
        )
        await self._emit("challenge_received", platform_challenge)

    async def _on_gamedata(self, game_id: int, data: dict) -> None:
        """Full game state received (on game connect or state change).

        OGS gamedata.moves is a flat list: [x1, y1, timedelta1, x2, y2, timedelta2, ...].
        We convert to a list of [x, y] pairs for internal tracking.
        """
        # Parse the flat moves array into [col, row] pairs
        raw_moves = data.get("moves", [])
        parsed_moves = []
        i = 0
        while i + 1 < len(raw_moves):
            parsed_moves.append([raw_moves[i], raw_moves[i + 1]])
            i += 3  # skip timedelta (x, y, timedelta triplets)
            if i > len(raw_moves):
                i -= 1  # some formats may omit timedelta for last move
                break
        data["moves"] = parsed_moves
        self._game_data[game_id] = data
        logger.debug(f"OGS game/{game_id}/gamedata: phase={data.get('phase')}, moves={len(parsed_moves)}")

    async def _on_move(self, game_id: int, data) -> None:
        """Move received (both ours and opponent's). OGS sends all moves."""
        if not data:
            return

        # data can be [col, row, timedelta] or a dict with {move_number, move: [x,y,...]}
        if isinstance(data, list):
            col, row = data[0], data[1]
        elif isinstance(data, dict):
            move = data.get("move")
            if isinstance(move, list):
                col, row = move[0], move[1]
            elif isinstance(move, str) and len(move) == 2:
                col, row = sgf_to_katrain(move)
            else:
                return
        else:
            return

        # Update internal move tracking
        gamedata = self._game_data.get(game_id, {})
        if "moves" not in gamedata:
            gamedata["moves"] = []
        moves = gamedata["moves"]
        move_number = len(moves) + 1
        moves.append([col, row])

        # Determine color from move count + handicap
        # OGS: with handicap > 0, black places handicap stones first, then white moves first.
        # In the moves list from gamedata, handicap stones are NOT included — they're in initial_state.
        # So moves[0] is always the first normal move: Black if handicap=0, White if handicap>0.
        handicap = gamedata.get("handicap", 0)
        if handicap > 0:
            color = "W" if (move_number % 2 == 1) else "B"
        else:
            color = "B" if (move_number % 2 == 1) else "W"

        # Check if this is our own move echoed back
        players = gamedata.get("players", {})
        black_id = players.get("black", {}).get("id")
        my_color = "B" if black_id == self._rest.user_id else "W"

        if color == my_color:
            # Our own move echoed back — skip (already applied locally by gateway)
            return

        platform_move = PlatformMove(col=col, row=row, color=color, move_number=move_number)
        await self._emit("opponent_move", platform_move)

    async def _on_clock(self, game_id: int, data: dict) -> None:
        """Clock update received."""
        if not data:
            return
        gamedata = self._game_data.get(game_id, {})
        players = gamedata.get("players", {})
        black_id = players.get("black", {}).get("id")
        my_color = "B" if black_id == self._rest.user_id else "W"
        clock = _parse_clock(data, my_color)
        await self._emit("clock_update", clock)

    async def _on_phase(self, game_id: int, data) -> None:
        """Game phase changed (play -> stone removal -> finished)."""
        phase_str = data if isinstance(data, str) else data.get("phase", "") if isinstance(data, dict) else ""
        phase_map = {
            "play": GamePhase.PLAYING,
            "stone removal": GamePhase.SCORING,
            "finished": GamePhase.FINISHED,
        }
        phase = phase_map.get(phase_str, GamePhase.PLAYING)
        await self._emit("game_phase_changed", str(game_id), phase)

        if phase == GamePhase.FINISHED:
            # Game ended — fetch final state from REST for accurate result
            try:
                final_data = await self._rest.get_game(game_id)
                self._game_data[game_id] = final_data
            except Exception:
                final_data = self._game_data.get(game_id, {})
            result = final_data.get("outcome", "?")
            winner = final_data.get("winner", "?")
            await self._emit("game_ended", str(game_id), result, str(winner))

    async def _on_net_pong(self, data: dict) -> None:
        """Latency measurement response."""
        if data and isinstance(data, dict):
            client_time = data.get("client", 0)
            server_time = data.get("server", 0)
            now = int(time.time() * 1000)
            self._rt.latency = now - client_time
            self._rt.drift = server_time - now

    async def _on_seekgraph(self, data) -> None:
        """Seek graph update — maintain cache of open challenges.

        OGS always sends seekgraph/global as a list, even for single updates:
        - Initial snapshot: [{seek1}, {seek2}, ...] — many entries
        - Delete: [{"challenge_id": X, "delete": 1}]
        - New seek: [{seek_data}]
        - Game started: [{"game_started": true, ...}]
        """
        if not data or not isinstance(data, list):
            return

        # Distinguish initial snapshot (many entries) from incremental updates (1-2 entries)
        is_snapshot = len(data) > 5

        if is_snapshot:
            self._seek_graph.clear()
            total, parsed, failed = 0, 0, 0
            first_fail_reason = None
            for seek in data:
                if not isinstance(seek, dict):
                    continue
                if seek.get("delete") or seek.get("game_started"):
                    continue
                total += 1
                challenge = self._parse_seek(seek)
                if challenge:
                    self._seek_graph[challenge.challenge_id] = challenge
                    parsed += 1
                else:
                    failed += 1
                    if first_fail_reason is None:
                        first_fail_reason = f"keys={list(seek.keys())[:10]}"
            logger.info(f"OGS seek graph snapshot: {parsed}/{total} parsed, {failed} failed")
            if first_fail_reason:
                logger.warning(f"OGS seek graph parse failure sample: {first_fail_reason}")
        else:
            # Incremental update: process each entry
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                seek_id = str(entry.get("challenge_id", entry.get("game_id", "")))
                if entry.get("delete") or entry.get("game_started"):
                    self._seek_graph.pop(seek_id, None)
                else:
                    challenge = self._parse_seek(entry)
                    if challenge:
                        self._seek_graph[challenge.challenge_id] = challenge

    def _parse_seek(self, seek: dict) -> Optional[PlatformChallenge]:
        """Parse an OGS seek graph entry into PlatformChallenge.

        Seek entries have flat fields: username, ranking, challenge_id, width, etc.
        time_control is a STRING ("byoyomi"), time_control_parameters is the dict.
        """
        try:
            user = seek.get("user", seek)
            rank_str, rank_num = _parse_rank(user.get("ranking", 15))
            # time_control is a string in seek data; time_control_parameters is the dict
            tc_params = seek.get("time_control_parameters", {})
            if isinstance(tc_params, dict):
                tc = _parse_time_control(tc_params)
            else:
                tc = TimeControl(system=str(seek.get("time_control", "byoyomi")), main_time=0)

            return PlatformChallenge(
                platform="ogs",
                challenge_id=str(seek.get("challenge_id", seek.get("game_id", ""))),
                from_user=OnlineUser(
                    platform="ogs",
                    user_id=str(user.get("player_id", user.get("id", ""))),
                    username=user.get("username", "?"),
                    rank=rank_str,
                    rank_numeric=rank_num,
                ),
                board_size=seek.get("width", 19),
                time_control=tc,
                rules=seek.get("rules", "chinese"),
                ranked=seek.get("ranked", False),
                handicap=seek.get("handicap", 0),
                komi=seek.get("komi"),
            )
        except Exception as e:
            logger.debug(f"Failed to parse seek: {e}")
            return None

    async def _on_automatch_entry(self, data) -> None:
        """Automatch queue status update."""
        pass

    async def _on_automatch_start(self, data) -> None:
        """Automatch found a game."""
        if data and isinstance(data, dict):
            game_id = data.get("game_id")
            if game_id:
                game_session = await self._connect_to_game(game_id)
                await self._emit("automatch_found", game_session)

    async def _on_connection_lost_internal(self, data) -> None:
        """Internal connection lost handler."""
        self._connected = False
        await self._emit("connection_lost")

    async def _on_reconnected_internal(self, data) -> None:
        """Internal reconnected handler — re-register game events and resync state."""
        self._connected = True
        # Game events need re-registration since they were on the old WebSocket callback list
        for game_id in list(self._game_data.keys()):
            self._register_game_events(game_id)
        await self._emit("reconnected")
