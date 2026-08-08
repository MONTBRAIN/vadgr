"""Unit tests for the auth SRP split: tokens, pairing_store, devices."""

import re
import time

import pytest

from api.auth import tokens
from api.auth.pairing_store import PairingStore
from api.auth.devices import DeviceRepository


# --- tokens.py (pure crypto) ------------------------------------------------


def test_generated_tokens_are_high_entropy_and_unique():
    a, b = tokens.generate_token(), tokens.generate_token()
    assert a != b
    assert len(a) >= 32  # token_urlsafe(32) -> ~43 chars


def test_hash_is_sha256_hex_and_not_plaintext():
    tok = tokens.generate_token()
    h = tokens.hash_token(tok)
    assert h != tok
    assert len(h) == 64
    int(h, 16)  # valid hex


def test_verify_token_constant_time_roundtrip():
    tok = tokens.generate_token()
    assert tokens.verify_token(tok, tokens.hash_token(tok)) is True
    assert tokens.verify_token("wrong", tokens.hash_token(tok)) is False


# --- the pairing code (Crockford base32, typed by a person) -----------------

_GROUPED = re.compile(r"^[0-9ABCDEFGHJKMNPQRSTVWXYZ]{4}-[0-9ABCDEFGHJKMNPQRSTVWXYZ]{4}$")


def test_pairing_code_is_eight_crockford_symbols_grouped_in_fours():
    """Replaces the old "a pairing token is not a device token" test: a code can
    never be mistaken for a device token by shape, which is the stronger claim."""
    assert _GROUPED.match(tokens.generate_pairing_code())


def test_two_pairing_codes_differ():
    assert tokens.generate_pairing_code() != tokens.generate_pairing_code()


def test_the_alphabet_excludes_every_letter_that_reads_as_a_digit():
    for excluded in "ILOU":
        assert excluded not in tokens.CROCKFORD_ALPHABET
    assert len(tokens.CROCKFORD_ALPHABET) == 32  # 8 symbols is exactly 40 bits


def test_normalize_is_identity_on_a_canonical_code_minus_the_grouping():
    assert tokens.normalize_pairing_code("7QK4-M2XD") == "7QK4M2XD"


@pytest.mark.parametrize(
    "typed",
    ["7QK4-M2XD", "7qk4m2xd", "7QK4 M2XD", "7qk4-M2xd", " 7QK4-M2XD "],
)
def test_case_grouping_and_spacing_all_normalise_to_one_code(typed):
    """Forgiveness lives server-side, in one place, so a curl, the CLI and a
    phone keyboard cannot drift into three different answers."""
    assert tokens.normalize_pairing_code(typed) == "7QK4M2XD"


def test_the_documented_confusions_are_mapped():
    assert tokens.normalize_pairing_code("O1IL-0000") == "01110000"


def test_a_typed_u_is_not_a_code():
    """Crockford excludes U from the alphabet without giving it a mapping, so it
    is malformed rather than forgiven."""
    assert tokens.normalize_pairing_code("UUUU-UUUU") is None


@pytest.mark.parametrize("bad", ["7QK4-M2X", "7QK4-M2XDE", "", "!!!!-!!!!", "7QK4M2X"])
def test_wrong_length_or_off_alphabet_is_not_a_code(bad):
    assert tokens.normalize_pairing_code(bad) is None


# --- pairing_store.py (ephemeral, one-time) ---------------------------------


def test_mint_then_consume_once():
    store = PairingStore()
    code, _ = store.mint()
    assert store.consume(code) is True
    # One-time: a replay fails.
    assert store.consume(code) is False


def test_consume_unknown_code_fails():
    assert PairingStore().consume("AAAA-AAAA") is False


def test_expired_pairing_code_is_rejected():
    store = PairingStore(ttl_seconds=0)
    code, _ = store.mint()
    time.sleep(0.01)
    assert store.consume(code) is False


def test_size_is_never_more_than_one():
    """Minting replaces rather than accumulates -- which is what makes "five
    attempts against the code" a countable thing."""
    store = PairingStore()
    assert store.size() == 0
    store.mint()
    store.mint()
    assert store.size() == 1


# --- devices.py (persistent repo) -------------------------------------------


@pytest.mark.asyncio
async def test_device_create_and_lookup_by_hash(db):
    repo = DeviceRepository(db)
    h = tokens.hash_token(tokens.generate_token())
    device = await repo.create("Pixel 8", h)
    assert device["machine_name"] == "Pixel 8"
    found = await repo.find_by_token_hash(h)
    assert found["id"] == device["id"]


@pytest.mark.asyncio
async def test_device_lookup_miss_returns_none(db):
    repo = DeviceRepository(db)
    assert await repo.find_by_token_hash("deadbeef") is None


@pytest.mark.asyncio
async def test_revoked_device_no_longer_authenticates(db):
    repo = DeviceRepository(db)
    h = tokens.hash_token(tokens.generate_token())
    device = await repo.create("Phone", h)
    assert await repo.delete(device["id"]) is True
    assert await repo.find_by_token_hash(h) is None


@pytest.mark.asyncio
async def test_touch_updates_last_seen(db):
    repo = DeviceRepository(db)
    h = tokens.hash_token(tokens.generate_token())
    device = await repo.create("Phone", h)
    await repo.touch(device["id"])
    refreshed = await repo.get(device["id"])
    assert refreshed["last_seen"] is not None
