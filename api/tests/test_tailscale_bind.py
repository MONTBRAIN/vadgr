"""Tests for VADGR_BIND_TAILSCALE host selection."""

import pytest


class TestTailscaleBind:

    def test_default_bind_is_localhost(self, monkeypatch):
        monkeypatch.delenv("VADGR_BIND_TAILSCALE", raising=False)
        from cli.bind import resolve_bind_host
        assert resolve_bind_host() == "127.0.0.1"

    def test_bind_tailscale_uses_all_interfaces(self, monkeypatch):
        monkeypatch.setenv("VADGR_BIND_TAILSCALE", "1")
        from cli.bind import resolve_bind_host
        assert resolve_bind_host() == "0.0.0.0"

    def test_bind_tailscale_zero_is_off(self, monkeypatch):
        monkeypatch.setenv("VADGR_BIND_TAILSCALE", "0")
        from cli.bind import resolve_bind_host
        assert resolve_bind_host() == "127.0.0.1"

    def test_bind_tailscale_true_value(self, monkeypatch):
        monkeypatch.setenv("VADGR_BIND_TAILSCALE", "true")
        from cli.bind import resolve_bind_host
        assert resolve_bind_host() == "0.0.0.0"
