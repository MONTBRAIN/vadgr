"""In-memory pairing token store.

Pairing tokens are one-time-use, short-lived secrets that a desktop
operator hands to a mobile device (typically by displaying a QR code).
The mobile device redeems the pairing token via POST /api/auth/claim,
receiving back a long-lived bearer token tied to a row in the
`devices` table.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional


PAIRING_TTL_SECONDS = 300  # 5 minutes


@dataclass
class _PendingPair:
    token: str
    expires_at: float


class PairingStore:
    """Thread-safe pairing-token store. Process-local; not persisted."""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: dict[str, _PendingPair] = {}

    def mint(self) -> tuple[str, float]:
        token = secrets.token_urlsafe(24)
        expires_at = time.monotonic() + PAIRING_TTL_SECONDS
        with self._lock:
            self._pending[token] = _PendingPair(token=token, expires_at=expires_at)
        return token, expires_at

    def consume(self, token: str) -> bool:
        """Atomically validate + remove a pairing token. Returns True on success."""
        now = time.monotonic()
        with self._lock:
            # Drop expired tokens lazily
            expired = [t for t, p in self._pending.items() if p.expires_at <= now]
            for t in expired:
                self._pending.pop(t, None)
            pending = self._pending.pop(token, None)
        if pending is None:
            return False
        if pending.expires_at <= now:
            return False
        return True

    def clear(self) -> None:
        with self._lock:
            self._pending.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._pending)
