"""Human-in-the-loop gate v1: request_approval / ask_user / propose_plan.

These are the one place a tool call *blocks a loop iteration*. Because control-
plane tools dispatch exactly like any other tool, the pause happens inside
``call_tool`` here, so the loop's ``for`` iteration is already suspended at the
``await``. ``request_approval`` first asks the policy hook (auto_allow /
auto_deny / needs_human); only ``needs_human`` routes to the channel. The pause
is journaled as ``await_user`` on the still-open ``seq`` so a crash while waiting
resumes into the same pending request.
"""

from __future__ import annotations

from engine.channels.base import HumanPrompt
from engine.policy.base import AUTO_ALLOW, AUTO_DENY, ApprovalRequest
from engine.tools import control_tool

_APPROVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "risk": {"type": "string", "enum": ["low", "medium", "high"]},
        "preview": {"type": "string"},
        "timeout": {"type": "number"},
    },
    "required": ["action", "risk", "preview"],
}

_ASK_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "timeout": {"type": "number"},
    },
    "required": ["question"],
}

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {"plan": {"type": "string"}},
    "required": ["plan"],
}


def _journal_await(server, request: dict) -> None:
    traj = server.ctx.trajectory
    if traj is not None and hasattr(traj, "append_await_user"):
        traj.append_await_user(request)


@control_tool(
    description="Ask a human to approve a gated action. Blocks the loop until "
    "answered; a reject/timeout is a normal result, not a crash.",
    input_schema=_APPROVAL_SCHEMA,
)
async def request_approval(args: dict, server) -> dict:
    action = args["action"]
    risk = args.get("risk", "medium")
    preview = args.get("preview", "")
    timeout = args.get("timeout")

    req = ApprovalRequest(action=action, risk=risk, preview=preview)
    decision = await server.policy.check(req)
    if decision.outcome == AUTO_DENY:
        return {"decision": "reject", "note": decision.reason}
    if decision.outcome == AUTO_ALLOW:
        return {"decision": "approve", "note": None}

    # needs_human -> journal the pause, then block on the channel.
    _journal_await(server, {"kind": "approval", "action": action, "risk": risk})
    prompt = HumanPrompt(
        kind="approval", text=action, risk=risk, preview=preview, timeout=timeout
    )
    resp = await server.channels.request(prompt)
    if resp.get("timed_out"):
        return {"decision": "timeout", "note": None}
    choice = "approve" if resp.get("choice") == "approve" else "reject"
    return {"decision": choice, "note": resp.get("text") or None}


@control_tool(
    description="Ask a human a question, optionally with choices. Blocks the loop.",
    input_schema=_ASK_SCHEMA,
)
async def ask_user(args: dict, server) -> dict:
    question = args["question"]
    options = args.get("options")
    timeout = args.get("timeout")

    _journal_await(server, {"kind": "question", "question": question})
    prompt = HumanPrompt(
        kind="question", text=question, options=options, timeout=timeout
    )
    resp = await server.channels.request(prompt)
    if resp.get("timed_out"):
        return {"answer": None, "timed_out": True}
    return {"answer": resp.get("choice"), "timed_out": False}


@control_tool(
    description="Propose a plan for a human to approve / revise / reject. Blocks.",
    input_schema=_PLAN_SCHEMA,
)
async def propose_plan(args: dict, server) -> dict:
    plan = args["plan"]
    _journal_await(server, {"kind": "plan"})
    resp = await server.channels.request(HumanPrompt(kind="plan", text=plan))
    if resp.get("timed_out"):
        return {"decision": "reject", "feedback": "timed out"}
    return {"decision": resp.get("choice") or "reject", "feedback": resp.get("text") or None}
