"""pair -> claim -> devices loop, over loopback (Gate 0 bypass)."""

import re

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


def test_minting_supersedes_the_outstanding_code():
    """Replaces the old two-codes-at-once test, whose premise the single slot
    makes impossible. The property that test guarded - an expired code does not
    decay into unknown - is the one below."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    a, _ = store.mint()
    b, _ = store.mint()
    assert store.redeem(a) is ClaimResult.INVALID
    assert store.redeem(b) is ClaimResult.OK


def test_a_code_left_to_expire_reports_expired_not_unknown():
    """The real case: a code is minted, nobody mints another, the owner claims
    it late. It is still held, so the answer is EXPIRED and the phone can say
    "ask for a new one"."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore(ttl_seconds=0)
    code, _ = store.mint()
    assert store.redeem(code) is ClaimResult.EXPIRED


# --- the five-attempt cap ---------------------------------------------------


def _wrong(n):
    """Well-formed codes that are not the minted one. Crockford letters only, so
    each one is a real attempt rather than malformed input."""
    return [chr(ord("A") + i) * 4 + "-" + chr(ord("A") + i) * 4 for i in range(n)]


def test_four_wrong_guesses_still_leave_the_true_code_claimable():
    """The counter counts failures, so the owner mistyping four times still
    pairs on the fifth try."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    code, _ = store.mint()
    for guess in _wrong(4):
        assert store.redeem(guess) is ClaimResult.INVALID
    assert store.redeem(code) is ClaimResult.OK


def test_the_fifth_failure_is_rate_limited_and_burns_the_code():
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    code, _ = store.mint()
    guesses = _wrong(5)
    for guess in guesses[:4]:
        assert store.redeem(guess) is ClaimResult.INVALID
    assert store.redeem(guesses[4]) is ClaimResult.RATE_LIMITED
    # The burn is the point: the code that was correct all along is dead.
    assert store.redeem(code) is ClaimResult.INVALID
    assert store.size() == 0


def test_rate_limited_fires_once_and_everything_after_is_invalid():
    """`429` is the moment the cap acts. Afterwards the code does not exist, and
    INVALID is the truth - deliberately indistinguishable from never-minted."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    store.mint()
    for guess in _wrong(4):
        store.redeem(guess)
    assert store.redeem("ZZZZ-ZZZZ") is ClaimResult.RATE_LIMITED
    assert store.redeem("YYYY-YYYY") is ClaimResult.INVALID


def test_malformed_input_never_touches_the_counter():
    """Garbage cannot burn a code; only eight well-formed wrong characters can."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    code, _ = store.mint()
    # Too short, too long, off-alphabet, and a U - which Crockford excludes
    # without giving it a mapping, so it is malformed rather than forgiven.
    for _ in range(5):
        for malformed in ("7QK4-M2X", "7QK4-M2XDE", "!!!!-!!!!", "UUUU-UUUU"):
            assert store.redeem(malformed) is ClaimResult.INVALID
    assert store.redeem(code) is ClaimResult.OK


def test_a_fresh_mint_resets_the_counter():
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    store.mint()
    for guess in _wrong(4):
        store.redeem(guess)
    code, _ = store.mint()
    for guess in _wrong(4):
        assert store.redeem(guess) is ClaimResult.INVALID
    assert store.redeem(code) is ClaimResult.OK


def test_wrong_guesses_at_an_expired_code_do_not_convert_its_verdict():
    """A dead code answers EXPIRED to the right characters however many wrong
    ones preceded them - a wrong guess at a dead code counts for nothing."""
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore(ttl_seconds=0)
    code, _ = store.mint()
    for guess in _wrong(5):
        assert store.redeem(guess) is ClaimResult.INVALID
    assert store.redeem(code) is ClaimResult.EXPIRED


def test_a_code_is_redeemable_however_it_was_typed():
    from api.auth.pairing_store import PairingStore, ClaimResult

    store = PairingStore()
    code, _ = store.mint()
    assert store.redeem(code.replace("-", "").lower()) is ClaimResult.OK


# --- the claim mapping, total and injective ---------------------------------


def test_every_claim_result_maps_to_its_own_status_and_code():
    """Enumerated from the enum, so a value added without a route branch fails
    here rather than reaching a phone that has no case for it."""
    from api.auth.pairing_store import ClaimResult

    expected = {
        ClaimResult.OK: (200, None),
        ClaimResult.INVALID: (401, "PAIRING_CODE_INVALID"),
        ClaimResult.EXPIRED: (410, "PAIRING_CODE_EXPIRED"),
        ClaimResult.RATE_LIMITED: (429, "RATE_LIMITED"),
    }
    assert set(expected) == set(ClaimResult)                 # total
    assert len(set(expected.values())) == len(ClaimResult)   # injective


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,status,code",
    [
        ("INVALID", 401, "PAIRING_CODE_INVALID"),
        ("EXPIRED", 410, "PAIRING_CODE_EXPIRED"),
        ("RATE_LIMITED", 429, "RATE_LIMITED"),
    ],
)
async def test_the_route_answers_each_failure_with_its_own_status(
    app, client, monkeypatch, result, status, code
):
    """The other half of the mapping: the enum value the store returns and the
    envelope a client actually switches on."""
    from api.auth.pairing_store import ClaimResult

    monkeypatch.setattr(app.state.pairing_store, "redeem",
                        lambda raw: getattr(ClaimResult, result))
    resp = await client.post(
        "/api/auth/claim", json={"pairing_token": "AAAA-AAAA", "device_name": "X"}
    )
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code
    assert resp.json()["error"]["details"] == {}


# --- the same behaviour, over HTTP ------------------------------------------


@pytest.mark.asyncio
async def test_pair_returns_a_grouped_crockford_code_and_nothing_else(app, client):
    app.state.transport = _FakeTailscale()
    body = (await client.post("/api/auth/pair")).json()
    assert re.match(r"^[0-9ABCDEFGHJKMNPQRSTVWXYZ]{4}-[0-9ABCDEFGHJKMNPQRSTVWXYZ]{4}$",
                    body["pairing_token"])
    # A shape guard: this patch adds no field, because the phone is being built
    # against these four right now.
    assert set(body) == {"host", "port", "pairing_token", "machine_name"}


@pytest.mark.asyncio
@pytest.mark.parametrize("retype", [str.lower, lambda c: c.replace("-", ""),
                                    lambda c: c.replace("-", " ")])
async def test_claim_accepts_the_code_however_it_was_typed(app, client, retype):
    app.state.transport = _FakeTailscale()
    code = (await client.post("/api/auth/pair")).json()["pairing_token"]
    resp = await client.post(
        "/api/auth/claim",
        json={"pairing_token": retype(code), "device_name": "Pixel 8"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_claim_rejects_a_malformed_code(app, client):
    app.state.transport = _FakeTailscale()
    await client.post("/api/auth/pair")
    for malformed in ("7QK4-M2X", "UUUU-UUUU"):
        resp = await client.post(
            "/api/auth/claim", json={"pairing_token": malformed, "device_name": "X"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "PAIRING_CODE_INVALID"


@pytest.mark.asyncio
async def test_the_seven_attempt_trace_over_http(app, client):
    """The cap as a client sees it: four 401s, a 429 that burns the code, then
    401 even for the code that was correct all along."""
    app.state.transport = _FakeTailscale()
    code = (await client.post("/api/auth/pair")).json()["pairing_token"]

    async def claim(value):
        return await client.post(
            "/api/auth/claim", json={"pairing_token": value, "device_name": "X"}
        )

    seen = []
    for guess in _wrong(6):
        resp = await claim(guess)
        seen.append((resp.status_code, resp.json()["error"]["code"]))
    final = await claim(code)
    seen.append((final.status_code, final.json()["error"]["code"]))

    assert seen == [
        (401, "PAIRING_CODE_INVALID"),
        (401, "PAIRING_CODE_INVALID"),
        (401, "PAIRING_CODE_INVALID"),
        (401, "PAIRING_CODE_INVALID"),
        (429, "RATE_LIMITED"),
        (401, "PAIRING_CODE_INVALID"),
        (401, "PAIRING_CODE_INVALID"),
    ]


@pytest.mark.asyncio
async def test_pairing_twice_leaves_only_the_second_code_claimable(app, client):
    app.state.transport = _FakeTailscale()
    first = (await client.post("/api/auth/pair")).json()["pairing_token"]
    second = (await client.post("/api/auth/pair")).json()["pairing_token"]

    stale = await client.post(
        "/api/auth/claim", json={"pairing_token": first, "device_name": "A"}
    )
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "PAIRING_CODE_INVALID"

    fresh = await client.post(
        "/api/auth/claim", json={"pairing_token": second, "device_name": "B"}
    )
    assert fresh.status_code == 200
