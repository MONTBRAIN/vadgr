"""The Anthropic message/tool format adapter -- the only wire shape 0.4.0 needs.

vadgr's internal message representation is already Anthropic-flavoured
(role + content blocks, ``tool_use`` / ``tool_result``), so ``to_provider_*``
is mostly normalization: tool specs get their JSON-schema under the Anthropic
``input_schema`` key. ``from_provider_response`` reduces a wire message to the
loop's unified ``{content, usage, stop_reason}`` view. The OpenAI/Google
adapters (0.5.0) slot in beside this one without touching the loop.
"""

from __future__ import annotations

import json
from typing import Any

_EMPTY_SCHEMA = {"type": "object", "properties": {}}


class AnthropicFormat:
    """Translate unified messages/tools to the Anthropic wire shape and back."""

    def to_provider_messages(self, messages: list) -> list:
        """The internal representation is already the Anthropic content-block
        shape, so this is mostly an identity pass over a shallow copy. The one
        normalization the wire demands: a ``tool_result`` block's ``content``
        must be a **string** or a **list of content blocks**, never a bare
        object -- but MCP dispatch returns a dict, so a dict/other scalar is
        JSON-stringified here. (A list -- e.g. a screenshot's content blocks --
        and a plain string pass through untouched.)"""
        return [self._normalize_message(m) for m in messages]

    def _normalize_message(self, message: dict) -> dict:
        out = dict(message)
        content = out.get("content")
        if isinstance(content, list):
            out["content"] = [self._normalize_block(b) for b in content]
        return out

    def _normalize_block(self, block: Any) -> Any:  # noqa: ANN401
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            return block
        inner = block.get("content")
        if isinstance(inner, (str, list)):
            return block
        normalized = dict(block)
        normalized["content"] = (
            inner if isinstance(inner, str) else json.dumps(inner, default=str)
        )
        return normalized

    def to_provider_tools(self, tools: list) -> list:
        """Map each tool spec to the Anthropic ``{name, description,
        input_schema}`` shape, accepting an ``inputSchema`` / ``parameters`` /
        ``input_schema`` source key."""
        provider_tools = []
        for tool in tools:
            schema = (
                tool.get("input_schema")
                or tool.get("inputSchema")
                or tool.get("parameters")
                or dict(_EMPTY_SCHEMA)
            )
            provider_tools.append(
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": schema,
                }
            )
        return provider_tools

    def from_provider_response(self, response: dict) -> dict:
        """Reduce an Anthropic wire message to the loop's unified view."""
        usage = response.get("usage") or {}
        return {
            "content": response.get("content", []),
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
            "stop_reason": response.get("stop_reason"),
        }
