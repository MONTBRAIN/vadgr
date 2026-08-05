"""The two gates -- and nothing else (SRP).

Every request passes through, in order:

  Gate 0  loopback bypass: a 127.0.0.0/8 source is allowed outright, which is
          what keeps the on-box CLI working without a token.
  Gate 1  network: ``transport.is_authorized_source(peer_ip)`` -- a non-tailnet
          source is rejected *before* the token is even looked at.
  Gate 2  token: a valid ``Authorization: Bearer <token>`` (or ``?token=`` for
          WS) must hash to a stored device row.

The middleware depends only on the ``TransportProvider`` port (DIP) plus the
device repo -- never on Tailscale directly. Implemented as a pure ASGI
middleware (no ``BaseHTTPMiddleware``) so it adds no per-request task group,
keeping event-loop scheduling stable for the rest of the suite.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from starlette.types import ASGIApp, Receive, Scope, Send

from api.auth.tokens import hash_token
from api.transport.base import TransportProvider

logger = logging.getLogger(__name__)

# Paths reachable without a token -- the phone's connectivity probe and the
# pair/claim handshake itself (a phone has no token yet when it claims).
_PUBLIC_PATHS = {"/api/health", "/api/auth/pair", "/api/auth/claim"}


def _client_host(scope: Scope) -> Optional[str]:
    client = scope.get("client")
    return client[0] if client else None


def _extract_bearer(headers: list) -> Optional[str]:
    for raw_key, raw_val in headers:
        if raw_key.lower() == b"authorization":
            parts = raw_val.decode("latin-1").split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip()
    return None


async def _send_json_error(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps(
        {"error": {"code": code, "message": message, "details": {}}}
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def authenticate_device(app, token: Optional[str]) -> Optional[dict]:
    """Gate 2 helper, shared by HTTP and WS. Returns the device row on success
    (and touches its ``last_seen``), or ``None``."""
    if not token:
        return None
    device_repo = getattr(app.state, "device_repo", None)
    if device_repo is None:
        return None
    device = await device_repo.find_by_token_hash(hash_token(token))
    if device is None:
        return None
    try:
        await device_repo.touch(device["id"])
    except Exception:  # pragma: no cover -- best-effort bookkeeping
        logger.warning("device_repo.touch failed for %s", device["id"])
    return device


async def authorize_ws(
    app,
    transport: TransportProvider,
    client_host: Optional[str],
    token: Optional[str],
) -> bool:
    """Run the two gates for a WebSocket handshake (the middleware never sees
    the WS handshake -- Starlette dispatches it straight to the route)."""
    # Gate 0: loopback bypass.
    if _is_loopback(client_host):
        return True
    # Gate 1: network authorization.
    if client_host is None or not transport.is_authorized_source(client_host):
        return False
    # Gate 2: token.
    return await authenticate_device(app, token) is not None


def _is_loopback(host: Optional[str]) -> bool:
    if host is None:
        return False
    h = host.lower()
    return h in {"127.0.0.1", "::1", "localhost", "testclient"} or h.startswith("127.")


class TwoGateMiddleware:
    """Pure ASGI middleware enforcing Gate 0/1/2 on HTTP requests."""

    def __init__(self, app: ASGIApp, transport: TransportProvider):
        self.app = app
        self.transport = transport

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "")

        # CORS preflight -> defer to CORSMiddleware.
        if method == "OPTIONS" or path in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        host = _client_host(scope)

        # Gate 0: loopback bypass.
        if _is_loopback(host):
            await self.app(scope, receive, send)
            return

        # Gate 1: network authorization (before any token work).
        if host is None or not self.transport.is_authorized_source(host):
            await _send_json_error(
                send,
                403,
                "SOURCE_NOT_AUTHORIZED",
                "Source is not an authorized peer on this transport.",
            )
            return

        # Gate 2: token.
        token = _extract_bearer(scope.get("headers", []))
        app_obj = scope.get("app")
        device = await authenticate_device(app_obj, token) if app_obj else None
        if device is None:
            await _send_json_error(
                send,
                401,
                "INVALID_TOKEN" if token else "MISSING_TOKEN",
                "A valid Bearer token is required.",
            )
            return

        await self.app(scope, receive, send)
