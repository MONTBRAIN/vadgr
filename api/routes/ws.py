"""WebSocket route for live run streaming."""

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from api.auth.middleware import authorize_ws

logger = logging.getLogger(__name__)
router = APIRouter()


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
async def run_stream(websocket: WebSocket, run_id: str, token: str | None = Query(default=None)):
    """Mobile-friendly run event stream.

    Authenticates via `Authorization: Bearer <token>` header (preferred)
    or `?token=<token>` query string. Localhost connections bypass auth
    just like HTTP requests.
    """
    client_host = websocket.client.host if websocket.client else None
    headers = {k.decode(): v.decode() for k, v in websocket.headers.raw}
    allowed = await authorize_ws(websocket.app, headers, token, client_host)
    if not allowed:
        await websocket.close(code=4401, reason="Unauthorized")
        return

    manager = websocket.app.state.ws_manager
    run_repo = websocket.app.state.run_repo

    run = await run_repo.get(run_id)
    if not run:
        await websocket.close(code=4004, reason="Run not found")
        return

    await manager.connect(run_id, websocket)
    try:
        while True:
            # We do not currently consume client messages on this stream.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)
