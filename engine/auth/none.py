"""The no-auth strategy -- for local models that need no credentials."""

from __future__ import annotations

from typing import Any


class NoAuthStrategy:
    """Injects nothing and treats any 401 as terminal (a local endpoint that
    401s is misconfigured, not refreshable)."""

    async def inject_headers(self, request: dict) -> None:
        return None

    async def handle_401(self, response: Any) -> bool:
        return False
