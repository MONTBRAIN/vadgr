"""The Anthropic-family base + the native_anthropic_oauth provider.

Against a mock transport, the outbound request must carry every validator
invariant Anthropic enforces server-side: ``Authorization: Bearer`` (never
``x-api-key``), the ``claude-cli/<ver> (external, cli)`` User-Agent, the
``anthropic-beta`` flags, ``anthropic-version``, the Claude Code system prefix as
the first system block, and ``mcp_``-prefixed tool names -- un-prefixed on the
way back. A 403 maps to the validator-update error; a 401 refreshes and retries.
``run_agent`` wires the control-plane server in beside cua and drives the loop.
"""

import json
import re
import time

import httpx
import pytest

from engine.auth.none import NoAuthStrategy
from engine.auth.oauth import OAuthStrategy
from engine.http import HttpClient
from engine.providers._anthropic_base import (
    CLAUDE_CODE_SYSTEM_PREFIX,
    AnthropicBase,
    ValidatorRejectedError,
)
from engine.providers.native_anthropic_oauth import AnthropicOAuthProvider


REFRESH_URL = "https://platform.claude.com/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


def _final(text="done"):
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }


def _with_tool(name="mcp_cua__click"):
    return {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "clicking"},
            {"type": "tool_use", "id": "t1", "name": name, "input": {"x": 1}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 10, "output_tokens": 4},
    }


class _NoAuthBase(AnthropicBase):
    name = "test_anthropic"
    auth_mode = "none"
    default_model = "claude-sonnet-4-6"
    user_agent = "claude-cli/2.1.2 (external, cli)"
    extra_headers = {"anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14"}


class FakeCua:
    name = "cua"

    async def list_tools(self):
        return [{"name": "click", "description": "click"}]

    async def call_tool(self, name, args):
        return {"clicked": True, "name": name, "args": args}


class Sink:
    def __init__(self):
        self.events = []

    async def __call__(self, event):
        self.events.append(event)


# ---- validator invariants on the outbound request --------------------------

@pytest.mark.asyncio
async def test_outbound_request_carries_the_validator_invariants(tmp_path):
    captured = {}

    def handler(request):
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_final())

    creds = tmp_path / ".credentials.json"
    creds.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "acc-123",
                    "refreshToken": "ref",
                    "expiresAt": int(time.time() * 1000) + 3_600_000,
                }
            }
        )
    )
    http = HttpClient(transport=httpx.MockTransport(handler))
    oauth = OAuthStrategy(
        credentials_path=str(creds), refresh_url=REFRESH_URL, client_id=CLIENT_ID,
        os_name="Linux", http=http,
    )
    provider = _NoAuthBase(http=http, auth_strategy=oauth)

    tools = [{"name": "cua__click", "description": "click", "inputSchema": {"type": "object"}}]
    await provider.llm_call([{"role": "user", "content": "hi"}], tools=tools, max_tokens=64)

    headers = captured["headers"]
    body = captured["body"]
    assert headers["authorization"] == "Bearer acc-123"
    assert "x-api-key" not in headers
    assert re.match(r"claude-cli/[\d.]+ \(external, cli\)", headers["user-agent"])
    assert "oauth-2025-04-20" in headers["anthropic-beta"]
    assert headers["anthropic-version"] == "2023-06-01"
    # System starts with the Claude Code identity block.
    assert body["system"][0]["text"] == CLAUDE_CODE_SYSTEM_PREFIX
    # Tool names go out mcp_-prefixed.
    assert body["tools"][0]["name"] == "mcp_cua__click"
    await http.aclose()


@pytest.mark.asyncio
async def test_response_tool_names_are_un_prefixed_on_the_way_back():
    def handler(request):
        return httpx.Response(200, json=_with_tool("mcp_cua__click"))

    http = HttpClient(transport=httpx.MockTransport(handler))
    provider = _NoAuthBase(http=http, auth_strategy=NoAuthStrategy())
    unified = await provider.llm_call([{"role": "user", "content": "x"}], tools=[], max_tokens=64)
    tool_uses = [b for b in unified["content"] if b["type"] == "tool_use"]
    assert tool_uses[0]["name"] == "cua__click"
    await http.aclose()


@pytest.mark.asyncio
async def test_403_maps_to_validator_update_error():
    def handler(request):
        return httpx.Response(403, json={"error": "forbidden"})

    http = HttpClient(transport=httpx.MockTransport(handler))
    provider = _NoAuthBase(http=http, auth_strategy=NoAuthStrategy())
    with pytest.raises(ValidatorRejectedError):
        await provider.llm_call([{"role": "user", "content": "x"}], tools=[], max_tokens=64)
    await http.aclose()


@pytest.mark.asyncio
async def test_401_refreshes_then_retries_once(tmp_path):
    creds = tmp_path / ".credentials.json"
    now_ms = 1_000_000_000_000
    creds.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "acc-old",
                    "refreshToken": "ref-old",
                    "expiresAt": now_ms + 3_600_000,
                }
            }
        )
    )
    seen_tokens = []
    state = {"messages_calls": 0}

    def handler(request):
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(
                200,
                json={"access_token": "acc-new", "refresh_token": "ref-new", "expires_in": 3600},
            )
        # /v1/messages
        state["messages_calls"] += 1
        seen_tokens.append(request.headers["authorization"])
        if state["messages_calls"] == 1:
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json=_final("recovered"))

    http = HttpClient(transport=httpx.MockTransport(handler))
    oauth = OAuthStrategy(
        credentials_path=str(creds), refresh_url=REFRESH_URL, client_id=CLIENT_ID,
        os_name="Linux", http=http, now=lambda: now_ms,
    )
    provider = _NoAuthBase(http=http, auth_strategy=oauth)
    unified = await provider.llm_call([{"role": "user", "content": "x"}], tools=[], max_tokens=64)

    assert state["messages_calls"] == 2
    assert seen_tokens == ["Bearer acc-old", "Bearer acc-new"]
    assert "recovered" in unified["content"][0]["text"]
    await http.aclose()


# ---- run_agent wiring ------------------------------------------------------

@pytest.mark.asyncio
async def test_run_agent_wires_control_plane_and_drives_loop(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=_with_tool("mcp_cua__click"))
        return httpx.Response(200, json=_final("all done"))

    http = HttpClient(transport=httpx.MockTransport(handler))
    provider = _NoAuthBase(http=http, auth_strategy=NoAuthStrategy(), runs_dir=str(tmp_path))
    sink = Sink()

    result = await provider.run_agent(
        "do the thing", [FakeCua()], sink, run_id="run-xyz"
    )

    assert result.final_text == "all done"
    assert result.total_iterations == 2
    assert result.total_input_tokens == 15  # 10 + 5
    # The cua tool was actually dispatched (mcp_ stripped, routed to cua).
    assert any(e["type"] == "tool_call_complete" for e in sink.events)
    # The journal was written for this run.
    import os

    assert os.path.exists(result.trajectory.path)
    await provider.teardown()


@pytest.mark.asyncio
async def test_run_agent_control_tools_reach_the_agent(tmp_path):
    seen_tools = {}

    def handler(request):
        body = json.loads(request.content)
        for t in body.get("tools", []):
            seen_tools[t["name"]] = True
        return httpx.Response(200, json=_final("ok"))

    http = HttpClient(transport=httpx.MockTransport(handler))
    provider = _NoAuthBase(http=http, auth_strategy=NoAuthStrategy(), runs_dir=str(tmp_path))
    await provider.run_agent("go", [FakeCua()], Sink(), run_id="run-tools")

    # Control-plane tools are in the list the agent sees (mcp_-prefixed).
    assert "mcp_control__request_approval" in seen_tools
    assert "mcp_cua__click" in seen_tools
    await provider.teardown()


# ---- the concrete OAuth provider -------------------------------------------

def test_oauth_provider_identity():
    provider = AnthropicOAuthProvider()
    assert provider.name == "anthropic_oauth"
    assert provider.auth_mode == "oauth"
    assert provider.user_agent.startswith("claude-cli/")
    assert "oauth-2025-04-20" in provider.extra_headers["anthropic-beta"]


@pytest.mark.asyncio
async def test_oauth_provider_refuses_production_mode(monkeypatch):
    monkeypatch.setenv("VADGR_MODE", "production")
    provider = AnthropicOAuthProvider()
    with pytest.raises(RuntimeError):
        await provider.setup()
