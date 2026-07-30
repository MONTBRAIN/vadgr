"""Auth strategies: OAuth (token cache + refresh + per-OS store), API-key, none.

The OAuth path is driven with ``httpx.MockTransport`` (via ``HttpClient``) and a
frozen clock so the refresh window is deterministic. Per-OS credential
resolution is asserted by branch: Linux/Windows/WSL read+write the file (WSL
uses the *Linux-side* home, never ``/mnt/c``); macOS goes through a Keychain
backend, not a file.
"""

import json
import os
import time

import httpx
import pytest

from engine.auth.api_key import APIKeyStrategy
from engine.auth.none import NoAuthStrategy
from engine.auth.oauth import (
    CredentialsMissingError,
    OAuthStrategy,
    resolve_token_store,
    FileTokenStore,
    KeychainTokenStore,
)
from engine.http import HttpClient


REFRESH_URL = "https://platform.claude.com/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


def _write_creds(path, *, access="acc-old", refresh="ref-old", expires_at_ms=None):
    if expires_at_ms is None:
        expires_at_ms = int(time.time() * 1000) + 3_600_000
    path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": access,
                    "refreshToken": refresh,
                    "expiresAt": expires_at_ms,
                    "scopes": ["user:inference"],
                    "subscriptionType": "max",
                }
            }
        )
    )


def _refresh_transport(new_access="acc-new", new_refresh="ref-new", expires_in=3600):
    def handler(request):
        body = json.loads(request.content)
        assert body["grant_type"] == "refresh_token"
        assert body["client_id"] == CLIENT_ID
        return httpx.Response(
            200,
            json={
                "access_token": new_access,
                "refresh_token": new_refresh,
                "expires_in": expires_in,
            },
        )

    return httpx.MockTransport(handler)


# ---- API-key + no-auth -----------------------------------------------------

@pytest.mark.asyncio
async def test_api_key_injects_header_from_env(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "sk-test-123")
    strat = APIKeyStrategy(env_var="MY_API_KEY", header="x-api-key")
    request = {"headers": {}}
    await strat.inject_headers(request)
    assert request["headers"]["x-api-key"] == "sk-test-123"


@pytest.mark.asyncio
async def test_api_key_bearer_scheme(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "sk-test-123")
    strat = APIKeyStrategy(env_var="MY_API_KEY", header="Authorization", scheme="Bearer")
    request = {"headers": {}}
    await strat.inject_headers(request)
    assert request["headers"]["Authorization"] == "Bearer sk-test-123"


@pytest.mark.asyncio
async def test_api_key_missing_env_raises(monkeypatch):
    monkeypatch.delenv("MY_API_KEY", raising=False)
    strat = APIKeyStrategy(env_var="MY_API_KEY")
    with pytest.raises(RuntimeError):
        await strat.inject_headers({"headers": {}})


@pytest.mark.asyncio
async def test_api_key_401_is_terminal(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "x")
    strat = APIKeyStrategy(env_var="MY_API_KEY")
    assert await strat.handle_401(object()) is False


@pytest.mark.asyncio
async def test_no_auth_is_noop_and_terminal():
    strat = NoAuthStrategy()
    request = {"headers": {"keep": "me"}}
    await strat.inject_headers(request)
    assert request["headers"] == {"keep": "me"}
    assert await strat.handle_401(object()) is False


# ---- OAuth: inject, refresh window, 401 ------------------------------------

@pytest.mark.asyncio
async def test_inject_headers_uses_cached_token_when_fresh(tmp_path):
    creds = tmp_path / ".credentials.json"
    _write_creds(creds, access="acc-fresh")
    strat = OAuthStrategy(
        credentials_path=str(creds),
        refresh_url=REFRESH_URL,
        client_id=CLIENT_ID,
        os_name="Linux",
        now=lambda: int(time.time() * 1000),
    )
    request = {"headers": {}}
    await strat.inject_headers(request)
    assert request["headers"]["Authorization"] == "Bearer acc-fresh"


@pytest.mark.asyncio
async def test_refresh_when_within_window_writes_back_to_file(tmp_path):
    creds = tmp_path / ".credentials.json"
    # expires in 60s -> inside the 5-minute refresh window
    now_ms = 1_000_000_000_000
    _write_creds(creds, access="acc-old", refresh="ref-old", expires_at_ms=now_ms + 60_000)

    http = HttpClient(transport=_refresh_transport("acc-new", "ref-new", 3600))
    strat = OAuthStrategy(
        credentials_path=str(creds),
        refresh_url=REFRESH_URL,
        client_id=CLIENT_ID,
        os_name="Linux",
        http=http,
        now=lambda: now_ms,
    )
    request = {"headers": {}}
    await strat.inject_headers(request)

    assert request["headers"]["Authorization"] == "Bearer acc-new"
    # The new token was written back to the credentials file.
    on_disk = json.loads(creds.read_text())["claudeAiOauth"]
    assert on_disk["accessToken"] == "acc-new"
    assert on_disk["refreshToken"] == "ref-new"
    assert on_disk["expiresAt"] == now_ms + 3600 * 1000
    await http.aclose()


@pytest.mark.asyncio
async def test_missing_credentials_file_raises_setup_token_error(tmp_path):
    strat = OAuthStrategy(
        credentials_path=str(tmp_path / "nope.json"),
        refresh_url=REFRESH_URL,
        client_id=CLIENT_ID,
        os_name="Linux",
    )
    with pytest.raises(CredentialsMissingError) as ei:
        await strat.ensure_ready()
    assert "setup-token" in str(ei.value)


@pytest.mark.asyncio
async def test_handle_401_drops_token_refreshes_and_signals_retry(tmp_path):
    creds = tmp_path / ".credentials.json"
    now_ms = 1_000_000_000_000
    _write_creds(creds, access="acc-old", refresh="ref-old", expires_at_ms=now_ms + 3_600_000)
    http = HttpClient(transport=_refresh_transport("acc-after-401", "ref-2", 3600))
    strat = OAuthStrategy(
        credentials_path=str(creds),
        refresh_url=REFRESH_URL,
        client_id=CLIENT_ID,
        os_name="Linux",
        http=http,
        now=lambda: now_ms,
    )
    # prime the cache with the old (rejected) token
    req = {"headers": {}}
    await strat.inject_headers(req)
    assert req["headers"]["Authorization"] == "Bearer acc-old"

    retry = await strat.handle_401(httpx.Response(401))
    assert retry is True

    req2 = {"headers": {}}
    await strat.inject_headers(req2)
    assert req2["headers"]["Authorization"] == "Bearer acc-after-401"
    await http.aclose()


@pytest.mark.asyncio
async def test_handle_401_terminal_when_refresh_fails(tmp_path):
    creds = tmp_path / ".credentials.json"
    now_ms = 1_000_000_000_000
    _write_creds(creds, expires_at_ms=now_ms + 3_600_000)

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    http = HttpClient(transport=httpx.MockTransport(handler))
    strat = OAuthStrategy(
        credentials_path=str(creds),
        refresh_url=REFRESH_URL,
        client_id=CLIENT_ID,
        os_name="Linux",
        http=http,
        now=lambda: now_ms,
    )
    await strat.inject_headers({"headers": {}})
    assert await strat.handle_401(httpx.Response(401)) is False
    await http.aclose()


# ---- Per-OS credential resolution ------------------------------------------

def test_linux_windows_wsl_resolve_to_the_file_store(tmp_path):
    for os_name in ("Linux", "Windows"):
        store = resolve_token_store(os_name, str(tmp_path / ".credentials.json"))
        assert isinstance(store, FileTokenStore)


def test_wsl_uses_linux_side_home_not_mnt_c(monkeypatch, tmp_path):
    # On WSL, ``~`` expands to the Linux home -- never a /mnt/c Windows path.
    linux_home = tmp_path / "home" / "santiago"
    linux_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(linux_home))
    store = resolve_token_store("Linux", "~/.claude/.credentials.json")
    assert isinstance(store, FileTokenStore)
    assert "/mnt/c" not in store.path
    assert str(linux_home) in store.path


def test_macos_resolves_to_the_keychain_store():
    store = resolve_token_store("Darwin", "~/.claude/.credentials.json")
    assert isinstance(store, KeychainTokenStore)


@pytest.mark.asyncio
async def test_macos_keychain_backend_reads_and_writes_back(tmp_path):
    # A fake Keychain: load returns a JSON blob; save records the write-back.
    now_ms = 1_000_000_000_000
    saved = {}
    keychain_blob = {
        "claudeAiOauth": {
            "accessToken": "kc-old",
            "refreshToken": "kc-ref",
            "expiresAt": now_ms + 60_000,
        }
    }

    class FakeKeychain:
        def load(self):
            return keychain_blob["claudeAiOauth"]

        def save(self, block):
            saved.update(block)

    http = HttpClient(transport=_refresh_transport("kc-new", "kc-ref2", 3600))
    strat = OAuthStrategy(
        credentials_path="~/.claude/.credentials.json",
        refresh_url=REFRESH_URL,
        client_id=CLIENT_ID,
        os_name="Darwin",
        store=FakeKeychain(),
        http=http,
        now=lambda: now_ms,
    )
    request = {"headers": {}}
    await strat.inject_headers(request)
    # Refreshed through the Keychain backend (within window), written back there.
    assert request["headers"]["Authorization"] == "Bearer kc-new"
    assert saved["accessToken"] == "kc-new"
    await http.aclose()
