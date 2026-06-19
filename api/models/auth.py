"""Pairing / claim contract models (the seam mobile codegens from)."""

from pydantic import BaseModel

from .common import StrictBody


class PairResponse(BaseModel):
    """Desktop -> QR. ``host`` is ``transport.advertise_host()``, never 127.0.0.1."""

    host: str
    port: int
    pairing_token: str  # one-time, short-lived
    machine_name: str


class ClaimRequest(StrictBody):
    """Phone -> server. Carries the one-time pairing token."""

    pairing_token: str
    device_name: str


class ClaimResponse(BaseModel):
    """Server -> phone. The persistent token is returned exactly once."""

    token: str  # long-lived persistent token
    device_id: str
