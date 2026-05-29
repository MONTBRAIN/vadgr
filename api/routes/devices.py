"""Paired-device management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter(tags=["devices"])


def _redact(device: dict) -> dict:
    """Strip secret material from a device row before returning to clients."""
    return {
        "id": device["id"],
        "machine_name": device["machine_name"],
        "paired_at": device["paired_at"],
        "last_seen": device["last_seen"],
    }


@router.get("/api/devices")
async def list_devices(request: Request):
    device_repo = request.app.state.device_repo
    rows = await device_repo.list_all()
    return {"devices": [_redact(d) for d in rows]}


@router.delete("/api/devices/{device_id}", status_code=204)
async def delete_device(device_id: str, request: Request):
    device_repo = request.app.state.device_repo
    existing = await device_repo.get(device_id)
    if not existing:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "DEVICE_NOT_FOUND",
                    "message": f"Device with id '{device_id}' not found",
                    "details": {},
                }
            },
        )
    await device_repo.delete(device_id)
    return Response(status_code=204)
