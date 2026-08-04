"""Ephemeral one-time pairing tokens -- the pair->claim handshake (SRP).

Pairing tokens are minted by ``POST /api/auth/pair`` and redeemed exactly
once by ``POST /api/auth/claim``. They are short-lived and process-local
(never persisted): a desktop hands one to a phone via the QR, the phone
claims it for a persistent token, and it is consumed. Expired tokens are
swept lazily on access.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum

from api.auth.tokens import generate_pairing_token

PAIRING_TTL_SECONDS = 300  # 5 minutes


class ClaimResult(Enum):
    """Why a redemption succeeded or failed. `INVALID` covers wrong, unknown
    and already-used - all three are "that code is not claimable" and telling
    them apart would tell a guesser which codes exist."""

    OK = "ok"
    INVALID = "invalid"
    EXPIRED = "expired"


@dataclass
class _Pending:
    token: str
    expires_at: float


class PairingStore:
    """Thread-safe, in-memory store of unredeemed pairing tokens."""

    def __init__(self, ttl_seconds: int = PAIRING_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._pending: dict[str, _Pending] = {}

    def mint(self) -> tuple[str, float]:
        """Create a pairing token. Returns ``(token, expires_at_monotonic)``."""
        now = time.monotonic()
        token = generate_pairing_token()
        expires_at = now + self._ttl
        with self._lock:
            # Swept here rather than on redeem. The store only grows when a code
            # is minted, and sweeping on lookup destroyed the evidence that
            # another code had expired - it became simply unknown, which is the
            # wrong thing to tell the owner.
            for stale in [t for t, p in self._pending.items() if p.expires_at <= now]:
                self._pending.pop(stale, None)
            self._pending[token] = _Pending(token=token, expires_at=expires_at)
        return token, expires_at

    def consume(self, token: str) -> bool:
        """Atomically validate and remove a token. One-time: a second consume
        of the same token returns ``False``. Expired tokens also return
        ``False`` and are swept."""
        return self.redeem(token) is ClaimResult.OK

    def redeem(self, token: str) -> "ClaimResult":
        """Same as ``consume``, but says **why** it failed.

        Expired and invalid are different answers to the owner: one means "ask
        the machine for a new code", the other means "you typed it wrong". A
        single boolean collapses them, and the phone can only offer one of the
        two recoveries. The sweep runs after the lookup for the same reason -
        purging first turns every expired token into an unknown one.
        """
        now = time.monotonic()
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            return ClaimResult.INVALID
        if pending.expires_at <= now:
            return ClaimResult.EXPIRED
        return ClaimResult.OK

    def size(self) -> int:
        with self._lock:
            return len(self._pending)

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()
