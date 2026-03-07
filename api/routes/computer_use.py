"""Computer use status and direct control routes."""

from fastapi import APIRouter

from api.config import settings

router = APIRouter(prefix="/api/computer-use", tags=["computer-use"])


@router.get("/status")
async def computer_use_status():
    available = settings.computer_use_enabled
    return {
        "available": available,
        "platform": "wsl2",
    }
