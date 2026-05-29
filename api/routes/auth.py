"""Pairing endpoints for mobile / tailnet devices."""

from __future__ import annotations

import platform
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.auth.tokens import hash_token
from api.config import settings

router = APIRouter(tags=["auth"])


class ClaimRequest(BaseModel):
    token: str = Field(..., min_length=8)
    machine_name: str = Field(..., min_length=1, max_length=120)


@router.post("/api/auth/pair")
async def pair(request: Request):
    """Mint a one-time pairing token.

    Returned JSON: `{host, port, token, machine_name}`. The desktop
    displays this as a QR code; the mobile device redeems the token via
    POST /api/auth/claim within PAIRING_TTL_SECONDS.
    """
    store = request.app.state.pairing_store
    token, _expires_at = store.mint()
    return {
        "host": settings.host,
        "port": settings.port,
        "token": token,
        "machine_name": platform.node() or "vadgr",
    }


@router.post("/api/auth/claim")
async def claim(body: ClaimRequest, request: Request):
    """Redeem a pairing token for a persistent device token.

    The pairing token is invalidated on success (one-time use).
    """
    store = request.app.state.pairing_store
    if not store.consume(body.token):
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "INVALID_PAIRING_TOKEN",
                    "message": "Pairing token is invalid, already used, or expired.",
                    "details": {},
                }
            },
        )

    device_repo = request.app.state.device_repo
    persistent_token = secrets.token_urlsafe(32)
    device = await device_repo.create(
        machine_name=body.machine_name,
        token_hash=hash_token(persistent_token),
    )
    return {
        "token": persistent_token,
        "device_id": device["id"],
        "machine_name": device["machine_name"],
        "paired_at": device["paired_at"],
    }
