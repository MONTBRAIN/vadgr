"""CLI tests against a fake API server.

Every CLI command is tested by running the actual CLI binary via subprocess
against a lightweight HTTP server that returns preset responses. No real API,
no LLM, no database. Runs in seconds, CI-safe.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import pytest

import sys as _sys
if _sys.platform == "win32":
    _venv_python = Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe"
else:
    _venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
# Fall back to the current interpreter when the CLI venv doesn't exist
# (e.g., running tests on Windows with system Python).
PYTHON = str(_venv_python) if _venv_python.exists() else _sys.executable
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
FAKE_PORT = 18321

# -- Preset responses --

_AGENT = {
    "id": "aaaa-1111-2222-3333",
    "name": "Test-Agent",
    "status": "ready",
    "description": "A test agent",
    "provider": "claude_code",
    "model": "claude-sonnet-4-6",
    "computer_use": False,
    "steps": [
        {"name": "Step 1", "computer_use": False},
        {"name": "Step 2", "computer_use": True},
    ],
    "input_schema": [
        {"name": "query", "type": "text", "required": True, "description": "Search query", "label": "Query"},
        {"name": "data_file", "type": "file", "required": False, "description": "Optional CSV", "label": "Data File"},
    ],
    "output_schema": [
        {"name": "report", "type": ".pdf", "required": True, "description": "PDF report"},
    ],
}

_RUN = {
    "id": "run-aaaa-bbbb",
    "agent_id": "aaaa-1111-2222-3333",
    "agent_name": "Test-Agent",
    "status": "completed",
    "provider": "claude_code",
    "model": "claude-sonnet-4-6",
    "duration": 42.5,
    "created_at": "2026-03-27T10:00:00",
    "steps": [
        {"name": "Step 1", "status": "completed"},
        {"name": "Step 2", "status": "completed"},
    ],
}

_PROVIDERS = [
    {"id": "claude_code", "name": "Claude Code", "available": True, "models": [
        {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6"},
    ]},
    {"id": "codex", "name": "Codex", "available": False, "models": []},
]

_HEALTH = {"status": "healthy", "version": "0.1.0", "platform": "test", "modules": {"forge": True, "computer_use": True}}

_LOGS = [
    {"timestamp": "10:00:01", "type": "agent_log", "message": "Starting step 1"},
    {"timestamp": "10:00:05", "type": "agent_log", "message": "Step 1 complete"},
]

# Track poll count for spinner tests
_poll_count = 0


class _FakeAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _poll_count

        if self.path == "/api/health":
            self._json(200, _HEALTH)
        elif self.path == "/api/providers":
            self._json(200, _PROVIDERS)
        elif self.path == "/api/agents":
            self._json(200, [_AGENT])
        elif self.path.startswith("/api/agents/") and "/export" in self.path:
            # Return a minimal zip
            import io
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("agent-forge.json", json.dumps({"name": "exported"}))
            self._binary(200, buf.getvalue(), "application/zip")
        elif self.path.startswith("/api/agents/") and "/logs" not in self.path:
            agent_id = self.path.split("/api/agents/")[1].split("?")[0]
            # Spinner test: first poll returns creating, second returns ready
            _poll_count += 1
            if _poll_count <= 1:
                self._json(200, {**_AGENT, "id": agent_id, "status": "creating"})
            else:
                self._json(200, {**_AGENT, "id": agent_id, "status": "ready"})
        elif self.path.startswith("/api/runs/") and "/logs" in self.path:
            self._json(200, _LOGS)
        elif self.path.startswith("/api/runs/"):
            self._json(200, _RUN)
        elif self.path == "/api/runs" or self.path.startswith("/api/runs?"):
            self._json(200, [_RUN])
        else:
            self._json(404, {"detail": "Not found"})

    def do_POST(self):
        global _poll_count
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        if self.path == "/api/agents":
            # Check for empty name to simulate Pydantic 422
            parsed = json.loads(body) if body else {}
            if parsed.get("name") == "":
                self._json(422, {"detail": [
                    {"loc": ["body", "name"], "msg": "String should have at least 1 character", "type": "string_too_short"}
                ]})
                return
            _poll_count = 0  # Reset for spinner test
            self._json(201, {**_AGENT, "id": "new-agent-id", "status": "creating"})
        elif "/run" in self.path:
            self._json(200, {"run_id": "run-new-123", "status": "queued"})
        elif "/cancel" in self.path:
            self._json(200, {"status": "cancelled"})
        elif "/approve" in self.path:
            self._json(200, {"status": "running"})
        elif self.path == "/api/agents/import":
            _poll_count = 0
            self._json(201, {**_AGENT, "id": "imported-id", "name": "Imported", "status": "importing"})
        elif "/uploads" in self.path:
            self._json(200, {"kind": "file", "path": "uploads/test.csv", "filename": "test.csv"})
        else:
            self._json(404, {"detail": "Not found"})

    def do_PUT(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        agent_id = self.path.split("/api/agents/")[1] if "/api/agents/" in self.path else "?"
        self._json(200, {**_AGENT, "id": agent_id, **body})

    def do_DELETE(self):
        self.send_response(204)
        self.end_headers()

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _binary(self, code, data, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module", autouse=True)
def fake_api():
    server = HTTPServer(("127.0.0.1", FAKE_PORT), _FakeAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def _run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    cmd = [PYTHON, "-m", "cli", "--api-url", f"http://127.0.0.1:{FAKE_PORT}"] + list(args)
    env = {**os.environ, "PYTHONPATH": PROJECT_ROOT}
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=PROJECT_ROOT, timeout=timeout)


# -----------------------------------------------------------------------
# Help
# -----------------------------------------------------------------------

class TestHelp:
    def test_root_help(self):
        r = _run("--help")
        assert r.returncode == 0
        assert "agents" in r.stdout
        assert "runs" in r.stdout
        assert "registry" in r.stdout
        assert "start" in r.stdout

    def test_agents_help(self):
        r = _run("agents", "--help")
        assert "list" in r.stdout
        assert "create" in r.stdout
        assert "update" in r.stdout
        assert "import" in r.stdout
        assert "export" in r.stdout

    def test_runs_help(self):
        r = _run("runs", "--help")
        assert "list" in r.stdout
        assert "cancel" in r.stdout

    def test_registry_help(self):
        r = _run("registry", "--help")
        assert "pack" in r.stdout
        assert "add" in r.stdout
        assert "use" in r.stdout


# -----------------------------------------------------------------------
# Health & Providers
# -----------------------------------------------------------------------

class TestHealth:
    def test_shows_status(self):
        r = _run("health")
        assert r.returncode == 0
        assert "healthy" in r.stdout

    def test_shows_version(self):
        r = _run("health")
        assert "0.1.0" in r.stdout

    def test_shows_modules(self):
        r = _run("health")
        assert "forge" in r.stdout
        assert "computer_use" in r.stdout


class TestProviders:
    def test_lists_providers(self):
        r = _run("providers")
        assert r.returncode == 0
        assert "Claude Code" in r.stdout
        assert "Codex" in r.stdout

    def test_shows_availability(self):
        r = _run("providers")
        assert "available" in r.stdout


# -----------------------------------------------------------------------
# Agents
# -----------------------------------------------------------------------

class TestAgentsList:
    def test_lists_agents(self):
        r = _run("agents", "list")
        assert r.returncode == 0
        assert "Test-Agent" in r.stdout

    def test_ps_alias(self):
        r = _run("ps")
        assert "Test-Agent" in r.stdout


class TestAgentsGet:
    def test_shows_detail(self):
        r = _run("agents", "get", "aaaa-1111-2222-3333")
        assert r.returncode == 0
        assert "Test-Agent" in r.stdout
        assert "claude_code" in r.stdout

    def test_shows_steps(self):
        r = _run("agents", "get", "aaaa-1111-2222-3333")
        assert "Step 1" in r.stdout
        assert "Step 2" in r.stdout

    def test_shows_inputs(self):
        r = _run("agents", "get", "aaaa-1111-2222-3333")
        assert "query" in r.stdout
        assert "required" in r.stdout
        assert "data_file" in r.stdout

    def test_shows_outputs(self):
        r = _run("agents", "get", "aaaa-1111-2222-3333")
        assert "report" in r.stdout
        assert ".pdf" in r.stdout


class TestAgentsCreate:
    def test_create_waits_for_ready(self):
        global _poll_count
        _poll_count = 0
        r = _run("agents", "create", "--name", "new-agent", "--description", "test", timeout=60)
        assert r.returncode == 0
        assert "ready" in r.stdout.lower() or "new-agent" in r.stdout


class TestAgentsUpdate:
    def test_update_name(self):
        r = _run("agents", "update", "aaaa-1111-2222-3333", "--name", "renamed")
        assert r.returncode == 0
        assert "Updated" in r.stdout

    def test_update_nothing_fails(self):
        r = _run("agents", "update", "aaaa-1111-2222-3333")
        assert r.returncode != 0
        assert "Nothing to update" in r.stdout or "Nothing to update" in r.stderr


class TestAgentsDelete:
    def test_deletes(self):
        r = _run("agents", "delete", "aaaa-1111-2222-3333")
        assert r.returncode == 0
        assert "Deleted" in r.stdout


class TestAgentsRun:
    def test_run_with_input_flags(self):
        r = _run("run", "Test-Agent", "-i", "query=hello", "--background")
        assert r.returncode == 0
        assert "run-new-123" in r.stdout

    def test_run_by_partial_name(self):
        r = _run("run", "test", "-i", "query=hello", "--background")
        assert r.returncode == 0


class TestAgentsExport:
    def test_exports_file(self, tmp_path):
        output = tmp_path / "test.agnt"
        r = _run("agents", "export", "aaaa-1111-2222-3333", "-o", str(output))
        assert r.returncode == 0
        assert "Exported" in r.stdout
        assert output.exists()


class TestAgentsImport:
    def test_imports_agnt(self, tmp_path):
        global _poll_count
        _poll_count = 0
        agnt = tmp_path / "test.agnt"
        with zipfile.ZipFile(agnt, "w") as zf:
            zf.writestr("agent-forge.json", json.dumps({"name": "imported"}))
            zf.writestr("agent.bundle", b"fake")
        r = _run("agents", "import", str(agnt), timeout=60)
        assert r.returncode == 0
        assert "Imported" in r.stdout or "imported" in r.stdout


# -----------------------------------------------------------------------
# Runs
# -----------------------------------------------------------------------

class TestRunsList:
    def test_lists_runs(self):
        r = _run("runs", "list")
        assert r.returncode == 0
        assert "run-aaaa" in r.stdout

    def test_shows_status(self):
        r = _run("runs", "list")
        assert "completed" in r.stdout


class TestRunsGet:
    def test_shows_detail(self):
        r = _run("runs", "get", "run-aaaa-bbbb")
        assert r.returncode == 0
        assert "run-aaaa-bbbb" in r.stdout
        assert "Test-Agent" in r.stdout

    def test_shows_steps(self):
        r = _run("runs", "get", "run-aaaa-bbbb")
        assert "Step 1" in r.stdout


class TestRunsCancel:
    def test_cancels(self):
        r = _run("runs", "cancel", "run-aaaa-bbbb")
        assert r.returncode == 0
        assert "Cancelled" in r.stdout or "cancelled" in r.stdout


class TestRunsLogs:
    def test_shows_logs(self):
        r = _run("runs", "logs", "run-aaaa-bbbb")
        assert r.returncode == 0
        assert "Starting step 1" in r.stdout
        assert "Step 1 complete" in r.stdout


# -----------------------------------------------------------------------
# Registry (config commands only -- pack/pull/push tested in registry/)
# -----------------------------------------------------------------------

def _run_with_forge_home(forge_home: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run CLI command with an isolated FORGE_HOME so registry tests don't pollute the real config."""
    cmd = [PYTHON, "-m", "cli", "--api-url", f"http://127.0.0.1:{FAKE_PORT}"] + list(args)
    env = {**os.environ, "PYTHONPATH": PROJECT_ROOT, "FORGE_HOME": forge_home}
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=PROJECT_ROOT, timeout=timeout)


class TestRegistryConfig:
    @pytest.fixture(autouse=True)
    def _isolated_forge_home(self, tmp_path):
        """Each test gets its own FORGE_HOME so registry config is isolated."""
        self._forge_home = str(tmp_path / ".forge")

    def _reg_run(self, *args, **kwargs):
        return _run_with_forge_home(self._forge_home, *args, **kwargs)

    def test_list(self):
        r = self._reg_run("registry", "list")
        assert r.returncode == 0
        # Default config always includes 'official'
        assert "official" in r.stdout

    def test_add_and_remove(self):
        r = self._reg_run("registry", "add", "temp-test", "--type", "http", "--url", "https://fake.test")
        assert r.returncode == 0
        assert "Added" in r.stdout

        r = self._reg_run("registry", "list")
        assert "temp-test" in r.stdout

        # Switch to temp-test and back so we can remove it
        self._reg_run("registry", "use", "temp-test")
        self._reg_run("registry", "use", "official")

        r = self._reg_run("registry", "remove", "temp-test")
        assert r.returncode == 0
        assert "Removed" in r.stdout

    def test_add_duplicate_fails(self):
        # 'official' is always present in the default config
        r = self._reg_run("registry", "add", "official", "--type", "http", "--url", "https://x")
        assert r.returncode != 0

    def test_use_nonexistent_fails(self):
        r = self._reg_run("registry", "use", "nonexistent-xyz")
        assert r.returncode != 0

    def test_remove_active_fails(self):
        # 'official' is the default active registry
        r = self._reg_run("registry", "remove", "official")
        assert r.returncode != 0


# -----------------------------------------------------------------------
# Service (status only -- start/stop need real processes)
# -----------------------------------------------------------------------

class TestStatus:
    def test_shows_status(self):
        r = _run("status")
        assert r.returncode == 0 or "stopped" in r.stdout


# -----------------------------------------------------------------------
# Error handling
# -----------------------------------------------------------------------

class TestErrors:
    def test_api_down(self):
        cmd = [PYTHON, "-m", "cli", "--api-url", "http://127.0.0.1:19999", "health"]
        env = {**os.environ, "PYTHONPATH": PROJECT_ROOT}
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=PROJECT_ROOT, timeout=30)
        assert r.returncode != 0
        assert "not running" in r.stdout or "not running" in r.stderr

    def test_unknown_subcommand(self):
        r = _run("agents", "nonexistent")
        assert r.returncode != 0

    def test_missing_required_arg(self):
        r = _run("agents", "get")
        assert r.returncode != 0

    def test_runs_get_empty_id(self):
        """BUG-1: 'runs get ""' should fail gracefully, not crash with AttributeError."""
        r = _run("runs", "get", "")
        assert r.returncode != 0
        assert "required" in r.stderr.lower() or "required" in r.stdout.lower() or "not found" in r.stderr.lower() or "not found" in r.stdout.lower()

    def test_agents_get_empty_id(self):
        """BUG-2: 'agents get ""' should not silently return first agent."""
        r = _run("agents", "get", "")
        assert r.returncode != 0
        assert "No agent" in r.stderr or "No agent" in r.stdout

    def test_validation_error_readable(self):
        """BUG-3: Pydantic 422 errors should show human-readable messages, not raw JSON."""
        r = _run("agents", "create", "--name", "", "--description", "test")
        assert r.returncode != 0
        output = r.stdout + r.stderr
        # Should show readable message, not raw JSON list
        assert "[{" not in output
        assert "at least 1 character" in output or "string_too_short" in output
