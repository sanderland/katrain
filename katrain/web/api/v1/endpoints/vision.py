"""Vision REST API endpoints — thin proxies to VisionService."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# -- Request models ----------------------------------------------------------


class BindRequest(BaseModel):
    session_id: str


class SetupModeRequest(BaseModel):
    target_board: list[list[int]]  # (board_size x board_size) matrix


# -- Helpers -----------------------------------------------------------------


def _get_vision(request: Request):
    """Get VisionService from app state, raise 404 if not enabled."""
    vision = getattr(request.app.state, "vision", None)
    if vision is None:
        raise HTTPException(status_code=404, detail="Vision service not enabled")
    return vision


# -- Endpoints ---------------------------------------------------------------


@router.get("/status")
async def vision_status(request: Request):
    """Return vision service status."""
    vision = _get_vision(request)
    vision.refresh_status()
    return {
        "enabled": vision.enabled,
        "camera_status": vision.camera_status,
        "pose_lock_status": vision.pose_lock_status,
        "sync_state": vision.sync_state,
        "bound_session_id": vision.bound_session_id,
    }


@router.get("/stream")
async def vision_stream(request: Request):
    """MJPEG video stream of the camera preview (2-3 fps, backpressure-aware)."""
    vision = _get_vision(request)
    vision.set_viewer_active(True)

    async def generate():
        try:
            while True:
                jpeg = vision.get_preview_jpeg()
                if jpeg:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                await asyncio.sleep(0.05)  # ~20 fps polling
        finally:
            vision.set_viewer_active(False)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace;boundary=frame")


@router.get("/detected-board")
async def get_detected_board(request: Request):
    """Return the latest detected board state as a 19x19 matrix."""
    vision = _get_vision(request)
    vision.refresh_status()
    board = vision.get_detected_board()
    return {"board": board}


@router.post("/pose-lock/confirm")
async def confirm_pose_lock(request: Request):
    """Confirm board pose lock after calibration."""
    vision = _get_vision(request)
    ok = vision.confirm_pose_lock()
    return {"ok": ok}


@router.post("/bind")
async def bind_session(request: Request, body: BindRequest):
    """Bind vision to a game session."""
    vision = _get_vision(request)
    manager = request.app.state.session_manager
    session = manager.get_session(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {body.session_id} not found")

    vision.bind_session(body.session_id)

    # Set expected board from current game state
    game_state = session.get_game_state()
    if game_state and "stones" in game_state:
        vision.set_expected_from_stones(game_state["stones"])

    return {"ok": True, "session_id": body.session_id}


@router.post("/unbind")
async def unbind_session(request: Request):
    """Unbind from current session."""
    vision = _get_vision(request)
    vision.unbind_session()
    return {"ok": True}


@router.post("/sync/reset")
async def reset_sync(request: Request):
    """Reset sync — accept current physical board as new baseline. Research mode only."""
    vision = _get_vision(request)
    vision.reset_sync()
    return {"ok": True}


@router.post("/setup-mode")
async def enter_setup_mode(request: Request, body: SetupModeRequest):
    """Enter tsumego setup mode with a target board position."""
    vision = _get_vision(request)
    import numpy as np

    target = np.array(body.target_board, dtype=int)
    vision.enter_setup_mode(target)
    return {"ok": True}
