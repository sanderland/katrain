from fastapi import APIRouter
from katrain.web.api.v1.endpoints import health, auth, analysis, games, users, live, tsumego, kifu, user_games, board, vision, tutorials

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
api_router.include_router(user_games.router, prefix="/user-games", tags=["user-games"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(live.router, prefix="/live", tags=["live"])
api_router.include_router(tsumego.router, prefix="/tsumego", tags=["tsumego"])
api_router.include_router(kifu.router, prefix="/kifu", tags=["kifu"])
api_router.include_router(board.router, prefix="/board", tags=["board"])
api_router.include_router(vision.router, prefix="/vision", tags=["vision"])
api_router.include_router(tutorials.router, prefix="/tutorials", tags=["tutorials"])
