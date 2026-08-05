"""Tests for cli/commands/service.py -- service management."""

from pathlib import Path
from unittest import mock
import os
import sys

import click
from click.testing import CliRunner
import pytest

_IS_WINDOWS = sys.platform == "win32"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def tmp_forge(tmp_path, monkeypatch):
    """Set up fake FORGE_HOME structure with platform-appropriate venv layout."""
    import cli.commands.service as svc
    forge_home = tmp_path / ".forge"
    forge_repo = forge_home / "Agent-Forge"
    pid_dir = forge_home / "pids"
    forge_repo.mkdir(parents=True)
    pid_dir.mkdir(parents=True)
    if _IS_WINDOWS:
        (forge_repo / "api" / ".venv" / "Scripts").mkdir(parents=True)
        (forge_repo / "api" / ".venv" / "Scripts" / "python.exe").write_text("")
    else:
        (forge_repo / "api" / ".venv" / "bin").mkdir(parents=True)
        (forge_repo / "api" / ".venv" / "bin" / "python").write_text("#!/bin/sh")

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
        import cli.commands.service as svc
        (PID_DIR / "api.pid").write_text("12345")
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
        assert _read_pid("api") == 12345

    def test_returns_none_for_stale_pid(self, tmp_forge, monkeypatch):
        from cli.commands.service import _read_pid, PID_DIR
        import cli.commands.service as svc
        (PID_DIR / "api.pid").write_text("99999")
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
        assert _read_pid("api") is None
        assert not (PID_DIR / "api.pid").exists()


class TestKillTree:
    def test_kills_parent(self, monkeypatch):
        from cli.commands.service import _kill_tree
        if _IS_WINDOWS:
            # On Windows, _kill_tree calls taskkill /PID <pid> /T /F
            calls = []
            monkeypatch.setattr("subprocess.run", lambda *a, **kw: calls.append(a[0]) or mock.Mock(stdout="", returncode=0))
            _kill_tree(1234)
            assert any("1234" in str(c) for c in calls)
        else:
            killed = []
            monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock.Mock(stdout="", returncode=1))
            monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
            _kill_tree(1234)
            assert 1234 in killed

    @pytest.mark.skipif(_IS_WINDOWS, reason="Windows _kill_tree uses taskkill /T which kills the whole tree in one call")
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


class TestSessionKwargs:
    """Issue #74: background processes must not inherit terminal stdin."""

    def test_includes_devnull_stdin(self):
        """_session_kwargs must include stdin=DEVNULL to prevent terminal corruption."""
        import subprocess
        from cli.commands.service import _session_kwargs
        kwargs = _session_kwargs()
        assert kwargs.get("stdin") == subprocess.DEVNULL


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
        import cli.commands.service as svc
        from cli.commands.service import stop, PID_DIR
        (PID_DIR / "api.pid").write_text("111")
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
        monkeypatch.setattr(svc, "_kill_tree", lambda pid: None)

        result = runner.invoke(stop)
        assert result.exit_code == 0
        assert "Stopped" in result.output

    def test_not_running(self, runner, tmp_forge, monkeypatch):
        from cli.commands.service import stop
        # Prevent the stop command from detecting (and killing) real services
        monkeypatch.setattr("cli.commands.service._port_in_use", lambda port: False)
        result = runner.invoke(stop)
        assert "not running" in result.output


class TestStatus:
    def test_shows_running(self, runner, tmp_forge, monkeypatch):
        import cli.commands.service as svc
        from cli.commands.service import status, PID_DIR
        (PID_DIR / "api.pid").write_text("111")
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)

        result = runner.invoke(status)
        assert result.exit_code == 0
        assert "running" in result.output
        assert "111" in result.output

    def test_shows_stopped(self, runner, tmp_forge):
        from cli.commands.service import status
        result = runner.invoke(status)
        assert "stopped" in result.output


class TestStartIsApiOnly:
    """`vadgr start` boots the daemon and nothing else -- no second process."""

    @pytest.fixture
    def fake_popen(self, monkeypatch):
        spawned = []

        def record(cmd, *args, **kwargs):
            spawned.append(cmd)
            return mock.MagicMock(poll=lambda: None, pid=4242)

        monkeypatch.setattr("subprocess.Popen", record)
        monkeypatch.setattr("cli.commands.service._port_in_use", lambda p: False)
        monkeypatch.setattr("cli.commands.service._wait_for_api", lambda p, **kw: True)
        monkeypatch.setattr("time.sleep", lambda s: None)
        return spawned

    def test_spawns_only_uvicorn(self, runner, tmp_forge, fake_popen):
        from cli.commands.service import start
        result = runner.invoke(start)
        assert result.exit_code == 0, result.output
        assert len(fake_popen) == 1
        assert "uvicorn" in fake_popen[0]

    def test_reports_the_api_and_nothing_else(self, runner, tmp_forge, fake_popen):
        from cli.commands.service import start
        result = runner.invoke(start)
        assert "API: http://localhost:8000" in result.output
        assert "3000" not in result.output

    def test_writes_no_frontend_pid_or_port_file(self, runner, tmp_forge, fake_popen):
        from cli.commands.service import start, PID_DIR
        runner.invoke(start)
        assert not (PID_DIR / "frontend.pid").exists()
        assert not (PID_DIR / "frontend.port").exists()

    def test_writes_no_frontend_log(self, runner, tmp_forge, fake_popen):
        from cli.commands.service import start
        runner.invoke(start)
        assert not (tmp_forge / "frontend.log").exists()

    def test_child_env_carries_no_frontend_port(self, tmp_forge):
        from cli.commands.service import _build_env
        assert "AGENT_FORGE_FRONTEND_PORT" not in _build_env(8000)

    def test_rejects_the_frontend_port_flag(self, runner, tmp_forge, fake_popen):
        from cli.commands.service import start
        result = runner.invoke(start, ["--frontend-port", "3000"])
        assert result.exit_code != 0
        assert "no such option" in result.output.lower()

    def test_port_is_the_old_api_alias_spelling(self, runner, tmp_forge, fake_popen):
        """`vadgr api --port` kept working when the two commands collapsed."""
        from cli.commands.service import start
        result = runner.invoke(start, ["--port", "8123"])
        assert result.exit_code == 0, result.output
        assert "8123" in result.output


class TestApiAliasIsStart:
    def test_api_resolves_to_the_same_command(self):
        from cli.main import cli
        from cli.commands.service import start
        ctx = click.Context(cli)
        assert cli.get_command(ctx, "api") is start
        assert cli.get_command(ctx, "start") is start


class TestServiceInventory:
    """The daemon is the only service, so nothing else may be named."""

    def test_status_lists_only_the_api(self, runner, tmp_forge):
        from cli.commands.service import status
        result = runner.invoke(status)
        assert "api" in result.output
        assert "frontend" not in result.output

    def test_logs_rejects_an_unknown_service(self, runner, tmp_forge):
        """A usage error, not "no logs found" -- the value must not be accepted."""
        from cli.commands.service import logs
        result = runner.invoke(logs, ["-s", "frontend"])
        assert result.exit_code == 2
        assert "invalid value for '--service'" in result.output.lower()
