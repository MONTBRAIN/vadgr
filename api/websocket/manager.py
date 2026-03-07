"""WebSocket connection manager for run streaming."""

import json
from typing import Any

from fastapi import WebSocket

from .events import make_event


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, run_id: str, websocket: WebSocket):
        await websocket.accept()
        if run_id not in self._connections:
            self._connections[run_id] = []
        self._connections[run_id].append(websocket)

    def disconnect(self, run_id: str, websocket: WebSocket):
        if run_id in self._connections:
            self._connections[run_id] = [
                ws for ws in self._connections[run_id] if ws is not websocket
            ]
            if not self._connections[run_id]:
                del self._connections[run_id]

    async def emit(self, run_id: str, event_type: str, data: dict[str, Any] | None = None):
        event = make_event(event_type, data)
        if run_id not in self._connections:
            return
        dead = []
        for ws in self._connections[run_id]:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(run_id, ws)

    def has_connections(self, run_id: str) -> bool:
        return run_id in self._connections and len(self._connections[run_id]) > 0
