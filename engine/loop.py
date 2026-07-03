"""The shared tool-use loop -- and the history pruning it exists to own.

``run_loop`` is provider-agnostic: it takes a provider's ``llm_call`` callable,
the collected MCP tools, and an ``on_event`` sink, and runs the standard
tool-use cycle. It owns the conversation history -- including the keep-last-N
screenshot pruning that keeps the request body under the wire limit (issue
#10) -- and code-enforces the resume journal: every tool call writes
``in_flight`` before dispatch and ``done``/``error`` after.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from engine.base import RunResult
from engine.mcp import dispatch_to_mcp

# The text a pruned screenshot is replaced with. Small and constant so an
# arbitrarily large base64 payload collapses to a few bytes.
PRUNED_PLACEHOLDER_TEXT = "[screenshot pruned]"


class MaxIterationsExceeded(RuntimeError):
    """Raised when the agent does not finish within ``max_iterations`` -- a
    guard against an endless loop, never a silent hang."""


@dataclass
class Usage:
    """Token usage for one model turn, normalized across providers."""

    input_tokens: int = 0
    output_tokens: int = 0


def _image_slots(messages: list):
    """Yield ``(container_list, index)`` for every image block in the history,
    in document order -- including images nested inside ``tool_result`` blocks
    (where desktop screenshots actually live)."""
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for i, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "image":
                yield content, i
            elif block.get("type") == "tool_result" and isinstance(
                block.get("content"), list
            ):
                inner = block["content"]
                for j, sub in enumerate(inner):
                    if isinstance(sub, dict) and sub.get("type") == "image":
                        yield inner, j


def prune_old_images(messages: list, keep_last: int = 3) -> None:
    """Walk the history, keep the last ``keep_last`` image blocks intact, and
    replace every older one with a small text placeholder -- in place.

    Only the heavy image payloads are touched; tool-result *text* and the
    message order are left exactly as they were. This is the entire reason the
    loop owns the history instead of an external CLI."""
    slots = list(_image_slots(messages))
    if len(slots) <= keep_last:
        return
    for container, index in slots[: len(slots) - keep_last]:
        container[index] = {"type": "text", "text": PRUNED_PLACEHOLDER_TEXT}


def extract_usage(response: dict) -> Usage:
    """Pull token usage from a provider-normalized response."""
    usage = response.get("usage") or {}
    return Usage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )


def extract_tool_uses(response: dict) -> list[dict]:
    """Pull the ``tool_use`` blocks from a provider-normalized response."""
    return [
        block
        for block in response.get("content", [])
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def extract_text(response: dict) -> str:
    """Pull the final assistant text from a provider-normalized response."""
    return "".join(
        block.get("text", "")
        for block in response.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    )


async def run_loop(
    llm_call: Callable[..., Awaitable[dict]],
    initial_task: Any,
    mcp,
    trajectory,
    on_event: Callable[[dict], Awaitable[None]],
    max_iterations: int = 100,
    max_tokens: int = 8192,
    keep_last_images: int = 3,
) -> RunResult:
    """Standard tool-use loop, shared across all native providers. Owns the
    conversation history -- including screenshot pruning (issue #10) -- and
    code-enforces the resume journal: every tool call writes ``in_flight``
    BEFORE dispatch and ``done``/``error`` AFTER, so a mid-action crash always
    leaves a dangling record. ``mcp`` is the MCP host; ``trajectory`` is the
    journal."""
    messages: list = [{"role": "user", "content": initial_task}]
    mcp_tools = mcp.tools()
    total_input_tokens = total_output_tokens = 0

    for iteration in range(max_iterations):
        prune_old_images(messages, keep_last=keep_last_images)
        response = await llm_call(messages, tools=mcp_tools, max_tokens=max_tokens)
        usage = extract_usage(response)
        total_input_tokens += usage.input_tokens
        total_output_tokens += usage.output_tokens

        trajectory.append_response(iteration, response, usage)
        await on_event({"type": "llm_response", "response": response, "usage": usage})

        tool_uses = extract_tool_uses(response)
        if not tool_uses:
            return RunResult(
                final_text=extract_text(response),
                trajectory=trajectory,
                total_iterations=iteration + 1,
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
            )

        tool_results = []
        for tool_use in tool_uses:
            seq = trajectory.append_in_flight(iteration, tool_use)   # BEFORE dispatch
            try:
                result = await dispatch_to_mcp(tool_use, mcp)
                trajectory.append_done(seq, result)                  # AFTER dispatch
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": result,
                    }
                )
                await on_event(
                    {"type": "tool_call_complete", "tool_use": tool_use, "result": result}
                )
            except Exception as exc:  # captured, not fatal -- fed back to the model
                trajectory.append_error(seq, exc)                    # AFTER dispatch
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": f"Error: {exc}",
                        "is_error": True,
                    }
                )

        messages.append({"role": "assistant", "content": response["content"]})
        messages.append({"role": "user", "content": tool_results})

    raise MaxIterationsExceeded(
        f"Agent did not finish in {max_iterations} iterations"
    )
