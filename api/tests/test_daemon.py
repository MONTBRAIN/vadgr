"""Tests for daemon lifecycle management in computer_use_setup."""

from unittest import mock
from unittest.mock import MagicMock, patch

import pytest


class TestProbeDaemon:
    def test_running_when_ping_succeeds(self):
        from api.services.computer_use_setup import _probe_daemon
        with patch("api.services.computer_use_setup._get_bridge_client") as m:
            client = MagicMock()
            client.is_available.return_value = True
            m.return_value = client
            assert _probe_daemon() == "running"

    def test_stopped_when_connection_fails(self):
        from api.services.computer_use_setup import _probe_daemon
        with patch("api.services.computer_use_setup._get_bridge_client") as m:
            m.side_effect = Exception("connection refused")
            assert _probe_daemon() == "stopped"

    def test_degraded_when_port_open_but_ping_fails(self):
        from api.services.computer_use_setup import _probe_daemon
        with patch("api.services.computer_use_setup._get_bridge_client") as m:
            client = MagicMock()
            client.is_available.return_value = False
            m.return_value = client
            assert _probe_daemon() == "degraded"


class TestStartDaemon:
    def test_starts_successfully(self):
        from api.services.computer_use_setup import _start_daemon
        with patch("api.services.computer_use_setup._is_wsl2", return_value=True), \
             patch("api.services.computer_use_setup._find_windows_python", return_value="C:\\Python312\\python.exe"), \
             patch("api.services.computer_use_setup._deploy_and_launch_daemon") as m, \
             patch("api.services.computer_use_setup._probe_daemon", return_value="running"):
            result = _start_daemon()
            assert result is True
            m.assert_called_once()

    def test_returns_false_on_non_wsl2(self):
        from api.services.computer_use_setup import _start_daemon
        with patch("api.services.computer_use_setup._is_wsl2", return_value=False):
            assert _start_daemon() is False


class TestStopDaemon:
    def test_kills_by_port(self):
        from api.services.computer_use_setup import _stop_daemon
        with patch("api.services.computer_use_setup._is_wsl2", return_value=True), \
             patch("subprocess.run") as m:
            _stop_daemon()
            assert m.call_count == 2
            # First call kills by port
            assert "19542" in str(m.call_args_list[0])
            # Second call kills zombie pythonw.exe daemon.py processes
            assert "daemon.py" in str(m.call_args_list[1])

    def test_noop_on_non_wsl2(self):
        from api.services.computer_use_setup import _stop_daemon
        with patch("api.services.computer_use_setup._is_wsl2", return_value=False), \
             patch("subprocess.run") as m:
            _stop_daemon()
            assert not m.called


class TestGetStatusIncludesDaemon:
    def test_includes_daemon_field(self, tmp_path):
        from api.services.computer_use_setup import get_status, MCP_JSON_PATH
        import json
        # Write a valid .mcp.json so computer use is enabled
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text(json.dumps({
            "mcpServers": {"computer-use": {"command": "python", "env": {}}}
        }))
        with patch("api.services.computer_use_setup.MCP_JSON_PATH", mcp_path), \
             patch("api.services.computer_use_setup._probe_daemon", return_value="running"), \
             patch("api.services.computer_use_setup._is_wsl2", return_value=True):
            status = get_status()
            assert "daemon" in status
            assert status["daemon"] == "running"

    def test_daemon_null_on_non_wsl2(self):
        from api.services.computer_use_setup import get_status
        with patch("api.services.computer_use_setup._is_wsl2", return_value=False):
            status = get_status()
            assert status.get("daemon") is None

    def test_daemon_null_when_disabled(self, tmp_path):
        """Issue #66: daemon should not be probed when computer use is disabled."""
        from api.services.computer_use_setup import get_status
        with patch("api.services.computer_use_setup.MCP_JSON_PATH", tmp_path / "nope.json"), \
             patch("api.services.computer_use_setup._is_wsl2", return_value=True), \
             patch("api.services.computer_use_setup._probe_daemon") as mock_probe:
            status = get_status()
            assert status.get("daemon") is None
            mock_probe.assert_not_called()


class TestEnableManagesDaemon:
    def test_enable_starts_daemon_when_stopped(self):
        from api.services.computer_use_setup import enable_computer_use
        with patch("api.services.computer_use_setup._probe_daemon", return_value="stopped"), \
             patch("api.services.computer_use_setup._start_daemon", return_value=True) as m_start, \
             patch("api.services.computer_use_setup._venv_healthy", return_value=True), \
             patch("api.services.computer_use_setup._deps_need_install", return_value=False), \
             patch("api.services.computer_use_setup._write_all_provider_configs"), \
             patch("api.services.computer_use_setup._is_wsl2", return_value=True):
            enable_computer_use()
            m_start.assert_called_once()

    def test_enable_restarts_degraded_daemon(self):
        from api.services.computer_use_setup import enable_computer_use
        with patch("api.services.computer_use_setup._probe_daemon", return_value="degraded"), \
             patch("api.services.computer_use_setup._stop_daemon") as m_stop, \
             patch("api.services.computer_use_setup._start_daemon", return_value=True) as m_start, \
             patch("api.services.computer_use_setup._venv_healthy", return_value=True), \
             patch("api.services.computer_use_setup._deps_need_install", return_value=False), \
             patch("api.services.computer_use_setup._write_all_provider_configs"), \
             patch("api.services.computer_use_setup._is_wsl2", return_value=True):
            enable_computer_use()
            m_stop.assert_called_once()
            m_start.assert_called_once()

    def test_enable_skips_launch_when_running(self):
        from api.services.computer_use_setup import enable_computer_use
        with patch("api.services.computer_use_setup._probe_daemon", return_value="running"), \
             patch("api.services.computer_use_setup._start_daemon") as m_start, \
             patch("api.services.computer_use_setup._venv_healthy", return_value=True), \
             patch("api.services.computer_use_setup._deps_need_install", return_value=False), \
             patch("api.services.computer_use_setup._write_all_provider_configs"), \
             patch("api.services.computer_use_setup._is_wsl2", return_value=True):
            enable_computer_use()
            m_start.assert_not_called()


class TestDisableKillsDaemon:
    def test_disable_kills_daemon(self):
        from api.services.computer_use_setup import disable_computer_use
        with patch("api.services.computer_use_setup._stop_daemon") as m_stop, \
             patch("api.services.computer_use_setup._remove_all_provider_configs"), \
             patch("api.services.computer_use_setup._is_wsl2", return_value=True):
            disable_computer_use()
            m_stop.assert_called_once()
