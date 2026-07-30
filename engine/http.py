"""The shared async HTTP client -- retries, timeouts, logging, in one place.

Every native provider's model call and every OAuth token refresh goes through
one ``HttpClient``, so the retry/timeout/back-off/logging policy is written
once and reused. A concrete provider never touches ``httpx`` directly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

import httpx

_LOG = logging.getLogger("vadgr.engine.http")

# Statuses worth a retry: rate limit + the transient 5xx family. A 4xx other
# than 429 is the caller's fault (bad request / auth) and never retried.
DEFAULT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class HttpClient:
    """A thin async wrapper over ``httpx.AsyncClient`` that retries transient
    failures with exponential back-off and logs each attempt.

    ``transport`` lets a test inject ``httpx.MockTransport``; ``sleep`` lets it
    inject a no-op so back-off never actually waits."""

    def __init__(
        self,
        *,
        timeout: float = 60.0,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        retry_statuses: frozenset[int] = DEFAULT_RETRY_STATUSES,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        logger: logging.Logger | None = None,
    ):
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._retry_statuses = retry_statuses
        self._sleep = sleep
        self._log = logger or _LOG
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        """POST with retry-on-transient. Returns the final response even when it
        is an un-retryable error status -- the caller decides what a 4xx means."""
        return await self.request("POST", url, headers=headers, json=json)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method, url, headers=headers, json=json
                )
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    self._log.warning(
                        "%s %s failed after %d attempts: %s",
                        method, url, attempt + 1, exc,
                    )
                    raise
                await self._backoff(attempt, reason=str(exc))
                continue

            if (
                response.status_code in self._retry_statuses
                and attempt < self._max_retries
            ):
                await self._backoff(attempt, reason=f"HTTP {response.status_code}")
                continue
            return response

        # Only reachable if the loop exhausted on a transport error.
        assert last_exc is not None
        raise last_exc

    async def _backoff(self, attempt: int, *, reason: str) -> None:
        delay = self._backoff_base * (2 ** attempt)
        self._log.info("retrying in %.2fs (attempt %d, %s)", delay, attempt + 1, reason)
        await self._sleep(delay)

    async def aclose(self) -> None:
        await self._client.aclose()
