"""The transport port -- the only abstraction routes/middleware depend on."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class TransportProvider(Protocol):
    """Pluggable network transport. Adapters honour the contract table in
    ``design/vadgr/0.3.0/transport.md`` so callers never branch on the concrete
    type -- they depend only on this protocol (DIP)."""

    name: str

    def bind_host(self) -> str:
        """Interface uvicorn binds to. The transport's own address -- NEVER
        0.0.0.0. (Loopback: '127.0.0.1'; Tailscale: the node's 100.x IP.)"""
        ...

    def advertise_host(self) -> Optional[str]:
        """Address to embed in the pairing QR (reachable by the phone). The
        tailnet MagicDNS name / 100.x IP. ``None`` when the transport can't be
        paired to remotely (loopback, or tailscale down) -- the pair endpoint
        then refuses instead of advertising localhost."""
        ...

    def is_available(self) -> bool:
        """Transport up and ready (e.g. tailscaled running + logged in)."""
        ...

    def is_authorized_source(self, peer_ip: str) -> bool:
        """Gate 1: is this connection from an allowed peer?"""
        ...

    def status(self) -> dict:
        """Diagnostics for GET /api/health."""
        ...
