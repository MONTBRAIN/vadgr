"""Health check endpoint -- also the phone's post-pair connectivity probe."""

from fastapi import APIRouter, Request

from api.config import settings
from api.utils.platform import machine_platform

router = APIRouter()


@router.get("/api/health")
async def health(request: Request):
    transport = getattr(request.app.state, "transport", None)
    return {
        "status": "healthy",
        "modules": {
            "computer_use": settings.computer_use_enabled,
        },
        "platform": machine_platform(),
        "version": settings.version,
        "transport": transport.status() if transport is not None else None,
    }
