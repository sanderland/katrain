"""Platform Manager — orchestrates all platform adapters and bridges them to KaTrain sessions."""

from __future__ import annotations

import logging
from typing import Optional

from katrain.web.platforms.base import PlatformAdapter
from katrain.web.platforms.credentials import PlatformCredentialStore
from katrain.web.platforms.models import (
    ClockState,
    GamePhase,
    PlatformCredentials,
    PlatformGameContext,
    PlatformGameSession,
    PlatformMove,
)

logger = logging.getLogger("katrain_web")


class PlatformManager:
    """Singleton managing all platform connections for a user.

    Bridges platform games to KaTrain sessions: opponent moves from the platform
    are injected into the local game, and vision/touch moves are submitted to the platform.
    """

    def __init__(self, session_manager, credential_store: Optional[PlatformCredentialStore] = None):
        self._session_manager = session_manager
        self._credential_store = credential_store or PlatformCredentialStore()
        self._adapters: dict[str, PlatformAdapter] = {}
        self._active_games: dict[str, PlatformGameContext] = {}  # game_id -> context
        self._session_to_game: dict[str, str] = {}  # session_id -> game_id

    # --- Adapter registry ---

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """Register a platform adapter (call at startup for each supported platform)."""
        self._adapters[adapter.platform_name] = adapter

    def get_adapter(self, platform: str) -> Optional[PlatformAdapter]:
        return self._adapters.get(platform)

    def list_platforms(self) -> list[dict]:
        """List all registered platforms with connection status."""
        return [
            {
                "platform": name,
                "connected": adapter.is_connected,
                "supports_live_play": adapter.supports_live_play,
                "supports_automatch": adapter.supports_automatch,
                "supports_rooms": adapter.supports_rooms,
                "supports_seek_graph": adapter.supports_seek_graph,
            }
            for name, adapter in self._adapters.items()
        ]

    # --- Connection lifecycle ---

    async def connect_platform(self, platform: str, credentials: PlatformCredentials, user_id: int) -> bool:
        """Connect to a platform. Saves credentials on success."""
        adapter = self._adapters.get(platform)
        if adapter is None:
            raise ValueError(f"Unknown platform: {platform}")
        success = await adapter.connect(credentials)
        if success:
            self._credential_store.save_credentials(user_id, credentials)
            self._setup_callbacks(adapter)
            logger.info(f"Connected to {platform} as {credentials.username}")
        return success

    async def disconnect_platform(self, platform: str) -> None:
        adapter = self._adapters.get(platform)
        if adapter and adapter.is_connected:
            await adapter.disconnect()
            logger.info(f"Disconnected from {platform}")

    def list_connected_platforms(self) -> list[str]:
        return [name for name, a in self._adapters.items() if a.is_connected]

    # --- Game context ---

    def get_game_context(self, session_id: str) -> Optional[PlatformGameContext]:
        game_id = self._session_to_game.get(session_id)
        if game_id is None:
            return None
        return self._active_games.get(game_id)

    def is_platform_game(self, session_id: str) -> bool:
        return session_id in self._session_to_game

    # --- Bridge: platform game -> KaTrain session ---

    async def start_platform_game(self, platform: str, game_session: PlatformGameSession, user_id: int) -> str:
        """Creates a KaTrain session backed by a platform game. Returns session_id."""
        # Create a multiplayer session (local user vs virtual opponent)
        opponent_name = f"[{platform}] {game_session.opponent.username}"
        if game_session.my_color == "B":
            session = self._session_manager.create_multiplayer_session(
                player_b_id=user_id, player_w_id=-1, b_name="Me", w_name=opponent_name
            )
        else:
            session = self._session_manager.create_multiplayer_session(
                player_b_id=-1, player_w_id=user_id, b_name=opponent_name, w_name="Me"
            )

        ctx = PlatformGameContext(
            session_id=session.session_id,
            platform=platform,
            remote_game_id=game_session.game_id,
            my_color=game_session.my_color,
        )
        self._active_games[game_session.game_id] = ctx
        self._session_to_game[session.session_id] = game_session.game_id

        logger.info(f"Platform game started: {platform} game {game_session.game_id} -> session {session.session_id}")
        return session.session_id

    async def end_platform_game(self, game_id: str, result: str) -> None:
        """Clean up after a platform game ends."""
        ctx = self._active_games.pop(game_id, None)
        if ctx:
            self._session_to_game.pop(ctx.session_id, None)
            ctx.game_phase = GamePhase.FINISHED
            logger.info(f"Platform game ended: {game_id} result={result}")

    # --- Callbacks ---

    def _setup_callbacks(self, adapter: PlatformAdapter) -> None:
        adapter.on_opponent_move(self._on_opponent_move)
        adapter.on_clock_update(self._on_clock_update)
        adapter.on_game_started(self._on_game_started)
        adapter.on_game_ended(self._on_game_ended)
        adapter.on_game_phase_changed(self._on_game_phase_changed)
        adapter.on_connection_lost(self._on_connection_lost)
        adapter.on_reconnected(self._on_reconnected)
        adapter.on_auth_expired(self._on_auth_expired)
        adapter.on_token_refreshed(self._on_token_refreshed)

    async def _on_opponent_move(self, move: PlatformMove) -> None:
        """Platform opponent played a move -> inject into KaTrain game."""
        # Find the game context by scanning active games
        # In practice, the adapter should tag moves with game_id; for now find by active game
        for game_id, ctx in self._active_games.items():
            if ctx.game_phase == GamePhase.PLAYING:
                try:
                    session = self._session_manager.get_session(ctx.session_id)
                    session.katrain("play", coords=(move.col, move.row))
                    ctx.last_confirmed_move = move.move_number
                    self._session_manager.broadcast_to_session(
                        ctx.session_id,
                        {"type": "platform_move_confirmed", "col": move.col, "row": move.row, "move_number": move.move_number},
                    )
                except KeyError:
                    logger.warning(f"Session {ctx.session_id} not found for opponent move")
                break

    async def _on_clock_update(self, clock: ClockState) -> None:
        for game_id, ctx in self._active_games.items():
            if ctx.game_phase in (GamePhase.PLAYING, GamePhase.PAUSED):
                ctx.remote_clock_version += 1
                self._session_manager.broadcast_to_session(
                    ctx.session_id,
                    {
                        "type": "clock_update",
                        "black_time": clock.black_time,
                        "white_time": clock.white_time,
                        "current_player": clock.current_player,
                        "paused": clock.paused,
                    },
                )
                break

    async def _on_game_started(self, game_session: PlatformGameSession) -> None:
        logger.info(f"Game started event from {game_session.platform}: {game_session.game_id}")

    async def _on_game_ended(self, game_id: str, result: str, winner: str) -> None:
        ctx = self._active_games.get(game_id)
        if ctx:
            self._session_manager.broadcast_to_session(
                ctx.session_id, {"type": "platform_game_ended", "game_id": game_id, "result": result, "winner": winner}
            )
            await self.end_platform_game(game_id, result)

    async def _on_game_phase_changed(self, game_id: str, phase: GamePhase) -> None:
        ctx = self._active_games.get(game_id)
        if ctx:
            ctx.game_phase = phase
            self._session_manager.broadcast_to_session(
                ctx.session_id, {"type": "platform_phase_changed", "phase": phase.value}
            )

    async def _on_connection_lost(self) -> None:
        logger.warning("Platform connection lost")

    async def _on_reconnected(self) -> None:
        logger.info("Platform reconnected")
        # Mark games that may have missed events
        for ctx in self._active_games.values():
            if ctx.game_phase == GamePhase.PLAYING:
                ctx.needs_resync = True

    async def _on_auth_expired(self) -> None:
        logger.warning("Platform auth expired")

    async def _on_token_refreshed(self, new_auth_data: dict) -> None:
        logger.debug("Platform tokens refreshed — persistence handled by adapter-specific logic")
