"""Bind-host resolution for the API server.

Lives in its own module so it can be imported by tests without pulling
in the full CLI (which depends on rich, click, etc.).
"""

from __future__ import annotations

import os


def resolve_bind_host() -> str:
    """Return the host the API server should bind to.

    Default is loopback. Set `VADGR_BIND_TAILSCALE` to a truthy value
    (`1`, `true`, `yes`, `on`) to bind on all interfaces, exposing the
    API on the tailnet interface in addition to localhost. Bearer-token
    auth then guards all non-localhost requests.
    """
    raw = os.environ.get("VADGR_BIND_TAILSCALE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return "0.0.0.0"
    return "127.0.0.1"
