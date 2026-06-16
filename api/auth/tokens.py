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
# Pairing tokens are short-lived and one-time, so a slightly smaller secret
# is fine, but we keep them strong anyway.
_PAIRING_ENTROPY_BYTES = 24


def generate_token() -> str:
    """A new persistent bearer token (opaque, high-entropy)."""
    return secrets.token_urlsafe(_TOKEN_ENTROPY_BYTES)


def generate_pairing_token() -> str:
    """A new one-time, short-lived pairing token."""
    return secrets.token_urlsafe(_PAIRING_ENTROPY_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 hex digest -- what we store at rest, never the plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """Constant-time check that ``token`` hashes to ``token_hash``."""
    return hmac.compare_digest(hash_token(token), token_hash)
