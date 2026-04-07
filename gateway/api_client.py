"""HTTP client for talking to the Vadgr API.

Thin wrapper around httpx that the router and notifier use
to list agents, trigger runs, check status, etc.
"""

from __future__ import annotations

import asyncio

import httpx

_TIMEOUT = 30
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1


class VadgrAPIClient:
    """Async client for the Vadgr REST API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Initialize the persistent httpx.AsyncClient."""
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)

    async def aclose(self) -> None:
        """Tear down the persistent httpx.AsyncClient."""
        if self._client is not None:
            await self._client.aclose()

    async def _request_with_retry(self, coro_factory):
        """Execute coro_factory() up to _MAX_RETRIES times, retrying on 5xx errors."""
        for attempt in range(_MAX_RETRIES):
            resp = await coro_factory()
            try:
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_BACKOFF_BASE * (2 ** attempt))
                else:
                    raise

    async def list_agents(self) -> list[dict]:
        return await self._request_with_retry(
            lambda: self._client.get(f"{self._base_url}/api/agents")
        )

    async def get_agent(self, agent_id: str) -> dict:
        return await self._request_with_retry(
            lambda: self._client.get(f"{self._base_url}/api/agents/{agent_id}")
        )

    async def run_agent(self, agent_id: str, inputs: dict) -> dict:
        return await self._request_with_retry(
            lambda: self._client.post(
                f"{self._base_url}/api/agents/{agent_id}/run",
                json={"inputs": inputs},
            )
        )

    async def list_runs(self, status: str | None = None) -> list[dict]:
        params = {"status": status} if status else {}
        return await self._request_with_retry(
            lambda: self._client.get(f"{self._base_url}/api/runs", params=params)
        )

    async def get_run(self, run_id: str) -> dict:
        return await self._request_with_retry(
            lambda: self._client.get(f"{self._base_url}/api/runs/{run_id}")
        )

    async def cancel_run(self, run_id: str) -> dict:
        return await self._request_with_retry(
            lambda: self._client.post(f"{self._base_url}/api/runs/{run_id}/cancel")
        )

    async def resume_run(self, run_id: str) -> dict:
        return await self._request_with_retry(
            lambda: self._client.post(f"{self._base_url}/api/runs/{run_id}/resume")
        )

    async def get_run_logs(self, run_id: str) -> list[dict]:
        return await self._request_with_retry(
            lambda: self._client.get(f"{self._base_url}/api/runs/{run_id}/logs")
        )
