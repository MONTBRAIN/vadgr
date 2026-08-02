"""The CLI channel -- prompts on the controlling TTY, notifies to the terminal.

``request`` renders the prompt, reads a line (with an optional timeout), and
maps it to a normalized ``{choice, text, timed_out}``. ``notify`` writes to the
terminal, with ``importance`` selecting how loud the line is. The read/write
functions are injectable so a test never touches a real TTY.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Awaitable, Callable

from engine.channels.base import Delivery, HumanPrompt

_YES = {"approve", "approved", "a", "y", "yes", "ok", "allow"}
_NO = {"reject", "rejected", "r", "n", "no", "deny"}
_REVISE = {"revise", "edit", "change", "v"}


def _default_writer(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


class CLIChannel:
    name = "cli"

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] = input,
        writer: Callable[[str], None] = _default_writer,
        reader: Callable[[str, float | None], Awaitable[str]] | None = None,
    ):
        self._input_fn = input_fn
        self._writer = writer
        self._reader = reader

    async def _read(self, text: str, timeout: float | None) -> str:
        if self._reader is not None:
            return await self._reader(text, timeout)
        loop = asyncio.get_event_loop()
        fut = loop.run_in_executor(None, self._input_fn, text)
        if timeout:
            return await asyncio.wait_for(fut, timeout)
        return await fut

    async def request(self, prompt: HumanPrompt) -> dict:
        rendered = self._render(prompt)
        try:
            raw = await self._read(rendered, prompt.timeout)
        except (asyncio.TimeoutError, TimeoutError):
            return {"choice": None, "text": None, "timed_out": True}
        except EOFError:
            # This channel is stdin, and on the daemon there is no stdin: the
            # gate parks and fails ~3ms later with "EOF when reading a line",
            # which says nothing about the actual problem. It is not that the
            # human declined - it is that nothing on this path can reach one.
            # The answer is an API channel resolved by `POST /api/runs/{id}/
            # respond`, which ships at `0.5.0` (CONTRACT.md 2.4). Until then,
            # say so, because the model reads this string and a truthful one
            # lets it carry on rather than retry a gate that cannot succeed.
            raise RuntimeError(
                "no interactive channel: this run has no attached terminal, so "
                "a human cannot be asked. Proceed without the answer or stop and "
                "explain what you needed - do not retry the gate."
            ) from None
        return self._interpret(prompt, raw)

    async def notify(self, message: str, *, importance: str = "normal") -> Delivery:
        prefix = {"low": "[info]", "normal": "[notify]", "high": "[!] "}.get(
            importance, "[notify]"
        )
        self._writer(f"{prefix} {message}")
        return Delivery(delivered=[self.name])

    def _render(self, prompt: HumanPrompt) -> str:
        parts = [prompt.text]
        if prompt.risk:
            parts.append(f"(risk: {prompt.risk})")
        if prompt.preview:
            parts.append(f"\n{prompt.preview}")
        if prompt.kind == "approval":
            parts.append(" [approve/reject] ")
        elif prompt.kind == "plan":
            parts.append(" [approve/revise/reject] ")
        elif prompt.options:
            parts.append(f" [{'/'.join(prompt.options)}] ")
        return " ".join(parts)

    def _interpret(self, prompt: HumanPrompt, raw: str) -> dict:
        answer = (raw or "").strip()
        low = answer.lower()
        if prompt.kind == "approval":
            choice = "approve" if low in _YES else "reject"
            return {"choice": choice, "text": answer, "timed_out": False}
        if prompt.kind == "plan":
            if low in _YES:
                choice = "approve"
            elif low in _REVISE:
                choice = "revise"
            else:
                choice = "reject"
            return {"choice": choice, "text": answer, "timed_out": False}
        # question: the raw answer is the value.
        return {"choice": answer, "text": answer, "timed_out": False}
