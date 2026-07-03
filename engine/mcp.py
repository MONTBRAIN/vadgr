"""The MCP host -- one generic client fronting every tool the agent can call.

The loop dispatches every tool through a single host that fronts a configured
set of MCP servers (built-in: the cua servers + the in-process control-plane
server; plus any the operator adds). The host aggregates every server's specs
into the one list the agent sees, namespaces them by server, and routes each
call back to the owning server. The boundary is invisible at call time.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Separator between a server name and one of its tool names in the aggregated,
# namespaced tool list the agent sees (``<server>__<tool>``).
NAMESPACE_SEP = "__"


@runtime_checkable
class MCPServer(Protocol):
    """Any MCP server, transport-agnostic -- stdio (subprocess), SSE, or
    streamable-HTTP over the wire, or in-process (the control-plane server).
    cua is one such server; a third-party server is another."""

    name: str

    async def list_tools(self) -> list:
        """This server's tool specs (unmodified, un-namespaced)."""
        ...

    async def call_tool(self, name: str, args: dict) -> dict:
        """Invoke one of this server's tools by its un-namespaced name."""
        ...


class UnknownToolError(KeyError):
    """Raised when a dispatched tool name maps to no configured server."""


class MCPHost:
    """Fronts every tool the agent can call. Connects to the configured MCP
    servers, aggregates their specs (namespaced by server), and routes each
    call to the owning server."""

    def __init__(self, servers: list[MCPServer]):
        self._servers = list(servers)
        self._by_name: dict[str, MCPServer] = {}
        self._tools: list[dict] = []
        self._connected = False

    async def connect(self) -> None:
        """Start/handshake each server, build the ``name -> server`` map, and
        aggregate the namespaced tool specs. A server-name collision is a
        startup error -- two servers must never share a namespace."""
        by_name: dict[str, MCPServer] = {}
        aggregated: list[dict] = []
        for server in self._servers:
            if server.name in by_name:
                raise ValueError(
                    f"MCP server name collision: '{server.name}' is configured twice"
                )
            by_name[server.name] = server
            for spec in await server.list_tools():
                namespaced = dict(spec)
                namespaced["name"] = f"{server.name}{NAMESPACE_SEP}{spec['name']}"
                aggregated.append(namespaced)
        self._by_name = by_name
        self._tools = aggregated
        self._connected = True

    def tools(self) -> list:
        """The aggregated, namespaced specs -- the single list fed to the model."""
        return self._tools

    async def dispatch(self, tool_use: dict) -> dict:
        """Route a ``tool_use`` to its owning server by the namespaced name.
        Raises ``UnknownToolError`` on an unroutable name."""
        server, tool_name = self._resolve(tool_use["name"])
        return await server.call_tool(tool_name, tool_use.get("input", {}))

    async def aclose(self) -> None:
        """Release every server the host connected."""
        for server in self._servers:
            aclose = getattr(server, "aclose", None)
            if aclose is not None:
                await aclose()
        self._connected = False

    def _resolve(self, namespaced: str) -> tuple[MCPServer, str]:
        server_name, sep, tool_name = namespaced.partition(NAMESPACE_SEP)
        if not sep or server_name not in self._by_name:
            raise UnknownToolError(namespaced)
        return self._by_name[server_name], tool_name


async def dispatch_to_mcp(tool_use: dict, mcp: MCPHost) -> dict:
    """Loop-facing shim: resolve the owning server and call it. Raises on an
    unknown tool or a tool error -- the loop turns that into an is_error
    result."""
    return await mcp.dispatch(tool_use)
