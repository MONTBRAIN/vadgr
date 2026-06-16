"""Transport selection. ``VADGR_TRANSPORT`` picks the adapter (loopback default)."""

from __future__ import annotations

import json
import os
import socket
from typing import Optional

from .base import TransportProvider
from .loopback import LoopbackTransport
from .tailscale import TailscaleTransport


# Default unix socket for the Tailscale LocalAPI on Linux/macOS.
_TAILSCALED_SOCKET = os.environ.get(
    "VADGR_TAILSCALED_SOCKET", "/var/run/tailscale/tailscaled.sock"
)


class TailscaledLocalAPI:
    """Talks to the ``tailscaled`` LocalAPI over its unix socket.

    HTTP-over-unix: the socket speaks HTTP/1.1; the Host header is a fixed
    sentinel (``local-tailscaled.sock``) per Tailscale's convention.
    """

    def __init__(self, socket_path: str = _TAILSCALED_SOCKET):
        self._socket_path = socket_path

    def _get(self, path: str) -> Optional[dict]:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect(self._socket_path)
                req = (
                    f"GET {path} HTTP/1.1\r\n"
                    "Host: local-tailscaled.sock\r\n"
                    "Connection: close\r\n\r\n"
                )
                sock.sendall(req.encode("ascii"))
                chunks = []
                while True:
                    data = sock.recv(65536)
                    if not data:
                        break
                    chunks.append(data)
        except (OSError, socket.timeout):
            return None
        raw = b"".join(chunks)
        sep = raw.find(b"\r\n\r\n")
        if sep == -1:
            return None
        head, body = raw[:sep], raw[sep + 4 :]
        status_line = head.split(b"\r\n", 1)[0]
        if b" 200 " not in status_line:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def status(self) -> Optional[dict]:
        return self._get("/localapi/v0/status")

    def whois(self, peer_ip: str) -> Optional[dict]:
        return self._get(f"/localapi/v0/whois?addr={peer_ip}")


def create_transport(name: Optional[str] = None) -> TransportProvider:
    """Build the configured transport. ``name`` overrides ``VADGR_TRANSPORT``."""
    selected = (name or os.environ.get("VADGR_TRANSPORT", "loopback")).strip().lower()
    if selected == "tailscale":
        return TailscaleTransport(local_api=TailscaledLocalAPI())
    if selected == "loopback":
        return LoopbackTransport()
    raise ValueError(
        f"Unknown VADGR_TRANSPORT={selected!r}. Expected 'loopback' or 'tailscale'."
    )
