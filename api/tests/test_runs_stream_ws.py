"""Tests for the mobile-friendly run WebSocket stream.

Uses FastAPI / Starlette's sync TestClient because httpx ASGITransport
does not support WebSockets.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.auth.tokens import set_default_token


def _make_test_client(app):
    return TestClient(app)


def _create_run_sync(app, run_id="test-run-stream"):
    """Insert a run row directly using the existing run_repo."""
    import asyncio

    async def _insert():
        run_repo = app.state.run_repo
        agent_repo = app.state.agent_repo
        # Need an agent to satisfy FK chain? runs.agent_id is nullable. Skip.
        run = await run_repo.create(agent_id=None, inputs={})
        # repository uses uuid4, but we want a stable id for the URL — override
        await app.state.db.conn.execute(
            "UPDATE runs SET id = ? WHERE id = ?", (run_id, run["id"]),
        )
        await app.state.db.conn.commit()
        return run_id

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_insert())
    finally:
        loop.close()


class TestRunStreamWS:

    def test_ws_accepts_connection_with_valid_token(self, app):
        """WS /api/runs/{id}/stream accepts an authenticated connection."""
        set_default_token("default-token")
        run_id = "test-run-ws-1"
        # Create the run synchronously
        import asyncio
        asyncio.run(_seed_run(app, run_id))

        client = _make_test_client(app)
        with client.websocket_connect(
            f"/api/runs/{run_id}/stream",
            headers={"Authorization": "Bearer default-token"},
        ) as ws:
            # Manager replays buffer + the connection is open.
            # We just confirm the handshake succeeded.
            assert ws is not None

    def test_ws_receives_event_with_expected_schema(self, app):
        set_default_token("default-token")
        run_id = "test-run-ws-2"
        import asyncio
        asyncio.run(_seed_run(app, run_id))

        client = _make_test_client(app)
        with client.websocket_connect(
            f"/api/runs/{run_id}/stream",
            headers={"Authorization": "Bearer default-token"},
        ) as ws:
            # Push an event through the manager
            async def _emit():
                await app.state.ws_manager.emit(
                    run_id, "started", {"hello": "world"},
                )
            asyncio.run(_emit())
            raw = ws.receive_text()
            event = json.loads(raw)
            assert event["type"] == "started"
            assert event["data"] == {"hello": "world"}
            assert "timestamp" in event

    def test_ws_supports_documented_event_types(self):
        """All five mobile event types are valid through make_event."""
        from api.websocket.events import make_event
        for t in ("started", "tool_call", "output", "paused", "completed", "failed"):
            ev = make_event(t, {})
            assert ev["type"] == t


async def _seed_run(app, run_id):
    run_repo = app.state.run_repo
    created = await run_repo.create(agent_id=None, inputs={})
    await app.state.db.conn.execute(
        "UPDATE runs SET id = ? WHERE id = ?", (run_id, created["id"]),
    )
    await app.state.db.conn.commit()
    return run_id
