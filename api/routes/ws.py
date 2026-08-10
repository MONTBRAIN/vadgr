"""WebSocket routes for live run streaming.

Two surfaces:
  - ``/api/ws/runs/{run_id}``      -- the existing desktop stream (raw events).
  - ``/api/runs/{run_id}/stream``  -- the mobile stream: same machinery, but
    every frame is a contract ``RunEvent`` and the connection is guarded by the
    two-gate auth (header or ``?token=``).
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth.middleware import authorize_ws, authenticate_device, _is_loopback
from api.models.run import RunEvent, RunEventType

logger = logging.getLogger(__name__)
router = APIRouter()


# Map internal broadcast event types -> the mobile RunEvent contract.
#
# Every key here must be a name the daemon actually broadcasts. Five of the
# original eight were not: `step_started`, `tool_call`, `step_output`, `output`
# and `approval_required` are emitted by nothing, while the execution service's
# real vocabulary - `agent_log`, `awaiting`, `agent_failed`, `todos` - was absent. A
# phone therefore received `started`, then silence, then `completed`, however
# long the run and however much it reported: the only frames that mapped were
# the three run-level ones. Worse, `awaiting` is how a gate says it is waiting
# for a human, so an approval could never reach the device that has to answer it.
#
# The fix is the mapping, not new frame types. `todos` has no member in
# `RunEventType` and gets one at `0.5.0`, when this stream's frames are
# enriched; inventing it here would be a rename paid for twice.
_EVENT_TYPE_MAP = {
    "run_started": RunEventType.STARTED,
    "agent_started": RunEventType.TOOL_CALL,
    "agent_log": RunEventType.OUTPUT,
    "agent_completed": RunEventType.OUTPUT,
    "awaiting": RunEventType.PAUSED,
    "agent_failed": RunEventType.FAILED,
    "run_completed": RunEventType.COMPLETED,
    "run_failed": RunEventType.FAILED,
}


# Broadcast, understood, and deliberately not translatable yet. Neither `todos`
# nor `run_resumed` has a member in `RunEventType`, and inventing one here would
# be a published frame name chosen in the wrong place. Listed rather than left
# to the fallthrough so a type nobody has considered can be told apart from one
# that is waiting on a decision - `run_resumed` was reaching the fallthrough and
# logging a warning on every resume.
_NOT_YET_ON_THIS_STREAM = frozenset({"todos", "run_resumed"})


def _to_run_event(internal: dict) -> RunEvent | None:
    kind = internal.get("type")
    mapped = _EVENT_TYPE_MAP.get(kind)
    if mapped is None:
        if kind not in _NOT_YET_ON_THIS_STREAM:
            logger.warning(
                "run stream: no RunEvent for broadcast type %r; dropped. Add it "
                "to _EVENT_TYPE_MAP or to _NOT_YET_ON_THIS_STREAM.", kind,
            )
        return None
    ts = internal.get("timestamp")
    try:
        timestamp = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    except (TypeError, ValueError):
        timestamp = datetime.now(timezone.utc)
    return RunEvent(type=mapped, timestamp=timestamp, payload=internal.get("data", {}))


class _RunEventTranslator:
    """Wraps a WebSocket so the manager's ``send_json`` of internal events is
    translated into mobile ``RunEvent`` frames. Non-mappable events are dropped.

    Only ``accept``/``send_json``/``close`` are used by ConnectionManager, so we
    proxy those and forward identity for membership checks."""

    def __init__(self, ws: WebSocket):
        self._ws = ws

    async def accept(self, *a, **kw):
        # The route already accepted (after auth); avoid a double accept.
        return None

    async def send_json(self, event: dict):
        run_event = _to_run_event(event)
        if run_event is not None:
            await self._ws.send_text(run_event.model_dump_json())

    async def close(self, *a, **kw):
        await self._ws.close(*a, **kw)


@router.websocket("/api/ws/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    """The on-box stream the CLI watches (`cli/stream.py`).

    **Authenticated.** It was not: the auth middleware is HTTP-only and this
    route checked nothing, so any peer that gate 1 admits - every member of the
    tailnet - could open it. It also accepted an inbound `approval_response`
    that resumed a parked run, which made it an **unauthenticated way to answer
    a human-approval gate**, the one decision the gate layer exists to protect.

    Both are fixed here. Auth matches `/stream`, and the socket is now
    send-only: answering a gate is `POST /api/runs/{id}/respond`, which is
    authenticated, idempotent and auditable. Loopback is
    trusted by gate 1, so the CLI still connects with no token.

    It is deleted outright at `0.6.0`, when the conversation replaces this
    surface and one socket survives. Until then it has a live consumer.
    """
    logger.info(f"WebSocket connection attempt for run {run_id}")
    app = websocket.app
    manager = app.state.ws_manager
    run_repo = app.state.run_repo

    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header:
            parts = auth_header.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1].strip()
    if not await authorize_ws(app, app.state.transport, 
                              websocket.client.host if websocket.client else None,
                              token):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    run = await run_repo.get(run_id)
    if not run:
        logger.warning(f"WebSocket: run {run_id} not found, closing")
        await websocket.close(code=4004, reason="Run not found")
        return

    logger.info(f"WebSocket: run {run_id} found, accepting connection")

    await manager.connect(run_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Send-only. An `approval_response` used to be honoured here, which
            # made the socket a second way to answer a gate - with different
            # auth, no idempotency key, and no audit trail. Answering is
            # `POST /api/runs/{id}/respond` and only that.
            # Inbound frames are ignored rather than rejected, so an older
            # client that still sends one is not disconnected mid-run.
            if msg.get("type") == "approval_response":
                logger.warning(
                    "run %s: ignoring an inbound approval on the socket; "
                    "answer a gate with POST /api/runs/{id}/respond",
                    run_id,
                )
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)


@router.websocket("/api/runs/{run_id}/stream")
async def run_stream(websocket: WebSocket, run_id: str):
    """Mobile run stream. Two-gate authed; emits contract RunEvents."""
    app = websocket.app
    transport = app.state.transport
    client_host = websocket.client.host if websocket.client else None
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header:
            parts = auth_header.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1].strip()

    if not await authorize_ws(app, transport, client_host, token):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    run_repo = app.state.run_repo
    run = await run_repo.get(run_id)
    if not run:
        await websocket.close(code=4004, reason="Run not found")
        return

    # Resolve the owning device id (loopback has none) for revocation tracking.
    device_id = None
    if not _is_loopback(client_host):
        device = await authenticate_device(app, token)
        device_id = device["id"] if device else None

    await websocket.accept()
    manager = app.state.ws_manager
    translator = _RunEventTranslator(websocket)
    await manager.connect(run_id, translator, device_id=device_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, translator)
