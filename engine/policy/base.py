"""The policy port -- the approval / denylist / redaction hook the host owns.

cua stays policy-free: it emits ``tier`` + ``risk`` and drives the machine. The
*host* (vadgr) decides whether an action is auto-allowed, auto-denied
(denylist), or needs a human -- per the active auth-mode. This is where §5's
approval/denylist/redaction delegation lives, never in cua.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# The three outcomes a policy check can return.
AUTO_ALLOW = "auto_allow"
AUTO_DENY = "auto_deny"
NEEDS_HUMAN = "needs_human"


@dataclass
class ApprovalRequest:
    """A request to perform a gated action, handed to the policy hook."""

    action: str
    risk: str                       # "low" | "medium" | "high"
    preview: str = ""
    idem: str | None = None


@dataclass
class Decision:
    """A policy outcome plus the reason, for the journal / channel prompt."""

    outcome: str                    # AUTO_ALLOW | AUTO_DENY | NEEDS_HUMAN
    reason: str = ""


@runtime_checkable
class PolicyHook(Protocol):
    """Decides gated actions and redacts payloads before they are written."""

    async def check(self, req: ApprovalRequest) -> Decision:
        """``auto_allow`` | ``auto_deny`` (denylist) | ``needs_human`` -- per the
        active auth-mode."""
        ...

    def redact(self, payload: dict) -> dict:
        """The redaction hook the trajectory + channels call before write/emit."""
        ...
