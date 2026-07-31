"""The native loop behind the interface the executor already iterates.

`0.4.0` merged the engine and nothing called it: `ExecutionService` still built a
`CLIAgentProvider` and spawned `claude -p`. This module is the seam that makes a
triggered run reach the loop, and it exists as an adapter rather than a rewrite
because the two sides are opposite shapes:

- the executor **pulls** - it iterates an `AsyncIterator[ExecutionEvent]`
- the loop **pushes** - it calls `on_event(dict)` and returns a `RunResult`

A queue is the join. Nothing downstream of the executor cares which shape
produced an event, so everything below this file is untouched.

Design: `vadgr-docs/design/phase-0-pre-alpha/vadgr/0.4.1/`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from api.engine.providers import ExecutionEvent

logger = logging.getLogger(__name__)

# Closes the queue exactly once, so the consumer's loop terminates instead of
# waiting forever on a run that has already finished.
_DONE = object()


def map_event(event: dict) -> ExecutionEvent | None:
    """One loop event to one `ExecutionEvent`, or ``None`` to drop it.

    The mapping is here rather than inline in the iterator so it is a thing that
    can be tested directly and read in one place.

    **Two events are dropped on purpose.** `llm_response` carries the whole
    model response and `tool_result` can carry a base64 screenshot; the
    WebSocket is a live view, not the record. The record is `trajectory.jsonl`,
    which keeps both, and the raw log reads from there. Forwarding them would
    push megabytes through a phone's socket to render one line of text.
    """
    kind = event.get("type")

    if kind == "text":
        return ExecutionEvent(type="output", data=str(event.get("text", "")))

    if kind == "tool_call_complete":
        name = (event.get("tool_use") or {}).get("name", "tool")
        result = event.get("result")
        ok = not (isinstance(result, dict) and result.get("is_error"))
        return ExecutionEvent(type="output", data=f"{name} -> {'ok' if ok else 'error'}")

    if kind == "progress":
        return ExecutionEvent(type="output", data=str(event.get("message", "")))

    if kind == "todos":
        return ExecutionEvent(type="todos", data=str(event.get("todos", [])))

    if kind == "await_user":
        return ExecutionEvent(
            type="awaiting_approval", data=str(event.get("prompt", ""))
        )

    # llm_response, tool_result, and anything the loop grows later that this
    # bridge has not been taught: dropped rather than forwarded blind, because
    # an unrecognized payload is exactly the unbounded one.
    return None


class NativeLoopProvider:
    """The engine, wearing `CLIAgentProvider`'s streaming interface.

    Constructed with an already-built engine provider (the OAuth one today, an
    API-key one from `0.5.0`), so this class knows nothing about auth.
    """

    def __init__(self, provider: Any, mcp_servers: list | None = None):
        self._provider = provider
        self._mcp_servers = mcp_servers or []

    async def is_available(self) -> bool:
        return True

    async def execute_streaming(
        self,
        prompt: str,
        workspace: str | None = None,
        timeout: int | None = None,
        run_id: str | None = None,
        resume_state: Any = None,
        **_: object,  # use_stream_json / computer_use: the CLI path's, not ours
    ) -> AsyncIterator[ExecutionEvent]:
        """Run the loop and yield its events as the executor expects them.

        ``timeout`` is accepted and **ignored**: a native run has no wall-clock
        deadline. What bounds an unattended run is the gate layer and
        `max_iterations`, not a stopwatch, and the phase-0 gate is one real batch
        completing over hours (`PLANS.md` D-55). The parameter stays in the
        signature only because the executor passes it positionally to every
        provider.
        """
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event: dict) -> None:
            queue.put_nowait(event)

        async def drive() -> None:
            try:
                await self._provider.setup()
                result = await self._provider.run_agent(
                    task=prompt,
                    mcp_servers=self._mcp_servers,
                    on_event=on_event,
                    run_id=run_id,
                    resume_state=resume_state,
                )
                queue.put_nowait(
                    ExecutionEvent(type="done", data=result.final_text or "")
                )
            except Exception as exc:  # the loop failing is a run outcome, not a crash
                logger.exception("native run %s failed", run_id)
                queue.put_nowait(ExecutionEvent(type="error", data=str(exc)))
            finally:
                try:
                    await self._provider.teardown()
                finally:
                    queue.put_nowait(_DONE)

        task = asyncio.create_task(drive())
        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    break
                # `drive` puts terminal events in already-mapped; loop events
                # arrive raw and go through the table.
                mapped = item if isinstance(item, ExecutionEvent) else map_event(item)
                if mapped is not None:
                    yield mapped
        finally:
            # A consumer that stops early (client disconnects, run cancelled)
            # must not leave the loop running against a queue nobody drains.
            if not task.done():
                task.cancel()


def _providers_yaml() -> dict:
    """`providers.yaml`, raw. `ProviderConfig` drops `kind`, and `kind` is the
    only thing that says whether a provider is the engine or a subprocess."""
    import pathlib

    import yaml

    path = pathlib.Path(__file__).resolve().parent.parent.parent / "providers.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def is_native_provider(provider_key: str | None) -> bool:
    """True when this provider is the in-process engine rather than a CLI
    subprocess. One place, so the selection cannot drift between the timeout
    decision and the provider decision."""
    if not provider_key:
        return False
    entry = (_providers_yaml().get("providers") or {}).get(provider_key) or {}
    return entry.get("kind") == "native"


def build_native_provider(provider_key: str, model: str | None = None):
    """Construct the engine provider `providers.yaml` names for this key.

    The `module:` field is `package.module:ClassName`, so a new native provider
    (the API-key one in 0.5.0) is a config entry rather than a branch here.
    """
    import importlib

    entry = (_providers_yaml().get("providers") or {}).get(provider_key) or {}
    target = entry.get("module")
    if not target:
        raise ValueError(f"provider {provider_key!r} is native but names no module")
    module_name, _, class_name = target.partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    provider = cls()
    if model:
        provider.default_model = model
    return provider
