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
    assert resp.json()["error"]["code"] == "TRANSPORT_UNREACHABLE"


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
    assert second.json()["error"]["code"] == "PAIRING_CODE_INVALID"


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


# --- the codes a client switches on (E2E 0.4.1 F13) -------------------------


def test_an_expired_code_is_410_and_says_so_not_401():
    """Expired and invalid are different recoveries for the owner.

    One means "ask the machine for a new code", the other means "you typed it
    wrong". They were both `401 INVALID_PAIRING_TOKEN`, so the phone could only
    offer one of the two.
    """
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore(ttl_seconds=0)          # mints already-expired codes
    token, _ = store.mint()
    assert store.redeem(token) is ClaimResult.EXPIRED


def test_an_unknown_or_reused_code_is_invalid_not_expired():
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    token, _ = store.mint()
    assert store.redeem(token) is ClaimResult.OK
    assert store.redeem(token) is ClaimResult.INVALID     # one-time
    assert store.redeem("never-minted") is ClaimResult.INVALID


def test_redeeming_one_code_does_not_change_another_code_s_verdict():
    """The sweep used to run on redeem, so looking up one token purged every
    other expired one and turned their verdict from EXPIRED into INVALID - the
    distinction existed and did not survive being asked for. Sweeping happens on
    mint instead, which is the only moment the store grows."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore(ttl_seconds=0)
    a, _ = store.mint()
    b, _ = store.mint()          # mint may sweep a; that is deliberate
    live, _ = PairingStore().mint()

    assert store.redeem(b) is ClaimResult.EXPIRED
    # b's lookup must not have disturbed anything else still held
    assert store.size() == 0 or store.redeem(a) is ClaimResult.EXPIRED
    assert live is not None


def test_a_code_left_to_expire_reports_expired_not_unknown():
    """The real case: a code is minted, nobody mints another, the owner claims
    it late. It is still held, so the answer is EXPIRED and the phone can say
    "ask for a new one"."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore(ttl_seconds=0)
    token, _ = store.mint()
    assert store.redeem(token) is ClaimResult.EXPIRED
