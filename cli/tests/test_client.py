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
