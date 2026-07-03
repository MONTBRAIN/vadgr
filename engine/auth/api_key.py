"""The API-key strategy -- an env-var lookup injected as a header.

Terminal on 401: a rejected key is a bad key, not something a retry fixes. The
production API-key providers (0.5.0) compose this; it ships now because the base
class can compose any of the three strategies.
"""

from __future__ import annotations

import os
from typing import Any


class APIKeyStrategy:
    """Reads ``env_var`` and injects it as ``header`` (optionally with a
    ``scheme`` prefix like ``Bearer``)."""

    def __init__(
        self,
        env_var: str,
        *,
        header: str = "x-api-key",
        scheme: str | None = None,
    ):
        self._env_var = env_var
        self._header = header
        self._scheme = scheme

    async def inject_headers(self, request: dict) -> None:
        key = os.environ.get(self._env_var)
        if not key:
            raise RuntimeError(
                f"API key not found: set the {self._env_var} environment variable"
            )
        value = f"{self._scheme} {key}" if self._scheme else key
        request.setdefault("headers", {})[self._header] = value

    async def handle_401(self, response: Any) -> bool:
        return False
