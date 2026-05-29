"""Tests for the device management endpoints."""

import pytest

from api.auth.tokens import set_default_token


class TestDevicesEndpoint:

    @pytest.mark.asyncio
    async def test_list_devices_empty(self, client):
        set_default_token("default-token")
        resp = await client.get(
            "/api/devices",
            headers={"Authorization": "Bearer default-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "devices" in body
        assert body["devices"] == []

    @pytest.mark.asyncio
    async def test_list_devices_after_pair_and_claim(self, client):
        set_default_token("default-token")
        # Pair
        pair = await client.post(
            "/api/auth/pair",
            headers={"Authorization": "Bearer default-token"},
        )
        token = pair.json()["token"]
        # Claim
        claim = await client.post(
            "/api/auth/claim",
            json={"token": token, "machine_name": "iphone-12"},
        )
        assert claim.status_code == 200
        # List
        resp = await client.get(
            "/api/devices",
            headers={"Authorization": "Bearer default-token"},
        )
        body = resp.json()
        assert len(body["devices"]) == 1
        dev = body["devices"][0]
        assert dev["machine_name"] == "iphone-12"
        assert "paired_at" in dev
        assert "last_seen" in dev
        assert "id" in dev
        # Token hash MUST NOT be returned
        assert "token_hash" not in dev
        assert "token" not in dev

    @pytest.mark.asyncio
    async def test_delete_device_revokes_token(self, client):
        set_default_token("default-token")
        # Pair + claim
        pair = await client.post(
            "/api/auth/pair",
            headers={"Authorization": "Bearer default-token"},
        )
        pair_token = pair.json()["token"]
        claim = await client.post(
            "/api/auth/claim",
            json={"token": pair_token, "machine_name": "android-x"},
        )
        device_token = claim.json()["token"]

        listed = await client.get(
            "/api/devices",
            headers={"Authorization": "Bearer default-token"},
        )
        device_id = listed.json()["devices"][0]["id"]

        # Delete
        delete_resp = await client.delete(
            f"/api/devices/{device_id}",
            headers={"Authorization": "Bearer default-token"},
        )
        assert delete_resp.status_code in (200, 204)

        # The device's persistent token should no longer authenticate non-localhost
        from httpx import ASGITransport, AsyncClient
        app = client._transport.app  # type: ignore[attr-defined]
        transport = ASGITransport(app=app, client=("203.0.113.5", 12345))
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/agents",
                headers={"Authorization": f"Bearer {device_token}"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_nonexistent_device_404(self, client):
        set_default_token("default-token")
        resp = await client.delete(
            "/api/devices/does-not-exist",
            headers={"Authorization": "Bearer default-token"},
        )
        assert resp.status_code == 404
