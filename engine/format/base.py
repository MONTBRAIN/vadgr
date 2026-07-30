"""The format port -- unified internal messages <-> provider wire shape.

A new model family is a new adapter satisfying ``MessageFormat``; the unified
representation the loop passes never changes shape -- only the adapter at the
wire edge does. This slice ships the port only.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MessageFormat(Protocol):
    """Translates between vadgr's internal messages/tools and a provider's wire
    representation, in both directions."""

    def to_provider_messages(self, messages: list) -> list:
        """Unified internal messages -> provider-native wire shape."""
        ...

    def to_provider_tools(self, tools: list) -> list:
        """Unified tool specs -> provider-native tool schema."""
        ...

    def from_provider_response(self, response: dict) -> dict:
        """Provider-native response -> unified internal representation."""
        ...
