"""WebSocket route for live run streaming."""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/api/ws/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    manager = websocket.app.state.ws_manager
    run_repo = websocket.app.state.run_repo

    run = await run_repo.get(run_id)
    if not run:
        await websocket.close(code=4004, reason="Run not found")
        return

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
                    await run_repo.update_status(run_id, "running")
                    # In a full implementation, this would trigger
                    # execution_service.resume_after_approval(run_id)
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)
