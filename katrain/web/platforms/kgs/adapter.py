"""KGS platform adapter — connects KaTrain to gokgs.com via JSON protocol."""

from __future__ import annotations

import logging
from typing import Optional

from katrain.web.platforms.base import PlatformAdapter
from katrain.web.platforms.kgs.json_client import KGSJsonClient
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

logger = logging.getLogger("katrain_web")


def _parse_kgs_rank(rank_str: str) -> tuple[str, float]:
    """Parse KGS rank string (e.g., '5k', '3d') to (display, numeric)."""
    if not rank_str:
        return "?", 0.0
    rank_str = rank_str.strip().lower()
    try:
        if rank_str.endswith("k"):
            kyu = int(rank_str[:-1])
            return f"{kyu}k", 30.0 - kyu
        elif rank_str.endswith("d"):
            dan = int(rank_str[:-1])
            return f"{dan}d", 29.0 + dan
        elif rank_str.endswith("p"):
            dan = int(rank_str[:-1])
            return f"{dan}p", 39.0 + dan
    except ValueError:
        pass
    return rank_str, 0.0


def _parse_kgs_score(score) -> str:
    """Parse KGS score to result string."""
    if isinstance(score, str):
        return score  # "B+RESIGN", "W+TIME", etc.
    if isinstance(score, (int, float)):
        if score > 0:
            return f"B+{score}"
        elif score < 0:
            return f"W+{-score}"
        else:
            return "Draw"
    return "?"


class KGSAdapter(PlatformAdapter):
    """PlatformAdapter implementation for KGS (gokgs.com)."""

    platform_name = "kgs"
    supported_board_sizes = [9, 13, 19]
    supports_live_play = True
    supports_scoring = False  # KGS handles scoring server-side
    supports_automatch = False
    supports_rooms = True
    supports_seek_graph = False

    def __init__(self):
        super().__init__()
        self._client = KGSJsonClient()
        self._active_channel: Optional[int] = None
        self._game_channels: dict[int, dict] = {}  # channelId -> game info
        self._rooms: list[dict] = []

    # --- Connection lifecycle ---

    async def connect(self, credentials: PlatformCredentials) -> bool:
        try:
            password = credentials.auth_data.get("password", "")
            success = await self._client.login(credentials.username, password)
            if success:
                self._connected = True
                self._register_events()
            return success
        except Exception as e:
            logger.error(f"KGS connection failed: {e}")
            return False

    async def disconnect(self) -> None:
        await self._client.logout()
        self._connected = False
        self._active_channel = None
        self._game_channels.clear()

    # --- Event registration ---

    def _register_events(self) -> None:
        self._client.on("GAME_JOIN", self._on_game_join)
        self._client.on("GAME_UPDATE", self._on_game_update)
        self._client.on("GAME_OVER", self._on_game_over)
        self._client.on("GAME_STATE", self._on_game_state)
        self._client.on("GAME_NOTIFY", self._on_game_notify)
        self._client.on("CHALLENGE_JOIN", self._on_challenge)
        self._client.on("CHALLENGE_FINAL", self._on_challenge_final)
        self._client.on("ROOM_JOIN", self._on_room_join)

    # --- Lobby ---

    async def get_rooms(self) -> list[dict]:
        return self._rooms

    async def get_online_users(self, room: Optional[str] = None) -> list[OnlineUser]:
        # KGS provides user lists per room via GAME_LIST messages
        # For now return empty — populated by room join events
        return []

    # --- Challenge ---

    async def send_challenge(self, user_id: str, settings: dict) -> str:
        # KGS challenges go through rooms — need a room channelId
        # This is a simplified version; real implementation would need room context
        proposal = self._build_proposal(settings)
        if self._rooms:
            room_id = self._rooms[0].get("channelId", 0)
            await self._client.challenge_create(room_id, proposal)
            return f"kgs-challenge-{room_id}"
        raise NotImplementedError("Must join a room first to create challenges on KGS")

    async def accept_challenge(self, challenge_id: str) -> PlatformGameSession:
        channel_id = int(challenge_id.split("-")[-1]) if "-" in challenge_id else int(challenge_id)
        # KGS auto-joins the game after CHALLENGE_FINAL
        # Return a placeholder; the actual game session comes from GAME_JOIN callback
        raise NotImplementedError("KGS challenge accept flow requires CHALLENGE_FINAL event")

    async def decline_challenge(self, challenge_id: str) -> None:
        channel_id = int(challenge_id.split("-")[-1]) if "-" in challenge_id else int(challenge_id)
        await self._client.challenge_decline(channel_id)

    # --- In-game ---

    async def submit_move(self, game_id: str, col: int, row: int) -> bool:
        channel_id = int(game_id)
        await self._client.game_move(channel_id, col, row)
        return True  # KGS doesn't send explicit ACK; errors come as events

    async def submit_pass(self, game_id: str) -> bool:
        channel_id = int(game_id)
        await self._client.game_pass(channel_id)
        return True

    async def resign(self, game_id: str) -> None:
        channel_id = int(game_id)
        await self._client.game_resign(channel_id)

    # --- Event handlers ---

    async def _on_game_join(self, msg: dict) -> None:
        """We joined a game."""
        channel_id = msg.get("channelId")
        self._game_channels[channel_id] = msg
        self._active_channel = channel_id
        logger.info(f"KGS joined game channel {channel_id}")

        # Extract game info and notify
        summary = msg.get("gameSummary", {})
        players = summary.get("players", {})
        white = players.get("white", {})
        black = players.get("black", {})

        my_name = self._client.username
        if black.get("name") == my_name:
            my_color = "B"
            opp = white
        else:
            my_color = "W"
            opp = black

        opp_rank, opp_rank_num = _parse_kgs_rank(opp.get("rank", ""))

        game_session = PlatformGameSession(
            platform="kgs",
            game_id=str(channel_id),
            board_size=summary.get("size", 19),
            my_color=my_color,
            opponent=OnlineUser(
                platform="kgs",
                user_id=opp.get("name", ""),
                username=opp.get("name", "?"),
                rank=opp_rank,
                rank_numeric=opp_rank_num,
            ),
            time_control=TimeControl(
                system=summary.get("timeSystem", "byoyomi"),
                main_time=summary.get("mainTime", 0),
                period_time=summary.get("byoYomiTime"),
                periods=summary.get("byoYomiPeriods"),
            ),
            rules=summary.get("rules", "japanese"),
            ranked=summary.get("private", False) is False,
            handicap=summary.get("handicap", 0),
            komi=summary.get("komi", 6.5),
        )
        await self._emit("game_started", game_session)

    async def _on_game_update(self, msg: dict) -> None:
        """New moves or changes in a game."""
        channel_id = msg.get("channelId")
        sgf_events = msg.get("sgfEvents", [])

        for event in sgf_events:
            if event.get("type") == "MOVE":
                loc = event.get("loc")
                color = event.get("color", "").upper()
                if isinstance(loc, dict):
                    col, row = loc["x"], loc["y"]
                    # Determine move number from game state
                    game_info = self._game_channels.get(channel_id, {})
                    move_count = game_info.get("_move_count", 0) + 1
                    game_info["_move_count"] = move_count

                    # Check if this is our move
                    my_name = self._client.username
                    player_name = event.get("player", {}).get("name", "")
                    if player_name == my_name:
                        continue  # Our own move echoed back

                    move = PlatformMove(col=col, row=row, color=color[0] if color else "B", move_number=move_count)
                    await self._emit("opponent_move", move)
                elif loc == "PASS":
                    pass  # TODO: handle pass

    async def _on_game_over(self, msg: dict) -> None:
        """Game ended."""
        channel_id = msg.get("channelId")
        score = msg.get("score")
        result = _parse_kgs_score(score)
        winner = "B" if isinstance(score, (int, float)) and score > 0 else "W"
        await self._emit("game_ended", str(channel_id), result, winner)

    async def _on_game_state(self, msg: dict) -> None:
        """Game state update (clocks, actions)."""
        channel_id = msg.get("channelId")
        clocks = msg.get("clocks", {})
        if clocks:
            black_clock = clocks.get("black", {})
            white_clock = clocks.get("white", {})
            clock = ClockState(
                black_time=black_clock,
                white_time=white_clock,
                current_player="B" if msg.get("actions", {}).get("black") else "W",
            )
            await self._emit("clock_update", clock)

    async def _on_game_notify(self, msg: dict) -> None:
        """About to join an unknown game — e.g., someone challenged us."""
        logger.debug(f"KGS game notify: {msg}")

    async def _on_challenge(self, msg: dict) -> None:
        """Challenge received."""
        logger.debug(f"KGS challenge: {msg}")
        # TODO: parse challenge details and emit challenge_received

    async def _on_challenge_final(self, msg: dict) -> None:
        """Challenge accepted — game starting."""
        game_channel = msg.get("gameChannelId")
        if game_channel:
            await self._client.join_channel(game_channel)

    async def _on_room_join(self, msg: dict) -> None:
        """Joined a room."""
        channel_id = msg.get("channelId")
        self._rooms.append({"channelId": channel_id, "name": msg.get("name", ""), "users": msg.get("users", [])})

    # --- Helpers ---

    def _build_proposal(self, settings: dict) -> dict:
        """Build a KGS challenge proposal from settings."""
        return {
            "gameType": "free",
            "rules": {"rules": settings.get("rules", "japanese")},
            "boardSize": settings.get("board_size", 19),
            "komi": settings.get("komi", 6.5),
            "handicap": settings.get("handicap", 0),
            "timeSystem": settings.get("time_system", "byoyomi"),
            "mainTime": settings.get("main_time", 600),
            "byoYomiTime": settings.get("period_time", 30),
            "byoYomiPeriods": settings.get("periods", 5),
            "nigpiresPlayers": [
                {"role": "white"},
                {"role": "black", "name": self._client.username},
            ],
        }
