"""Security layer for the gateway.

Handles authentication, rate limiting, input sanitization,
and audit logging for all inbound messages.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from gateway.models import InboundMessage

logger = logging.getLogger(__name__)

# Characters that could enable shell injection via agent inputs
_DANGEROUS_CHARS = re.compile(r"[;&|`$(){}]")

# Max message length to prevent prompt injection via massive payloads
_MAX_MESSAGE_LENGTH = 2000

# Default rate limit: 10 commands per hour per user
_DEFAULT_RATE_LIMIT = 10
_DEFAULT_RATE_WINDOW = 3600  # seconds


class _SilentReject:
    """Sentinel returned by SecurityGuard.check() when a sender is not in the allowlist."""

    def __repr__(self) -> str:
        return "SILENT_REJECT"


SILENT_REJECT = _SilentReject()


@dataclass
class SecurityConfig:
    """Security configuration for the gateway."""

    allowed_senders: list[str] = field(default_factory=list)
    rate_limit: int = _DEFAULT_RATE_LIMIT
    rate_window: int = _DEFAULT_RATE_WINDOW
    audit_log_path: str | None = None


class SecurityGuard:
    """Validates inbound messages before they reach the router."""

    def __init__(self, config: SecurityConfig):
        self._config = config
        self._rate_buckets: dict[str, list[float]] = {}
        self._audit_log = None
        if config.audit_log_path:
            path = Path(config.audit_log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._audit_log = path

    def check(self, message: InboundMessage) -> str | _SilentReject | None:
        """Validate a message. Returns an error string if rejected, SILENT_REJECT if silently rejected, None if OK."""
        self._audit(message)

        # 1. Sender allowlist
        if self._config.allowed_senders:
            if message.sender_id not in self._config.allowed_senders:
                logger.warning(
                    "Rejected message from unknown sender: %s (%s)",
                    message.sender_id,
                    message.sender_name,
                )
                return SILENT_REJECT  # Silent reject -- don't reveal bot exists to strangers

        # 2. Rate limiting
        if self._is_rate_limited(message.sender_id):
            logger.warning("Rate limited sender: %s", message.sender_id)
            return "Slow down! Too many commands. Try again in a few minutes."

        # 3. Message length
        if len(message.text) > _MAX_MESSAGE_LENGTH:
            return f"Message too long (max {_MAX_MESSAGE_LENGTH} chars)."

        # 4. Input sanitization (warn but don't block -- the router handles escaping)
        if _DANGEROUS_CHARS.search(message.text):
            logger.warning(
                "Message from %s contains shell-sensitive chars: %s",
                message.sender_id,
                message.text[:100],
            )

        return None

    def sanitize_input(self, value: str) -> str:
        """Remove dangerous characters from a value before passing to agent inputs."""
        return _DANGEROUS_CHARS.sub("", value).strip()

    def _is_rate_limited(self, sender_id: str) -> bool:
        now = time.monotonic()
        window = self._config.rate_window
        limit = self._config.rate_limit

        bucket = self._rate_buckets.setdefault(sender_id, [])
        # Prune old entries
        bucket[:] = [t for t in bucket if now - t < window]

        if len(bucket) >= limit:
            return True

        bucket.append(now)
        return False

    def _audit(self, message: InboundMessage) -> None:
        if not self._audit_log:
            return
        import json
        entry = {
            "timestamp": message.timestamp.isoformat(),
            "channel": message.channel,
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
            "text": message.text[:200],
        }
        with open(self._audit_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
