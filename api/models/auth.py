"""Pairing / claim contract models (the seam mobile codegens from)."""

from pydantic import BaseModel

from .common import StrictBody


class PairResponse(BaseModel):
    """Desktop -> QR. ``host`` is ``transport.advertise_host()``, never 127.0.0.1."""

    host: str
    port: int
    # since 0.4.3: an 8-char Crockford base32 code, shown XXXX-XXXX; one-time,
    # 5-min TTL. The field name is the invariant -- only the value changed.
    pairing_token: str
    machine_name: str


class ClaimRequest(StrictBody):
    """Phone -> server. Carries the one-time pairing code, however it was typed
    -- case, hyphens and spaces are normalised server-side."""

    pairing_token: str
    device_name: str


class ClaimResponse(BaseModel):
    """Server -> phone. The persistent token is returned exactly once."""

    token: str  # long-lived persistent token
    device_id: str
