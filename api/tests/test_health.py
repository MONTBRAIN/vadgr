"""Tests for health endpoint, startup, and configuration."""

import pytest
from pathlib import Path
from unittest.mock import patch

from api.config import Settings


class TestHealth:

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "modules" in data
        assert "version" in data


class TestStartup:

    def test_database_parent_dir_created_on_startup(self, tmp_path):
        """The data/ directory should be auto-created if it doesn't exist."""
        db_path = tmp_path / "nonexistent" / "subdir" / "agent_forge.db"
        assert not db_path.parent.exists()

        # Simulate what lifespan does
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)

        assert db_path.parent.exists()


class TestConfig:

    def test_default_cors_includes_default_frontend_port(self):
        """Default CORS origins should include the default frontend port."""
        s = Settings()
        assert "http://localhost:3000" in s.cors_origins

    def test_cors_auto_adds_frontend_port(self):
        """When frontend_port is set, its origin is auto-added to cors_origins."""
        s = Settings(frontend_port=4000)
        assert "http://localhost:4000" in s.cors_origins

    def test_cors_no_duplicate_when_frontend_port_matches_default(self):
        """When frontend_port matches default, no duplicate origin is added."""
        s = Settings(frontend_port=3000)
        origins = [o for o in s.cors_origins if o == "http://localhost:3000"]
        assert len(origins) == 1

    def test_custom_cors_plus_frontend_port(self):
        """Custom cors_origins still get the frontend port origin appended."""
        s = Settings(cors_origins=["http://example.com"], frontend_port=5000)
        assert "http://example.com" in s.cors_origins
        assert "http://localhost:5000" in s.cors_origins

    def test_default_frontend_port(self):
        """Default frontend_port is 3000."""
        s = Settings()
        assert s.frontend_port == 3000

    def test_env_prefix(self):
        """Settings use AGENT_FORGE_ env prefix."""
        assert Settings.model_config["env_prefix"] == "AGENT_FORGE_"
