"""The channel port + router -- where a HITL request or notify reaches a human.

A ``Channel`` blocks for a human answer (``request``) or fires a notification
(``notify``). ``ChannelRouter`` picks the active channel (the one that launched
the run) and forwards; a per-call ``channel`` argument overrides for one call.
0.4.0 ships CLI + desktop; the mobile channel (0.7.0) drops in with no loop
change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class HumanPrompt:
    """A prompt routed to a channel and shown to a human. ``kind`` selects the
    interaction shape: ``approval`` (approve/reject), ``question`` (free
    answer, optional ``options``), or ``plan`` (approve/revise/reject)."""

    kind: str
    text: str
    options: list[str] | None = None
    risk: str | None = None
    preview: str | None = None
    timeout: float | None = None


@dataclass
class Delivery:
    """The outcome of a fire-and-forget ``notify``."""

    delivered: list[str] = field(default_factory=list)


@runtime_checkable
class Channel(Protocol):
    """One place a human can be reached."""

    name: str

    async def request(self, prompt: HumanPrompt) -> dict:
        """Block for a human answer. Returns ``{choice, text, timed_out}``."""
        ...

    async def notify(self, message: str, *, importance: str) -> Delivery:
        """Fire-and-forget notification at ``low`` | ``normal`` | ``high``."""
        ...


class ChannelRouter:
    """Picks the active channel and forwards. ``request``/``notify`` accept a
    per-call ``channel`` override for a single interaction."""

    def __init__(self, channels: dict[str, Channel], active: str):
        self._channels = dict(channels)
        if active not in self._channels:
            raise ValueError(f"active channel '{active}' is not configured")
        self._active = active

    def _pick(self, channel: str | None) -> Channel:
        name = channel or self._active
        try:
            return self._channels[name]
        except KeyError:
            raise ValueError(f"unknown channel: {name}")

    async def request(self, prompt: HumanPrompt, *, channel: str | None = None) -> dict:
        return await self._pick(channel).request(prompt)

    async def notify(
        self, message: str, *, importance: str = "normal", channel: str | None = None
    ) -> Delivery:
        return await self._pick(channel).notify(message, importance=importance)
