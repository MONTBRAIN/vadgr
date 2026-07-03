"""The auth port -- how a provider proves who it is on the wire.

A provider composes exactly one ``AuthStrategy`` by reference; the loop never
sees auth. Concrete strategies (OAuth / API-key / no-auth) land in a subsequent
slice -- this slice ships the port only.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthStrategy(Protocol):
    """Mutates the outbound request to carry credentials, and reacts to a 401."""

    async def inject_headers(self, request: dict) -> None:
        """Mutate outbound headers -- Bearer / x-api-key / none -- before send."""
        ...

    async def handle_401(self, response: Any) -> bool:
        """React to an auth failure. Return ``True`` if the caller should retry
        (e.g. token refreshed), ``False`` if it is terminal."""
        ...
