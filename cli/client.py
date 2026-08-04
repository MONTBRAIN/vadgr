"""HTTP client for the Vadgr API."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request

import click

_TIMEOUT = 15
_LONG_TIMEOUT = 120

# A local daemon is either listening or it is not; there is no slow-but-fine
# case for the connect itself. Kept short and separate from `_TIMEOUT`, which
# has to stay generous because a request can be doing real work.
_CONNECT_TIMEOUT = 1.5


def _base_url(ctx: click.Context) -> str:
    return ctx.obj["api_url"]


def _request(ctx: click.Context, method: str, path: str, body: dict | None = None,
             timeout: int | None = None) -> dict | list:
    url = f"{_base_url(ctx)}{path}"
    data = json.dumps(body).encode() if body is not None else b"{}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    # Cheap reachability probe before the request, so a down daemon is answered
    # in milliseconds rather than after the request timeout. See `_port_is_open`
    # for why the OS does not always do this for us.
    parsed = urllib.parse.urlparse(_base_url(ctx))
    if parsed.hostname and not _port_is_open(parsed.hostname, parsed.port or 80):
        raise DaemonUnreachable(
            f"API is not running at {_base_url(ctx)}. Start it with: vadgr start"
        )

    req = urllib.request.Request(url, data=data if method != "GET" else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as resp:
            body = resp.read()
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
            # API returns {"error": {"message": "..."}} or {"detail": "..."}
            if "error" in body and isinstance(body["error"], dict):
                detail = body["error"].get("message", e.reason)
            else:
                raw_detail = body.get("detail", e.reason)
                if isinstance(raw_detail, list):
                    # Pydantic 422 validation errors -- extract human-readable messages
                    msgs = []
                    for err in raw_detail:
                        loc = " -> ".join(str(p) for p in err.get("loc", []) if p != "body")
                        msg = err.get("msg", "")
                        msgs.append(f"{loc}: {msg}" if loc else msg)
                    detail = "; ".join(msgs)
                else:
                    detail = raw_detail
        except Exception:
            detail = e.reason
        raise click.ClickException(f"{detail}") from None
    except socket.timeout:
        raise click.ClickException(
            f"Request timed out ({url}). The operation may still be running."
        ) from None
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        raise DaemonUnreachable(
            f"API is not running at {_base_url(ctx)}. Start it with: vadgr start"
        ) from None


class DaemonUnreachable(click.ClickException):
    """The daemon could not be reached.

    Its own exit code, because "it is down" and "it ran and said no" are
    different problems and a script has to branch on them: the first is retried
    after a start, the second never is. `ClickException` exits `1`, which
    collapses them.
    """

    exit_code = 3


def api_get(ctx: click.Context, path: str) -> dict | list:
    return _request(ctx, "GET", path)


def api_post(ctx: click.Context, path: str, body: dict | None = None) -> dict | list:
    return _request(ctx, "POST", path, body or {})


def api_put(ctx: click.Context, path: str, body: dict | None = None,
            timeout: int | None = None) -> dict | list:
    return _request(ctx, "PUT", path, body or {}, timeout=timeout)


def api_delete(ctx: click.Context, path: str) -> dict | list:
    return _request(ctx, "DELETE", path)


def _port_is_open(host: str, port: int) -> bool:
    """Whether anything is listening, answered in milliseconds.

    On Linux and macOS a closed local port is refused instantly and this is
    redundant. **On WSL2 it is not**: IPv4 loopback to a port nothing listens on
    is swallowed rather than refused, so the connect runs to the full timeout -
    measured at 15s for `vadgr health` against a dead daemon, where `::1`
    refuses the same port in under a millisecond. WSL2 is a platform this
    daemon claims, and "your daemon is down" should not take fifteen seconds to
    say on it.
    """
    import socket

    try:
        with socket.create_connection((host, port), timeout=_CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def is_api_running(ctx: click.Context) -> bool:
    try:
        api_get(ctx, "/api/health")
        return True
    except click.ClickException:
        return False
