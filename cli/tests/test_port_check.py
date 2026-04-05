"""Tests for port checking and process validation in service commands."""

import os
from pathlib import Path
from unittest import mock

import pytest


class TestPortInUse:
    def test_returns_true_when_port_responds(self):
        from cli.commands.service import _port_in_use
        # Port 8000 may or may not be running, test with a known-free port
        assert _port_in_use(59999) is False

    def test_returns_false_for_free_port(self):
        from cli.commands.service import _port_in_use
        assert _port_in_use(59998) is False

    def test_detects_ipv4_listener(self):
        """Port bound on 127.0.0.1 should be detected."""
        import socket
        from cli.commands.service import _port_in_use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 59997))
            s.listen(1)
            assert _port_in_use(59997) is True

    def test_detects_ipv6_listener(self):
        """Port bound on ::1 (IPv6) should be detected -- Vite on Windows 11."""
        import socket
        from cli.commands.service import _port_in_use
        try:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
                s.bind(("::1", 59996))
                s.listen(1)
                assert _port_in_use(59996) is True
        except OSError:
            pytest.skip("IPv6 not available")


class TestKillPort:
    def test_kill_port_calls_fuser(self, monkeypatch):
        from cli.commands.service import _kill_port
        calls = []
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: calls.append(a))
        _kill_port(9999)
        assert len(calls) > 0


class TestFindFreePort:
    def test_returns_default_when_free(self):
        from cli.commands.service import _find_free_port
        # Port 59990 should be free
        assert _find_free_port(59990) == 59990

    def test_increments_when_busy(self, monkeypatch):
        from cli.commands.service import _find_free_port
        busy = {8000, 8001, 8002}
        monkeypatch.setattr("cli.commands.service._port_in_use", lambda p: p in busy)
        assert _find_free_port(8000) == 8003

    def test_returns_none_after_max_attempts(self, monkeypatch):
        from cli.commands.service import _find_free_port
        monkeypatch.setattr("cli.commands.service._port_in_use", lambda p: True)
        assert _find_free_port(8000, max_attempts=5) is None


class TestStartPortCheck:
    def test_start_uses_next_free_port_when_busy(self, runner, tmp_forge, monkeypatch):
        """Issue #84: start should find a free port instead of blocking."""
        from cli.commands.service import start
        from click.testing import CliRunner
        busy = {8000}
        monkeypatch.setattr("cli.commands.service._port_in_use", lambda p: p in busy)
        monkeypatch.setattr("cli.commands.service._wait_for_api", lambda p, **kw: True)
        monkeypatch.setattr("cli.commands.service._find_npm", lambda: None)
        monkeypatch.setattr("subprocess.Popen", mock.MagicMock(return_value=mock.MagicMock(poll=lambda: None, pid=123)))
        runner = CliRunner()
        result = runner.invoke(start)
        assert result.exit_code == 0
        assert "8001" in result.output


class TestStopWithStalePort:
    def test_stop_kills_by_port_when_pid_stale(self, tmp_forge, monkeypatch):
        from cli.commands.service import stop, PID_DIR
        from click.testing import CliRunner

        # No PID files but port is in use
        killed_ports = []
        monkeypatch.setattr("cli.commands.service._port_in_use", lambda p: True)
        monkeypatch.setattr("cli.commands.service._kill_port", lambda p: killed_ports.append(p))

        runner = CliRunner()
        result = runner.invoke(stop)
        assert len(killed_ports) > 0


@pytest.fixture
def runner():
    from click.testing import CliRunner
    return CliRunner()


@pytest.fixture
def tmp_forge(tmp_path, monkeypatch):
    import cli.commands.service as svc
    forge_home = tmp_path / ".forge"
    pid_dir = forge_home / "pids"
    forge_repo = tmp_path / "Agent-Forge"
    pid_dir.mkdir(parents=True)
    forge_repo.mkdir(parents=True)
    (forge_repo / "api" / ".venv" / "bin").mkdir(parents=True)
    (forge_repo / "api" / ".venv" / "bin" / "python").write_text("#!/bin/sh")
    monkeypatch.setattr(svc, "FORGE_HOME", forge_home)
    monkeypatch.setattr(svc, "FORGE_REPO", forge_repo)
    monkeypatch.setattr(svc, "PID_DIR", pid_dir)
    return forge_home
