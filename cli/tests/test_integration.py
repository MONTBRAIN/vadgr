"""Integration tests for the CLI against a live API.

These tests require the API to be running at localhost:8000.
Skip with: pytest -m "not integration"
"""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

PYTHON = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python")
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)

pytestmark = pytest.mark.integration


def _run(*args: str) -> subprocess.CompletedProcess:
    """Run a CLI command and return the result."""
    cmd = [PYTHON, "-m", "cli"] + list(args)
    env = {**os.environ, "PYTHONPATH": PROJECT_ROOT}
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=PROJECT_ROOT, timeout=30)


def _api_available() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2)
        return True
    except Exception:
        return False


# Skip entire module if API is not running
if not _api_available():
    pytest.skip("API not running at localhost:8000", allow_module_level=True)


# -----------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------

class TestHealth:
    def test_returns_healthy(self):
        r = _run("health")
        assert r.returncode == 0
        assert "healthy" in r.stdout

    def test_shows_version(self):
        r = _run("health")
        assert "Version:" in r.stdout

    def test_shows_platform(self):
        r = _run("health")
        assert "Platform:" in r.stdout

    def test_shows_modules(self):
        r = _run("health")
        assert "forge:" in r.stdout
        assert "computer_use:" in r.stdout


# -----------------------------------------------------------------------
# Providers
# -----------------------------------------------------------------------

class TestProviders:
    def test_lists_providers(self):
        r = _run("providers")
        assert r.returncode == 0
        assert "Claude Code" in r.stdout

    def test_shows_models(self):
        r = _run("providers")
        assert "claude-" in r.stdout or "Sonnet" in r.stdout or "Opus" in r.stdout

    def test_shows_availability(self):
        r = _run("providers")
        assert "available" in r.stdout


# -----------------------------------------------------------------------
# Agents
# -----------------------------------------------------------------------

class TestAgentsList:
    def test_lists_existing_agents(self):
        r = _run("agents", "list")
        assert r.returncode == 0
        # At minimum the linkedin agent should exist
        assert "Linkedin-Profile-Updater" in r.stdout or "No agents" in r.stdout

    def test_ps_alias_works(self):
        r = _run("ps")
        assert r.returncode == 0
        # Same output as agents list
        list_r = _run("agents", "list")
        assert r.stdout == list_r.stdout


class TestAgentsGet:
    def _get_first_agent_id(self) -> str | None:
        import urllib.request
        data = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/agents", timeout=5).read())
        return data[0]["id"] if data else None

    def test_shows_agent_detail(self):
        agent_id = self._get_first_agent_id()
        if not agent_id:
            pytest.skip("No agents in database")
        r = _run("agents", "get", agent_id)
        assert r.returncode == 0
        assert agent_id in r.stdout
        assert "Name:" in r.stdout
        assert "Status:" in r.stdout

    def test_bad_id_returns_error(self):
        r = _run("agents", "get", "nonexistent-uuid-here")
        assert r.returncode != 0
        assert "Error" in r.stderr or "Error" in r.stdout or r.returncode != 0


class TestAgentsCRUD:
    """Full create -> list -> get -> delete cycle."""

    def test_full_lifecycle(self):
        # Create
        r = _run("agents", "create", "--name", "cli-integration-test", "--description", "Temp agent for CLI integration test")
        assert r.returncode == 0
        assert "Created" in r.stdout
        # Extract ID from output
        # Output: "Created: cli-integration-test (ID: uuid-here)"
        agent_id = r.stdout.split("ID: ")[1].strip().rstrip(")")

        try:
            # Verify in list
            r = _run("agents", "list")
            assert "cli-integration-test" in r.stdout

            # Get detail
            r = _run("agents", "get", agent_id)
            assert r.returncode == 0
            assert "cli-integration-test" in r.stdout
        finally:
            # Always clean up
            r = _run("agents", "delete", agent_id)
            assert r.returncode == 0
            assert "Deleted" in r.stdout

        # Verify gone
        r = _run("agents", "list")
        assert "cli-integration-test" not in r.stdout


class TestAgentsRun:
    def _get_first_agent_id(self) -> str | None:
        import urllib.request
        data = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/agents", timeout=5).read())
        return data[0]["id"] if data else None

    def test_run_triggers_execution(self):
        agent_id = self._get_first_agent_id()
        if not agent_id:
            pytest.skip("No agents in database")
        r = _run("run", agent_id[:8])
        # May succeed or fail with 409 (missing required inputs), both are valid
        assert "Run started" in r.stdout or "Error" in r.stderr or r.returncode != 0


# -----------------------------------------------------------------------
# Runs
# -----------------------------------------------------------------------

class TestRunsList:
    def test_lists_runs(self):
        r = _run("runs", "list")
        assert r.returncode == 0
        # Should show header at minimum
        assert "Run ID" in r.stdout or "No runs" in r.stdout

    def test_filter_by_status(self):
        r = _run("runs", "list", "--status", "failed")
        assert r.returncode == 0

    def test_filter_by_nonexistent_status(self):
        r = _run("runs", "list", "--status", "running")
        assert r.returncode == 0


class TestRunsGet:
    def _get_first_run_id(self) -> str | None:
        import urllib.request
        data = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/runs", timeout=5).read())
        return data[0]["id"] if data else None

    def test_shows_run_detail(self):
        run_id = self._get_first_run_id()
        if not run_id:
            pytest.skip("No runs in database")
        r = _run("runs", "get", run_id)
        assert r.returncode == 0
        assert run_id in r.stdout
        assert "Status:" in r.stdout


class TestRunsCancel:
    def _get_first_run_id(self) -> str | None:
        import urllib.request
        data = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/runs", timeout=5).read())
        return data[0]["id"] if data else None

    def test_cancel_completed_run_returns_error(self):
        run_id = self._get_first_run_id()
        if not run_id:
            pytest.skip("No runs in database")
        r = _run("runs", "cancel", run_id)
        # Cancelling a completed/failed run should return a conflict error
        assert r.returncode != 0 or "Error" in r.stderr or "Cancelled" in r.stdout


# -----------------------------------------------------------------------
# Registry
# -----------------------------------------------------------------------

class TestRegistrySearch:
    def test_search_github(self):
        """Search the live MONTBRAIN/sample-registry."""
        r = _run("registry", "search", "linkedin")
        assert r.returncode == 0
        assert "linkedin-profile-updater" in r.stdout
        assert "0.1.0" in r.stdout

    def test_search_no_results(self):
        r = _run("registry", "search", "zzz-nonexistent-agent-xyz")
        assert r.returncode == 0
        assert "No agents found" in r.stdout


class TestRegistryAgents:
    def test_lists_installed(self):
        r = _run("registry", "agents")
        assert r.returncode == 0
        # linkedin-profile-updater should be installed from earlier tests
        assert "linkedin-profile-updater" in r.stdout or "No agents" in r.stdout


class TestRegistryPack:
    def test_pack_creates_agnt(self, tmp_path):
        agent_dir = tmp_path / "test-pack-agent"
        agent_dir.mkdir()
        (agent_dir / "agentic.md").write_text("# Pack Test\nTest agent for pack.")
        output = tmp_path / "test.agnt"

        r = _run("registry", "pack", str(agent_dir), "-o", str(output))
        assert r.returncode == 0
        assert "Packed" in r.stdout
        assert output.exists()

        # Verify zip contents
        with zipfile.ZipFile(output) as zf:
            assert "manifest.json" in zf.namelist()
            assert "agentic.md" in zf.namelist()

    def test_pack_missing_agentic(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        r = _run("registry", "pack", str(empty_dir))
        assert r.returncode != 0
        assert "agentic.md" in r.stderr or "agentic.md" in r.stdout


class TestRegistryPull:
    def test_pull_from_github(self, tmp_path):
        """Pull linkedin-profile-updater from the live registry."""
        # Use --force in case it's already installed
        r = _run("registry", "pull", "linkedin-profile-updater", "--force")
        assert r.returncode == 0
        assert "Installed" in r.stdout

        # Verify files exist
        install_dir = Path.home() / ".forge" / "agents" / "linkedin-profile-updater"
        assert install_dir.exists()
        assert (install_dir / "agentic.md").exists()
        assert (install_dir / "manifest.json").exists()


# -----------------------------------------------------------------------
# Error handling
# -----------------------------------------------------------------------

class TestRegistryConfig:
    """Test add/use/list/remove against real config file."""

    def test_full_config_lifecycle(self):
        # List (should have at least sample)
        r = _run("registry", "list")
        assert r.returncode == 0
        assert "sample" in r.stdout

        # Add
        r = _run("registry", "add", "integration-test-reg", "--type", "http", "--url", "https://fake.test")
        assert r.returncode == 0
        assert "Added" in r.stdout

        # List (should show both)
        r = _run("registry", "list")
        assert "integration-test-reg" in r.stdout
        assert "sample" in r.stdout

        # Use
        r = _run("registry", "use", "integration-test-reg")
        assert r.returncode == 0
        assert "integration-test-reg" in r.stdout

        # Switch back
        r = _run("registry", "use", "sample")
        assert r.returncode == 0

        # Remove
        r = _run("registry", "remove", "integration-test-reg")
        assert r.returncode == 0
        assert "Removed" in r.stdout

        # Verify gone
        r = _run("registry", "list")
        assert "integration-test-reg" not in r.stdout

    def test_add_duplicate_fails(self):
        r = _run("registry", "add", "sample", "--type", "http", "--url", "https://x.com")
        assert r.returncode != 0
        assert "already exists" in r.stdout or "already exists" in r.stderr

    def test_use_nonexistent_fails(self):
        r = _run("registry", "use", "nonexistent-reg-xyz")
        assert r.returncode != 0

    def test_remove_active_fails(self):
        r = _run("registry", "remove", "sample")
        assert r.returncode != 0


class TestErrorHandling:
    def test_api_down_error(self):
        r = _run("--api-url", "http://127.0.0.1:19999", "health")
        assert r.returncode != 0
        assert "not running" in r.stderr or "not running" in r.stdout

    def test_unknown_subcommand(self):
        r = _run("agents", "nonexistent")
        assert r.returncode != 0

    def test_missing_required_args(self):
        r = _run("agents", "get")
        assert r.returncode != 0

    def test_registry_pack_nonexistent_dir(self):
        r = _run("registry", "pack", "/nonexistent/path/abc")
        assert r.returncode != 0
