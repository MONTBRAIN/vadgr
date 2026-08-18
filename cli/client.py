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
    # No body means no body. Sending `{}` to a route that declares no body
    # parameter leaves it unread on the wire, and the server must then close the
    # connection abruptly rather than reuse it -- which on WSL2 loopback races
    # the client's read and arrives as ECONNRESET *after* the request was
    # served. `vadgr pair` lost roughly one code in twenty that way, reporting
    # "API is not running" about a daemon that had already answered 200.
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"

    # Cheap reachability probe before the request, so a down daemon is answered
    # in milliseconds rather than after the request timeout. Loopback only, on
    # purpose - see `_should_probe`.
    if _should_probe(_base_url(ctx)):
        parsed = urllib.parse.urlparse(_base_url(ctx))
        if not _port_is_open(parsed.hostname, parsed.port):
            raise DaemonUnreachable(
                f"API is not running at {_base_url(ctx)}. Start it with: vadgr start"
            )

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as resp:
            body = resp.read()
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as e:
        code = None
        details = {}
        try:
            body = json.loads(e.read())
            # API returns {"error": {"message": "..."}} or {"detail": "..."}
            if "error" in body and isinstance(body["error"], dict):
                detail = body["error"].get("message", e.reason)
                code = body["error"].get("code")
                details = body["error"].get("details") or {}
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
        raise ApiClientError(f"{detail}", status=e.code, code=code, details=details) from None
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


class ApiClientError(click.ClickException):
    """A structured daemon error that commands can recover from by code."""

    def __init__(self, message: str, *, status: int, code: str | None,
                 details: dict):
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


def api_get(ctx: click.Context, path: str) -> dict | list:
    return _request(ctx, "GET", path)


def api_post(ctx: click.Context, path: str, body: dict | None = None,
             timeout: int | None = None) -> dict | list:
    return _request(ctx, "POST", path, body, timeout=timeout)


def api_put(ctx: click.Context, path: str, body: dict | None = None,
            timeout: int | None = None) -> dict | list:
    return _request(ctx, "PUT", path, body, timeout=timeout)


def api_delete(ctx: click.Context, path: str) -> dict | list:
    return _request(ctx, "DELETE", path)


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _should_probe(base_url: str) -> bool:
    """Whether the pre-request reachability probe applies to this URL.

    **Loopback with an explicit port, and nothing else.** The probe exists for
    the local daemon, and it is only ever allowed to make the answer *faster* -
    never to invent a failure the request itself would not have hit.

    Two ways a broader probe would do exactly that. `--api-url`/`FORGE_API_URL`
    can point at an `https://` host with no port, where `port or 80` would test
    80 while the request goes to 443 and report a live machine as down. And a
    remote host over a tailnet can be reachable-but-slow, which is a normal
    state for it and not one to fail early on.
    """
    parsed = urllib.parse.urlparse(base_url)
    return bool(parsed.port) and parsed.hostname in _LOOPBACK_HOSTS


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
