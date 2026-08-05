"""Pairing endpoints: mint a one-time code (pair) and redeem it (claim)."""

import socket

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.auth import tokens
from api.auth.pairing_store import ClaimResult
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
    """Mint a one-time, short-lived pairing code and return the QR payload.

    Refuses (503) when the transport can't advertise a reachable host -- we
    never hand out a localhost QR a phone could not use."""
    transport = request.app.state.transport
    host = transport.advertise_host()
    if host is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "TRANSPORT_UNREACHABLE",
                    "message": (
                        "Transport cannot advertise a reachable address. Enable "
                        "Tailscale (VADGR_TRANSPORT=tailscale) to pair over your tailnet."
                    ),
                    "details": {"transport": transport.name},
                }
            },
        )

    # The field on the wire stays `pairing_token`; only the value it carries
    # changed shape. Renaming it would break the shipped CLI and the phone.
    pairing_code, _ = request.app.state.pairing_store.mint()
    return PairResponse(
        host=host,
        port=settings.port,
        pairing_token=pairing_code,
        machine_name=_machine_name(),
    )


@router.post("/claim", response_model=ClaimResponse)
async def claim(body: ClaimRequest, request: Request):
    """Redeem a pairing code (one-time) for a persistent device token.

    The plaintext token is returned exactly once; only its hash is stored."""
    result = request.app.state.pairing_store.redeem(body.pairing_token)
    if result is ClaimResult.RATE_LIMITED:
        # Fired exactly once, at the moment the cap acts -- the one moment "too
        # many attempts" is a fact distinct from "not claimable", and what lets
        # the phone say the code is dead instead of inviting another retype.
        # No `retry_after`: the recovery is a new code, not waiting.
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": (
                        "Too many failed attempts. That pairing code is no longer "
                        "valid; generate a new one on the machine."
                    ),
                    "details": {},
                }
            },
        )
    if result is ClaimResult.EXPIRED:
        # 410 rather than 401, and the split is the point: the phone tells the
        # owner to ask for a new code instead of that they mistyped this one.
        return JSONResponse(
            status_code=410,
            content={
                "error": {
                    "code": "PAIRING_CODE_EXPIRED",
                    "message": "That pairing code has expired. Generate a new one on the machine.",
                    "details": {},
                }
            },
        )
    if result is not ClaimResult.OK:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "PAIRING_CODE_INVALID",
                    "message": "That pairing code is wrong or has already been used.",
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
