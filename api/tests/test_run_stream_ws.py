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
