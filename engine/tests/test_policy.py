"""The host-owned policy hook: denylist, risk, auth-mode -> a decision.

cua emits ``tier`` + ``risk`` and no policy; the host decides. A denylisted
action is auto-denied without ever reaching a human; ``risk == "high"`` needs a
human; otherwise the auth-mode (bypass / default / autonomous / paranoid)
decides. ``redact`` strips secrets before any write / emit.
"""

import pytest

from engine.policy.base import AUTO_ALLOW, AUTO_DENY, NEEDS_HUMAN, ApprovalRequest
from engine.policy.default import DefaultPolicy


def _req(action="shell.run rm -rf /tmp/x", risk="medium"):
    return ApprovalRequest(action=action, risk=risk, preview="preview", idem="sha256:x")


@pytest.mark.asyncio
async def test_denylist_match_is_auto_deny_without_a_human():
    policy = DefaultPolicy(denylist=["rm -rf /"], auth_mode="default")
    d = await policy.check(_req(action="shell.run rm -rf / now", risk="low"))
    assert d.outcome == AUTO_DENY


@pytest.mark.asyncio
async def test_high_risk_needs_human_in_default_mode():
    policy = DefaultPolicy(auth_mode="default")
    d = await policy.check(_req(risk="high"))
    assert d.outcome == NEEDS_HUMAN


@pytest.mark.asyncio
async def test_medium_risk_auto_allows_in_default_mode():
    policy = DefaultPolicy(auth_mode="default")
    d = await policy.check(_req(risk="medium"))
    assert d.outcome == AUTO_ALLOW


@pytest.mark.asyncio
async def test_bypass_mode_allows_even_high_risk():
    policy = DefaultPolicy(auth_mode="bypass")
    d = await policy.check(_req(risk="high"))
    assert d.outcome == AUTO_ALLOW


@pytest.mark.asyncio
async def test_paranoid_mode_needs_human_even_for_low_risk():
    policy = DefaultPolicy(auth_mode="paranoid")
    d = await policy.check(_req(risk="low"))
    assert d.outcome == NEEDS_HUMAN


@pytest.mark.asyncio
async def test_paranoid_still_denies_denylisted():
    policy = DefaultPolicy(denylist=["curl evil"], auth_mode="paranoid")
    d = await policy.check(_req(action="shell.run curl evil.com", risk="low"))
    assert d.outcome == AUTO_DENY


@pytest.mark.asyncio
async def test_autonomous_allows_medium_but_gates_high():
    policy = DefaultPolicy(auth_mode="autonomous")
    assert (await policy.check(_req(risk="medium"))).outcome == AUTO_ALLOW
    assert (await policy.check(_req(risk="high"))).outcome == NEEDS_HUMAN


def test_redact_strips_secrets():
    policy = DefaultPolicy()
    out = policy.redact({"api_key": "sk-ant-oat01-SECRET", "keep": "ok"})
    assert out["api_key"] == "[REDACTED]"
    assert out["keep"] == "ok"
