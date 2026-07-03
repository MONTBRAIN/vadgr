"""The default policy hook: denylist + risk + auth-mode.

Precedence: a denylist match is ``auto_deny`` regardless of mode; then the
auth-mode and the action's risk decide. ``redact`` delegates to the trajectory's
secret redactor so one implementation strips tokens everywhere.
"""

from __future__ import annotations

from engine.policy.base import (
    AUTO_ALLOW,
    AUTO_DENY,
    NEEDS_HUMAN,
    ApprovalRequest,
    Decision,
)
from engine.trajectory import redact_secrets

# Auth modes, from most permissive to most restrictive.
BYPASS = "bypass"
DEFAULT = "default"
AUTONOMOUS = "autonomous"
PARANOID = "paranoid"


class DefaultPolicy:
    """denylist -> risk -> auth-mode. Ships as the 0.4.0 host policy."""

    def __init__(
        self,
        denylist: list[str] | None = None,
        auth_mode: str = DEFAULT,
        redactor=redact_secrets,
    ):
        self._denylist = list(denylist or [])
        self._auth_mode = auth_mode
        self._redactor = redactor

    async def check(self, req: ApprovalRequest) -> Decision:
        for pattern in self._denylist:
            if pattern in (req.action or ""):
                return Decision(AUTO_DENY, reason=f"denylisted: {pattern}")

        if self._auth_mode == BYPASS:
            return Decision(AUTO_ALLOW, reason="bypass mode")
        if self._auth_mode == PARANOID:
            return Decision(NEEDS_HUMAN, reason="paranoid mode")

        # default / autonomous: high risk always needs a human, else allow.
        if (req.risk or "").lower() == "high":
            return Decision(NEEDS_HUMAN, reason="high-risk action")
        return Decision(AUTO_ALLOW, reason=f"{self._auth_mode} mode, risk={req.risk}")

    def redact(self, payload: dict) -> dict:
        return self._redactor(payload)
