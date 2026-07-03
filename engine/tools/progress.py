"""Self / progress: report_progress / get_run_status.

``report_progress`` surfaces a human-readable line to the client stream;
``get_run_status`` introspects the live run (state / iteration / todos / tokens).
"""

from __future__ import annotations

from engine.tools import control_tool, emit_event

_PROGRESS_SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
}

_STATUS_SCHEMA = {
    "type": "object",
    "properties": {"run_id": {"type": "string"}},
}


@control_tool(
    description="Surface a progress message to the watching client.",
    input_schema=_PROGRESS_SCHEMA,
)
async def report_progress(args: dict, server) -> dict:
    message = args.get("message", "")
    await emit_event(server, {"type": "progress", "message": message})
    return {"ok": True}


@control_tool(
    description="Introspect the current run: state, iteration, todos, tokens.",
    input_schema=_STATUS_SCHEMA,
)
async def get_run_status(args: dict, server) -> dict:
    ctx = server.ctx
    return {
        "run_id": args.get("run_id") or ctx.run_id,
        "state": ctx.state,
        "iteration": ctx.iteration,
        "todos": ctx.todos,
        "tokens": {"input": ctx.input_tokens, "output": ctx.output_tokens},
    }
