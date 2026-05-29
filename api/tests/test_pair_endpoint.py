"""Tests for the pairing endpoint."""

import asyncio

import pytest

from api.auth.tokens import set_default_token


class TestPairEndpoint:

    @pytest.mark.asyncio
    async def test_pair_returns_expected_schema(self, client):
        set_default_token("default-token")
        resp = await client.post(
            "/api/auth/pair",
            headers={"Authorization": "Bearer default-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "host" in body
        assert "port" in body
        assert "token" in body
        assert "machine_name" in body
        assert isinstance(body["token"], str) and len(body["token"]) >= 16

    @pytest.mark.asyncio
    async def test_pair_token_is_one_time_use(self, client, app):
        """Once a device claims the pairing token, the token is consumed."""
        set_default_token("default-token")
        resp = await client.post(
            "/api/auth/pair",
            headers={"Authorization": "Bearer default-token"},
        )
        assert resp.status_code == 200
        pair_token = resp.json()["token"]

        # Simulate device claim: POST /api/auth/claim with the pair token
        claim_resp = await client.post(
            "/api/auth/claim",
            json={"token": pair_token, "machine_name": "mobile-test"},
        )
        assert claim_resp.status_code == 200
        device_token = claim_resp.json()["token"]
        assert isinstance(device_token, str) and len(device_token) >= 16

        # Re-claim with the same pair token should fail (one-time use)
        replay = await client.post(
            "/api/auth/claim",
            json={"token": pair_token, "machine_name": "mobile-other"},
        )
        assert replay.status_code in (400, 401, 404)

    @pytest.mark.asyncio
    async def test_pair_token_expires(self, client, monkeypatch):
        """Pairing token expires after configured TTL."""
        set_default_token("default-token")
        # Force a 0-second TTL via monkeypatch
        from api import auth as auth_mod
        from api.auth import pairing
        monkeypatch.setattr(pairing, "PAIRING_TTL_SECONDS", 0)
        resp = await client.post(
            "/api/auth/pair",
            headers={"Authorization": "Bearer default-token"},
        )
        assert resp.status_code == 200
        pair_token = resp.json()["token"]
        await asyncio.sleep(0.05)
        claim_resp = await client.post(
            "/api/auth/claim",
            json={"token": pair_token, "machine_name": "mobile-late"},
        )
        assert claim_resp.status_code in (400, 401, 404)
        _ = auth_mod  # keep import alive
