"""The in-process control-plane MCP server + its 7 tools.

Driven against a fake run context, a fake channel, and the default policy. The
server satisfies ``MCPServer`` (so the ``MCPHost`` wires it in beside cua); its
tools cover todo/progress/HITL/notify. The HITL gate is spec-critical:
``request_approval`` **blocks then resolves** on approve / reject / timeout, and
an auto-decision from policy never touches the channel.
"""

import asyncio

import pytest

from engine.channels.base import Delivery, HumanPrompt
from engine.mcp import MCPHost, MCPServer
from engine.policy.default import DefaultPolicy
from engine.tools import ControlPlaneServer, RunContext
from engine.tools.hitl import _seconds


class FakeChannel:
    def __init__(self, name="cli", answer=None, gate=None):
        self.name = name
        self._answer = answer or {"choice": "approve", "text": None, "timed_out": False}
        self._gate = gate            # optional asyncio.Event to block on
        self.requests = []
        self.notes = []

    async def request(self, prompt):
        self.requests.append(prompt)
        if self._gate is not None:
            await self._gate.wait()
        return self._answer

    async def notify(self, message, *, importance):
        self.notes.append((message, importance))
        return Delivery(delivered=[self.name])


class Router:
    """Minimal ChannelRouter stand-in exposing request/notify."""

    def __init__(self, channel):
        self.channel = channel

    async def request(self, prompt, *, channel=None):
        return await self.channel.request(prompt)

    async def notify(self, message, *, importance="normal", channel=None):
        return await self.channel.notify(message, importance=importance)


class RecordingCtx(RunContext):
    pass


def _server(channel=None, policy=None, ctx=None):
    channel = channel or FakeChannel()
    events = []

    async def emit(event):
        events.append(event)

    ctx = ctx or RunContext(run_id="run-1", emit=emit)
    ctx._events = events  # type: ignore[attr-defined]
    return ControlPlaneServer(ctx, Router(channel), policy or DefaultPolicy()), ctx, channel


# ---- server plumbing -------------------------------------------------------

def test_server_satisfies_mcp_server_protocol():
    server, _, _ = _server()
    assert isinstance(server, MCPServer)
    assert server.name == "control"


@pytest.mark.asyncio
async def test_list_tools_exposes_the_seven_control_plane_tools():
    server, _, _ = _server()
    names = {spec["name"] for spec in await server.list_tools()}
    assert names == {
        "todo_write",
        "todo_update",
        "report_progress",
        "get_run_status",
        "request_approval",
        "ask_user",
        "propose_plan",
        "notify_user",
    }


@pytest.mark.asyncio
async def test_host_aggregates_control_tools_beside_cua():
    server, _, _ = _server()

    class Cua:
        name = "cua"

        async def list_tools(self):
            return [{"name": "click", "description": "c"}]

        async def call_tool(self, name, args):
            return {"ok": True}

    host = MCPHost([Cua(), server])
    await host.connect()
    names = {s["name"] for s in host.tools()}
    assert "cua__click" in names
    assert "control__request_approval" in names


# ---- todo / progress -------------------------------------------------------

@pytest.mark.asyncio
async def test_todo_write_replaces_list_and_streams_event():
    server, ctx, _ = _server()
    res = await server.call_tool(
        "todo_write", {"items": [{"id": "1", "content": "step one"}]}
    )
    assert res["ok"] is True
    assert ctx.todos[0]["content"] == "step one"
    assert ctx.todos[0]["status"] == "pending"
    assert any(e["type"] == "todos" for e in ctx._events)


@pytest.mark.asyncio
async def test_todo_update_walks_status_and_rejects_bad_status():
    server, ctx, _ = _server()
    await server.call_tool("todo_write", {"items": [{"id": "1", "content": "x"}]})
    res = await server.call_tool("todo_update", {"id": "1", "status": "in_progress"})
    assert res["todo"]["status"] == "in_progress"

    with pytest.raises(ValueError):
        await server.call_tool("todo_update", {"id": "1", "status": "bogus"})
    with pytest.raises(ValueError):
        await server.call_tool("todo_update", {"id": "nope", "status": "done"})


@pytest.mark.asyncio
async def test_report_progress_emits_event():
    server, ctx, _ = _server()
    res = await server.call_tool("report_progress", {"message": "halfway"})
    assert res == {"ok": True}
    assert any(
        e["type"] == "progress" and e["message"] == "halfway" for e in ctx._events
    )


@pytest.mark.asyncio
async def test_get_run_status_reports_shape():
    server, ctx, _ = _server()
    ctx.iteration = 4
    ctx.input_tokens = 100
    ctx.output_tokens = 20
    await server.call_tool("todo_write", {"items": [{"id": "1", "content": "x"}]})
    status = await server.call_tool("get_run_status", {})
    assert status["run_id"] == "run-1"
    assert status["state"] == "running"
    assert status["iteration"] == 4
    assert status["tokens"] == {"input": 100, "output": 20}
    assert len(status["todos"]) == 1


# ---- HITL gate -------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_approval_auto_allow_never_touches_channel():
    channel = FakeChannel()
    server, _, _ = _server(channel=channel, policy=DefaultPolicy(auth_mode="bypass"))
    res = await server.call_tool(
        "request_approval",
        {"action": "shell.run ls", "risk": "high", "preview": "ls"},
    )
    assert res["decision"] == "approve"
    assert channel.requests == []


@pytest.mark.asyncio
async def test_request_approval_denylist_auto_denies_without_channel():
    channel = FakeChannel()
    policy = DefaultPolicy(denylist=["rm -rf /"], auth_mode="default")
    server, _, _ = _server(channel=channel, policy=policy)
    res = await server.call_tool(
        "request_approval",
        {"action": "shell.run rm -rf / now", "risk": "low", "preview": "danger"},
    )
    assert res["decision"] == "reject"
    assert channel.requests == []


@pytest.mark.asyncio
async def test_request_approval_high_risk_routes_to_channel_and_approves():
    channel = FakeChannel(answer={"choice": "approve", "text": "go", "timed_out": False})
    server, _, _ = _server(channel=channel, policy=DefaultPolicy(auth_mode="default"))
    res = await server.call_tool(
        "request_approval",
        {"action": "shell.run deploy", "risk": "high", "preview": "deploy"},
    )
    assert res["decision"] == "approve"
    assert len(channel.requests) == 1
    assert channel.requests[0].kind == "approval"


@pytest.mark.asyncio
async def test_request_approval_reject_is_a_normal_result_not_a_crash():
    channel = FakeChannel(answer={"choice": "reject", "text": None, "timed_out": False})
    server, _, _ = _server(channel=channel, policy=DefaultPolicy(auth_mode="default"))
    res = await server.call_tool(
        "request_approval", {"action": "x", "risk": "high", "preview": "p"}
    )
    assert res["decision"] == "reject"


@pytest.mark.asyncio
async def test_request_approval_timeout_maps_to_timeout_decision():
    channel = FakeChannel(answer={"choice": None, "text": None, "timed_out": True})
    server, _, _ = _server(channel=channel, policy=DefaultPolicy(auth_mode="paranoid"))
    res = await server.call_tool(
        "request_approval", {"action": "x", "risk": "low", "preview": "p", "timeout": 1}
    )
    assert res["decision"] == "timeout"


@pytest.mark.asyncio
async def test_request_approval_blocks_until_channel_responds():
    gate = asyncio.Event()
    channel = FakeChannel(
        answer={"choice": "approve", "text": None, "timed_out": False}, gate=gate
    )
    server, _, _ = _server(channel=channel, policy=DefaultPolicy(auth_mode="paranoid"))

    task = asyncio.create_task(
        server.call_tool("request_approval", {"action": "x", "risk": "low"})
    )
    await asyncio.sleep(0.02)
    # Still blocked -- no decision yet, loop iteration is suspended on the await.
    assert not task.done()
    gate.set()
    res = await task
    assert res["decision"] == "approve"


@pytest.mark.asyncio
async def test_request_approval_journals_await_user_on_the_open_seq(tmp_path):
    from engine.trajectory import Trajectory

    traj = Trajectory("run-await", path=str(tmp_path / "t.jsonl"))
    # The loop opens the in_flight action just before dispatch.
    seq = traj.append_in_flight(0, {"id": "t1", "name": "control__request_approval", "input": {}})

    channel = FakeChannel(answer={"choice": "approve", "text": None, "timed_out": False})
    ctx = RunContext(run_id="run-await", trajectory=traj)
    server = ControlPlaneServer(ctx, Router(channel), DefaultPolicy(auth_mode="paranoid"))
    await server.call_tool("request_approval", {"action": "x", "risk": "low"})
    traj.append_done(seq, {"decision": "approve"})

    import json

    lines = [json.loads(l) for l in open(traj.path) if l.strip()]
    await_lines = [l for l in lines if l["phase"] == "await_user"]
    assert await_lines and await_lines[0]["seq"] == seq


@pytest.mark.asyncio
async def test_ask_user_returns_answer():
    channel = FakeChannel(answer={"choice": "green", "text": "green", "timed_out": False})
    server, _, _ = _server(channel=channel)
    res = await server.call_tool("ask_user", {"question": "colour?"})
    assert res == {"answer": "green", "timed_out": False}


@pytest.mark.asyncio
async def test_propose_plan_returns_decision():
    channel = FakeChannel(answer={"choice": "revise", "text": "tweak step 2", "timed_out": False})
    server, _, _ = _server(channel=channel)
    res = await server.call_tool("propose_plan", {"plan": "do a, b, c"})
    assert res["decision"] == "revise"
    assert res["feedback"] == "tweak step 2"


# ---- notify ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_user_routes_to_channel_and_maps_importance():
    channel = FakeChannel()
    server, _, _ = _server(channel=channel)
    res = await server.call_tool(
        "notify_user", {"message": "done", "importance": "high"}
    )
    assert res["ok"] is True
    assert res["delivered"] == ["cli"]
    assert channel.notes == [("done", "high")]


@pytest.mark.asyncio
async def test_todo_status_accepts_the_synonyms_a_model_reaches_for():
    """Regression (E2E/0.4.0 F3): given a plain goal the model wrote
    ``completed``; the vocabulary is ``done``, the schema enum is advisory, and
    the mismatch cost an iteration on an error."""
    server, _, _ = _server()
    await server.call_tool("todo_write", {"items": [{"id": "1", "content": "step one"}]})

    result = await server.call_tool("todo_update", {"id": "1", "status": "completed"})

    assert result["todo"]["status"] == "done"


@pytest.mark.asyncio
async def test_todo_status_synonyms_across_the_vocabulary():
    server, _, _ = _server()
    for given, expected in (
        ("complete", "done"),
        ("Finished", "done"),
        ("in-progress", "in_progress"),
        ("in progress", "in_progress"),
        ("canceled", "cancelled"),
        ("todo", "pending"),
    ):
        result = await server.call_tool(
            "todo_write", {"items": [{"content": "x", "status": given}]}
        )
        assert result["todos"][0]["status"] == expected, given


@pytest.mark.asyncio
async def test_an_unknown_todo_status_names_every_legal_value():
    server, _, _ = _server()
    with pytest.raises(ValueError) as excinfo:
        await server.call_tool(
            "todo_write", {"items": [{"content": "x", "status": "nope"}]}
        )

    message = str(excinfo.value)
    for status in ("pending", "in_progress", "done", "cancelled"):
        assert status in message


@pytest.mark.asyncio
async def test_an_unknown_todo_id_names_the_known_ids():
    server, _, _ = _server()
    await server.call_tool(
        "todo_write", {"items": [{"content": "a"}, {"content": "b"}]}
    )

    with pytest.raises(ValueError) as excinfo:
        await server.call_tool("todo_update", {"id": "99", "status": "done"})

    assert "known ids: 1, 2" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_string_timeout_reaches_the_real_channel_without_raising():
    """Regression (E2E/0.4.1 F6), against the REAL channel.

    A fake channel never reaches `asyncio.wait_for`, so a fake proves nothing
    here: the crash was the comparison inside it. The schema says `number` and a
    JSON Schema type is advisory, so a model that sends "300" used to raise at
    the exact moment the run was trying to consult a human - the one outcome a
    HITL tool must never have.
    """
    from engine.channels.base import ChannelRouter, HumanPrompt
    from engine.channels.cli import CLIChannel

    seen = {}

    async def reader(text, timeout):
        seen["timeout"] = timeout
        return "the answer"

    channel = CLIChannel(reader=reader, writer=lambda line: None)
    # The path that used to blow up: a str timeout into wait_for.
    answer = await channel.request(
        HumanPrompt(kind="question", text="which folder?", timeout=_seconds("300"))
    )
    assert answer is not None
    assert seen["timeout"] == 300.0, "the string was not coerced to a number"


@pytest.mark.asyncio
async def test_an_unparseable_timeout_becomes_no_timeout_not_a_crash():
    assert _seconds("soon") is None
    assert _seconds(None) is None
    assert _seconds(0) is None
    assert _seconds("300") == 300.0
    assert _seconds(12.5) == 12.5
