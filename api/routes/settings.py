"""Settings routes for experimental features."""

from fastapi import APIRouter

from api.models.common import StrictBody
from api.services.computer_use_setup import (
    get_status,
    enable_computer_use,
    disable_computer_use,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ComputerUseUpdate(StrictBody):
    enabled: bool


@router.get("/computer-use")
async def get_computer_use_status():
    return get_status()


@router.put("/computer-use")
async def update_computer_use(body: ComputerUseUpdate):
    if body.enabled:
        result = enable_computer_use()
    else:
        result = disable_computer_use()
    return result
