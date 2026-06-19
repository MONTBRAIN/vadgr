"""Device management: list paired devices, revoke one."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.models.device import Device

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[Device])
async def list_devices(request: Request):
    rows = await request.app.state.device_repo.list_all()
    return [Device(**row) for row in rows]


@router.delete("/{device_id}")
async def revoke_device(device_id: str, request: Request):
    """Revoke a device. Future requests with its token fail Gate 2; any live WS
    connections it holds are dropped now (revocation propagation)."""
    deleted = await request.app.state.device_repo.delete(device_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "DEVICE_NOT_FOUND",
                    "message": f"Device '{device_id}' not found.",
                    "details": {},
                }
            },
        )
    # Drop any live WS connections owned by this device.
    ws_manager = getattr(request.app.state, "ws_manager", None)
    if ws_manager is not None and hasattr(ws_manager, "disconnect_device"):
        await ws_manager.disconnect_device(device_id)
    return {"status": "revoked", "device_id": device_id}
