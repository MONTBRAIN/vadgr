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
_EVENT_TYPE_MAP = {
    "run_started": RunEventType.STARTED,
    "step_started": RunEventType.TOOL_CALL,
    "tool_call": RunEventType.TOOL_CALL,
    "step_output": RunEventType.OUTPUT,
    "output": RunEventType.OUTPUT,
    "approval_required": RunEventType.PAUSED,
    "run_completed": RunEventType.COMPLETED,
    "run_failed": RunEventType.FAILED,
}


def _to_run_event(internal: dict) -> RunEvent | None:
    mapped = _EVENT_TYPE_MAP.get(internal.get("type"))
    if mapped is None:
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
    logger.info(f"WebSocket connection attempt for run {run_id}")
    manager = websocket.app.state.ws_manager
    run_repo = websocket.app.state.run_repo

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

            if msg.get("type") == "approval_response":
                action = msg.get("data", {}).get("action", "approve")
                if action == "approve":
                    execution_service = websocket.app.state.execution_service
                    await run_repo.update_status(run_id, "running")
                    import asyncio
                    asyncio.create_task(
                        execution_service.resume_after_approval(run_id)
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
