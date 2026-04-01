"""Tests for cli/commands/service.py -- service management."""

from pathlib import Path
from unittest import mock
import os

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_forge(tmp_path, monkeypatch):
    """Set up fake FORGE_HOME structure."""
    import cli.commands.service as svc
    forge_home = tmp_path / ".forge"
    forge_repo = forge_home / "Agent-Forge"
    pid_dir = forge_home / "pids"
    forge_repo.mkdir(parents=True)
    pid_dir.mkdir(parents=True)
    (forge_repo / "api" / ".venv" / "bin").mkdir(parents=True)
    (forge_repo / "api" / ".venv" / "bin" / "python").write_text("#!/bin/sh")
    (forge_repo / "frontend").mkdir(parents=True)

    monkeypatch.setattr(svc, "FORGE_HOME", forge_home)
    monkeypatch.setattr(svc, "FORGE_REPO", forge_repo)
    monkeypatch.setattr(svc, "PID_DIR", pid_dir)
    return forge_home


class TestReadPid:
    def test_returns_none_when_no_file(self, tmp_forge):
        from cli.commands.service import _read_pid
        assert _read_pid("api") is None

    def test_returns_pid_when_alive(self, tmp_forge, monkeypatch):
        from cli.commands.service import _read_pid, PID_DIR
        (PID_DIR / "api.pid").write_text("12345")
        monkeypatch.setattr(os, "kill", lambda pid, sig: None)
        assert _read_pid("api") == 12345

    def test_returns_none_for_stale_pid(self, tmp_forge, monkeypatch):
        from cli.commands.service import _read_pid, PID_DIR
        (PID_DIR / "api.pid").write_text("99999")
        monkeypatch.setattr(os, "kill", mock.Mock(side_effect=ProcessLookupError))
        assert _read_pid("api") is None
        assert not (PID_DIR / "api.pid").exists()


class TestKillTree:
    def test_kills_parent(self, monkeypatch):
        from cli.commands.service import _kill_tree
        killed = []
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock.Mock(stdout="", returncode=1))
        monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
        _kill_tree(1234)
        assert 1234 in killed

    def test_kills_children_first(self, monkeypatch):
        from cli.commands.service import _kill_tree
        killed = []

        def mock_pgrep(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "1234" in str(cmd):
                return mock.Mock(stdout="5678\n", returncode=0)
            return mock.Mock(stdout="", returncode=1)

        monkeypatch.setattr("subprocess.run", mock_pgrep)
        monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
        _kill_tree(1234)
        assert killed.index(5678) < killed.index(1234)


class TestFindNode:
    def test_finds_node_on_path(self, monkeypatch):
        from cli.commands.service import _find_node
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/node" if cmd == "node" else None)
        assert _find_node() == "/usr/bin/node"

    def test_returns_none_when_not_found(self, monkeypatch):
        from cli.commands.service import _find_node
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setattr(os.environ, "get", lambda k, d="": d)
        assert _find_node() is None


class TestFindNpm:
    """Frontend must launch via npm (not npx) for consistent behavior across Node versions."""

    def test_finds_npm_on_path(self, monkeypatch):
        from cli.commands.service import _find_npm
        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/npm" if cmd == "npm" else None)
        assert _find_npm() == "/usr/bin/npm"

    def test_finds_npm_cmd_on_windows(self, monkeypatch, tmp_path):
        from cli.commands.service import _find_npm
        node_dir = tmp_path / "nodejs"
        node_dir.mkdir()
        (node_dir / "node.exe").write_text("")
        (node_dir / "npm.cmd").write_text("")
        monkeypatch.setattr("shutil.which", lambda cmd: str(node_dir / "node.exe") if cmd == "node" else None)
        result = _find_npm()
        assert result is not None
        assert "npm" in result


class TestSessionKwargs:
    """Issue #74: background processes must not inherit terminal stdin."""

    def test_includes_devnull_stdin(self):
        """_session_kwargs must include stdin=DEVNULL to prevent terminal corruption."""
        import subprocess
        from cli.commands.service import _session_kwargs
        kwargs = _session_kwargs()
        assert kwargs.get("stdin") == subprocess.DEVNULL


class TestDetectFrontendPort:
    def test_parses_vite_log(self, tmp_path):
        from cli.commands.service import _detect_frontend_port
        log = tmp_path / "frontend.log"
        log.write_text("  VITE v5.0.0  ready in 300ms\n  > Local: http://localhost:3001/\n")
        assert _detect_frontend_port(log, 3000, timeout=1.0) == 3001

    def test_returns_default_on_timeout(self, tmp_path):
        from cli.commands.service import _detect_frontend_port
        log = tmp_path / "frontend.log"
        log.write_text("no port here")
        assert _detect_frontend_port(log, 3000, timeout=0.5) == 3000

    def test_returns_default_when_no_file(self, tmp_path):
        from cli.commands.service import _detect_frontend_port
        assert _detect_frontend_port(tmp_path / "nope.log", 3000, timeout=0.5) == 3000


class TestWaitForApi:
    def test_returns_true_when_healthy(self, monkeypatch):
        from cli.commands.service import _wait_for_api
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: mock.Mock())
        assert _wait_for_api(8000, timeout=2) is True

    def test_returns_false_on_timeout(self, monkeypatch):
        from cli.commands.service import _wait_for_api
        monkeypatch.setattr("urllib.request.urlopen", mock.Mock(side_effect=Exception("down")))
        assert _wait_for_api(8000, timeout=1) is False


class TestStop:
    def test_stops_running_services(self, runner, tmp_forge, monkeypatch):
        from cli.commands.service import stop, PID_DIR
        (PID_DIR / "api.pid").write_text("111")
        (PID_DIR / "frontend.pid").write_text("222")
        monkeypatch.setattr(os, "kill", lambda pid, sig: None)
        monkeypatch.setattr("cli.commands.service._kill_tree", lambda pid: None)

        result = runner.invoke(stop)
        assert result.exit_code == 0
        assert "Stopped" in result.output

    def test_not_running(self, runner, tmp_forge):
        from cli.commands.service import stop
        result = runner.invoke(stop)
        assert "not running" in result.output


class TestStatus:
    def test_shows_running(self, runner, tmp_forge, monkeypatch):
        from cli.commands.service import status, PID_DIR
        (PID_DIR / "api.pid").write_text("111")
        (PID_DIR / "frontend.pid").write_text("222")
        monkeypatch.setattr(os, "kill", lambda pid, sig: None)

        result = runner.invoke(status)
        assert result.exit_code == 0
        assert "running" in result.output
        assert "111" in result.output

    def test_shows_stopped(self, runner, tmp_forge):
        from cli.commands.service import status
        result = runner.invoke(status)
        assert "stopped" in result.output
