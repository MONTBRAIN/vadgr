"""`POST /api/runs` end to end over HTTP.

The route tests elsewhere stub the service out so they can assert the route.
This one does not: it drives the real execution service from the real route,
with only the provider replaced, so the chain from a task sentence to a
completed run row and its frames is exercised in one piece.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.engine.providers import ExecutionEvent
from api.main import create_app
from api.persistence.database import Database
from api.persistence.repositories import RunRepository
from api.services.execution_service import ExecutionService
from api.transport import LoopbackTransport
from api.websocket.events import make_event
from api.websocket.manager import ConnectionManager


class _RecordingProvider:
    """A provider that answers with a fixed script and records its prompt."""

    def __init__(self, *events: ExecutionEvent):
        self.events = events
        self.prompts: list[str] = []

    async def execute_streaming(self, prompt, **kwargs):
        self.prompts.append(prompt)
        for event in self.events:
            yield event


@pytest_asyncio.fixture
async def wired(tmp_path):
    """The real app, the real service, one fake provider, and the frames it
    broadcast."""
    db = Database(":memory:")
    await db.connect()
    await db.create_tables()

    app = create_app(db)
    app.state.db = db
    app.state.run_repo = RunRepository(db)
    app.state.transport = LoopbackTransport()
    app.state.ws_manager = ConnectionManager()
    app.state.active_run_tasks = {}

    frames: list[tuple[str, str, dict]] = []

    async def emit(run_id, event_type, data):
        frames.append((run_id, event_type, data))
        await app.state.ws_manager.broadcast_event(run_id, make_event(event_type, data))

    provider = _RecordingProvider(
        ExecutionEvent(type="output", data="looking"),
        ExecutionEvent(type="done", data="seven unread, two need you"),
    )
    service = ExecutionService(run_repo=app.state.run_repo, emit=emit)

    async def _fixed_provider(*args, **kwargs):
        return provider

    service._get_run_provider = _fixed_provider
    app.state.execution_service = service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app, provider, frames

    for task in list(app.state.active_run_tasks.values()):
        if not task.done():
            task.cancel()
    await db.disconnect()


async def _drain(app):
    """Let the run task the route created finish."""
    tasks = list(app.state.active_run_tasks.values())
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_sentence_becomes_a_completed_run(wired):
    client, app, provider, _ = wired

    resp = await client.post("/api/runs", json={"task": "Check my mail"})
    assert resp.status_code == 202
    run_id = resp.json()["id"]
    await _drain(app)

    row = (await client.get(f"/api/runs/{run_id}")).json()
    assert row["status"] == "completed"
    assert row["outputs"] == {"result": "seven unread, two need you"}
    assert row["agent_name"] == "Check my mail"


@pytest.mark.asyncio
async def test_the_prompt_is_the_sentence_verbatim(wired):
    client, app, provider, _ = wired

    await client.post("/api/runs", json={"task": "Check my mail"})
    await _drain(app)

    assert provider.prompts == ["Check my mail"]


@pytest.mark.asyncio
async def test_the_frames_are_the_published_vocabulary(wired):
    client, app, _, frames = wired

    resp = await client.post("/api/runs", json={"task": "Check my mail"})
    run_id = resp.json()["id"]
    await _drain(app)

    kinds = [kind for _, kind, _ in frames]
    assert kinds == [
        "run_started", "agent_started", "agent_log", "agent_completed", "run_completed",
    ]
    started = next(data for _, kind, data in frames if kind == "agent_started")
    assert started == {"run_id": run_id, "name": "Check my mail"}


@pytest.mark.asyncio
async def test_a_run_that_fails_lands_failed_with_its_error(wired):
    client, app, provider, frames = wired
    provider.events = (ExecutionEvent(type="error", data="the loop gave up"),)

    resp = await client.post("/api/runs", json={"task": "Check my mail"})
    run_id = resp.json()["id"]
    await _drain(app)

    row = (await client.get(f"/api/runs/{run_id}")).json()
    assert row["status"] == "failed"
    assert row["outputs"] == {"error": "the loop gave up"}
    assert ("run_failed" in [kind for _, kind, _ in frames])


@pytest.mark.asyncio
async def test_the_run_path_creates_no_directories(wired, monkeypatch):
    """Seven pieces of per-run filesystem work left the run path: no output
    directories, no log writer, no step files, no materialized artifacts. The
    journal under the engine's own tree is a different thing and is untouched."""
    import pathlib

    client, app, _, _ = wired
    made: list[str] = []
    real_mkdir = pathlib.Path.mkdir

    def recording_mkdir(self, *args, **kwargs):
        made.append(str(self))
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "mkdir", recording_mkdir)

    await client.post("/api/runs", json={"task": "Check my mail"})
    await _drain(app)

    assert made == [], f"the run path created directories: {made}"


@pytest.mark.asyncio
async def test_the_run_is_cancellable_while_it_runs(wired):
    client, app, provider, _ = wired

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_stream(prompt, **kwargs):
        started.set()
        await release.wait()
        yield ExecutionEvent(type="done", data="never")

    provider.execute_streaming = slow_stream

    resp = await client.post("/api/runs", json={"task": "Check my mail"})
    run_id = resp.json()["id"]
    await asyncio.wait_for(started.wait(), timeout=2)

    cancel = await client.post(f"/api/runs/{run_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "failed"
    release.set()
    await _drain(app)
