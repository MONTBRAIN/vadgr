"""Tests for the bearer-token auth middleware.

Localhost requests bypass auth (CLI + frontend). Non-localhost requests
must present a valid bearer token (either the default token at
~/.config/vadgr/token, or a paired-device token stored in the DB).
"""

import pytest


class TestLocalhostBypass:

    @pytest.mark.asyncio
    async def test_localhost_no_token_allowed(self, client):
        """127.0.0.1 / localhost requests do not require auth."""
        # ASGITransport sets client to ("testclient", port) by default but the
        # middleware treats that as localhost (loopback). Health must pass.
        resp = await client.get("/api/health")
        assert resp.status_code == 200


class TestNonLocalhostAuth:

    @pytest.mark.asyncio
    async def test_non_localhost_without_token_is_rejected(self, app):
        """Simulated non-localhost request without auth header → 401."""
        from httpx import ASGITransport, AsyncClient
        # Force a non-loopback peer via ASGI scope override
        transport = ASGITransport(app=app, client=("203.0.113.5", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/agents")
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body or "detail" in body

    @pytest.mark.asyncio
    async def test_non_localhost_with_wrong_token_is_rejected(self, app, monkeypatch):
        from api.auth.tokens import set_default_token
        set_default_token("correct-token")
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app, client=("203.0.113.5", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/agents",
                headers={"Authorization": "Bearer wrong-token"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_localhost_with_default_token_is_allowed(self, app):
        from api.auth.tokens import set_default_token
        set_default_token("good-default-token")
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app, client=("203.0.113.5", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/agents",
                headers={"Authorization": "Bearer good-default-token"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_is_public_even_from_non_localhost(self, app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app, client=("203.0.113.5", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/health")
        assert resp.status_code == 200
