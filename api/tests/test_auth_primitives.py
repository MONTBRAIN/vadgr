"""Unit tests for the auth SRP split: tokens, pairing_store, devices."""

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


def test_pairing_token_distinct_from_persistent_token():
    assert tokens.generate_pairing_token() != tokens.generate_token()


# --- pairing_store.py (ephemeral, one-time) ---------------------------------


def test_mint_then_consume_once():
    store = PairingStore()
    token, _ = store.mint()
    assert store.consume(token) is True
    # One-time: a replay fails.
    assert store.consume(token) is False


def test_consume_unknown_token_fails():
    assert PairingStore().consume("nope") is False


def test_expired_pairing_token_is_rejected():
    store = PairingStore(ttl_seconds=0)
    token, _ = store.mint()
    time.sleep(0.01)
    assert store.consume(token) is False


def test_size_tracks_pending():
    store = PairingStore()
    assert store.size() == 0
    store.mint()
    store.mint()
    assert store.size() == 2


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
