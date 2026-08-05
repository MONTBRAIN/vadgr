"""Two-gate middleware: gate order, loopback bypass, rejects, happy path.

Exercises the pure-ASGI ``TwoGateMiddleware`` directly with crafted scopes so
we control the peer IP (httpx's ASGITransport always reports 127.0.0.1)."""

import pytest

from api.auth import tokens
from api.auth.devices import DeviceRepository
from api.auth.middleware import TwoGateMiddleware, authorize_ws


class _FakeTransport:
    name = "fake"

    def is_authorized_source(self, peer_ip):
        return peer_ip.startswith("100.")

    def advertise_host(self):
        return "host"

    def is_available(self):
        return True

    def bind_host(self):
        return "100.1.2.3"

    def status(self):
        return {}


class _AppState:
    pass


class _App:
    def __init__(self, device_repo):
        self.state = _AppState()
        self.state.device_repo = device_repo


async def _call(middleware, *, host, path="/api/devices", token=None):
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "client": (host, 12345) if host is not None else None,
        "app": middleware._app_for_test,
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await middleware(scope, receive, send)
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    return status, sent


def _make_middleware(device_repo):
    reached = {"hit": False}

    async def inner(scope, receive, send):
        reached["hit"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = TwoGateMiddleware(inner, transport=_FakeTransport())
    mw._app_for_test = _App(device_repo)
    mw._reached = reached
    return mw


@pytest.mark.asyncio
async def test_gate0_loopback_bypasses_everything(db):
    mw = _make_middleware(DeviceRepository(db))
    status, _ = await _call(mw, host="127.0.0.1", token=None)
    assert status == 200
    assert mw._reached["hit"] is True


@pytest.mark.asyncio
async def test_gate1_non_tailnet_rejected_before_token(db):
    mw = _make_middleware(DeviceRepository(db))
    # A LAN peer with NO token: must be rejected at gate 1 (403), not gate 2.
    status, _ = await _call(mw, host="192.168.1.50", token=None)
    assert status == 403
    assert mw._reached["hit"] is False


@pytest.mark.asyncio
async def test_gate2_authorized_source_bad_token_rejected(db):
    mw = _make_middleware(DeviceRepository(db))
    status, _ = await _call(mw, host="100.64.1.2", token="bogus")
    assert status == 401
    assert mw._reached["hit"] is False


@pytest.mark.asyncio
async def test_gate2_authorized_source_missing_token_rejected(db):
    mw = _make_middleware(DeviceRepository(db))
    status, _ = await _call(mw, host="100.64.1.2", token=None)
    assert status == 401


@pytest.mark.asyncio
async def test_happy_path_tailnet_peer_with_valid_token(db):
    repo = DeviceRepository(db)
    token = tokens.generate_token()
    await repo.create("Phone", tokens.hash_token(token))
    mw = _make_middleware(repo)
    status, _ = await _call(mw, host="100.64.1.2", token=token)
    assert status == 200
    assert mw._reached["hit"] is True


@pytest.mark.asyncio
async def test_public_paths_skip_gates(db):
    mw = _make_middleware(DeviceRepository(db))
    for path in ("/api/health", "/api/auth/pair", "/api/auth/claim"):
        status, _ = await _call(mw, host="8.8.8.8", path=path, token=None)
        assert status == 200, path


# --- WS authorize helper ----------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_ws_loopback_allowed(db):
    app = _App(DeviceRepository(db))
    assert await authorize_ws(app, _FakeTransport(), "127.0.0.1", None) is True


@pytest.mark.asyncio
async def test_authorize_ws_non_tailnet_rejected(db):
    app = _App(DeviceRepository(db))
    assert await authorize_ws(app, _FakeTransport(), "192.168.0.5", "anything") is False


@pytest.mark.asyncio
async def test_authorize_ws_tailnet_requires_valid_token(db):
    repo = DeviceRepository(db)
    token = tokens.generate_token()
    await repo.create("Phone", tokens.hash_token(token))
    app = _App(repo)
    assert await authorize_ws(app, _FakeTransport(), "100.64.1.2", token) is True
    assert await authorize_ws(app, _FakeTransport(), "100.64.1.2", "bad") is False


# -- the socket that had no auth at all --------------------------------------

@pytest.mark.asyncio
async def test_both_run_sockets_authorize():
    """Regression: `/api/ws/runs/{id}` checked nothing.

    The auth middleware is HTTP-only, so a WebSocket route that does not call
    the authorizer itself is open to every peer gate 1 admits - which over a
    tailnet is every member of it. That socket also honoured an inbound
    `approval_response`, making it an unauthenticated way to answer a
    human-approval gate.
    """
    import inspect

    from api.routes import ws as ws_routes

    for fn in (ws_routes.run_websocket, ws_routes.run_stream):
        src = inspect.getsource(fn)
        assert "authorize_ws" in src, f"{fn.__name__} does not authorize"
        assert "4401" in src, f"{fn.__name__} does not close unauthorized"


@pytest.mark.asyncio
async def test_neither_socket_acts_on_an_inbound_frame():
    """Answering a gate is an authenticated, idempotent, audited HTTP call.

    A socket that accepts decisions is a second authorization surface to get
    right, and it was the one that was wrong.
    """
    import inspect

    from api.routes import ws as ws_routes

    src = inspect.getsource(ws_routes.run_websocket)
    assert "resume_after_approval" not in src, (
        "the socket resumes a run from an inbound frame again"
    )


def test_options_no_longer_skips_the_gates():
    """`OPTIONS` was waved through so a browser's preflight could reach
    `CORSMiddleware`. That middleware went with the dashboard, and no client
    here speaks preflight - so the exemption skipped all three gates for anyone
    who asked with the right verb and protected nothing in return."""
    import inspect
    from api.auth import middleware

    src = inspect.getsource(middleware.TwoGateMiddleware.__call__)
    assert '"OPTIONS"' not in src, "OPTIONS is exempt from the gates again"
    assert "_PUBLIC_PATHS" in src, "the pairing paths must still be public"
