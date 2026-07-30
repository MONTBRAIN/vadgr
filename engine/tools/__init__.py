"""vadgr's in-process control-plane MCP server (§4.9) + the @control_tool registry.

The server satisfies ``MCPServer`` so the ``MCPHost`` wires it in beside the cua
servers -- no wire hop. Handlers register via ``@control_tool``; ``list_tools()``
returns their specs, ``call_tool()`` invokes one. Adding a control-plane tool is
a new ``@control_tool`` in ``engine/tools/`` -- never a cua or loop change.

The seven 0.4.0 tools live one group per file (``todo``/``progress``/``hitl``/
``notify``); importing this package registers them all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# name -> {"handler": fn, "spec": {...}}
_REGISTRY: dict[str, dict] = {}


def control_tool(
    fn: Callable | None = None,
    *,
    description: str = "",
    input_schema: dict | None = None,
):
    """Register one handler + its MCP spec. Usable bare (``@control_tool``) or
    with metadata (``@control_tool(description=..., input_schema=...)``)."""

    def wrap(f: Callable) -> Callable:
        desc = description or (f.__doc__ or "").strip().split("\n")[0]
        _REGISTRY[f.__name__] = {
            "handler": f,
            "spec": {
                "name": f.__name__,
                "description": desc,
                "input_schema": input_schema or {"type": "object", "properties": {}},
            },
        }
        return f

    return wrap(fn) if fn is not None else wrap


@dataclass
class RunContext:
    """The live run state the control-plane tools read and mutate: the run id,
    the resume journal, the event sink, and the working-memory todo list.

    The provider's ``on_event`` wrapper keeps ``iteration`` / token counters
    current, so ``get_run_status`` reports the real run, not a stub."""

    run_id: str
    trajectory: Any = None
    emit: Callable[[dict], Awaitable[None]] | None = None
    state: str = "running"
    iteration: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    todos: list = field(default_factory=list)


class ControlPlaneServer:
    """vadgr's own in-process MCP server. One per run; holds the run context,
    the channel router (for HITL / notify), and the policy hook."""

    name = "control"

    def __init__(self, run_ctx: RunContext, channels, policy):
        self.ctx = run_ctx
        self.channels = channels
        self.policy = policy

    async def list_tools(self) -> list:
        return [dict(entry["spec"]) for entry in _REGISTRY.values()]

    async def call_tool(self, name: str, args: dict) -> dict:
        entry = _REGISTRY.get(name)
        if entry is None:
            raise KeyError(f"unknown control-plane tool: {name}")
        return await entry["handler"](args or {}, self)


async def emit_event(server: "ControlPlaneServer", event: dict) -> None:
    """Stream a RunEvent to the watching client, if a sink is wired."""
    if server.ctx.emit is not None:
        await server.ctx.emit(event)


# Importing the handler modules registers every @control_tool. Kept at the
# bottom so the registry + RunContext + ControlPlaneServer exist first.
from engine.tools import hitl, notify, progress, todo  # noqa: E402,F401
