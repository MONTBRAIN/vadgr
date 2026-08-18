"""Tests for health endpoint, startup, and configuration."""

import pytest
from pathlib import Path
from unittest.mock import patch

from api.config import Settings
from api.utils.platform import computer_use_platform, machine_platform


class TestHealth:

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "modules" in data
        assert data["version"] == Settings().version

    @pytest.mark.asyncio
    async def test_health_names_this_machine_rather_than_a_constant(self, client):
        """The platform is read from the host, not baked in.

        The phone prints this string verbatim in its machine row, so a constant
        told every owner their machine was WSL: a native Windows box reported
        ``wsl2``, a word the Rust daemon does not even use for the same field.
        """
        resp = await client.get("/api/health")
        assert resp.json()["platform"] == machine_platform()
        assert resp.json()["platform"] in {"linux", "macos", "windows", "wsl"}

    @pytest.mark.asyncio
    async def test_computer_use_status_names_this_machine(self, client):
        resp = await client.get("/api/computer-use/status")
        assert resp.status_code == 200
        assert resp.json()["platform"] == computer_use_platform()

    @pytest.mark.asyncio
    async def test_health_sends_no_cors_headers(self, client):
        """The daemon answers a browser preflight-style request with no
        access-control headers, because it serves no browser."""
        resp = await client.get("/api/health", headers={"Origin": "http://localhost:3000"})
        assert resp.status_code == 200
        assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


class TestStartup:

    def test_database_parent_dir_created_on_startup(self, tmp_path):
        """The data/ directory should be auto-created if it doesn't exist."""
        db_path = tmp_path / "nonexistent" / "subdir" / "agent_forge.db"
        assert not db_path.parent.exists()

        # Simulate what lifespan does
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)

        assert db_path.parent.exists()


class TestConfig:

    def test_settings_carry_no_browser_surface(self):
        """No frontend port and no CORS allowlist: no browser client remains."""
        s = Settings()
        assert not hasattr(s, "frontend_port")
        assert not hasattr(s, "cors_origins")

    def test_env_prefix(self):
        """Settings use VADGR_ env prefix."""
        assert Settings.model_config["env_prefix"] == "VADGR_"
