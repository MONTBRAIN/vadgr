"""The shared async HTTP client: retries, timeouts, logging.

Every provider model call and every OAuth token refresh goes through one
``HttpClient`` so retry/timeout/logging is written once. Tests drive it with
``httpx.MockTransport`` -- no socket -- and an injected no-op sleep so a
back-off never actually waits.
"""

import httpx
import pytest

from engine.http import HttpClient


async def _noop_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_post_returns_response_on_success():
    def handler(request):
        assert request.headers["x-test"] == "1"
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(
        transport=httpx.MockTransport(handler), sleep=_noop_sleep
    )
    resp = await client.post(
        "https://example.test/v1/messages", headers={"x-test": "1"}, json={"a": 1}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    await client.aclose()


@pytest.mark.asyncio
async def test_retries_on_retryable_status_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="try later")
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        max_retries=3,
        sleep=_noop_sleep,
    )
    resp = await client.post("https://example.test/x", json={})
    assert resp.status_code == 200
    assert calls["n"] == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_gives_up_after_max_retries_returning_last_response():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        max_retries=2,
        sleep=_noop_sleep,
    )
    resp = await client.post("https://example.test/x", json={})
    assert resp.status_code == 500
    # initial try + 2 retries
    assert calls["n"] == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_does_not_retry_a_4xx():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(403, text="nope")

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        max_retries=3,
        sleep=_noop_sleep,
    )
    resp = await client.post("https://example.test/x", json={})
    assert resp.status_code == 403
    assert calls["n"] == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_retries_a_transport_error_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        max_retries=2,
        sleep=_noop_sleep,
    )
    resp = await client.post("https://example.test/x", json={})
    assert resp.status_code == 200
    assert calls["n"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_backoff_sleeps_between_retries():
    slept = []

    async def spy_sleep(seconds):
        slept.append(seconds)

    def handler(request):
        return httpx.Response(503)

    client = HttpClient(
        transport=httpx.MockTransport(handler),
        max_retries=2,
        backoff_base=0.5,
        sleep=spy_sleep,
    )
    await client.post("https://example.test/x", json={})
    # one sleep per retry (2), growing
    assert slept == [0.5, 1.0]
    await client.aclose()
