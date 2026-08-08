"""The one outstanding pairing code -- the pair->claim handshake (SRP).

A code is minted by ``POST /api/auth/pair`` and redeemed exactly once by
``POST /api/auth/claim``. It is short-lived and process-local (never
persisted): a machine hands one to a phone via the QR or the owner's eyes, the
phone claims it for a persistent token, and it is consumed.

**One slot, not a dict.** Minting replaces whatever code was outstanding, so at
most one code exists at a time -- which is also what makes "5 attempts against
this code" well defined. A failed guess matches no key, so with several
concurrent codes there would be nothing to charge it against; with exactly one,
a failed claim is unambiguously an attempt on it.
"""

from __future__ import annotations

import hmac
import threading
import time
from dataclasses import dataclass
from enum import Enum

from api.auth.tokens import generate_pairing_code, normalize_pairing_code

PAIRING_TTL_SECONDS = 300  # 5 minutes
PAIRING_MAX_FAILURES = 5   # five failed attempts burn the code


class ClaimResult(Enum):
    """Why a redemption succeeded or failed. `INVALID` covers wrong, malformed,
    unknown, already-used, superseded and burned - all of them are "that code is
    not claimable", and telling them apart would tell a guesser which codes
    exist."""

    OK = "ok"
    INVALID = "invalid"
    EXPIRED = "expired"
    RATE_LIMITED = "rate_limited"  # this attempt hit the cap and burned the code


@dataclass
class _Slot:
    code: str          # normalized 8-char form; process-local, never persisted
    expires_at: float  # monotonic
    failures: int = 0


class PairingStore:
    """Thread-safe, in-memory holder of the single outstanding pairing code."""

    def __init__(self, ttl_seconds: int = PAIRING_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._slot: _Slot | None = None

    def mint(self) -> tuple[str, float]:
        """Mint a code, replacing any outstanding one -- live or expired.

        Returns ``(display_code, expires_at_monotonic)``. The display form is
        the grouped ``XXXX-XXXX`` the route puts on the wire; the slot holds the
        normalized form, because that is what a redemption is compared against.
        """
        display = generate_pairing_code()
        normalized = normalize_pairing_code(display)
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            # Atomic swap under the lock: the previous code stops being
            # claimable at the same instant the new one starts.
            self._slot = _Slot(code=normalized, expires_at=expires_at)
        return display, expires_at

    def consume(self, raw: str) -> bool:
        """Atomically validate and remove a code. One-time: a second consume of
        the same code returns ``False``, as do expired, unknown and burned."""
        return self.redeem(raw) is ClaimResult.OK

    def redeem(self, raw: str) -> "ClaimResult":
        """Same as ``consume``, but says **why** it failed.

        Expired and invalid are different recoveries for the owner: one means
        "ask the machine for a new code", the other means "you typed it wrong".
        A single boolean collapses them, and the phone can then only offer one
        of the two.
        """
        now = time.monotonic()
        norm = normalize_pairing_code(raw)
        with self._lock:
            slot = self._slot
            if norm is None or slot is None:
                # Malformed input never reaches the counter, so garbage cannot
                # burn a code -- only eight well-formed wrong characters can.
                return ClaimResult.INVALID
            matches = hmac.compare_digest(norm, slot.code)
            if slot.expires_at <= now:
                # The slot is held until it is minted over, so the RIGHT code
                # typed late still answers EXPIRED - "ask for a new one" -
                # instead of decaying into unknown.
                if matches:
                    self._slot = None
                    return ClaimResult.EXPIRED
                return ClaimResult.INVALID  # a wrong guess at a dead code counts for nothing
            if matches:
                self._slot = None  # single-use, even on the fifth try
                return ClaimResult.OK
            slot.failures += 1
            if slot.failures >= PAIRING_MAX_FAILURES:
                self._slot = None  # burned; the true code is now dead too
                return ClaimResult.RATE_LIMITED
            return ClaimResult.INVALID

    def size(self) -> int:
        """0 or 1 -- at most one code is ever outstanding."""
        with self._lock:
            return 0 if self._slot is None else 1

    def clear(self) -> None:
        with self._lock:
            self._slot = None
