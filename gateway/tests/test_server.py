"""Tests for the gateway webhook server pipeline (_process_message)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from gateway.models import CommandResult, InboundMessage
from gateway.server import _process_message


def _msg(sender_id="5731200000", text="hello"):
    return InboundMessage(
        channel="whatsapp",
        chat_id=f"{sender_id}@s.whatsapp.net",
        sender_id=sender_id,
        sender_name="Test",
        text=text,
    )


def _make_app(security_check_return=None, allowed_senders=None, router_response="Done"):
    """Build a minimal mock FastAPI app with wired state."""
    app = MagicMock()
    app.state.config.security.allowed_senders = allowed_senders or []

    security = MagicMock()
    security.check.return_value = security_check_return
    app.state.security = security

    router = AsyncMock()
    router.handle.return_value = CommandResult(response=router_response)
    app.state.router = router

    return app


class TestProcessMessageSilentReject:
    """
    Issue #117: server.py re-checks the allowlist after security.check() has
    already handled it (lines 96-99). After the fix, _process_message must rely
    solely on the SILENT_REJECT sentinel returned by security.check() instead
    of duplicating the allowlist logic.
    """

    @pytest.mark.asyncio
    async def test_silent_reject_drops_message_silently(self):
        """When security.check() returns SILENT_REJECT, no response must be sent."""
        import gateway.security as sec
        assert hasattr(sec, "SILENT_REJECT"), (
            "SILENT_REJECT sentinel not found in gateway.security -- "
            "add it before this server test can exercise the correct behavior."
        )
        adapter = AsyncMock()
        app = _make_app(security_check_return=sec.SILENT_REJECT)

        await _process_message(app, _msg(sender_id="9999999999"), adapter)

        adapter.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_silent_reject_does_not_reach_router(self):
        """When security returns SILENT_REJECT, the router must not be invoked."""
        import gateway.security as sec
        assert hasattr(sec, "SILENT_REJECT"), (
            "SILENT_REJECT sentinel not found in gateway.security -- "
            "add it before this server test can exercise the correct behavior."
        )
        adapter = AsyncMock()
        app = _make_app(security_check_return=sec.SILENT_REJECT)

        await _process_message(app, _msg(sender_id="9999999999"), adapter)

        app.state.router.handle.assert_not_called()

    @pytest.mark.asyncio
    async def test_allowed_sender_reaches_router(self):
        """When security returns None (allowed), the message must be routed normally."""
        adapter = AsyncMock()
        app = _make_app(security_check_return=None)

        await _process_message(app, _msg(sender_id="5731200000"), adapter)

        app.state.router.handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_string_sends_rejection_response(self):
        """When security returns a non-sentinel string, that string is sent to the user."""
        adapter = AsyncMock()
        app = _make_app(security_check_return="Slow down! Too many commands.")

        await _process_message(app, _msg(), adapter)

        adapter.send_message.assert_called_once()
        sent = adapter.send_message.call_args[0][0]
        assert "Slow down" in sent.text
