"""Planning / working memory: todo_write / todo_update.

The step list the agent maintains, streamed to the watching client on every
write/update via a ``todos`` RunEvent.
"""

from __future__ import annotations

from engine.tools import control_tool, emit_event

VALID_STATUSES = ("pending", "in_progress", "done", "cancelled")

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
    status = item.get("status", "pending")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid todo status: {status}")
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
    status = args["status"]
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid todo status: {status}")
    for todo in server.ctx.todos:
        if str(todo.get("id")) == todo_id:
            todo["status"] = status
            await emit_event(server, {"type": "todos", "todos": server.ctx.todos})
            return {"ok": True, "todo": todo}
    raise ValueError(f"unknown todo id: {todo_id}")
