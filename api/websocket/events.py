"""WebSocket event types and envelope."""

from datetime import datetime, timezone
from typing import Any


def make_event(event_type: str, data: dict[str, Any] | None = None) -> dict:
    return {
        "type": event_type,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
