"""Tests for computer use setup service and settings endpoints.

The Windows daemon lifecycle is owned by the published ``vadgr-computer-use``
package. The setup service only installs the package, writes MCP configs, and
delegates daemon management to ``vadgr-cua`` CLI subcommands.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import api.services.computer_use_setup as cu_setup
from api.utils.platform import venv_bin_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_fake_venv(venv_path: Path) -> None:
    """Create a fake venv with pip and vadgr-cua binaries so checks succeed."""
    bin_dir = venv_bin_dir(venv_path)
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "pip").touch()
    (bin_dir / "vadgr-cua").touch()


@pytest.fixture(autouse=True)
def _no_wsl2_by_default(monkeypatch):
    """Default every test to non-WSL2 so daemon calls are skipped.

    Tests that exercise WSL2-specific behavior opt in by re-patching.
    """
    monkeypatch.setattr(cu_setup, "_is_wsl2", lambda: False)


@pytest.fixture
def paths(tmp_path):
    """Return a paths bundle with all setup module locations patched to tmp_path."""
    venv = tmp_path / ".cu_venv"
    mcp = tmp_path / ".mcp.json"
    gemini = tmp_path / ".gemini" / "settings.json"
    codex = tmp_path / ".codex" / "config.toml"
    with (
        patch.object(cu_setup, "CU_VENV_DIR", venv),
        patch.object(cu_setup, "MCP_JSON_PATH", mcp),
        patch.object(cu_setup, "GEMINI_SETTINGS_PATH", gemini),
        patch.object(cu_setup, "CODEX_GLOBAL_CONFIG_PATH", codex),
    ):
        yield {
            "venv": venv,
            "mcp": mcp,
            "gemini": gemini,
            "codex": codex,
            "tmp": tmp_path,
        }


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_disabled_when_no_mcp_json(self, paths):
        status = cu_setup.get_status()
        assert status["enabled"] is False

    def test_enabled_when_mcp_json_has_vadgr_server(self, paths):
        paths["mcp"].write_text(json.dumps({
            "mcpServers": {"vadgr-computer-use": {"command": "x"}}
        }))
        assert cu_setup.get_status()["enabled"] is True

    def test_not_enabled_when_mcp_json_has_other_server_only(self, paths):
        paths["mcp"].write_text(json.dumps({
            "mcpServers": {"something-else": {"command": "x"}}
        }))
        assert cu_setup.get_status()["enabled"] is False

    def test_not_enabled_when_mcp_json_malformed(self, paths):
        paths["mcp"].write_text("{ not valid json")
        assert cu_setup.get_status()["enabled"] is False

    def test_venv_ready_reflects_directory_presence(self, paths):
        assert cu_setup.get_status()["venv_ready"] is False
        paths["venv"].mkdir()
        assert cu_setup.get_status()["venv_ready"] is True

    def test_daemon_none_on_non_wsl2(self, paths):
        paths["mcp"].write_text(json.dumps({
            "mcpServers": {"vadgr-computer-use": {}}
        }))
        assert cu_setup.get_status()["daemon"] is None

    def test_daemon_none_when_disabled_on_wsl2(self, paths, monkeypatch):
        monkeypatch.setattr(cu_setup, "_is_wsl2", lambda: True)
        with patch.object(cu_setup, "_doctor_status") as probe:
            status = cu_setup.get_status()
            assert status["daemon"] is None
            probe.assert_not_called()

    def test_daemon_probed_when_enabled_on_wsl2(self, paths, monkeypatch):
        monkeypatch.setattr(cu_setup, "_is_wsl2", lambda: True)
        paths["mcp"].write_text(json.dumps({
            "mcpServers": {"vadgr-computer-use": {}}
        }))
        with patch.object(cu_setup, "_doctor_status", return_value="running"):
            assert cu_setup.get_status()["daemon"] == "running"

    def test_platform_reports_wsl2_or_native(self, paths, monkeypatch):
        assert cu_setup.get_status()["platform"] == "native"
        monkeypatch.setattr(cu_setup, "_is_wsl2", lambda: True)
        assert cu_setup.get_status()["platform"] == "wsl2"


# ---------------------------------------------------------------------------
# _doctor_status
# ---------------------------------------------------------------------------

class TestDoctorStatus:
    def test_running_when_doctor_reports_daemon_running(self, paths):
        _create_fake_venv(paths["venv"])
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0,
                "stdout": json.dumps({"daemon_running": True, "port": 19542}),
                "stderr": "",
            })()
            assert cu_setup._doctor_status() == "running"

    def test_stopped_when_doctor_reports_daemon_not_running(self, paths):
        _create_fake_venv(paths["venv"])
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0,
                "stdout": json.dumps({"daemon_running": False}),
                "stderr": "",
            })()
            assert cu_setup._doctor_status() == "stopped"

    def test_none_when_binary_missing(self, paths):
        assert cu_setup._doctor_status() is None

    def test_none_when_doctor_exits_nonzero(self, paths):
        _create_fake_venv(paths["venv"])
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 1, "stdout": "", "stderr": "boom",
            })()
            assert cu_setup._doctor_status() is None

    def test_none_when_doctor_returns_invalid_json(self, paths):
        _create_fake_venv(paths["venv"])
        with patch("subprocess.run") as run:
            run.return_value = type("R", (), {
                "returncode": 0, "stdout": "not json", "stderr": "",
            })()
            assert cu_setup._doctor_status() is None

    def test_none_when_subprocess_times_out(self, paths):
        _create_fake_venv(paths["venv"])
        import subprocess
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="vadgr-cua", timeout=10),
        ):
            assert cu_setup._doctor_status() is None


# ---------------------------------------------------------------------------
# enable_computer_use
# ---------------------------------------------------------------------------

class TestEnable:
    def test_creates_venv_when_missing(self, paths):
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            if "-m" in cmd and "venv" in cmd:
                _create_fake_venv(paths["venv"])
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch("subprocess.run", side_effect=fake_run):
            cu_setup.enable_computer_use()

        venv_cmd = next(c for c in captured if "venv" in c)
        assert "--clear" in venv_cmd

    def test_skips_venv_creation_when_healthy(self, paths):
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text(
            __import__("hashlib").md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        )
        with patch("subprocess.run") as run:
            cu_setup.enable_computer_use()
        for call in run.call_args_list:
            assert "venv" not in str(call) or "-m" not in str(call)

    def test_recreates_venv_when_pip_missing(self, paths):
        paths["venv"].mkdir()

        def fake_run(cmd, **kwargs):
            if "-m" in cmd and "venv" in cmd:
                _create_fake_venv(paths["venv"])
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch("subprocess.run", side_effect=fake_run) as run:
            cu_setup.enable_computer_use()
        assert any("venv" in str(c) for c in run.call_args_list)

    def test_pip_install_runs_when_marker_absent(self, paths):
        def fake_run(cmd, **kwargs):
            if "-m" in cmd and "venv" in cmd:
                _create_fake_venv(paths["venv"])
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch("subprocess.run", side_effect=fake_run) as run:
            cu_setup.enable_computer_use()
        pip_calls = [
            c for c in run.call_args_list
            if isinstance(c.args[0], list) and c.args[0][-1] == cu_setup.CU_PACKAGE_SPEC
        ]
        assert pip_calls
        assert "install" in pip_calls[0].args[0]

    def test_pip_install_skipped_when_marker_matches_pin(self, paths):
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text(
            __import__("hashlib").md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        )
        with patch("subprocess.run") as run:
            cu_setup.enable_computer_use()
        assert not any("install" in str(c) for c in run.call_args_list)

    def test_pip_install_reruns_when_pin_changes(self, paths):
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text("stale_hash")
        with patch("subprocess.run") as run:
            cu_setup.enable_computer_use()
        assert any("install" in str(c) for c in run.call_args_list)

    def test_marker_written_after_successful_install(self, paths):
        import hashlib

        def fake_run(cmd, **kwargs):
            if "-m" in cmd and "venv" in cmd:
                _create_fake_venv(paths["venv"])
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch("subprocess.run", side_effect=fake_run):
            cu_setup.enable_computer_use()

        marker = paths["venv"] / cu_setup.DEPS_MARKER
        assert marker.exists()
        expected = hashlib.md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        assert marker.read_text() == expected

    def test_install_daemon_called_on_wsl2(self, paths, monkeypatch):
        monkeypatch.setattr(cu_setup, "_is_wsl2", lambda: True)
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text(
            __import__("hashlib").md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        )
        with (
            patch.object(cu_setup, "_install_daemon") as install,
            patch.object(cu_setup, "_doctor_status", return_value="running"),
        ):
            cu_setup.enable_computer_use()
            install.assert_called_once()

    def test_install_daemon_skipped_off_wsl2(self, paths):
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text(
            __import__("hashlib").md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        )
        with patch.object(cu_setup, "_install_daemon") as install:
            cu_setup.enable_computer_use()
            install.assert_not_called()


# ---------------------------------------------------------------------------
# MCP configs
# ---------------------------------------------------------------------------

class TestMcpConfigs:
    def _enable_with_fake_venv(self, paths, monkeypatch=None):
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text(
            __import__("hashlib").md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        )
        cu_setup.enable_computer_use()

    def test_mcp_json_written_with_vadgr_server_name(self, paths):
        self._enable_with_fake_venv(paths)
        data = json.loads(paths["mcp"].read_text())
        assert "vadgr-computer-use" in data["mcpServers"]

    def test_mcp_json_command_points_to_venv_console_script(self, paths):
        self._enable_with_fake_venv(paths)
        data = json.loads(paths["mcp"].read_text())
        command = data["mcpServers"]["vadgr-computer-use"]["command"]
        assert command.endswith("vadgr-cua") or command.endswith("vadgr-cua.exe")
        assert str(paths["venv"]) in command

    def test_mcp_json_args_use_stdio_transport(self, paths):
        self._enable_with_fake_venv(paths)
        data = json.loads(paths["mcp"].read_text())
        args = data["mcpServers"]["vadgr-computer-use"]["args"]
        assert args == ["--transport", "stdio"]

    def test_mcp_json_does_not_set_removed_env_vars(self, paths):
        """AGENT_FORGE_CACHE_ENABLED / AGENT_FORGE_DEBUG / PYTHONPATH are gone."""
        self._enable_with_fake_venv(paths)
        data = json.loads(paths["mcp"].read_text())
        server = data["mcpServers"]["vadgr-computer-use"]
        env = server.get("env", {})
        assert "AGENT_FORGE_CACHE_ENABLED" not in env
        assert "AGENT_FORGE_DEBUG" not in env
        assert "PYTHONPATH" not in env

    def test_mcp_json_type_is_stdio(self, paths):
        self._enable_with_fake_venv(paths)
        data = json.loads(paths["mcp"].read_text())
        assert data["mcpServers"]["vadgr-computer-use"]["type"] == "stdio"

    def test_gemini_settings_written(self, paths):
        self._enable_with_fake_venv(paths)
        data = json.loads(paths["gemini"].read_text())
        assert "vadgr-computer-use" in data["mcpServers"]

    def test_gemini_disables_respect_git_ignore(self, paths):
        self._enable_with_fake_venv(paths)
        data = json.loads(paths["gemini"].read_text())
        assert data["context"]["fileFiltering"]["respectGitIgnore"] is False

    def test_codex_section_written_to_global_config(self, paths):
        self._enable_with_fake_venv(paths)
        assert paths["codex"].exists()
        assert "[mcp_servers.vadgr-computer-use]" in paths["codex"].read_text()

    def test_codex_preserves_existing_settings(self, paths):
        paths["codex"].parent.mkdir(parents=True, exist_ok=True)
        paths["codex"].write_text(
            'model = "o3"\napproval_mode = "suggest"\n'
        )
        self._enable_with_fake_venv(paths)
        content = paths["codex"].read_text()
        assert 'model = "o3"' in content
        assert "[mcp_servers.vadgr-computer-use]" in content

    def test_codex_replaces_stale_mcp_section(self, paths):
        paths["codex"].parent.mkdir(parents=True, exist_ok=True)
        paths["codex"].write_text(
            'model = "o3"\n\n'
            '[mcp_servers.computer-use]\ncommand = "/old/python"\n\n'
            '[mcp_servers.computer-use.env]\nAGENT_FORGE_DEBUG = "1"\n'
        )
        self._enable_with_fake_venv(paths)
        content = paths["codex"].read_text()
        assert content.count("[mcp_servers.vadgr-computer-use]") == 1
        assert "/old/python" not in content
        assert "AGENT_FORGE_DEBUG" not in content

    def test_codex_uses_toml_literal_strings_for_paths(self, paths):
        """Windows-style backslash paths must be wrapped in single quotes."""
        self._enable_with_fake_venv(paths)
        content = paths["codex"].read_text()
        # command = 'PATH' uses single quotes (TOML literal)
        assert "command = '" in content

    def test_codex_preserves_unrelated_mcp_servers(self, paths):
        paths["codex"].parent.mkdir(parents=True, exist_ok=True)
        paths["codex"].write_text(
            '[mcp_servers.my-other-tool]\ncommand = "npx"\nargs = ["my-tool"]\n'
        )
        self._enable_with_fake_venv(paths)
        content = paths["codex"].read_text()
        assert "[mcp_servers.my-other-tool]" in content
        assert "[mcp_servers.vadgr-computer-use]" in content


# ---------------------------------------------------------------------------
# disable_computer_use
# ---------------------------------------------------------------------------

class TestDisable:
    def test_removes_mcp_json(self, paths):
        paths["mcp"].write_text('{"mcpServers": {"vadgr-computer-use": {}}}')
        result = cu_setup.disable_computer_use()
        assert not paths["mcp"].exists()
        assert result["enabled"] is False

    def test_removes_gemini_settings(self, paths):
        paths["gemini"].parent.mkdir(parents=True, exist_ok=True)
        paths["gemini"].write_text('{"mcpServers": {"vadgr-computer-use": {}}}')
        cu_setup.disable_computer_use()
        assert not paths["gemini"].exists()

    def test_removes_codex_section_preserves_rest(self, paths):
        paths["codex"].parent.mkdir(parents=True, exist_ok=True)
        paths["codex"].write_text(
            'model = "o3"\n\n'
            '[mcp_servers.vadgr-computer-use]\ncommand = "x"\n'
        )
        cu_setup.disable_computer_use()
        content = paths["codex"].read_text()
        assert "[mcp_servers.vadgr-computer-use]" not in content
        assert 'model = "o3"' in content
        assert paths["codex"].exists()

    def test_tolerates_no_configs(self, paths):
        result = cu_setup.disable_computer_use()
        assert result["enabled"] is False

    def test_stop_daemon_called_on_wsl2(self, paths, monkeypatch):
        monkeypatch.setattr(cu_setup, "_is_wsl2", lambda: True)
        with patch.object(cu_setup, "_stop_daemon") as stop:
            cu_setup.disable_computer_use()
            stop.assert_called_once()

    def test_stop_daemon_skipped_off_wsl2(self, paths):
        with patch.object(cu_setup, "_stop_daemon") as stop:
            cu_setup.disable_computer_use()
            stop.assert_not_called()


# ---------------------------------------------------------------------------
# Settings HTTP endpoints
# ---------------------------------------------------------------------------

class TestComputerUseSettingsEndpoints:
    @pytest.mark.asyncio
    async def test_get_returns_status_shape(self, client):
        resp = await client.get("/api/settings/computer-use")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "venv_ready" in data
        assert "daemon" in data

    @pytest.mark.asyncio
    async def test_put_enable_creates_mcp_json(self, client, paths):
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text(
            __import__("hashlib").md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        )
        resp = await client.put(
            "/api/settings/computer-use", json={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        assert paths["mcp"].exists()

    @pytest.mark.asyncio
    async def test_put_disable_removes_mcp_json(self, client, paths):
        paths["mcp"].write_text('{"mcpServers": {"vadgr-computer-use": {}}}')
        resp = await client.put(
            "/api/settings/computer-use", json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
        assert not paths["mcp"].exists()

    @pytest.mark.asyncio
    async def test_put_body_does_not_accept_cache_enabled(self, client, paths):
        """The cache toggle is gone; ignore unknown fields via pydantic default."""
        _create_fake_venv(paths["venv"])
        (paths["venv"] / cu_setup.DEPS_MARKER).write_text(
            __import__("hashlib").md5(cu_setup.CU_PACKAGE_SPEC.encode()).hexdigest()
        )
        resp = await client.put(
            "/api/settings/computer-use",
            json={"enabled": True, "cache_enabled": False},
        )
        assert resp.status_code == 200
        data = json.loads(paths["mcp"].read_text())
        env = data["mcpServers"]["vadgr-computer-use"].get("env", {})
        assert "AGENT_FORGE_CACHE_ENABLED" not in env


# ---------------------------------------------------------------------------
# Agent run gate (unchanged behavior, just verifies integration)
# ---------------------------------------------------------------------------

class TestRunBlockedWhenComputerUseDisabled:
    @pytest.mark.asyncio
    async def test_run_blocked_when_cu_disabled(self, client, app, paths):
        agent = await app.state.agent_repo.create(
            name="CU Agent", description="needs desktop",
            computer_use=True, status="ready",
        )
        resp = await client.post(f"/api/agents/{agent['id']}/run", json={})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "COMPUTER_USE_DISABLED"

    @pytest.mark.asyncio
    async def test_run_allowed_when_cu_enabled(self, client, app, paths):
        agent = await app.state.agent_repo.create(
            name="CU Agent", description="needs desktop",
            computer_use=True, status="ready",
            forge_path="output/test/",
        )
        paths["mcp"].write_text('{"mcpServers": {"vadgr-computer-use": {}}}')
        resp = await client.post(f"/api/agents/{agent['id']}/run", json={})
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_run_allowed_for_cli_agent_when_cu_disabled(
        self, client, app, paths,
    ):
        agent = await app.state.agent_repo.create(
            name="CLI Agent", description="no desktop",
            computer_use=False, status="ready",
        )
        resp = await client.post(f"/api/agents/{agent['id']}/run", json={})
        assert resp.status_code == 202
