"""HTTP client for the Agent Forge API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import click

_TIMEOUT = 15


def _base_url(ctx: click.Context) -> str:
    return ctx.obj["api_url"]


def _request(ctx: click.Context, method: str, path: str, body: dict | None = None) -> dict | list:
    url = f"{_base_url(ctx)}{path}"
    data = json.dumps(body).encode() if body is not None else b"{}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    req = urllib.request.Request(url, data=data if method != "GET" else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read()
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", e.reason)
        except Exception:
            detail = e.reason
        raise click.ClickException(f"{detail} (HTTP {e.code})") from None
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        raise click.ClickException(
            f"API is not running at {_base_url(ctx)}. Start it with: forge start"
        ) from None


def api_get(ctx: click.Context, path: str) -> dict | list:
    return _request(ctx, "GET", path)


def api_post(ctx: click.Context, path: str, body: dict | None = None) -> dict | list:
    return _request(ctx, "POST", path, body or {})


def api_put(ctx: click.Context, path: str, body: dict | None = None) -> dict | list:
    return _request(ctx, "PUT", path, body or {})


def api_delete(ctx: click.Context, path: str) -> dict | list:
    return _request(ctx, "DELETE", path)


def is_api_running(ctx: click.Context) -> bool:
    try:
        api_get(ctx, "/api/health")
        return True
    except click.ClickException:
        return False
