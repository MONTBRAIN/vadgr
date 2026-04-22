"""Settings routes for experimental features."""

from fastapi import APIRouter
from pydantic import BaseModel

from api.services.computer_use_setup import (
    get_status,
    enable_computer_use,
    disable_computer_use,
)
from api.services.gateway_setup import (
    get_status as get_gateway_status,
    update_discord,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ComputerUseUpdate(BaseModel):
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


class DiscordUpdate(BaseModel):
    enabled: bool
    token: str | None = None


@router.get("/messaging-gateway")
async def messaging_gateway_status():
    return get_gateway_status()


@router.put("/messaging-gateway/discord")
async def update_discord_gateway(body: DiscordUpdate):
    return update_discord(enabled=body.enabled, token=body.token)
