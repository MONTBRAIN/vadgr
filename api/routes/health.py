"""Health check endpoint -- also the phone's post-pair connectivity probe."""

from fastapi import APIRouter, Request

from api.config import settings

router = APIRouter()


@router.get("/api/health")
async def health(request: Request):
    transport = getattr(request.app.state, "transport", None)
    return {
        "status": "healthy",
        "modules": {
            "forge": True,
            "computer_use": settings.computer_use_enabled,
        },
        "platform": "wsl2",
        "version": settings.version,
        "transport": transport.status() if transport is not None else None,
    }
