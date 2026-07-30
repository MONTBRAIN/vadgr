"""The Anthropic-family base: format + endpoint + the validator invariants.

Anthropic's OAuth validator enforces a fixed request shape server-side (the
April 2026 enforcement); get any one wrong and the request is rejected. Pinning
all of them in one family base means a validator change is a one-file patch:

- ``Authorization: Bearer`` (never ``x-api-key``) -- from the auth strategy.
- ``User-Agent`` matches ``claude-cli/<version> (external, cli)``.
- ``anthropic-beta`` carries the subscription-auth flags; ``anthropic-version:
  2023-06-01``.
- the system prompt **starts** with the Claude Code identity block.
- tool names prefixed ``mcp_`` on the way out, un-prefixed on the way back.

``run_agent`` builds the MCP host over the cua servers **plus** the in-process
control-plane server, opens a fresh ``Trajectory``, and drives the shared
``run_loop``.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from engine.base import RunResult
from engine.channels.base import ChannelRouter
from engine.channels.cli import CLIChannel
from engine.channels.desktop import DesktopChannel
from engine.format.anthropic import AnthropicFormat
from engine.http import HttpClient
from engine.loop import run_loop
from engine.mcp import MCPHost
from engine.policy.default import DefaultPolicy
from engine.tools import ControlPlaneServer, RunContext
from engine.trajectory import Trajectory

# The identity block every Claude Code request opens its system prompt with.
# The validator checks the system prompt STARTS with this; the real agent
# prompt (if any) follows it.
CLAUDE_CODE_SYSTEM_PREFIX = (
    "You are Claude Code, Anthropic's official CLI for Claude."
)


class ProviderError(RuntimeError):
    """A non-retryable HTTP error from the provider endpoint."""


class ValidatorRejectedError(ProviderError):
    """A 403 -- Anthropic's server-side validator rejected the request shape.

    Almost always the invariants drifted (User-Agent / beta flags / system
    prefix). Watch the community ``opencode-claude-code-auth`` pattern and patch
    this one file."""


class AnthropicBase:
    """Composable base for the Anthropic-family native providers. Holds an auth
    strategy and a message format; the concrete provider supplies identity
    (name / model / headers / prefix) and its auth strategy."""

    name: str = "anthropic_base"
    auth_mode: str = "oauth"
    default_model: str = "claude-opus-5"

    auth_strategy: Any = None
    user_agent: str = "claude-cli/2.1.2 (external, cli)"
    extra_headers: dict = {"anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14"}
    system_prompt_prefix: str = CLAUDE_CODE_SYSTEM_PREFIX

    base_url: str = "https://api.anthropic.com/v1"
    anthropic_version: str = "2023-06-01"
    tool_prefix: str = "mcp_"

    def __init__(
        self,
        *,
        http: HttpClient | None = None,
        message_format: AnthropicFormat | None = None,
        auth_strategy: Any = None,
        system_prompt: str = "",
        policy=None,
        channels: ChannelRouter | None = None,
        runs_dir: str | None = None,
    ):
        self._http = http or HttpClient()
        self._format = message_format or AnthropicFormat()
        if auth_strategy is not None:
            self.auth_strategy = auth_strategy
        self._system_prompt = system_prompt
        self._policy = policy or DefaultPolicy()
        self._channels = channels or ChannelRouter(
            {"cli": CLIChannel(), "desktop": DesktopChannel()}, active="cli"
        )
        self._runs_dir = runs_dir

    # -- lifecycle -----------------------------------------------------------

    async def setup(self) -> None:
        """Fail fast: validate credentials / reachability before any run."""
        ensure = getattr(self.auth_strategy, "ensure_ready", None)
        if ensure is not None:
            await ensure()

    async def teardown(self) -> None:
        await self._http.aclose()

    # -- the model call ------------------------------------------------------

    async def llm_call(self, messages: list, tools: list, max_tokens: int = 8192) -> dict:
        """Build the request (format + prefix + invariants + auth), POST it, and
        return the unified response with tool names un-prefixed."""
        wire_messages = self._format.to_provider_messages(messages)
        wire_tools = [
            {**t, "name": self.tool_prefix + t["name"]}
            for t in self._format.to_provider_tools(tools)
        ]

        system = [{"type": "text", "text": self.system_prompt_prefix}]
        if self._system_prompt:
            system.append({"type": "text", "text": self._system_prompt})

        body: dict = {
            "model": self.default_model,
            "max_tokens": max_tokens,
            "messages": wire_messages,
            "system": system,
        }
        if wire_tools:
            body["tools"] = wire_tools

        request = {"headers": self._base_headers()}
        await self.auth_strategy.inject_headers(request)
        wire_response = await self._post(request, body)
        return self._decode(wire_response)

    def _base_headers(self) -> dict:
        headers = {
            "content-type": "application/json",
            "anthropic-version": self.anthropic_version,
            "User-Agent": self.user_agent,
        }
        headers.update(self.extra_headers)
        return headers

    async def _post(self, request: dict, body: dict) -> dict:
        url = f"{self.base_url}/messages"
        response = await self._http.post(url, headers=request["headers"], json=body)

        if response.status_code == 401:
            retry = await self.auth_strategy.handle_401(response)
            if retry:
                await self.auth_strategy.inject_headers(request)
                response = await self._http.post(
                    url, headers=request["headers"], json=body
                )

        if response.status_code == 401:
            raise ProviderError(
                "Anthropic rejected the credentials (401). Re-run `claude setup-token`."
            )
        if response.status_code == 403:
            raise ValidatorRejectedError(
                "Anthropic's validator rejected the request (403). The request "
                "shape (User-Agent / anthropic-beta / system prefix) likely "
                "drifted -- apply the current community pattern in "
                "engine/providers/_anthropic_base.py and re-run."
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"Anthropic request failed (HTTP {response.status_code}): {response.text}"
            )
        return response.json()

    def _decode(self, wire_response: dict) -> dict:
        unified = self._format.from_provider_response(wire_response)
        for block in unified.get("content", []):
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and isinstance(block.get("name"), str)
                and block["name"].startswith(self.tool_prefix)
            ):
                block["name"] = block["name"][len(self.tool_prefix):]
        return unified

    # -- the run -------------------------------------------------------------

    async def run_agent(
        self,
        task: Any,
        mcp_servers: list,
        on_event: Callable[[dict], Awaitable[None]],
        *,
        run_id: str | None = None,
        max_iterations: int = 100,
        max_tokens: int = 8192,
        keep_last_images: int = 3,
        **kwargs: Any,
    ) -> RunResult:
        """Build the MCP host over the cua servers PLUS the in-process
        control-plane server, open a fresh journal, and delegate the cycle to
        the shared ``run_loop``."""
        run_id = run_id or _new_run_id()
        trajectory = Trajectory(run_id, path=_journal_path(self._runs_dir, run_id))

        ctx = RunContext(run_id=run_id, trajectory=trajectory)
        control = ControlPlaneServer(ctx, self._channels, self._policy)
        host = MCPHost([*mcp_servers, control])
        await host.connect()

        async def _tracking_on_event(event: dict) -> None:
            if event.get("type") == "llm_response":
                ctx.iteration += 1
                usage = event.get("usage")
                if usage is not None:
                    ctx.input_tokens += getattr(usage, "input_tokens", 0)
                    ctx.output_tokens += getattr(usage, "output_tokens", 0)
            await on_event(event)

        # The RunContext's sink is the same tracking wrapper, so control-plane
        # events (todos / progress) reach the watching client too.
        ctx.emit = _tracking_on_event

        try:
            result = await run_loop(
                self.llm_call,
                task,
                host,
                trajectory,
                _tracking_on_event,
                max_iterations=max_iterations,
                max_tokens=max_tokens,
                keep_last_images=keep_last_images,
            )
        finally:
            ctx.state = "done"
            await host.aclose()
        return result


def _new_run_id() -> str:
    import uuid

    return "run-" + uuid.uuid4().hex[:12]


def _journal_path(runs_dir: str | None, run_id: str) -> str | None:
    if runs_dir is None:
        return None
    from pathlib import Path

    return str(Path(runs_dir) / run_id / "trajectory.jsonl")
