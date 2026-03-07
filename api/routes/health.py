"""Health check endpoint."""

from fastapi import APIRouter

from api.config import settings

router = APIRouter()


@router.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "modules": {
            "forge": True,
            "computer_use": settings.computer_use_enabled,
        },
        "platform": "wsl2",
        "version": settings.version,
    }
