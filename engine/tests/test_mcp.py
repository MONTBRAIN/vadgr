"""The generic MCP host: aggregate + namespace + route.

The host fronts a configured set of MCP servers, aggregates their specs into
one namespaced list the agent sees, and routes each call to the owning server.
A control-plane tool and a cua tool sit in the same list; a name collision
across servers is a startup error.
"""

import pytest

from engine.mcp import MCPHost, MCPServer, UnknownToolError, dispatch_to_mcp


class FakeServer:
    def __init__(self, name, tools):
        self.name = name
        self._tools = tools
        self.calls = []

    async def list_tools(self):
        return [{"name": t, "description": f"{t} tool"} for t in self._tools]

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return {"server": self.name, "tool": name, "args": args}


def test_fake_server_satisfies_the_protocol():
    assert isinstance(FakeServer("cua", ["click"]), MCPServer)


@pytest.mark.asyncio
async def test_tools_is_the_namespaced_union_across_servers():
    cua = FakeServer("cua", ["click", "type"])
    control = FakeServer("control", ["request_approval"])
    host = MCPHost([cua, control])
    await host.connect()

    names = {spec["name"] for spec in host.tools()}
    # cua capability tools AND the control-plane tool are all reachable.
    assert names == {"cua__click", "cua__type", "control__request_approval"}


@pytest.mark.asyncio
async def test_dispatch_routes_to_the_owning_server():
    cua = FakeServer("cua", ["click"])
    control = FakeServer("control", ["request_approval"])
    host = MCPHost([cua, control])
    await host.connect()

    result = await dispatch_to_mcp(
        {"id": "t1", "name": "control__request_approval", "input": {"risk": "high"}}, host
    )

    assert result["server"] == "control"
    assert control.calls == [("request_approval", {"risk": "high"})]
    assert cua.calls == []


@pytest.mark.asyncio
async def test_unknown_tool_raises():
    host = MCPHost([FakeServer("cua", ["click"])])
    await host.connect()
    with pytest.raises(UnknownToolError):
        await host.dispatch({"id": "t1", "name": "nope__missing", "input": {}})


@pytest.mark.asyncio
async def test_server_name_collision_is_a_startup_error():
    host = MCPHost([FakeServer("cua", ["click"]), FakeServer("cua", ["type"])])
    with pytest.raises(ValueError):
        await host.connect()


class BrokenServer:
    """A server that will not start -- a misconfigured or unreachable one."""

    def __init__(self, name):
        self.name = name

    async def list_tools(self):
        raise RuntimeError(f"{self.name}: cannot start")

    async def call_tool(self, name, args):  # pragma: no cover - never reached
        raise AssertionError("a dropped server must never be dispatched to")


@pytest.mark.asyncio
async def test_a_broken_server_is_dropped_not_fatal():
    """Regression (E2E/0.4.0 F5): one unreachable server raised straight out of
    connect(), so the run never started and every healthy server's tools were
    lost with it."""
    host = MCPHost([FakeServer("control", ["ask_user"]), BrokenServer("broken")])

    await host.connect()

    assert [t["name"] for t in host.tools()] == ["control__ask_user"]
    assert "broken" in host.failed()
    assert "cannot start" in host.failed()["broken"]
    # The healthy server still routes.
    assert await host.dispatch({"name": "control__ask_user", "input": {}})


@pytest.mark.asyncio
async def test_a_dropped_server_is_unroutable():
    host = MCPHost([FakeServer("control", ["ask_user"]), BrokenServer("broken")])
    await host.connect()

    with pytest.raises(UnknownToolError):
        await host.dispatch({"name": "broken__anything", "input": {}})


@pytest.mark.asyncio
async def test_failed_is_empty_when_every_server_starts():
    host = MCPHost([FakeServer("control", ["ask_user"]), FakeServer("cua", ["click"])])
    await host.connect()

    assert host.failed() == {}
