"""WS /api/runs/{run_id}/stream: RunEvent translation + auth + revocation."""

from datetime import datetime, timezone

import anyio
import pytest
import pytest_asyncio
from starlette.testclient import TestClient

from api.main import create_app
from api.persistence.database import Database
from api.routes.ws import _to_run_event, _RunEventTranslator
from api.models.run import RunEventType
from api.transport import LoopbackTransport


# --- pure translation -------------------------------------------------------


def test_internal_event_maps_to_run_event():
    ev = _to_run_event(
        {
            "type": "run_started",
            "data": {"x": 1},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    assert ev.type == RunEventType.STARTED
    assert ev.payload == {"x": 1}


def test_run_completed_maps_to_completed():
    assert _to_run_event({"type": "run_completed", "data": {}}).type == RunEventType.COMPLETED


def test_unmappable_event_dropped():
    assert _to_run_event({"type": "task_progress", "data": {}}) is None


def test_translator_only_forwards_mapped_events():
    sent = []

    class _Sock:
        async def send_text(self, txt):
            sent.append(txt)

    translator = _RunEventTranslator(_Sock())

    async def run():
        await translator.send_json({"type": "task_progress", "data": {}})  # dropped
        await translator.send_json(
            {
                "type": "run_failed",
                "data": {"e": 1},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    anyio.run(run)
    assert len(sent) == 1
    assert '"failed"' in sent[0]


# --- live socket via TestClient (lifespan wires state from our db) -----------


@pytest_asyncio.fixture
async def live_db():
    database = Database(":memory:")
    await database.connect()
    await database.create_tables()
    await database.conn.execute("INSERT INTO runs (id, status) VALUES ('run-1', 'running')")
    await database.conn.commit()
    yield database
    await database.disconnect()


def test_stream_loopback_accepts_and_translates(live_db):
    app = create_app(live_db, transport=LoopbackTransport())
    with TestClient(app) as tc:
        with tc.websocket_connect("/api/runs/run-1/stream") as ws:
            # Broadcast an internal event from within the app's event loop via
            # the manager; the translator must deliver a contract RunEvent.
            tc.portal.call(
                lambda: app.state.ws_manager.broadcast_event(
                    "run-1",
                    {
                        "type": "run_started",
                        "data": {"hello": "world"},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )
            frame = ws.receive_json()
            assert frame["type"] == "started"
            assert frame["payload"] == {"hello": "world"}


def test_stream_unknown_run_is_rejected(live_db):
    app = create_app(live_db, transport=LoopbackTransport())
    with TestClient(app) as tc:
        with pytest.raises(Exception):
            with tc.websocket_connect("/api/runs/does-not-exist/stream"):
                pass


class _DenyAll(LoopbackTransport):
    """Treats the TestClient peer as a non-loopback, non-authorized source so
    the WS auth path rejects (no token)."""

    def is_authorized_source(self, peer_ip):
        return False


def test_stream_rejects_unauthorized_non_loopback(live_db, monkeypatch):
    import api.routes.ws as ws_module
    import api.auth.middleware as mw_module

    # Force both the WS route and the shared authorize_ws helper to treat the
    # TestClient peer as a non-loopback source.
    monkeypatch.setattr(ws_module, "_is_loopback", lambda host: False)
    monkeypatch.setattr(mw_module, "_is_loopback", lambda host: False)
    app = create_app(live_db, transport=_DenyAll())
    with TestClient(app) as tc:
        with pytest.raises(Exception):
            with tc.websocket_connect("/api/runs/run-1/stream"):
                pass


# --- the map must name what the daemon actually emits (E2E 0.4.1 F9) --------


def test_every_mapped_key_is_a_name_the_daemon_broadcasts():
    """The map is a contract with the emitter, and it was one-sided.

    Five of its eight keys - `step_started`, `tool_call`, `step_output`,
    `output`, `approval_required` - were emitted by nothing, so the phone got
    `started`, silence, `completed`. Asserting against the source keeps the two
    sides from drifting again, which is the whole failure mode: nothing raises
    when a map names a string nobody sends.
    """
    from api.routes.ws import _EVENT_TYPE_MAP
    from api.tests.frames import emitted_frame_names

    unsent = set(_EVENT_TYPE_MAP) - emitted_frame_names()
    assert not unsent, f"mapped but never broadcast: {sorted(unsent)}"


def test_progress_and_gate_events_reach_the_phone():
    """The two that matter: a run's progress, and a gate asking for a human."""
    assert _to_run_event({"type": "agent_log", "data": {"message": "step one"}}).type is RunEventType.OUTPUT
    assert _to_run_event({"type": "awaiting", "data": {"prompt": "which folder?"}}).type is RunEventType.PAUSED
    assert _to_run_event({"type": "agent_failed", "data": {}}).type is RunEventType.FAILED


def test_a_deferred_type_is_quiet_and_an_unknown_one_is_not(caplog):
    """`todos` is understood and waiting on `0.5.0`; an unrecognized type is a
    gap nobody has looked at. Both drop, so the log is the only thing that
    tells them apart afterwards."""
    import logging

    with caplog.at_level(logging.WARNING):
        assert _to_run_event({"type": "todos", "data": {"items": []}}) is None
    assert not caplog.records, "a deliberate deferral must not warn"

    with caplog.at_level(logging.WARNING):
        assert _to_run_event({"type": "a_type_added_later", "data": {}}) is None
    assert any("no RunEvent" in r.message for r in caplog.records)
