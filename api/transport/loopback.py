"""Loopback transport -- the dev / single-machine default.

Binds to 127.0.0.1 and authorizes only loopback peers. It deliberately
cannot advertise a host: there is no address a remote phone could reach,
so ``advertise_host()`` returns ``None`` and the pair endpoint refuses
rather than handing out a useless localhost QR.
"""

from __future__ import annotations

import ipaddress
from typing import Optional


class LoopbackTransport:
    name = "loopback"

    def bind_host(self) -> str:
        return "127.0.0.1"

    def advertise_host(self) -> Optional[str]:
        return None

    def is_available(self) -> bool:
        return True

    def is_authorized_source(self, peer_ip: str) -> bool:
        try:
            return ipaddress.ip_address(peer_ip) in ipaddress.ip_network("127.0.0.0/8")
        except ValueError:
            return False

    def status(self) -> dict:
        return {
            "name": self.name,
            "available": True,
            "advertise_host": None,
            "bind_host": self.bind_host(),
        }
