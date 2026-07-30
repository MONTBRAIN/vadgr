"""Planning / working memory: todo_write / todo_update.

The step list the agent maintains, streamed to the watching client on every
write/update via a ``todos`` RunEvent.
"""

from __future__ import annotations

from engine.tools import control_tool, emit_event

VALID_STATUSES = ("pending", "in_progress", "done", "cancelled")

# The vocabulary a model actually reaches for. The schema declares an ``enum``,
# but a JSON-Schema enum is advisory -- an off-vocabulary value reaches the tool
# anyway -- and a model given a plain goal writes "completed", not "done". These
# map to the canonical status instead of costing an iteration on an error.
_STATUS_ALIASES = {
    "complete": "done",
    "completed": "done",
    "finished": "done",
    "success": "done",
    "todo": "pending",
    "not_started": "pending",
    "in-progress": "in_progress",
    "inprogress": "in_progress",
    "active": "in_progress",
    "running": "in_progress",
    "canceled": "cancelled",
    "cancel": "cancelled",
    "skipped": "cancelled",
}


def _canonical_status(status: str) -> str:
    """The canonical status, accepting the common synonyms. Raises naming every
    legal value -- an error a model can act on without guessing again."""
    if not isinstance(status, str):
        raise ValueError(f"invalid todo status: {status!r}")
    key = status.strip().lower().replace(" ", "_")
    resolved = _STATUS_ALIASES.get(key, key)
    if resolved not in VALID_STATUSES:
        raise ValueError(
            f"invalid todo status: {status!r} -- expected one of "
            + ", ".join(VALID_STATUSES)
        )
    return resolved

_ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "content": {"type": "string"},
                    "status": {"type": "string", "enum": list(VALID_STATUSES)},
                },
                "required": ["content"],
            },
        }
    },
    "required": ["items"],
}

_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "status": {"type": "string", "enum": list(VALID_STATUSES)},
    },
    "required": ["id", "status"],
}


def _normalize(item: dict, index: int) -> dict:
    content = item.get("content") or item.get("title") or item.get("text") or ""
    status = _canonical_status(item.get("status", "pending"))
    return {
        "id": str(item.get("id") or index + 1),
        "content": content,
        "status": status,
    }


@control_tool(
    description="Replace the agent's todo list (the step plan it maintains).",
    input_schema=_ITEMS_SCHEMA,
)
async def todo_write(args: dict, server) -> dict:
    items = [_normalize(it, i) for i, it in enumerate(args.get("items", []))]
    server.ctx.todos = items
    await emit_event(server, {"type": "todos", "todos": items})
    return {"ok": True, "todos": items}


@control_tool(
    description="Update one todo's status (pending|in_progress|done|cancelled).",
    input_schema=_UPDATE_SCHEMA,
)
async def todo_update(args: dict, server) -> dict:
    todo_id = str(args["id"])
    status = _canonical_status(args["status"])
    for todo in server.ctx.todos:
        if str(todo.get("id")) == todo_id:
            todo["status"] = status
            await emit_event(server, {"type": "todos", "todos": server.ctx.todos})
            return {"ok": True, "todo": todo}
    known = ", ".join(str(t.get("id")) for t in server.ctx.todos) or "none"
    raise ValueError(f"unknown todo id: {todo_id} -- known ids: {known}")
