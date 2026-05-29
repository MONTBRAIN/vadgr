"""Default token bootstrap + token hashing helpers.

The default bearer token lives at ~/.config/vadgr/token (chmod 0600).
It's generated on first start. Non-localhost API requests must present
this token (or a paired-device token) via Authorization: Bearer <tok>.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
from pathlib import Path
from typing import Optional


TOKEN_DIR = Path.home() / ".config" / "vadgr"
TOKEN_PATH = TOKEN_DIR / "token"

_lock = threading.Lock()
_cached: Optional[str] = None


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token. Used to store device tokens at rest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def load_or_create_default_token(path: Path = TOKEN_PATH) -> str:
    """Load the default token from disk, creating it (0600) if missing."""
    global _cached
    with _lock:
        if path.exists():
            token = path.read_text(encoding="utf-8").strip()
            if token:
                _cached = token
                return token
        # Create
        path.parent.mkdir(parents=True, exist_ok=True)
        token = _generate_token()
        # Write then chmod (Windows: best-effort).
        path.write_text(token, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _cached = token
        return token


def set_default_token(token: str) -> None:
    """Override the in-memory default token. Used by tests and pairing flows."""
    global _cached
    with _lock:
        _cached = token


def get_default_token() -> Optional[str]:
    """Return the cached default token, or None if not yet bootstrapped."""
    return _cached


def reset_for_tests() -> None:
    global _cached
    with _lock:
        _cached = None
