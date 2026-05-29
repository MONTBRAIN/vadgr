"""Bearer-token middleware.

Localhost requests (CLI on the same machine, frontend served on
loopback) bypass auth entirely. Anything originating from a non-loopback
peer must present a valid bearer token: either the default token
stored at ~/.config/vadgr/token, or a paired-device token whose hash
matches a row in the `devices` table.

WebSocket connections are handled by their own route (the WS handshake
is not part of an HTTP middleware call — Starlette dispatches it
directly to the WebSocket route). The WS route is responsible for
calling `authorize_ws` below.

Implemented as a pure ASGI middleware (no `BaseHTTPMiddleware`) so it
does not spawn an extra task group per request. That keeps the event
loop scheduling stable for tests that rely on the order of
`asyncio.create_task` calls inside route handlers.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.auth.tokens import get_default_token, hash_token

logger = logging.getLogger(__name__)

# Paths that bypass auth even from non-localhost peers.
_PUBLIC_PATHS = {"/api/health"}

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _is_loopback(host: Optional[str]) -> bool:
    if host is None:
        return True
    h = host.lower()
    if h in _LOOPBACK_HOSTS:
        return True
    if h.startswith("127."):
        return True
    return False


def _extract_bearer_from_headers(headers: list) -> Optional[str]:
    for raw_key, raw_val in headers:
        if raw_key.lower() == b"authorization":
            val = raw_val.decode("latin-1")
            parts = val.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip()
    return None


async def _send_json_401(send: Send, code: str, message: str) -> None:
    body = json.dumps(
        {"error": {"code": code, "message": message, "details": {}}}
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


async def authorize_ws(
    request_app,
    headers: dict,
    query_token: Optional[str],
    client_host: Optional[str],
) -> bool:
    """Authorization helper for WebSocket routes."""
    if _is_loopback(client_host):
        return True
    token: Optional[str] = None
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if auth_header:
        parts = auth_header.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    if token is None and query_token:
        token = query_token
    if not token:
        return False
    default = get_default_token()
    if default and token == default:
        return True
    device_repo = getattr(request_app.state, "device_repo", None)
    if device_repo is None:
        return False
    token_hash = hash_token(token)
    device = await device_repo.find_by_token_hash(token_hash)
    if device is None:
        return False
    try:
        await device_repo.touch(device["id"])
    except Exception:
        pass
    return True


class BearerTokenMiddleware:
    """Pure ASGI bearer-token middleware for non-localhost HTTP requests."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "")

        # CORS preflight: defer to CORSMiddleware.
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if path in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else None
        if _is_loopback(client_host):
            await self.app(scope, receive, send)
            return

        token = _extract_bearer_from_headers(scope.get("headers", []))
        if not token:
            await _send_json_401(
                send,
                "MISSING_TOKEN",
                "Authorization: Bearer <token> required for non-localhost requests.",
            )
            return

        default = get_default_token()
        if default and token == default:
            await self.app(scope, receive, send)
            return

        # Device-token lookup requires app.state.device_repo.
        app_obj = scope.get("app")
        device_repo = getattr(app_obj.state, "device_repo", None) if app_obj else None
        if device_repo is not None:
            token_hash = hash_token(token)
            device = await device_repo.find_by_token_hash(token_hash)
            if device is not None:
                try:
                    await device_repo.touch(device["id"])
                except Exception:  # pragma: no cover
                    logger.warning("device_repo.touch failed for %s", device["id"])
                await self.app(scope, receive, send)
                return

        await _send_json_401(
            send,
            "INVALID_TOKEN",
            "Bearer token is invalid or has been revoked.",
        )
