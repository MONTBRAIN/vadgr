"""Settings routes for experimental features."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from api.services.computer_use_setup import (
    get_status,
    enable_computer_use,
    disable_computer_use,
    update_cache_setting,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ComputerUseUpdate(BaseModel):
    enabled: bool
    cache_enabled: bool = True


@router.get("/computer-use")
async def get_computer_use_status():
    return get_status()


@router.put("/computer-use")
async def update_computer_use(body: ComputerUseUpdate):
    if body.enabled:
        result = enable_computer_use(cache_enabled=body.cache_enabled)
    else:
        result = disable_computer_use()
    return result
