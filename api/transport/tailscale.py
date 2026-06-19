"""Tailscale transport -- exposes the API over the tailnet only.

Reachability + peer identity come from the Tailscale **LocalAPI** (the
``tailscaled`` unix socket), preferred over shelling out to
``tailscale status --json``. The LocalAPI client is injected so the adapter
is unit-testable with a fake WhoIs / status (no live tailnet needed).

Authorization is structural-and-checked: bind only to the node's 100.x
interface (so non-tailnet peers can't even connect at the socket level),
and additionally verify each peer is a tailnet member via WhoIs, falling
back to the 100.64.0.0/10 CGNAT range when WhoIs is unavailable.
"""

from __future__ import annotations

import ipaddress
from typing import Optional, Protocol


# Tailscale assigns node addresses from the CGNAT range 100.64.0.0/10.
_TAILNET_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class LocalAPI(Protocol):
    """The slice of the Tailscale LocalAPI this adapter needs."""

    def status(self) -> Optional[dict]:
        """Parsed ``tailscaled`` status, or None when unavailable/logged out."""
        ...

    def whois(self, peer_ip: str) -> Optional[dict]:
        """Identity of a peer by IP, or None if not a tailnet member."""
        ...


class TailscaleTransport:
    name = "tailscale"

    def __init__(self, local_api: LocalAPI):
        self._api = local_api

    def _self_ip(self) -> Optional[str]:
        status = self._api.status()
        if not status:
            return None
        self_node = status.get("Self") or {}
        ips = self_node.get("TailscaleIPs") or []
        for ip in ips:
            try:
                if ipaddress.ip_address(ip).version == 4:
                    return ip
            except ValueError:
                continue
        return ips[0] if ips else None

    def _magic_dns(self) -> Optional[str]:
        status = self._api.status()
        if not status:
            return None
        self_node = status.get("Self") or {}
        dns = self_node.get("DNSName")
        if dns:
            return dns.rstrip(".")
        return None

    def bind_host(self) -> str:
        """The node's 100.x address. Raises if the transport is unavailable --
        callers must check ``is_available()`` first."""
        ip = self._self_ip()
        if not ip:
            raise RuntimeError(
                "Tailscale transport unavailable: tailscaled not running or logged out."
            )
        return ip

    def advertise_host(self) -> Optional[str]:
        if not self.is_available():
            return None
        return self._magic_dns() or self._self_ip()

    def is_available(self) -> bool:
        status = self._api.status()
        if not status:
            return False
        # BackendState == "Running" means up + logged in.
        if status.get("BackendState") not in (None, "Running"):
            return False
        return self._self_ip() is not None

    def is_authorized_source(self, peer_ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(peer_ip)
        except ValueError:
            return False
        # Prefer an authoritative WhoIs identity check.
        try:
            who = self._api.whois(peer_ip)
        except Exception:
            who = None
        if who is not None:
            return True
        # Fall back to the CGNAT range when WhoIs is unavailable.
        return addr in _TAILNET_CGNAT

    def status(self) -> dict:
        available = self.is_available()
        return {
            "name": self.name,
            "available": available,
            "advertise_host": self.advertise_host() if available else None,
            "bind_host": self._self_ip(),
        }
