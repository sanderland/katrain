"""REST API endpoints for cross-platform online play."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from katrain.web.api.v1.endpoints.auth import get_current_user
from katrain.web.models import User

logger = logging.getLogger("katrain_web")

router = APIRouter()


# --- Request/Response models ---


class PlatformLoginRequest(BaseModel):
    username: str
    password: str


class PlatformChallengeRequest(BaseModel):
    user_id: str
    board_size: int = 19
    time_control: dict = {}
    rules: str = "chinese"
    ranked: bool = True
    handicap: int = 0
    komi: Optional[float] = None


class AcceptChallengeRequest(BaseModel):
    challenge_id: str


class DeclineChallengeRequest(BaseModel):
    challenge_id: str


class AutomatchRequest(BaseModel):
    board_size: int = 19
    time_control: dict = {}
    rank_range: Optional[list[int]] = None


# --- Credential management ---


@router.post("/{platform}/login")
async def platform_login(platform: str, req: PlatformLoginRequest, request: Request, user: User = Depends(get_current_user)):
    """Login to a Go platform. Tries saved JWT first, then password."""
    from katrain.web.platforms.models import PlatformCredentials

    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Unknown platform: {platform}")

    # Try saved credentials (JWT token) first to avoid OGS rate-limiting
    saved = pm._credential_store.load_credentials(user.id, platform)
    if saved and saved.auth_data.get("user_jwt"):
        saved.auth_data["password"] = req.password  # Keep password as fallback
        success = await pm.connect_platform(platform, saved, user.id)
        if success:
            return {"status": "connected", "platform": platform, "username": saved.username}

    # Fresh login with password
    credentials = PlatformCredentials(platform=platform, username=req.username, auth_data={"password": req.password})
    success = await pm.connect_platform(platform, credentials, user.id)
    if not success:
        raise HTTPException(status_code=401, detail="Login failed")

    return {"status": "connected", "platform": platform, "username": req.username}


@router.delete("/{platform}/logout")
async def platform_logout(platform: str, request: Request, user: User = Depends(get_current_user)):
    """Logout from a platform and delete saved credentials."""
    pm = request.app.state.platform_manager
    await pm.disconnect_platform(platform)
    pm._credential_store.delete_credentials(user.id, platform)
    return {"status": "disconnected", "platform": platform}


@router.get("/status")
async def platform_status(request: Request, user: User = Depends(get_current_user)):
    """List all platforms and their connection/credential status."""
    pm = request.app.state.platform_manager
    platforms = pm.list_platforms()
    saved = {p["platform"]: p["username"] for p in pm._credential_store.list_platforms(user.id)}
    for p in platforms:
        p["saved_username"] = saved.get(p["platform"])
    return {"platforms": platforms}


# --- Lobby ---


@router.get("/{platform}/users")
async def platform_users(platform: str, q: Optional[str] = None, room: Optional[str] = None, request: Request = None, user: User = Depends(get_current_user)):
    """List online users on a platform.

    Without `q`: returns seek graph / open challenge users (actively looking for games).
    With `q`: searches players by username prefix.
    """
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")

    if q:
        # Specific player search
        users = await adapter.get_online_users(room=q)
    else:
        # Default: show seek graph users (one entry per open challenge)
        challenges = await adapter.get_open_challenges()
        seen = set()
        users = []
        for c in challenges:
            # Deduplicate by username (not user_id which may be empty)
            key = c.from_user.username
            if key not in seen:
                seen.add(key)
                c.from_user.status = "seeking"
                users.append(c.from_user)
    return {"users": [{"user_id": u.user_id, "username": u.username, "rank": u.rank, "status": u.status} for u in users]}


@router.get("/{platform}/rooms")
async def platform_rooms(platform: str, request: Request, user: User = Depends(get_current_user)):
    """List rooms/channels on a platform (Fox, KGS)."""
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")
    if not adapter.supports_rooms:
        raise HTTPException(status_code=400, detail=f"{platform} does not support rooms")
    rooms = await adapter.get_rooms()
    return {"rooms": rooms}


@router.get("/{platform}/challenges")
async def platform_challenges(platform: str, request: Request, user: User = Depends(get_current_user)):
    """List open challenges on a platform (OGS seek graph)."""
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")
    challenges = await adapter.get_open_challenges()
    return {"challenges": challenges}


# --- Challenge flow ---


@router.post("/{platform}/challenge")
async def send_challenge(platform: str, req: PlatformChallengeRequest, request: Request, user: User = Depends(get_current_user)):
    """Send a challenge to a user on a platform."""
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")
    challenge_id = await adapter.send_challenge(req.user_id, req.model_dump())
    return {"challenge_id": challenge_id}


@router.post("/{platform}/challenge/accept")
async def accept_challenge(platform: str, req: AcceptChallengeRequest, request: Request, user: User = Depends(get_current_user)):
    """Accept an incoming challenge."""
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")
    game_session = await adapter.accept_challenge(req.challenge_id)
    session_id = await pm.start_platform_game(platform, game_session, user.id)
    return {"session_id": session_id, "game": game_session.__dict__}


@router.post("/{platform}/challenge/decline")
async def decline_challenge(platform: str, req: DeclineChallengeRequest, request: Request, user: User = Depends(get_current_user)):
    """Decline an incoming challenge."""
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")
    await adapter.decline_challenge(req.challenge_id)
    return {"status": "declined"}


# --- Automatch ---


@router.post("/{platform}/automatch/start")
async def start_automatch(platform: str, req: AutomatchRequest, request: Request, user: User = Depends(get_current_user)):
    """Start automatch on a platform."""
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")
    if not adapter.supports_automatch:
        raise HTTPException(status_code=400, detail=f"{platform} does not support automatch")
    await adapter.start_automatch(req.model_dump())
    return {"status": "searching"}


@router.post("/{platform}/automatch/cancel")
async def cancel_automatch(platform: str, request: Request, user: User = Depends(get_current_user)):
    """Cancel automatch on a platform."""
    pm = request.app.state.platform_manager
    adapter = pm.get_adapter(platform)
    if adapter is None or not adapter.is_connected:
        raise HTTPException(status_code=400, detail=f"Not connected to {platform}")
    await adapter.cancel_automatch()
    return {"status": "cancelled"}
