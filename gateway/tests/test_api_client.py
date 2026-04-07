"""Tests for VadgrAPIClient connection pooling and retry behavior.

Issue #119: api_client.py creates a new httpx.AsyncClient per request.
Fix: persistent client with connect/close lifecycle, 3-retry with backoff on 5xx.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from gateway.api_client import VadgrAPIClient


# ---------------------------------------------------------------------------
# Lifecycle: connect() and aclose() must exist and manage a persistent client
# ---------------------------------------------------------------------------

class TestClientLifecycle:
    def test_client_exposes_connect_method(self):
        """Client must expose connect() to initialize the persistent httpx.AsyncClient."""
        client = VadgrAPIClient()
        assert hasattr(client, "connect") and callable(client.connect)

    def test_client_exposes_aclose_method(self):
        """Client must expose aclose() to tear down the persistent httpx.AsyncClient."""
        client = VadgrAPIClient()
        assert hasattr(client, "aclose") and callable(client.aclose)

    @pytest.mark.asyncio
    async def test_connect_initializes_persistent_client(self):
        """After connect(), the client holds a live httpx.AsyncClient instance."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            client = VadgrAPIClient()
            await client.connect()

            assert mock_cls.call_count == 1
            assert client._client is mock_instance

    @pytest.mark.asyncio
    async def test_aclose_closes_the_persistent_client(self):
        """aclose() must call aclose() on the underlying httpx.AsyncClient."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            client = VadgrAPIClient()
            await client.connect()
            await client.aclose()

            mock_instance.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Connection pooling: a single httpx.AsyncClient must be reused across calls
# ---------------------------------------------------------------------------

class TestConnectionPooling:
    @pytest.mark.asyncio
    async def test_single_httpx_client_reused_across_calls(self):
        """All method calls must reuse the persistent client; httpx.AsyncClient
        must be instantiated exactly once (at connect()), not once per request."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            agents_resp = MagicMock(status_code=200)
            agents_resp.raise_for_status = MagicMock()
            agents_resp.json.return_value = []

            runs_resp = MagicMock(status_code=200)
            runs_resp.raise_for_status = MagicMock()
            runs_resp.json.return_value = []

            mock_instance.get.side_effect = [agents_resp, runs_resp]

            client = VadgrAPIClient()
            await client.connect()
            await client.list_agents()
            await client.list_runs()

            # httpx.AsyncClient() must be instantiated exactly once
            assert mock_cls.call_count == 1


# ---------------------------------------------------------------------------
# Retry on 5xx: 3 attempts with backoff; no retry on 4xx
# ---------------------------------------------------------------------------

class TestRetryOn5xx:
    @pytest.mark.asyncio
    async def test_retries_up_to_3_times_on_503(self):
        """list_agents() must retry up to 3 times when the server returns 503."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep"):
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            fail_resp = MagicMock(status_code=503)
            fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "503 Service Unavailable",
                request=MagicMock(),
                response=MagicMock(status_code=503),
            )
            ok_resp = MagicMock(status_code=200)
            ok_resp.raise_for_status = MagicMock()
            ok_resp.json.return_value = []

            # First two calls fail, third succeeds
            mock_instance.get.side_effect = [fail_resp, fail_resp, ok_resp]

            client = VadgrAPIClient()
            await client.connect()
            result = await client.list_agents()

            assert mock_instance.get.call_count == 3
            assert result == []

    @pytest.mark.asyncio
    async def test_retries_on_500(self):
        """list_agents() must retry on 500 Internal Server Error."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep"):
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            fail_resp = MagicMock(status_code=500)
            fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
            ok_resp = MagicMock(status_code=200)
            ok_resp.raise_for_status = MagicMock()
            ok_resp.json.return_value = [{"id": "agent-1", "name": "QA Engineer"}]

            mock_instance.get.side_effect = [fail_resp, ok_resp]

            client = VadgrAPIClient()
            await client.connect()
            result = await client.list_agents()

            assert mock_instance.get.call_count == 2
            assert result[0]["name"] == "QA Engineer"

    @pytest.mark.asyncio
    async def test_raises_after_3_consecutive_5xx(self):
        """list_agents() must raise HTTPStatusError after exhausting all 3 retries."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep"):
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            fail_resp = MagicMock(status_code=503)
            fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "503 Service Unavailable",
                request=MagicMock(),
                response=MagicMock(status_code=503),
            )
            mock_instance.get.return_value = fail_resp

            client = VadgrAPIClient()
            await client.connect()

            with pytest.raises(httpx.HTTPStatusError):
                await client.list_agents()

            # Exactly 3 attempts before giving up
            assert mock_instance.get.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self):
        """list_agents() must not retry on 404 -- client errors are not transient."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep") as mock_sleep:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            fail_resp = MagicMock(status_code=404)
            fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
            mock_instance.get.return_value = fail_resp

            client = VadgrAPIClient()
            await client.connect()

            with pytest.raises(httpx.HTTPStatusError):
                await client.list_agents()

            # Called only once; no sleep between retries
            assert mock_instance.get.call_count == 1
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self):
        """list_agents() must not retry on 401 Unauthorized."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep") as mock_sleep:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            fail_resp = MagicMock(status_code=401)
            fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )
            mock_instance.get.return_value = fail_resp

            client = VadgrAPIClient()
            await client.connect()

            with pytest.raises(httpx.HTTPStatusError):
                await client.list_agents()

            assert mock_instance.get.call_count == 1
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_applies_to_post_methods(self):
        """run_agent() must also retry on 5xx, not just GET methods."""
        with patch("gateway.api_client.httpx.AsyncClient") as mock_cls, \
             patch("asyncio.sleep"):
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance

            fail_resp = MagicMock(status_code=503)
            fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "503",
                request=MagicMock(),
                response=MagicMock(status_code=503),
            )
            ok_resp = MagicMock(status_code=200)
            ok_resp.raise_for_status = MagicMock()
            ok_resp.json.return_value = {"run_id": "run-xyz"}

            mock_instance.post.side_effect = [fail_resp, ok_resp]

            client = VadgrAPIClient()
            await client.connect()
            result = await client.run_agent("agent-1", {"repo_path": "/tmp/repo"})

            assert mock_instance.post.call_count == 2
            assert result["run_id"] == "run-xyz"
