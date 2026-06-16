"""Pairing endpoints: mint a one-time token (pair) and redeem it (claim)."""

import socket

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.auth import tokens
from api.config import settings
from api.models.auth import ClaimRequest, ClaimResponse, PairResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _machine_name() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "vadgr"


@router.post("/pair", response_model=PairResponse)
async def pair(request: Request):
    """Mint a one-time, short-lived pairing token and return the QR payload.

    Refuses (503) when the transport can't advertise a reachable host -- we
    never hand out a localhost QR a phone could not use."""
    transport = request.app.state.transport
    host = transport.advertise_host()
    if host is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "TRANSPORT_UNAVAILABLE",
                    "message": (
                        "Transport cannot advertise a reachable address. Enable "
                        "Tailscale (VADGR_TRANSPORT=tailscale) to pair over your tailnet."
                    ),
                    "details": {"transport": transport.name},
                }
            },
        )

    pairing_token, _ = request.app.state.pairing_store.mint()
    return PairResponse(
        host=host,
        port=settings.port,
        pairing_token=pairing_token,
        machine_name=_machine_name(),
    )


@router.post("/claim", response_model=ClaimResponse)
async def claim(body: ClaimRequest, request: Request):
    """Redeem a pairing token (one-time) for a persistent device token.

    The plaintext token is returned exactly once; only its hash is stored."""
    consumed = request.app.state.pairing_store.consume(body.pairing_token)
    if not consumed:
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

    token = tokens.generate_token()
    device = await request.app.state.device_repo.create(
        machine_name=body.device_name,
        token_hash=tokens.hash_token(token),
    )
    return ClaimResponse(token=token, device_id=device["id"])
