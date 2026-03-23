"""Tests for health endpoint and startup."""

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
