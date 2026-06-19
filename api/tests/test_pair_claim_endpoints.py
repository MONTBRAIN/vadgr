"""pair -> claim -> devices loop, over loopback (Gate 0 bypass)."""

import pytest

from api.auth import tokens
from api.transport import TailscaleTransport


class _FakeTailscale(TailscaleTransport):
    """Tailscale-shaped transport that advertises a host (so pair succeeds)
    without a live tailnet."""

    def __init__(self):
        pass

    name = "tailscale"

    def advertise_host(self):
        return "my-box.tailnet-1234.ts.net"

    def is_available(self):
        return True

    def is_authorized_source(self, peer_ip):
        return peer_ip.startswith("100.")

    def bind_host(self):
        return "100.1.2.3"

    def status(self):
        return {"name": "tailscale", "available": True}


@pytest.mark.asyncio
async def test_pair_refuses_when_transport_cannot_advertise(client):
    # Default test transport is loopback -> advertise_host() is None.
    resp = await client.post("/api/auth/pair")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "TRANSPORT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_pair_returns_qr_payload_when_advertisable(app, client):
    app.state.transport = _FakeTailscale()
    resp = await client.post("/api/auth/pair")
    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == "my-box.tailnet-1234.ts.net"
    assert body["host"] != "127.0.0.1"
    assert body["pairing_token"]
    assert "machine_name" in body and "port" in body


@pytest.mark.asyncio
async def test_full_pair_claim_devices_loop(app, client):
    app.state.transport = _FakeTailscale()

    # 1. pair -> pairing token
    pair = (await client.post("/api/auth/pair")).json()
    pairing_token = pair["pairing_token"]

    # 2. claim -> persistent token + device
    claim = await client.post(
        "/api/auth/claim",
        json={"pairing_token": pairing_token, "device_name": "Pixel 8"},
    )
    assert claim.status_code == 200
    claimed = claim.json()
    assert claimed["token"] and claimed["device_id"]

    # Token is stored hashed, never plaintext.
    stored = await app.state.device_repo.find_by_token_hash(
        tokens.hash_token(claimed["token"])
    )
    assert stored is not None and stored["id"] == claimed["device_id"]

    # 3. devices lists it (loopback bypasses the gates)
    devices = (await client.get("/api/devices")).json()
    assert any(d["id"] == claimed["device_id"] for d in devices)
    assert all("token_hash" not in d for d in devices)  # never serialized


@pytest.mark.asyncio
async def test_pairing_token_is_one_time(app, client):
    app.state.transport = _FakeTailscale()
    pairing_token = (await client.post("/api/auth/pair")).json()["pairing_token"]
    first = await client.post(
        "/api/auth/claim",
        json={"pairing_token": pairing_token, "device_name": "A"},
    )
    assert first.status_code == 200
    # Replay the same token -> rejected.
    second = await client.post(
        "/api/auth/claim",
        json={"pairing_token": pairing_token, "device_name": "B"},
    )
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "INVALID_PAIRING_TOKEN"


@pytest.mark.asyncio
async def test_claim_with_bogus_token_rejected(client):
    resp = await client.post(
        "/api/auth/claim",
        json={"pairing_token": "not-a-real-token", "device_name": "X"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_revoke_device(app, client):
    app.state.transport = _FakeTailscale()
    pairing_token = (await client.post("/api/auth/pair")).json()["pairing_token"]
    claimed = (
        await client.post(
            "/api/auth/claim",
            json={"pairing_token": pairing_token, "device_name": "P"},
        )
    ).json()

    revoke = await client.delete(f"/api/devices/{claimed['device_id']}")
    assert revoke.status_code == 200
    assert await app.state.device_repo.find_by_token_hash(
        tokens.hash_token(claimed["token"])
    ) is None

    missing = await client.delete("/api/devices/does-not-exist")
    assert missing.status_code == 404
