import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Union, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from katrain.web.api.v1.api import api_router
from katrain.web.core.config import settings
from katrain.web.session import SessionManager, LobbyManager, Matchmaker
from katrain.web.models import *

@asynccontextmanager
async def lifespan(app: FastAPI):
    log = logging.getLogger("katrain_web")

    if settings.KATRAIN_MODE == "board":
        # ── Board mode startup (design.md Section 4.9) ──
        await _lifespan_board(app, log)
    else:
        # ── Server mode startup (existing logic, unchanged) ──
        await _lifespan_server(app, log)

    yield

    # ── Shutdown ──
    # Vision service shutdown (board mode)
    vision = getattr(app.state, "vision", None)
    if vision:
        vision.stop()
    vision_poller = getattr(app.state, "vision_poller_task", None)
    if vision_poller:
        vision_poller.cancel()

    if settings.KATRAIN_MODE == "board":
        connectivity = getattr(app.state, "connectivity_manager", None)
        if connectivity:
            await connectivity.stop()
        remote_client = getattr(app.state, "remote_client", None)
        if remote_client:
            await remote_client.close()
    else:
        live_service = getattr(app.state, "live_service", None)
        if live_service:
            await live_service.stop()

    task = getattr(app.state, "cleanup_task", None)
    if task:
        task.cancel()
    app.state.session_manager.cleanup_expired()


async def _lifespan_server(app: FastAPI, log):
    """Server mode initialization — existing logic, unchanged."""
    from katrain.web.core.auth import SQLAlchemyUserRepository, get_password_hash
    from katrain.web.core.game_repo import GameRepository
    from katrain.web.core.user_game_repo import UserGameRepository, UserGameAnalysisRepository
    from katrain.web.core.db import SessionLocal

    repo = SQLAlchemyUserRepository(SessionLocal)
    repo.init_db()

    game_repo = GameRepository(SessionLocal)
    user_game_repo = UserGameRepository(SessionLocal)
    user_game_analysis_repo = UserGameAnalysisRepository(SessionLocal)

    # Create default admin user if no users exist
    if not repo.list_users():
        log.info("No users found. Creating default admin user (admin/admin)")
        try:
            repo.create_user("admin", get_password_hash("admin"))
        except ValueError:
            pass  # Already exists race condition

    app.state.user_repo = repo
    app.state.game_repo = game_repo
    app.state.user_game_repo = user_game_repo
    app.state.user_game_analysis_repo = user_game_analysis_repo
    app.state.lobby_manager = LobbyManager()
    app.state.matchmaker = Matchmaker()

    # Initialize Engine Clients and Router
    from katrain.web.core.engine_client import KataGoClient
    from katrain.web.core.router import RequestRouter

    local_client = KataGoClient(url=settings.LOCAL_KATAGO_URL)
    cloud_client = None
    if settings.CLOUD_KATAGO_URL:
        cloud_client = KataGoClient(url=settings.CLOUD_KATAGO_URL)

    app.state.router = RequestRouter(local_client=local_client, cloud_client=cloud_client)

    manager = app.state.session_manager
    try:
        from katrain.web.interface import WebKaTrain

        kt = WebKaTrain(force_package_config=False, enable_engine=False)

        engine_cfg = kt.config("engine")
        if settings.LOCAL_KATAGO_URL and engine_cfg.get("http_url") != settings.LOCAL_KATAGO_URL:
            if engine_cfg.get("backend") == "http":
                print(f"Syncing KataGo URL to {settings.LOCAL_KATAGO_URL} from environment")
                kt.update_config("engine/http_url", settings.LOCAL_KATAGO_URL)
                kt.save_config("engine")
                engine_cfg = kt.config("engine")

        engine_cfg = kt.config("engine")
        if engine_cfg.get("backend") == "http":
            import httpx

            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("httpcore").setLevel(logging.WARNING)
            url = engine_cfg.get("http_url")
            health = engine_cfg.get("http_health_path", "/health")
            full_url = f"{url.rstrip('/')}/{health.lstrip('/')}"
            print(f"Testing KataGo Engine at {full_url}...")
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    resp = await client.get(full_url, timeout=5.0)
                    if resp.status_code == 200:
                        print(f"KataGo Engine is reachable: {resp.json()}")
                    else:
                        print(f"WARNING: KataGo Engine returned status {resp.status_code}")
            except Exception as e:
                print(f"WARNING: Failed to connect to KataGo Engine: {e}")

    except Exception as e:
        log.error(f"Initialization failed: {e}")

    manager.attach_loop(asyncio.get_running_loop())
    app.state.cleanup_task = asyncio.create_task(_cleanup_loop(manager))

    # Initialize Live Broadcasting Service
    from katrain.web.live import create_live_service

    live_service = create_live_service()
    app.state.live_service = live_service
    try:
        await live_service.start()
        log.info("Live broadcasting service started")
    except Exception as e:
        log.warning(f"Failed to start live service: {e}")

    # ── Tutorial Module (V2 — database-backed) ─────────────────────────────
    log.info("Tutorial V2: using database-backed tutorials")


async def _lifespan_board(app: FastAPI, log):
    """Board mode initialization — design.md Section 4.9."""
    from functools import partial

    from katrain.web.core.auth import SQLAlchemyUserRepository
    from katrain.web.core.user_game_repo import UserGameRepository, UserGameAnalysisRepository
    from katrain.web.core.db import SessionLocal
    from katrain.web.core.remote_client import RemoteAPIClient
    from katrain.web.core.sync_worker import SyncWorker
    from katrain.web.core.connectivity import ConnectivityManager
    from katrain.web.core.repository import (
        RepositoryDispatcher,
        RemoteTsumegoRepository,
        RemoteKifuRepository,
        RemoteUserGameRepository,
        enqueue_sync_item,
    )

    log.info(f"Starting in BOARD mode (device={settings.DEVICE_ID[:8]}..., remote={settings.REMOTE_API_URL})")

    # Local SQLite — create only the core tables needed for offline
    repo = SQLAlchemyUserRepository(SessionLocal)
    repo.init_db()
    app.state.user_repo = repo

    local_user_game_repo = UserGameRepository(SessionLocal)
    local_user_game_analysis_repo = UserGameAnalysisRepository(SessionLocal)
    app.state.user_game_repo = local_user_game_repo
    app.state.user_game_analysis_repo = local_user_game_analysis_repo

    # Remote API client
    remote_client = RemoteAPIClient(
        base_url=settings.REMOTE_API_URL,
        device_id=settings.DEVICE_ID,
    )
    app.state.remote_client = remote_client

    # Try to restore refresh token from encrypted credentials
    try:
        from katrain.web.core.credentials import load_refresh_token

        saved_token = load_refresh_token(settings.DEVICE_ID)
        if saved_token:
            remote_client.set_refresh_token(saved_token)
            log.info("Restored refresh token from credentials store")
    except Exception as e:
        log.debug(f"No saved credentials: {e}")

    # Sync worker
    sync_worker = SyncWorker(SessionLocal, remote_client)
    sync_worker.recover_stale_leases()
    app.state.sync_worker = sync_worker

    # Connectivity manager
    connectivity = ConnectivityManager(remote_client, sync_worker)
    app.state.connectivity_manager = connectivity

    # Repository dispatcher
    sync_fn = partial(enqueue_sync_item, SessionLocal, device_id=settings.DEVICE_ID)
    dispatcher = RepositoryDispatcher(
        connectivity_manager=connectivity,
        remote_tsumego=RemoteTsumegoRepository(remote_client),
        remote_kifu=RemoteKifuRepository(remote_client),
        remote_user_games=RemoteUserGameRepository(remote_client),
        local_user_game_repo=local_user_game_repo,
        sync_enqueue_fn=sync_fn,
    )
    app.state.repository_dispatcher = dispatcher

    # Engine (local KataGo for offline play)
    from katrain.web.core.engine_client import KataGoClient
    from katrain.web.core.router import RequestRouter

    local_client = KataGoClient(url=settings.LOCAL_KATAGO_URL)
    app.state.router = RequestRouter(local_client=local_client, cloud_client=None)

    # Lobby/matchmaker placeholders (not used in board mode but needed by endpoints)
    app.state.lobby_manager = LobbyManager()
    app.state.matchmaker = Matchmaker()
    app.state.game_repo = None  # Multiplayer game_repo not used in board mode

    manager = app.state.session_manager
    try:
        from katrain.web.interface import WebKaTrain

        kt = WebKaTrain(force_package_config=False, enable_engine=False)
        engine_cfg = kt.config("engine")
        log.info(
            f"Board engine profile: max_visits={engine_cfg.get('max_visits')}, "
            f"fast_visits={engine_cfg.get('fast_visits')}, max_time={engine_cfg.get('max_time')}"
        )
    except Exception as e:
        log.error(f"Board mode initialization warning: {e}")

    manager.attach_loop(asyncio.get_running_loop())
    app.state.cleanup_task = asyncio.create_task(_cleanup_loop(manager))

    # Start connectivity monitoring (do NOT start live_service in board mode)
    connectivity.start()

    # Vision service (optional — enabled when --vision-model is provided)
    vision_config = getattr(settings, "_vision_config", None)
    if vision_config and vision_config.enabled:
        from katrain.vision.service import VisionService

        vision = VisionService(vision_config)
        vision.start()
        app.state.vision = vision
        app.state.vision_poller_task = asyncio.create_task(_vision_move_poller(app))
        log.info("Vision service started (backend=%s)", vision_config.backend)
    else:
        app.state.vision = None

    log.info("Board mode initialization complete")

def create_app(enable_engine=True, session_timeout=None, max_sessions=None):
    from katrain.web.api.v1.endpoints.auth import get_current_user, get_current_user_optional
    if session_timeout is None:
        session_timeout = settings.SESSION_TIMEOUT
    if max_sessions is None:
        max_sessions = settings.MAX_SESSIONS
    # Set logging levels for our application
    logging.getLogger("katrain_web").setLevel(logging.INFO)
    
    app = FastAPI(lifespan=lifespan)
    app.include_router(api_router, prefix="/api/v1")
    static_root = Path(__file__).resolve().parent / "static"
    assets_root = Path(__file__).resolve().parent.parent
    
    # Specific asset mounts first
    app.mount("/assets/img", StaticFiles(directory=assets_root / "img"), name="img")
    app.mount("/assets/fonts", StaticFiles(directory=assets_root / "fonts"), name="fonts")
    app.mount("/assets/sounds", StaticFiles(directory=assets_root / "sounds"), name="sounds")

    manager = SessionManager(
        session_timeout=session_timeout,
        max_sessions=max_sessions,
        enable_engine=enable_engine,
    )
    app.state.session_manager = manager

    @app.get("/health")
    async def health():
        from katrain.web.api.v1.endpoints.health import health as health_v1
        return await health_v1()

    @app.post("/api/session")
    def create_session(current_user: User = Depends(get_current_user_optional), mode: str = "play"):
        try:
            katago_uuid = current_user.uuid if current_user else None
            if mode == "research" and current_user:
                session = manager.create_research_session(user_id=current_user.id, katago_uuid=katago_uuid)
            else:
                session = manager.create_session(katago_uuid=katago_uuid)
                if current_user:
                    session.user_id = current_user.id
        except Exception as exc:
            logging.getLogger("katrain_web").error(f"API: create_session failed: {exc}")
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"session_id": session.session_id, "state": session.last_state, "mode": session.mode}

    @app.delete("/api/session/{session_id}")
    def delete_session(session_id: str, current_user: User = Depends(get_current_user_optional)):
        try:
            session = manager.get_session(session_id)
            # Only allow owner to delete research sessions
            if session.mode == "research" and current_user and session.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Not authorized")
            manager.remove_session(session_id)
        except KeyError:
            pass  # Already gone, that's fine
        return {"status": "deleted"}

    @app.get("/api/state")
    def get_state(session_id: str):
        try:
            session = manager.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        return {"session_id": session.session_id, "state": session.last_state or session.katrain.get_state()}

    @app.post("/api/move")
    def play_move(request: MoveRequest, current_user: User = Depends(get_current_user_optional)):
        session = _get_session_or_404(manager, request.session_id)

        # Skip turn validation for research sessions
        # Enforce Multiplayer Turns (only if this is a multiplayer session)
        if session.mode != "research" and (session.player_b_id is not None or session.player_w_id is not None):
            # This is a multiplayer game - require authentication and turn check
            if current_user is None:
                raise HTTPException(status_code=401, detail="Authentication required for multiplayer games")
            state = session.katrain.get_state()
            next_player = state["player_to_move"]
            allowed_user_id = session.player_b_id if next_player == 'B' else session.player_w_id
            if current_user.id != allowed_user_id:
                raise HTTPException(status_code=403, detail="Not your turn")

        coords = None if request.pass_move else request.coords
        if coords is None and not request.pass_move:
            raise HTTPException(status_code=400, detail="coords required unless pass_move is true")
        with session.lock:
            session.katrain("play", None if coords is None else tuple(coords))
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/undo")
    def undo_move(request: UndoRedoRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("undo", request.n_times)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/redo")
    def redo_move(request: UndoRedoRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("redo", request.n_times)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.get("/api/sgf/save")
    def save_sgf(session_id: str):
        session = _get_session_or_404(manager, session_id)
        with session.lock:
            sgf = session.katrain.get_sgf()
        return {"sgf": sgf}

    @app.post("/api/sgf/load")
    def load_sgf(request: LoadSGFRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("load_sgf", request.sgf, skip_initial_analysis=request.skip_analysis)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/new-game")
    def new_game(request: NewGameRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            if request.players:
                for bw, p in request.players.items():
                    session.katrain("update_player", bw=bw, player_type=p.player_type, player_subtype=p.player_subtype, name=p.name)
                    if p.name:
                        session.katrain.game.root.set_property("P" + bw, p.name)
            
            if request.clear_cache:
                session.katrain.engine.on_new_game()

            session.katrain("new_game", size=request.size, handicap=request.handicap, komi=request.komi, rules=request.rules)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/game/setup")
    def game_setup(request: GameSettingsRequest):
        session = _get_session_or_404(manager, request.session_id)
        mode = request.mode
        settings = request.settings
        with session.lock:
            # Update players
            players = settings.get("players")
            if players:
                for bw, p in players.items():
                    session.katrain("update_player", bw=bw, player_type=p["player_type"], player_subtype=p["player_subtype"], name=p.get("name"))
                    if p.get("name"):
                        session.katrain.game.root.set_property("P" + bw, p["name"])

            if mode == "newgame" or mode == "setupposition":
                if settings.get("clear_cache"):
                    session.katrain.engine.on_new_game()
                session.katrain("new_game", size=settings.get("size"), handicap=settings.get("handicap"), komi=settings.get("komi"))
                if mode == "setupposition":
                    session.katrain("selfplay_setup", until_move=settings.get("setup_move"), target_b_advantage=settings.get("setup_advantage"))
            elif mode == "editgame":
                session.katrain("_do_edit_game", size=settings.get("size"), handicap=settings.get("handicap"), komi=settings.get("komi"), rules=settings.get("rules"))
            elif mode in ("free", "ranked"):
                # Kiosk human-vs-AI game setup
                color = settings.get("color", "black")
                human_bw = "B" if color == "black" else "W"
                ai_bw = "W" if color == "black" else "B"
                ai_strategy = settings.get("ai_strategy", "ai:default")
                rank_slider = int(settings.get("rank", 14))  # 0-28 slider value

                session.katrain("update_player", bw=human_bw, player_type="player:human", player_subtype="player:human")
                session.katrain("update_player", bw=ai_bw, player_type="player:ai", player_subtype=ai_strategy)

                if ai_strategy == "ai:human":
                    session.katrain.update_config(f"ai/ai:human/human_kyu_rank", 20 - rank_slider)
                else:
                    session.katrain.update_config(f"ai/{ai_strategy}/kyu_rank", rank_slider - 19)

                time_enabled = settings.get("time_enabled", False)
                if time_enabled:
                    session.katrain.update_config("timer/main_time", settings.get("main_time", 0))
                    session.katrain.update_config("timer/byo_length", settings.get("byo_length", 30))
                    session.katrain.update_config("timer/byo_periods", settings.get("byo_periods", 3))
                    session.katrain.update_config("timer/paused", False)
                else:
                    session.katrain.update_config("timer/main_time", 0)
                    session.katrain.update_config("timer/byo_length", 0)
                    session.katrain.update_config("timer/paused", True)

                session.katrain("new_game",
                    size=settings.get("board_size", 19),
                    handicap=settings.get("handicap", 0),
                    komi=settings.get("komi", 6.5),
                    rules=settings.get("rules", "japanese")
                )
            
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/edit-game")
    def edit_game(request: EditGameRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("edit_game", size=request.size, handicap=request.handicap, komi=request.komi, rules=request.rules)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/nav")
    def navigate(request: NavRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("nav", request.node_id)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/ai-move")
    def ai_move(request: UndoRedoRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("ai-move")
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.get("/api/config")
    def get_config(session_id: str, setting: str):
        session = _get_session_or_404(manager, session_id)
        # config is thread-safe enough for read
        value = session.katrain.config(setting)
        return {"setting": setting, "value": value}

    @app.post("/api/config")
    def update_config(request: ConfigUpdateRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain.update_config(request.setting, request.value)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/config/bulk")
    def update_config_bulk(request: ConfigBulkUpdateRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            for setting, value in request.updates.items():
                session.katrain.update_config(setting, value)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/player")
    def update_player(request: UpdatePlayerRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("update_player", bw=request.bw, player_type=request.player_type, player_subtype=request.player_subtype, name=request.name)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/player/swap")
    def swap_players(request: ToggleAnalysisRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("swap_players")
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/analysis/continuous")
    def toggle_continuous_analysis(request: ToggleAnalysisRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain.pondering = not session.katrain.pondering
            session.katrain.update_state()
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state, "pondering": session.katrain.pondering}

    @app.post("/api/analysis/extra")
    def analyze_extra(request: AnalyzeExtraRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            kwargs = request.kwargs or {}
            session.katrain("analyze_extra", mode=request.mode, **kwargs)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/analysis/show-pv")
    def show_pv(request: PVRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("_do_show_pv", request.pv)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/analysis/clear-pv")
    def clear_pv(request: ToggleAnalysisRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("_do_clear_pv")
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/mode")
    def set_mode(request: ModeRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain.play_analyze_mode = request.mode
            session.katrain.update_state()
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state, "mode": session.katrain.play_analyze_mode}

    @app.post("/api/nav/mistake")
    def find_mistake(request: FindMistakeRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("find_mistake", fn=request.fn)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/nav/branch")
    def switch_branch(request: SwitchBranchRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("switch_branch", direction=request.direction)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/analysis/tsumego")
    def tsumego_frame(request: TsumegoRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("tsumego_frame", ko=request.ko, margin=request.margin)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/analysis/selfplay")
    def selfplay(request: SelfPlayRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("selfplay_setup", until_move=request.until_move, target_b_advantage=request.target_b_advantage)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/analysis/region")
    def set_region(request: SelectBoxRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("select_box", coords=request.coords)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/resign")
    def resign(request: ToggleAnalysisRequest, current_user: User = Depends(get_current_user_optional)):
        session = _get_session_or_404(manager, request.session_id)

        # For multiplayer games, record the result
        is_multiplayer = session.player_b_id is not None or session.player_w_id is not None

        with session.lock:
            session.katrain("resign")
            state = session.katrain.get_state()
            session.last_state = state

        # Record game result for multiplayer
        if is_multiplayer and current_user:
            try:
                winner_id = session.player_w_id if current_user.id == session.player_b_id else session.player_b_id
                result = f"{'W' if winner_id == session.player_w_id else 'B'}+R"

                app.state.game_repo.record_multiplayer_game(
                    sgf_content=session.katrain.get_sgf(),
                    result=result,
                    game_type=getattr(session, 'game_type', 'free'),
                    black_id=session.player_b_id,
                    white_id=session.player_w_id,
                )

                manager._schedule_broadcast(session, {
                    "type": "game_end",
                    "data": {"reason": "resign", "winner_id": winner_id, "result": result}
                })
            except Exception as e:
                logging.getLogger("katrain_web").error(f"Failed to record game result: {e}")

        return {"session_id": session.session_id, "state": state}

    def _complete_count(session, app, current_user):
        """Helper to complete counting and record result."""
        # Get the score from current node's analysis
        current_node = session.katrain.game.current_node
        score = current_node.score

        if score is None:
            raise HTTPException(status_code=400, detail="Analysis not available yet. Please wait for KataGo analysis to complete.")

        # Format result: positive = Black leads, negative = White leads
        if score >= 0:
            result = f"B+{abs(score):.1f}"
            winner_color = "B"
        else:
            result = f"W+{abs(score):.1f}"
            winner_color = "W"

        # Set end state on the current node (game.end_result reads from current_node.end_state)
        session.katrain.game.game_result = result
        session.katrain.game.current_node.end_state = result

        # Record multiplayer game result
        is_multiplayer = session.player_b_id is not None or session.player_w_id is not None
        if is_multiplayer:
            winner_id = session.player_b_id if winner_color == "B" else session.player_w_id
            try:
                app.state.game_repo.record_multiplayer_game(
                    sgf_content=session.katrain.get_sgf(),
                    result=result,
                    game_type=getattr(session, 'game_type', 'free'),
                    black_id=session.player_b_id,
                    white_id=session.player_w_id,
                )
            except Exception as e:
                logging.getLogger("katrain_web").error(f"Failed to record count game result: {e}")

            manager._schedule_broadcast(session, {
                "type": "game_end",
                "data": {"reason": "count", "winner_id": winner_id, "result": result}
            })

        return result

    @app.post("/api/count/request")
    def request_count(request: CountRequest, current_user: User = Depends(get_current_user_optional)):
        """Request to end game by counting. For HvAI, completes immediately. For HvH, sends request to opponent."""
        session = _get_session_or_404(manager, request.session_id)

        # Verify move count >= configured minimum
        state = session.katrain.get_state()
        count_min_moves = session.katrain.config("game/count_min_moves", 100)
        if len(state.get("history", [])) < count_min_moves:
            raise HTTPException(status_code=400, detail=f"Cannot count before {count_min_moves} moves")

        # Check if game is already over
        if state.get("end_result"):
            raise HTTPException(status_code=400, detail="Game is already over")

        is_multiplayer = session.player_b_id is not None or session.player_w_id is not None

        if is_multiplayer:
            # HvH: Check if user is a player
            if not current_user:
                raise HTTPException(status_code=401, detail="Authentication required")

            is_player = current_user.id in (session.player_b_id, session.player_w_id)
            if not is_player:
                raise HTTPException(status_code=403, detail="Only players can request count")

            # Check if there's already a pending request
            if session.pending_count_request is not None:
                # If same user requests again, ignore
                if session.pending_count_request == current_user.id:
                    return {"session_id": session.session_id, "status": "pending"}

                # If other player requests, treat as accept
                with session.lock:
                    result = _complete_count(session, app, current_user)
                    session.pending_count_request = None
                    session.pending_count_timestamp = None
                    state = session.katrain.get_state()
                    session.last_state = state
                return {"session_id": session.session_id, "state": state, "result": result}

            # Set pending request
            import time as time_module
            session.pending_count_request = current_user.id
            session.pending_count_timestamp = time_module.time()

            # Broadcast to opponent
            manager._schedule_broadcast(session, {
                "type": "count_request",
                "data": {"requester_id": current_user.id, "requester_name": current_user.username}
            })

            return {"session_id": session.session_id, "status": "pending"}
        else:
            # HvAI: Complete immediately
            with session.lock:
                result = _complete_count(session, app, current_user)
                state = session.katrain.get_state()
                session.last_state = state
            return {"session_id": session.session_id, "state": state, "result": result}

    @app.post("/api/count/respond")
    def respond_count(request: CountResponse, current_user: User = Depends(get_current_user)):
        """Respond to a count request (HvH only). Accept or reject."""
        session = _get_session_or_404(manager, request.session_id)

        # Only for multiplayer games
        is_multiplayer = session.player_b_id is not None or session.player_w_id is not None
        if not is_multiplayer:
            raise HTTPException(status_code=400, detail="Not a multiplayer game")

        # Check if there's a pending request
        if session.pending_count_request is None:
            raise HTTPException(status_code=400, detail="No pending count request")

        # Verify user is the opponent (not the requester)
        if current_user.id == session.pending_count_request:
            raise HTTPException(status_code=400, detail="Cannot respond to your own request")

        # Verify user is a player
        is_player = current_user.id in (session.player_b_id, session.player_w_id)
        if not is_player:
            raise HTTPException(status_code=403, detail="Only players can respond to count")

        if request.accept:
            # Accept: complete the count
            with session.lock:
                result = _complete_count(session, app, current_user)
                session.pending_count_request = None
                session.pending_count_timestamp = None
                state = session.katrain.get_state()
                session.last_state = state
            return {"session_id": session.session_id, "state": state, "result": result, "accepted": True}
        else:
            # Reject: clear request and notify
            session.pending_count_request = None
            session.pending_count_timestamp = None

            manager._schedule_broadcast(session, {
                "type": "count_rejected",
                "data": {"rejected_by": current_user.id}
            })

            return {"session_id": session.session_id, "accepted": False}

    @app.post("/api/timeout")
    def timeout(request: ToggleAnalysisRequest, current_user: User = Depends(get_current_user_optional)):
        """End game due to timeout - current player loses on time"""
        session = _get_session_or_404(manager, request.session_id)

        # For multiplayer games, record the result
        is_multiplayer = session.player_b_id is not None or session.player_w_id is not None

        with session.lock:
            session.katrain("timeout")
            state = session.katrain.get_state()
            session.last_state = state

        # Record game result for multiplayer
        if is_multiplayer and current_user:
            try:
                winner_id = session.player_w_id if current_user.id == session.player_b_id else session.player_b_id
                result = f"{'W' if winner_id == session.player_w_id else 'B'}+T"

                app.state.game_repo.record_multiplayer_game(
                    sgf_content=session.katrain.get_sgf(),
                    result=result,
                    game_type=getattr(session, 'game_type', 'free'),
                    black_id=session.player_b_id,
                    white_id=session.player_w_id,
                )

                manager._schedule_broadcast(session, {
                    "type": "game_end",
                    "data": {"reason": "timeout", "winner_id": winner_id, "result": result}
                })
            except Exception as e:
                logging.getLogger("katrain_web").error(f"Failed to record game result: {e}")

        return {"session_id": session.session_id, "state": state}

    @app.post("/api/multiplayer/leave")
    def leave_multiplayer_game(request: ToggleAnalysisRequest, current_user: User = Depends(get_current_user)):
        """Leave a multiplayer game (counts as forfeit)"""
        session = _get_session_or_404(manager, request.session_id)

        is_multiplayer = session.player_b_id is not None or session.player_w_id is not None
        if not is_multiplayer:
            raise HTTPException(status_code=400, detail="Not a multiplayer game")

        # Check if user is a player
        is_player = current_user.id in (session.player_b_id, session.player_w_id)
        if not is_player:
            # Spectator leaving - just return
            return {"status": "left", "redirect": "/galaxy/play/human"}

        # Player leaving = forfeit
        winner_id = session.player_w_id if current_user.id == session.player_b_id else session.player_b_id
        result = f"{'W' if winner_id == session.player_w_id else 'B'}+F"  # F for Forfeit

        try:
            app.state.game_repo.record_multiplayer_game(
                sgf_content=session.katrain.get_sgf(),
                result=result,
                game_type=getattr(session, 'game_type', 'free'),
                black_id=session.player_b_id,
                white_id=session.player_w_id,
            )
        except Exception as e:
            logging.getLogger("katrain_web").error(f"Failed to record game forfeit: {e}")

        # Broadcast game end to all connected sockets
        manager._schedule_broadcast(session, {
            "type": "game_end",
            "data": {"reason": "forfeit", "winner_id": winner_id, "result": result, "leaver_id": current_user.id}
        })

        # Clean up the session
        manager.remove_session(request.session_id)

        return {"status": "forfeited", "redirect": "/galaxy/play/human"}

    @app.post("/api/timer/pause")
    def pause_timer(request: ToggleAnalysisRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain.timer_paused = not session.katrain.timer_paused
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state, "paused": session.katrain.timer_paused}

    @app.post("/api/rotate")
    def rotate(request: ToggleAnalysisRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("rotate")
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/node/delete")
    def delete_node(request: NavRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("delete_node", node_id=request.node_id)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/node/prune")
    def prune_branch(request: NavRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("prune_branch", node_id=request.node_id)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/node/make-main")
    def make_main_branch(request: NavRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("make_main_branch", node_id=request.node_id)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/node/toggle-collapse")
    def toggle_collapse(request: NavRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("toggle_collapse", node_id=request.node_id)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/ui/toggle")
    def toggle_ui(request: UIToggleRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("toggle_ui", setting=request.setting)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/language")
    def switch_language(request: LanguageRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("switch_lang", lang=request.lang)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state, "language": session.katrain.config("general/language")}

    @app.get("/api/translations")
    def get_translations(lang: str):
        from katrain.core.lang import i18n
        # Switch language temporarily to get the catalog if needed, 
        # but i18n.switch_lang is global.
        # However, the frontend will call this when it wants to refresh its labels.
        i18n.switch_lang(lang)
        catalog = getattr(i18n.ugettext.__self__, "_catalog", {})
        return {"lang": lang, "translations": catalog}

    @app.get("/api/ai-constants")
    def get_ai_constants():
        from katrain.core.constants import (
            AI_STRATEGIES_RECOMMENDED_ORDER,
            AI_OPTION_VALUES,
            AI_KEY_PROPERTIES,
            AI_CONFIG_DEFAULT
        )
        # Convert range objects to lists for JSON serialization
        json_option_values = {}
        for k, v in AI_OPTION_VALUES.items():
            if isinstance(v, range):
                json_option_values[k] = list(v)
            elif isinstance(v, list):
                # Check for tuples inside list (value, label)
                new_list = []
                for item in v:
                    if isinstance(item, tuple):
                        new_list.append(list(item))
                    else:
                        new_list.append(item)
                json_option_values[k] = new_list
            else:
                json_option_values[k] = v

        # Default settings for each AI strategy
        strategy_defaults = {
            "ai:default": {},
            "ai:antimirror": {},
            "ai:handicap": {"automatic": True, "pda": 0},
            "ai:jigo": {"target_score": 0.5},
            "ai:scoreloss": {"strength": 0.2},
            "ai:policy": {"opening_moves": 24},
            "ai:simple": {
                "max_points_lost": 1.75,
                "settled_weight": 1.0,
                "opponent_fac": 0.5,
                "min_visits": 3,
                "attach_penalty": 1,
                "tenuki_penalty": 0.5
            },
            "ai:p:weighted": {"weaken_fac": 0.5, "pick_override": 1.0, "lower_bound": 0.001},
            "ai:p:pick": {"pick_override": 0.95, "pick_n": 5, "pick_frac": 0.35},
            "ai:p:local": {"pick_override": 0.95, "stddev": 1.5, "pick_n": 15, "pick_frac": 0.0, "endgame": 0.5},
            "ai:p:tenuki": {"pick_override": 0.85, "stddev": 7.5, "pick_n": 5, "pick_frac": 0.4, "endgame": 0.45},
            "ai:p:influence": {"pick_override": 0.95, "pick_n": 5, "pick_frac": 0.3, "threshold": 3.5, "line_weight": 10, "endgame": 0.4},
            "ai:p:territory": {"pick_override": 0.95, "pick_n": 5, "pick_frac": 0.3, "threshold": 3.5, "line_weight": 2, "endgame": 0.4},
            "ai:p:rank": {"kyu_rank": -2},
            "ai:human": {"human_kyu_rank": 0, "modern_style": True},
            "ai:pro": {"pro_year": 2010, "modern_style": True},
        }

        return {
            "strategies": AI_STRATEGIES_RECOMMENDED_ORDER,
            "options": json_option_values,
            "key_properties": list(AI_KEY_PROPERTIES),
            "default_strategy": AI_CONFIG_DEFAULT,
            "strategy_defaults": strategy_defaults
        }

    @app.post("/api/ai/estimate-rank")
    def estimate_rank(request: RankEstimationRequest):
        from katrain.core.ai import ai_rank_estimation
        from katrain.core.lang import rank_label
        try:
            rank = ai_rank_estimation(request.strategy, request.settings)
            return {"rank": rank_label(rank)}
        except Exception as e:
            logging.getLogger("katrain_web").error(f"Rank estimation failed: {e}")
            return {"rank": "??"}

    @app.post("/api/theme")
    def switch_theme(request: ThemeRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("switch_theme", theme=request.theme)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state, "theme": session.katrain.config("trainer/theme")}

    @app.post("/api/analysis/game")
    def analyze_game(request: GameAnalysisRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            kwargs = {
                "visits": request.visits,
                "mistakes_only": request.mistakes_only,
                "move_range": request.move_range,
            }
            # remove None values
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            session.katrain("game_analysis", **kwargs)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.post("/api/analysis/scan")
    def analysis_scan(request: AnalysisScanRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("analysis_scan", visits=request.visits or 500)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    @app.get("/api/analysis/progress")
    def analysis_progress(session_id: str):
        session = _get_session_or_404(manager, session_id)
        with session.lock:
            progress = session.katrain._do_analysis_progress()
        return {"session_id": session.session_id, **progress}

    @app.post("/api/analysis/report")
    def get_game_report(request: GameReportRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            report = session.katrain._do_game_report(depth_filter=request.depth_filter)
        return {"session_id": session.session_id, "report": report}

    @app.post("/api/mode/insert")
    def set_insert_mode(request: InsertModeRequest):
        session = _get_session_or_404(manager, request.session_id)
        with session.lock:
            session.katrain("insert_mode", mode=request.mode)
            state = session.katrain.get_state()
            session.last_state = state
        return {"session_id": session.session_id, "state": state}

    # NOTE: /ws/lobby MUST be defined BEFORE /ws/{session_id} to avoid routing conflicts
    @app.websocket("/ws/lobby")
    async def lobby_websocket_endpoint(websocket: WebSocket):
        from katrain.web.api.v1.endpoints.auth import get_user_from_token
        logger = logging.getLogger("katrain_web")
        token = websocket.query_params.get("token")
        if not token:
            logger.warning("Lobby WebSocket: No token provided, closing connection")
            await websocket.accept()
            await websocket.close(code=1008, reason="No token provided")
            return

        try:
            current_user = await get_user_from_token(token=token, repo=app.state.user_repo)
        except Exception as e:
            logger.warning(f"Lobby WebSocket: Token validation failed: {e}")
            await websocket.accept()
            await websocket.close(code=1008, reason="Invalid token")
            return

        await websocket.accept()
        lobby_manager = app.state.lobby_manager
        lobby_manager.add_user(current_user.id, websocket)
        logger.info(f"User {current_user.username} (ID: {current_user.id}) joined the lobby. Online users: {lobby_manager.get_online_user_ids()}")
        try:
            # Broadcast update immediately
            await lobby_manager.broadcast({"type": "lobby_update", "online_count": len(lobby_manager.get_online_user_ids())})
            while True:
                message = await websocket.receive_json()
                msg_type = message.get("type")
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                
                elif msg_type == "start_matchmaking":
                    game_type = message.get("game_type", "free")
                    logging.getLogger("katrain_web").info(f"User {current_user.username} (ID: {current_user.id}) started matchmaking for {game_type}")

                    # Prerequisite Check for Rated Games
                    if game_type == "rated":
                        count = app.state.user_repo.count_completed_rated_games(current_user.id)
                        if count < 3:
                            await websocket.send_json({
                                "type": "error",
                                "code": "PREREQUISITE_FAILED",
                                "message": f"You must complete 3 rated AI games before playing rated PvP. (Completed: {count}/3)"
                            })
                            continue

                    match = app.state.matchmaker.add_to_queue(current_user.id, game_type, websocket)
                    if match:
                        logging.getLogger("katrain_web").info(f"Match found: {match.player1_id} vs {match.player2_id}")
                        # Fetch Usernames
                        user_repo = app.state.user_repo
                        u1 = user_repo.get_user_by_id(match.player1_id)
                        u2 = user_repo.get_user_by_id(match.player2_id)
                        
                        # Create Multiplayer Session
                        # Randomly assign B/W
                        import random
                        if random.random() < 0.5:
                            pb, pw = match.player1_id, match.player2_id
                            pb_name, pw_name = u1.get("username") if u1 else "Black", u2.get("username") if u2 else "White"
                        else:
                            pb, pw = match.player2_id, match.player1_id
                            pb_name, pw_name = u2.get("username") if u2 else "Black", u1.get("username") if u1 else "White"
                        
                        game_session = app.state.session_manager.create_multiplayer_session(
                            pb, pw, b_name=pb_name, w_name=pw_name
                        )
                        
                        # Found a match!
                        match_payload = {
                            "type": "match_found",
                            "match_id": match.match_id,
                            "session_id": game_session.session_id,
                            "game_type": match.game_type,
                            "players": {
                                "player_b": pb,
                                "player_w": pw,
                                "player_b_name": pb_name,
                                "player_w_name": pw_name
                            }
                        }
                        
                        # Send reliably
                        try:
                            await match.player1_socket.send_json(match_payload)
                        except Exception as e:
                            logger.error(f"Failed to send match to Player 1: {e}")
                            
                        try:
                            await match.player2_socket.send_json(match_payload)
                        except Exception as e:
                            logger.error(f"Failed to send match to Player 2: {e}")

                elif msg_type == "stop_matchmaking":
                    app.state.matchmaker.remove_from_queue(current_user.id)

                elif msg_type == "invite":
                    target_id = message.get("target_id")
                    if target_id and target_id != current_user.id:
                        # Find target sockets
                        # Note: accessing _online_users directly as get_online_user_ids only returns keys
                        # We need to expose sockets or lock properly. LobbyManager._online_users is internal but we are in the same module logic context mostly.
                        # Ideally LobbyManager should expose a method 'send_to_user'
                        with lobby_manager._lock:
                            target_sockets = list(lobby_manager._online_users.get(target_id, []))
                        
                        if target_sockets:
                            invite_payload = {
                                "type": "invitation",
                                "from_id": current_user.id,
                                "from_name": current_user.username,
                                "mode": message.get("mode", "free")
                            }
                            for ws in target_sockets:
                                try: await ws.send_json(invite_payload)
                                except: pass
                            
                            # Confirm to sender
                            await websocket.send_json({"type": "info", "message": "Invitation sent."})
                        else:
                            await websocket.send_json({"type": "error", "message": "User is offline or not in lobby."})

                elif msg_type == "accept_invite":
                    target_id = message.get("target_id") # The inviter
                    if target_id:
                         # Fetch Usernames
                        user_repo = app.state.user_repo
                        all_users = user_repo.list_users()
                        users_by_id = {u["id"]: u["username"] for u in all_users}

                        # Create Session (Inviter = Black, Acceptor = White by default, or random)
                        pb, pw = target_id, current_user.id
                        
                        game_session = app.state.session_manager.create_multiplayer_session(
                            pb, pw, b_name=users_by_id.get(pb), w_name=users_by_id.get(pw)
                        )
                        
                        match_payload = {
                            "type": "match_found",
                            "session_id": game_session.session_id,
                            "game_type": "free", # Direct invites are free for now
                             "players": {
                                "player_b": pb,
                                "player_w": pw
                            }
                        }
                        
                        # Send to self (Acceptor)
                        await websocket.send_json(match_payload)
                        
                        # Send to Inviter
                        with lobby_manager._lock:
                            target_sockets = list(lobby_manager._online_users.get(target_id, []))
                        for ws in target_sockets:
                            try: await ws.send_json(match_payload)
                            except: pass

        except WebSocketDisconnect:
            logging.getLogger("katrain_web").info(f"User {current_user.username} disconnected from lobby.")
            pass
        finally:
            app.state.matchmaker.remove_from_queue(current_user.id)
            lobby_manager.remove_user(current_user.id, websocket)
            await lobby_manager.broadcast({"type": "lobby_update", "online_count": len(lobby_manager.get_online_user_ids())})

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        try:
            session = manager.get_session(session_id)
        except KeyError:
            await websocket.accept()
            await websocket.close(code=1008, reason="Session not found")
            return

        await websocket.accept()
        session.sockets.add(websocket)
        try:
            state = session.last_state or session.katrain.get_state()
            state["sockets_count"] = len(session.sockets)
            # Send initial state to this client
            await websocket.send_json({"type": "game_update", "state": state})
            # Broadcast updated spectator count to all other clients (lightweight update)
            manager.broadcast_to_session(session_id, {"type": "spectator_count", "count": len(session.sockets)})
            while True:
                message = await websocket.receive_json()
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "chat":
                    manager.broadcast_to_session(session_id, message)
        except WebSocketDisconnect:
            pass
        finally:
            session.sockets.discard(websocket)
            # Broadcast updated spectator count when someone leaves
            if session.sockets:  # Only if there are still connected clients
                manager.broadcast_to_session(session_id, {"type": "spectator_count", "count": len(session.sockets)})

    @app.websocket("/ws/vision")
    async def vision_websocket(websocket: WebSocket):
        """Vision event WebSocket — pushes sync events and status changes to the frontend."""
        await websocket.accept()
        vision = getattr(app.state, "vision", None)
        if vision is None:
            await websocket.close(code=1008, reason="Vision service not enabled")
            return
        try:
            while True:
                # Poll for events and send them
                vision.refresh_status()
                events = vision.poll_events()
                for evt in events:
                    if isinstance(evt, dict):
                        await websocket.send_json(evt)

                # Send status update periodically
                await websocket.send_json({
                    "type": "vision_status",
                    "data": {
                        "camera_status": vision.camera_status,
                        "pose_lock_status": vision.pose_lock_status,
                        "sync_state": vision.sync_state,
                    },
                })

                # Check for client messages (ping)
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            pass

    # SPA Routing for Galaxy UI
    @app.get("/galaxy", response_class=FileResponse)
    @app.get("/galaxy/{full_path:path}", response_class=FileResponse)
    async def serve_galaxy_app(full_path: str = None):
        return str(static_root / "index.html")

    # SPA Routing for Kiosk UI
    @app.get("/kiosk", response_class=FileResponse)
    @app.get("/kiosk/{full_path:path}", response_class=FileResponse)
    async def serve_kiosk_app(full_path: str = None):
        return str(static_root / "index.html")

    # SPA Routing for Video Recorder
    @app.get("/record", response_class=FileResponse)
    async def serve_record_app():
        return str(static_root / "index.html")

    # Catch-all for other static files (like vite.svg and JS/CSS in assets/)
    app.mount("/", StaticFiles(directory=static_root, html=True), name="root")

    return app


async def _cleanup_loop(manager: SessionManager):
    while True:
        await asyncio.sleep(30)
        manager.cleanup_expired()


def _get_session_or_404(manager: SessionManager, session_id: str):
    try:
        return manager.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


async def _vision_move_poller(app: FastAPI):
    """Poll vision worker for confirmed moves, submit via VisionPlayerBridge."""
    from katrain.vision.ipc import ConfirmedMove
    from katrain.vision.katrain_bridge import vision_move_to_katrain
    from katrain.vision.sync import game_state_stones_to_board

    log = logging.getLogger("katrain_web.vision")
    while True:
        try:
            vision = getattr(app.state, "vision", None)
            if vision and vision.bound_session_id:
                move_data = vision.get_confirmed_move()
                if move_data and isinstance(move_data, ConfirmedMove):
                    session_id = vision.bound_session_id
                    manager = app.state.session_manager
                    session = manager.get_session(session_id)
                    if session:
                        # Convert to KaTrain move and submit
                        move = vision_move_to_katrain(
                            move_data.col, move_data.row, move_data.color, board_size=19
                        )
                        session.katrain("play", move.coords)
                        log.info("Vision move submitted: col=%d row=%d color=%d", move_data.col, move_data.row, move_data.color)

                        # Update expected board from new game state
                        game_state = session.get_game_state()
                        if game_state and "stones" in game_state:
                            vision.set_expected_from_stones(game_state["stones"])
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Vision move poller error: %s", e)
        await asyncio.sleep(0.1)


def build_frontend():
    ui_path = Path(__file__).resolve().parent / "ui"
    if not (ui_path / "package.json").exists():
        logging.getLogger("katrain_web").warning("Frontend source not found, skipping build.")
        return

    import shutil
    import subprocess
    import sys

    if not shutil.which("npm"):
        logging.getLogger("katrain_web").warning("npm not found, skipping frontend build. UI might be outdated.")
        return

    print("Building frontend...", flush=True)
    try:
        # Check dependencies
        if not (ui_path / "node_modules").exists():
            print("Installing frontend dependencies...", flush=True)
            subprocess.run(["npm", "install"], cwd=ui_path, check=True, capture_output=False)
        
        # Build
        subprocess.run(["npm", "run", "build"], cwd=ui_path, check=True, capture_output=False)
        print("Frontend build successful.", flush=True)
    except subprocess.CalledProcessError as e:
        print(f"Frontend build failed with exit code {e.returncode}.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error during frontend build: {e}", file=sys.stderr)
        sys.exit(1)


def run_web():
    default_host = settings.KATRAIN_HOST
    default_port = settings.KATRAIN_PORT
    parser = argparse.ArgumentParser(description="Run KaTrain Web UI server")
    parser.add_argument(
        "--host",
        default=default_host,
        help="Host to bind the server to. Default: $KATRAIN_HOST or 0.0.0.0.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="Port to bind the server to. Default: $KATRAIN_PORT or 8001.",
    )
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="warning")
    parser.add_argument("--disable-engine", action="store_true")
    parser.add_argument("--ui", default=None, help="Interface mode to use. web (default) starts the FastAPI server, while desktop launches the Kivy GUI.")
    parser.add_argument("--vision-backend", default="onnx", choices=["onnx", "rknn", "ultralytics"], help="Vision inference backend")
    parser.add_argument("--vision-model", default=None, help="Path to vision model file. Providing this enables the vision service.")
    parser.add_argument("--vision-camera", default="0", help="Camera device ID (int) or path (e.g. /dev/video73)")
    args, _unknown = parser.parse_known_args()

    # Configure vision service if model path provided
    if args.vision_model:
        from katrain.vision.config_service import VisionServiceConfig

        camera_dev = int(args.vision_camera) if args.vision_camera.isdigit() else args.vision_camera
        settings._vision_config = VisionServiceConfig(
            enabled=True,
            backend=args.vision_backend,
            model_path=args.vision_model,
            camera_device=camera_dev,
            process_mode="worker" if settings.KATRAIN_MODE == "board" else "inprocess",
        )

    # Build frontend if running in web mode and not explicitly disabled (could add flag later if needed)
    # We only build if we are actually starting the web server, or if --ui=web is explicit
    # However, create_app is used by uvicorn workers too, so we should be careful.
    # But run_web is the entry point.
    if not args.reload:  # Skip build in reload mode to avoid loops
        build_frontend()

    import uvicorn

    host = args.host
    port = args.port
    
    # Configure uvicorn logging to reduce noise
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "%(levelname)s:     %(message)s"
    log_config["formatters"]["access"]["fmt"] = "%(levelname)s:     %(message)s"

    print(f"\n" + "=" * 50, flush=True)
    print(f"Starting KaTrain Web UI", flush=True)
    if host == "0.0.0.0":
        print(f"Local access: http://127.0.0.1:{port}", flush=True)
        print(f"Network access: http://<your-ip-address>:{port}", flush=True)
    else:
        print(f"Access: http://{host}:{port}", flush=True)
    print("=" * 50 + "\n", flush=True)

    app = create_app(enable_engine=not args.disable_engine)
    uvicorn.run(
        app, 
        host=host, 
        port=port, 
        reload=args.reload, 
        log_level=args.log_level,
        access_log=False # Disable access logs to keep console clean for KataGo logs
    )


if __name__ == "__main__":
    run_web()
