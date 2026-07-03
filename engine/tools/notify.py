"""Notify: notify_user (CLI / desktop).

Fire-and-forget -- routes a message to the active channel (or a per-call
override) and returns immediately with the delivery targets. ``importance``
selects how loud: low -> log, normal -> toast, high -> modal/alert.
"""

from __future__ import annotations

from engine.tools import control_tool

_NOTIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "channel": {"type": "string"},
        "importance": {"type": "string", "enum": ["low", "normal", "high"]},
    },
    "required": ["message"],
}


@control_tool(
    description="Notify the user on the active channel. Fire-and-forget.",
    input_schema=_NOTIFY_SCHEMA,
)
async def notify_user(args: dict, server) -> dict:
    message = args["message"]
    channel = args.get("channel")
    importance = args.get("importance", "normal")
    delivery = await server.channels.notify(
        message, importance=importance, channel=channel
    )
    return {"ok": True, "delivered": delivery.delivered}
