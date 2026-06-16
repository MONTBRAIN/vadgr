"""Pluggable transport providers (loopback / tailscale)."""

from .base import TransportProvider
from .loopback import LoopbackTransport
from .tailscale import TailscaleTransport
from .factory import create_transport

__all__ = [
    "TransportProvider",
    "LoopbackTransport",
    "TailscaleTransport",
    "create_transport",
]
