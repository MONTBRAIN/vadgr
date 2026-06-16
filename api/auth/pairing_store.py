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

from api.auth.tokens import generate_pairing_token

PAIRING_TTL_SECONDS = 300  # 5 minutes


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
        token = generate_pairing_token()
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            self._pending[token] = _Pending(token=token, expires_at=expires_at)
        return token, expires_at

    def consume(self, token: str) -> bool:
        """Atomically validate and remove a token. One-time: a second consume
        of the same token returns ``False``. Expired tokens also return
        ``False`` and are swept."""
        now = time.monotonic()
        with self._lock:
            for stale in [t for t, p in self._pending.items() if p.expires_at <= now]:
                self._pending.pop(stale, None)
            pending = self._pending.pop(token, None)
        return pending is not None and pending.expires_at > now

    def size(self) -> int:
        with self._lock:
            return len(self._pending)

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()
