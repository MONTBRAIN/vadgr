"""Tests for settings endpoints (computer use toggle)."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

import api.services.computer_use_setup as cu_setup


class TestComputerUseSetupService:
    """Tests for the computer_use_setup service functions."""

    def test_get_status_no_mcp_json(self, tmp_path):
        """When .mcp.json doesn't exist, computer use is disabled."""
        with patch.object(cu_setup, "MCP_JSON_PATH", tmp_path / ".mcp.json"):
            status = cu_setup.get_status()
            assert status["enabled"] is False
            assert status["cache_enabled"] is True

    def test_enable_creates_mcp_json(self, tmp_path):
        """Enabling computer use creates .mcp.json."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "computer_use" / ".venv"
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", tmp_path / "nonexistent.txt"),
            patch("subprocess.run"),
        ):
            result = cu_setup.enable_computer_use(cache_enabled=True)
            assert mcp_path.exists()
            data = json.loads(mcp_path.read_text())
            assert "computer-use" in data["mcpServers"]
            assert result["enabled"] is True

    def test_enable_with_cache_disabled(self, tmp_path):
        """Enabling with cache_enabled=False sets env var in .mcp.json."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "computer_use" / ".venv"
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", tmp_path / "nonexistent.txt"),
            patch("subprocess.run"),
        ):
            cu_setup.enable_computer_use(cache_enabled=False)
            data = json.loads(mcp_path.read_text())
            env = data["mcpServers"]["computer-use"]["env"]
            assert env["AGENT_FORGE_CACHE_ENABLED"] == "0"

    def test_enable_skips_pip_when_deps_marker_fresh(self, tmp_path):
        """When deps marker exists and requirements unchanged, pip is skipped."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        reqs_path = tmp_path / "requirements.txt"
        reqs_path.write_text("some-package==1.0\n")
        # Create marker with matching hash
        import hashlib
        reqs_hash = hashlib.md5(reqs_path.read_bytes()).hexdigest()
        marker = venv_path / ".deps_installed"
        marker.write_text(reqs_hash)
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", reqs_path),
            patch("subprocess.run") as mock_run,
        ):
            cu_setup.enable_computer_use()
            # pip should NOT be called since deps are already installed
            mock_run.assert_not_called()

    def test_enable_runs_pip_when_deps_marker_stale(self, tmp_path):
        """When requirements changed since marker was written, pip runs."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        reqs_path = tmp_path / "requirements.txt"
        reqs_path.write_text("some-package==1.0\n")
        # Create marker with old/stale hash
        marker = venv_path / ".deps_installed"
        marker.write_text("stale_hash")
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", reqs_path),
            patch("subprocess.run") as mock_run,
        ):
            cu_setup.enable_computer_use()
            assert mock_run.called
            assert "pip" in str(mock_run.call_args_list[0])

    def test_enable_writes_deps_marker_after_pip(self, tmp_path):
        """After pip install, a marker file with requirements hash is written."""
        import hashlib
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        reqs_path = tmp_path / "requirements.txt"
        reqs_path.write_text("some-package==1.0\n")
        expected_hash = hashlib.md5(reqs_path.read_bytes()).hexdigest()
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", reqs_path),
            patch("subprocess.run"),
        ):
            cu_setup.enable_computer_use()
            marker = venv_path / ".deps_installed"
            assert marker.exists()
            assert marker.read_text() == expected_hash

    def test_enable_runs_pip_when_no_marker(self, tmp_path):
        """When venv exists but no marker, pip runs (first enable after upgrade)."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        reqs_path = tmp_path / "requirements.txt"
        reqs_path.write_text("some-package==1.0\n")
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", reqs_path),
            patch("subprocess.run") as mock_run,
        ):
            cu_setup.enable_computer_use()
            assert mock_run.called

    def test_disable_removes_mcp_json(self, tmp_path):
        """Disabling computer use removes .mcp.json."""
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text('{"mcpServers": {"computer-use": {}}}')
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            result = cu_setup.disable_computer_use()
            assert not mcp_path.exists()
            assert result["enabled"] is False

    def test_update_cache_setting(self, tmp_path):
        """Toggling cache updates env var in .mcp.json."""
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text('{"mcpServers": {"computer-use": {"env": {}}}}')
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "PROJECT_ROOT", tmp_path),
        ):
            cu_setup.update_cache_setting(cache_enabled=False)
            data = json.loads(mcp_path.read_text())
            assert data["mcpServers"]["computer-use"]["env"]["AGENT_FORGE_CACHE_ENABLED"] == "0"

    def test_get_status_reads_cache_disabled(self, tmp_path):
        """get_status reads cache_enabled=False from .mcp.json env."""
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text(json.dumps({
            "mcpServers": {
                "computer-use": {
                    "env": {"AGENT_FORGE_CACHE_ENABLED": "0"}
                }
            }
        }))
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            status = cu_setup.get_status()
            assert status["enabled"] is True
            assert status["cache_enabled"] is False

    def test_get_status_malformed_json(self, tmp_path):
        """Malformed .mcp.json is treated as disabled."""
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text("{invalid json!!!")
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            status = cu_setup.get_status()
            assert status["enabled"] is False

    def test_get_status_venv_ready(self, tmp_path):
        """venv_ready reflects whether venv directory exists."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
        ):
            assert cu_setup.get_status()["venv_ready"] is False
            venv_path.mkdir()
            assert cu_setup.get_status()["venv_ready"] is True

    def test_enable_skips_venv_creation_when_healthy(self, tmp_path):
        """Re-enabling reuses existing venv with pip, does not recreate it."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        venv_path.mkdir()
        # Create fake pip binary so venv looks healthy
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", tmp_path / "nonexistent.txt"),
            patch("subprocess.run") as mock_run,
        ):
            cu_setup.enable_computer_use()
            # subprocess.run should NOT be called for venv creation
            for call_args in mock_run.call_args_list:
                assert "venv" not in str(call_args)

    def test_enable_recreates_broken_venv(self, tmp_path):
        """When venv exists but pip is missing, venv is recreated with --clear."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        venv_path.mkdir()  # venv dir exists but no bin/pip
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", tmp_path / "nonexistent.txt"),
            patch("subprocess.run") as mock_run,
        ):
            cu_setup.enable_computer_use()
            # venv creation should be called with --clear
            assert mock_run.called
            venv_call = str(mock_run.call_args_list[0])
            assert "venv" in venv_call
            assert "--clear" in venv_call

    def test_enable_installs_deps_when_requirements_exist(self, tmp_path):
        """When requirements.txt exists, pip install is called."""
        mcp_path = tmp_path / ".mcp.json"
        venv_path = tmp_path / "cu_venv"
        venv_path.mkdir()
        (venv_path / "bin").mkdir()
        (venv_path / "bin" / "pip").touch()
        reqs_path = tmp_path / "requirements.txt"
        reqs_path.write_text("some-package==1.0\n")
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", venv_path),
            patch.object(cu_setup, "CU_REQUIREMENTS", reqs_path),
            patch("subprocess.run") as mock_run,
        ):
            cu_setup.enable_computer_use()
            # pip install should have been called
            assert mock_run.called
            pip_call = mock_run.call_args_list[0]
            assert "pip" in str(pip_call)

    def test_update_cache_noop_when_no_mcp_json(self, tmp_path):
        """update_cache_setting is a no-op when .mcp.json doesn't exist."""
        mcp_path = tmp_path / ".mcp.json"
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            result = cu_setup.update_cache_setting(cache_enabled=False)
            assert result["enabled"] is False
            assert not mcp_path.exists()

    def test_disable_noop_when_already_disabled(self, tmp_path):
        """Disabling when already disabled is a no-op."""
        mcp_path = tmp_path / ".mcp.json"  # doesn't exist
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            result = cu_setup.disable_computer_use()
            assert result["enabled"] is False

    def test_mcp_json_uses_python_on_windows(self, tmp_path):
        """On Windows, .mcp.json uses 'python' not 'python3'."""
        with patch.object(cu_setup, "sys") as mock_sys:
            mock_sys.platform = "win32"
            assert cu_setup._python_command() == "python"

    def test_mcp_json_uses_python3_on_unix(self, tmp_path):
        """On non-Windows, .mcp.json uses 'python3'."""
        with patch.object(cu_setup, "sys") as mock_sys:
            mock_sys.platform = "linux"
            assert cu_setup._python_command() == "python3"


class TestComputerUseSettingsEndpoints:
    """Tests for GET/PUT /api/settings/computer-use."""

    @pytest.mark.asyncio
    async def test_get_computer_use_status(self, client):
        """GET returns current computer use status."""
        resp = await client.get("/api/settings/computer-use")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "cache_enabled" in data

    @pytest.mark.asyncio
    async def test_put_enable_computer_use(self, client, tmp_path):
        """PUT with enabled=true creates .mcp.json."""
        mcp_path = tmp_path / ".mcp.json"
        with (
            patch.object(cu_setup, "MCP_JSON_PATH", mcp_path),
            patch.object(cu_setup, "CU_VENV_DIR", tmp_path / "cu_venv"),
            patch.object(cu_setup, "CU_REQUIREMENTS", tmp_path / "nonexistent.txt"),
            patch("subprocess.run"),
        ):
            resp = await client.put("/api/settings/computer-use", json={
                "enabled": True, "cache_enabled": True,
            })
            assert resp.status_code == 200
            assert resp.json()["enabled"] is True
            assert mcp_path.exists()

    @pytest.mark.asyncio
    async def test_put_disable_computer_use(self, client, tmp_path):
        """PUT with enabled=false removes .mcp.json."""
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text('{"mcpServers": {"computer-use": {}}}')
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            resp = await client.put("/api/settings/computer-use", json={
                "enabled": False,
            })
            assert resp.status_code == 200
            assert resp.json()["enabled"] is False
            assert not mcp_path.exists()


class TestRunBlockedWhenComputerUseDisabled:
    """Tests that agents with computer_use=true can't run when disabled."""

    @pytest.mark.asyncio
    async def test_run_blocked_when_cu_disabled(self, client, app, tmp_path):
        """Running an agent with computer_use=true returns 409 when disabled."""
        agent = await app.state.agent_repo.create(
            name="CU Agent", description="needs desktop",
            computer_use=True, status="ready",
        )
        mcp_path = tmp_path / ".mcp.json"  # doesn't exist = disabled
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            resp = await client.post(f"/api/agents/{agent['id']}/run", json={})
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "COMPUTER_USE_DISABLED"

    @pytest.mark.asyncio
    async def test_run_allowed_when_cu_enabled(self, client, app, tmp_path):
        """Running an agent with computer_use=true succeeds when enabled."""
        agent = await app.state.agent_repo.create(
            name="CU Agent", description="needs desktop",
            computer_use=True, status="ready",
            forge_path="output/test/",
        )
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text('{"mcpServers": {"computer-use": {}}}')
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            resp = await client.post(f"/api/agents/{agent['id']}/run", json={})
            assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_run_allowed_for_cli_agent_when_cu_disabled(self, client, app, tmp_path):
        """Running a CLI-only agent works even when computer use is disabled."""
        agent = await app.state.agent_repo.create(
            name="CLI Agent", description="no desktop",
            computer_use=False, status="ready",
        )
        mcp_path = tmp_path / ".mcp.json"  # doesn't exist = disabled
        with patch.object(cu_setup, "MCP_JSON_PATH", mcp_path):
            resp = await client.post(f"/api/agents/{agent['id']}/run", json={})
            assert resp.status_code == 202
