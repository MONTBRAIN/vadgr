"""WebSocket connection manager for run streaming."""

import json
from typing import Any

from fastapi import WebSocket

from .events import make_event

# Maximum buffered events per run to prevent unbounded memory growth.
_MAX_BUFFER = 500


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        # Buffer events so late-connecting clients receive the full history.
        self._buffers: dict[str, list[dict]] = {}
        # Track which device (if any) owns each socket, for revocation.
        self._device_sockets: dict[str, list[WebSocket]] = {}

    async def connect(self, run_id: str, websocket: WebSocket, device_id: str | None = None):
        await websocket.accept()
        if run_id not in self._connections:
            self._connections[run_id] = []
        self._connections[run_id].append(websocket)
        if device_id:
            self._device_sockets.setdefault(device_id, []).append(websocket)

        # Replay any buffered events to the newly connected client.
        for event in self._buffers.get(run_id, []):
            try:
                await websocket.send_json(event)
            except Exception:
                break

    def disconnect(self, run_id: str, websocket: WebSocket):
        if run_id in self._connections:
            self._connections[run_id] = [
                ws for ws in self._connections[run_id] if ws is not websocket
            ]
            if not self._connections[run_id]:
                del self._connections[run_id]
        for device_id, socks in list(self._device_sockets.items()):
            self._device_sockets[device_id] = [ws for ws in socks if ws is not websocket]
            if not self._device_sockets[device_id]:
                del self._device_sockets[device_id]

    async def disconnect_device(self, device_id: str):
        """Close every live socket owned by a (revoked) device."""
        for ws in list(self._device_sockets.get(device_id, [])):
            try:
                await ws.close(code=4003, reason="Device revoked")
            except Exception:
                pass
            for run_id in list(self._connections.keys()):
                if ws in self._connections.get(run_id, []):
                    self.disconnect(run_id, ws)
        self._device_sockets.pop(device_id, None)

    async def emit(self, run_id: str, event_type: str, data: dict[str, Any] | None = None):
        event = make_event(event_type, data)
        await self.broadcast_event(run_id, event)

    async def broadcast_event(self, run_id: str, event: dict):
        """Broadcast a pre-built event dict to all connected clients and buffer it."""
        # Always buffer events so late-connecting clients get the full history.
        if run_id not in self._buffers:
            self._buffers[run_id] = []
        if len(self._buffers[run_id]) < _MAX_BUFFER:
            self._buffers[run_id].append(event)

        # Clean up buffer when the run finishes.
        if event.get("type") in ("run_completed", "run_failed"):
            # Keep the buffer around briefly for late connectors;
            # it will be cleaned up when the last client disconnects.
            pass

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

    def clear_buffer(self, run_id: str):
        """Remove the event buffer for a run."""
        self._buffers.pop(run_id, None)

    def has_connections(self, run_id: str) -> bool:
        return run_id in self._connections and len(self._connections[run_id]) > 0
