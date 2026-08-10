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

# The run row as the daemon publishes it. `agent_name` is the run's title: the
# key outlived the entity it was named for, because the shipped phone reads it.
_RUN = {
    "id": "run-aaaa-bbbb",
    "agent_name": "Summarise this week's mail",
    "status": "completed",
    "inputs": {"task": "Summarise this week's mail"},
    "outputs": {"result": "done"},
    "provider": "anthropic_oauth",
    "model": "claude-opus-5",
    "log_path": None,
    "started_at": "2026-03-27T10:00:00",
    "completed_at": "2026-03-27T10:00:42",
}

_PROVIDERS = [
    {"id": "anthropic_oauth", "name": "Anthropic (OAuth)", "available": True, "models": [
        {"id": "claude-opus-5", "name": "Claude Opus 5"},
    ]},
    {"id": "codex", "name": "Codex", "available": False, "models": []},
]

_HEALTH = {"status": "healthy", "version": "0.1.0", "platform": "test",
           "modules": {"computer_use": True}}


class _FakeAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            self._json(200, _HEALTH)
        elif self.path == "/api/providers":
            self._json(200, _PROVIDERS)
        elif self.path.startswith("/api/runs/"):
            self._json(200, _RUN)
        elif self.path == "/api/runs" or self.path.startswith("/api/runs?"):
            self._json(200, [_RUN])
        else:
            self._json(404, {"detail": "Not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/api/runs":
            if not body.get("task"):
                self._json(422, {"detail": [
                    {"loc": ["body", "task"], "msg": "Field required", "type": "missing"}
                ]})
                return
            self._json(202, {**_RUN, "id": "run-new-123", "status": "queued",
                             "agent_name": body["task"]})
        elif "/cancel" in self.path:
            self._json(200, {**_RUN, "status": "failed"})
        elif "/resume" in self.path:
            self._json(200, {"run_id": "run-aaaa-bbbb", "status": "running",
                             "message": "Resuming"})
        else:
            self._json(404, {"detail": "Not found"})

    def do_PUT(self):
        self._json(404, {"detail": "Not found"})

    def do_DELETE(self):
        self._json(404, {"detail": "Not found"})

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        assert "runs" in r.stdout
        assert "run" in r.stdout
        assert "start" in r.stdout

    def test_root_help_offers_no_deleted_groups(self):
        r = _run("--help")
        for gone in ("agents", "registry", " ps "):
            assert gone not in r.stdout, f"--help still offers {gone!r}"

    def test_runs_help(self):
        r = _run("runs", "--help")
        assert "list" in r.stdout
        assert "cancel" in r.stdout
        assert "resume" in r.stdout

    def test_runs_help_offers_no_deleted_commands(self):
        r = _run("runs", "--help")
        assert "approve" not in r.stdout
        assert "logs" not in r.stdout


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


class TestProviders:
    def test_lists_providers(self):
        r = _run("providers")
        assert r.returncode == 0
        assert "anthropic_oauth" in r.stdout or "Anthropic" in r.stdout


# -----------------------------------------------------------------------
# The trigger
# -----------------------------------------------------------------------

class TestRun:
    def test_starts_a_run_from_a_sentence(self):
        r = _run("run", "Summarise this week's mail", "--background")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "run-new-123" in r.stdout

    def test_json_prints_the_row(self):
        r = _run("run", "Summarise this week's mail", "--background", "--json")
        assert r.returncode == 0
        row = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
        assert row["id"] == "run-new-123"
        assert row["agent_name"] == "Summarise this week's mail"

    def test_provider_without_model_is_a_usage_error(self):
        r = _run("run", "do a thing", "--provider", "codex")
        assert r.returncode == 2, r.stdout + r.stderr

    def test_empty_task_is_a_usage_error(self):
        r = _run("run", "   ")
        assert r.returncode == 2

    def test_missing_task_is_a_usage_error(self):
        r = _run("run")
        assert r.returncode == 2


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

    def test_shows_the_task_not_an_id(self):
        r = _run("runs", "list")
        assert "Summarise" in r.stdout


class TestRunsGet:
    def test_shows_detail(self):
        r = _run("runs", "get", "run-aaaa-bbbb")
        assert r.returncode == 0
        assert "run-aaaa-bbbb" in r.stdout
        assert "Summarise" in r.stdout


class TestRunsCancel:
    def test_cancels(self):
        r = _run("runs", "cancel", "run-aaaa-bbbb")
        assert r.returncode == 0
        assert "Cancelled" in r.stdout or "cancelled" in r.stdout


class TestRunsResume:
    def test_resumes(self):
        r = _run("runs", "resume", "run-aaaa-bbbb")
        assert r.returncode == 0
        assert "Resuming" in r.stdout or "resuming" in r.stdout


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
        assert r.returncode == 3
        assert "not running" in r.stdout or "not running" in r.stderr

    def test_unknown_subcommand(self):
        r = _run("runs", "nonexistent")
        assert r.returncode != 0

    def test_missing_required_arg(self):
        r = _run("runs", "get")
        assert r.returncode != 0

    def test_runs_get_empty_id(self):
        """'runs get ""' should fail gracefully, not crash with AttributeError."""
        r = _run("runs", "get", "")
        assert r.returncode != 0
        output = (r.stdout + r.stderr).lower()
        assert "required" in output or "not found" in output

    def test_validation_error_readable(self):
        """A 422 from the API shows a human-readable message, not raw JSON."""
        r = _run("run", "-", "--background")
        output = r.stdout + r.stderr
        assert "[{" not in output
