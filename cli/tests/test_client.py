"""`cli/client.py` -- the HTTP layer every command goes through.

Exit codes are the part scripts depend on, so they are asserted here rather
than left to whichever command happened to raise.
"""

import click

from cli.client import DaemonUnreachable


# --- exit codes: down and refused are different problems (E2E 0.4.1 F14) ----


def test_an_unreachable_daemon_exits_3_not_1():
    """`3` is reserved for "the daemon is not reachable" and `1` for "it ran and
    the answer is no".

    Both came back as `1`, so a script could not tell a machine that is off
    from a request that was refused - and the first is worth retrying after a
    `vadgr start` while the second never is.
    """
    assert DaemonUnreachable.exit_code == 3
    assert issubclass(DaemonUnreachable, click.ClickException)


def test_a_refusal_still_exits_1():
    """The fix must not promote ordinary refusals to `3`."""
    assert click.ClickException("nope").exit_code == 1


def test_the_unreachable_message_names_the_url_and_the_remedy():
    """The message is what a human acts on: which address was tried, and what
    to run. A bare "connection refused" leaves both to guesswork."""
    exc = DaemonUnreachable(
        "API is not running at http://127.0.0.1:9999. Start it with: vadgr start"
    )
    assert "127.0.0.1:9999" in exc.format_message()
    assert "vadgr start" in exc.format_message()


# --- a down daemon is answered fast, not after the request timeout ----------


def test_a_closed_port_is_detected_without_waiting_for_the_request_timeout():
    """`_TIMEOUT` is 15s because a request can be doing real work. Deciding
    nothing is listening must not cost that.

    On Linux and macOS the OS refuses a closed local port instantly and this is
    belt-and-braces. On WSL2 it does not - IPv4 loopback to an unbound port is
    swallowed rather than refused, so `vadgr health` against a dead daemon took
    15.2s to say so. Measured at 1.6s after.
    """
    import time
    from cli.client import _port_is_open, _CONNECT_TIMEOUT, _TIMEOUT

    assert _CONNECT_TIMEOUT < _TIMEOUT

    start = time.time()
    assert _port_is_open("127.0.0.1", 9) is False
    elapsed = time.time() - start
    assert elapsed < _TIMEOUT / 2, f"took {elapsed:.1f}s; the point is not to wait"


def test_the_probe_never_invents_a_failure_the_request_would_not_have_hit():
    """It may only make the answer faster, never change it.

    `VADGR_API_URL` can name an `https://` host with no port, where a naive
    `port or 80` would test 80 while the request goes to 443 - reporting a live
    machine as down. And a tailnet host being slow is normal for it, not a
    reason to fail before trying.
    """
    from cli.client import _should_probe

    assert _should_probe("http://127.0.0.1:8791") is True
    assert _should_probe("http://localhost:8791") is True

    assert _should_probe("https://machine.tail1234.ts.net") is False   # no port; 443, not 80
    assert _should_probe("https://machine.tail1234.ts.net:8347") is False  # remote
    assert _should_probe("http://100.64.0.7:8347") is False               # remote
    assert _should_probe("http://127.0.0.1") is False                     # no explicit port


# --- a request with no body sends no body -----------------------------------


def _capture_request(monkeypatch):
    """Capture the urllib Request the client builds, without a daemon."""
    seen = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    def fake_urlopen(req, timeout=None):
        seen["req"] = req
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("cli.client._should_probe", lambda url: False)
    return seen


def test_a_bodyless_post_sends_no_body_at_all(monkeypatch):
    """`vadgr pair` posts to a route that declares no body parameter. Sending
    `{}` anyway leaves bytes unread on the wire, so the server cannot reuse the
    connection and closes it abruptly - which on WSL2 loopback arrives at the
    client as ECONNRESET *after* the response was already produced. The command
    then reports "API is not running" about a daemon that answered 200, and the
    code it minted is lost. Measured at 5-9 failures per 120 `vadgr pair`
    invocations before, 0 per 120 after.
    """
    from cli.client import api_post

    seen = _capture_request(monkeypatch)
    ctx = click.Context(click.Command("x"))
    ctx.obj = {"api_url": "http://127.0.0.1:8000"}
    api_post(ctx, "/api/auth/pair")

    assert seen["req"].data is None
    assert seen["req"].get_header("Content-type") is None
    assert seen["req"].get_method() == "POST"


def test_a_post_with_a_body_still_sends_it(monkeypatch):
    from cli.client import api_post

    seen = _capture_request(monkeypatch)
    ctx = click.Context(click.Command("x"))
    ctx.obj = {"api_url": "http://127.0.0.1:8000"}
    api_post(ctx, "/api/runs", {"task": "a"})

    assert seen["req"].data == b'{"task": "a"}'
    assert seen["req"].get_header("Content-type") == "application/json"


def test_a_delete_sends_no_body(monkeypatch):
    from cli.client import api_delete

    seen = _capture_request(monkeypatch)
    ctx = click.Context(click.Command("x"))
    ctx.obj = {"api_url": "http://127.0.0.1:8000"}
    api_delete(ctx, "/api/devices/abc")

    assert seen["req"].data is None
    assert seen["req"].get_method() == "DELETE"
