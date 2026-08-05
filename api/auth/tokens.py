"""Token primitives -- pure crypto, no I/O (SRP).

Tokens are opaque, high-entropy random strings. Only their SHA-256 hash is
ever stored. Verification is constant-time. Nothing here touches disk, the
network, or a database -- swapping the hash or entropy touches only this file.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# 32 bytes of entropy -> ~43 url-safe chars. Comfortably beyond brute force.
_TOKEN_ENTROPY_BYTES = 32

# Crockford base32: digits 0-9 plus the alphabet minus I, L, O and U. 32
# symbols, so 8 of them is 40 bits by construction. The exclusions are the
# whole point -- a person reads this off a terminal and types it on a phone,
# and 0/O and 1/I/L are where that goes wrong.
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Crockford's documented decode confusions. U is excluded from the alphabet
# but is NOT a confusable: a typed U is simply not a code.
_CONFUSABLES = str.maketrans({"O": "0", "I": "1", "L": "1"})


def generate_token() -> str:
    """A new persistent bearer token (opaque, high-entropy)."""
    return secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)


def generate_pairing_code() -> str:
    """An 8-character Crockford base32 pairing code, in its canonical grouped
    form ``XXXX-XXXX``.

    40 bits of entropy: ``secrets.choice`` picks each of the 8 symbols
    uniformly from the 32-symbol alphabet. Choosing symbols directly rather
    than encoding random bytes means there is no modulo bias to reason about.
    """
    raw = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_pairing_code(raw: str) -> str | None:
    """The ungrouped 8-character form of whatever a person typed, or ``None``.

    Uppercases, drops hyphens and spaces, and maps the Crockford confusions
    (O->0, I/L->1). Returns ``None`` when the result is not exactly 8
    characters of the alphabet -- malformed and unknown deliberately share one
    verdict downstream, so a guesser learns nothing from the difference.

    Normalising server-side rather than in each client is what makes the
    forgiveness identical everywhere: the CLI, the QR and a phone keyboard all
    get the same answer for the same intent.
    """
    if not isinstance(raw, str):
        return None
    candidate = raw.upper().replace("-", "").replace(" ", "").translate(_CONFUSABLES)
    if len(candidate) != 8:
        return None
    if any(ch not in CROCKFORD_ALPHABET for ch in candidate):
        return None
    return candidate


def hash_token(token: str) -> str:
    """SHA-256 hex digest -- what we store at rest, never the plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """Constant-time check that ``token`` hashes to ``token_hash``."""
    return hmac.compare_digest(hash_token(token), token_hash)
