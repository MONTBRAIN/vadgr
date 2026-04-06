"""Tests for cli/commands -- info, agents, runs.

All API commands use a mocked HTTP layer via patching cli.client functions.
"""

from unittest import mock

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


# -- Info commands --

class TestHealth:
    def test_healthy(self, runner):
        from cli.commands.info import health
        with mock.patch("cli.commands.info.api_get") as m:
            m.return_value = {"status": "healthy", "version": "0.1.0"}
            result = runner.invoke(health, [], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "healthy" in result.output

    def test_api_down(self, runner):
        from cli.commands.info import health
        with mock.patch("cli.commands.info.api_get") as m:
            m.side_effect = click.ClickException("API is not running")
            result = runner.invoke(health, [], obj={"api_url": "http://x"})
            assert result.exit_code != 0


class TestProviders:
    def test_lists_providers(self, runner):
        from cli.commands.info import providers
        with mock.patch("cli.commands.info.api_get") as m:
            m.return_value = [
                {"id": "claude_code", "name": "Claude Code", "available": True, "models": [
                    {"id": "opus", "name": "Opus"}
                ]},
                {"id": "codex", "name": "Codex", "available": False, "models": []},
            ]
            result = runner.invoke(providers, [], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "Claude Code" in result.output
            assert "Codex" in result.output


# -- Agent commands --

class TestAgentsList:
    def test_lists_agents(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as m:
            m.return_value = [
                {"id": "abc", "name": "My Agent", "status": "ready", "steps": [{"name": "s1"}], "computer_use": False}
            ]
            result = runner.invoke(agents_group, ["list"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "My Agent" in result.output
            assert "ready" in result.output

    def test_no_agents(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as m:
            m.return_value = []
            result = runner.invoke(agents_group, ["list"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "No agents" in result.output


_AGENT_DETAIL = {
    "id": "abc-123", "name": "My Agent", "status": "ready",
    "description": "Does stuff", "provider": "claude_code",
    "steps": [{"name": "Step 1", "computer_use": False}],
}
_AGENT_LIST = [_AGENT_DETAIL]


def _mock_get_side_effect(ctx, path):
    if path == "/api/agents":
        return _AGENT_LIST
    return _AGENT_DETAIL


class TestAgentsGet:
    def test_shows_detail(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get", side_effect=_mock_get_side_effect):
            result = runner.invoke(agents_group, ["get", "abc-123"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "My Agent" in result.output
            assert "abc-123" in result.output


class TestAgentsDelete:
    def test_deletes(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get", side_effect=_mock_get_side_effect), \
             mock.patch("cli.commands.agents.api_delete") as m:
            m.return_value = {"deleted": True}
            result = runner.invoke(agents_group, ["delete", "abc-123"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "Deleted" in result.output


class TestAgentsRun:
    def test_triggers_run(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as mg, \
             mock.patch("cli.commands.agents.api_post") as mp:
            mg.return_value = [
                {"id": "abc-123", "name": "my-agent", "status": "ready"}
            ]
            mp.return_value = {"run_id": "run-456", "status": "queued"}
            result = runner.invoke(agents_group, ["run", "my-agent"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "run-456" in result.output

    def test_agent_not_found(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as m:
            m.return_value = []
            result = runner.invoke(agents_group, ["run", "nonexistent"], obj={"api_url": "http://x"})
            assert result.exit_code != 0
            assert "not found" in result.output.lower() or "No agent" in result.output


# -- Run commands --

class TestRunsList:
    def test_lists_runs(self, runner):
        from cli.commands.runs import runs_group
        with mock.patch("cli.commands.runs.api_get") as m:
            m.return_value = [
                {"id": "run-1", "agent_name": "my-agent", "status": "completed", "duration": 45.2,
                 "created_at": "2026-03-27T10:00:00"},
            ]
            result = runner.invoke(runs_group, ["list"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "run-1" in result.output

    def test_filter_by_status(self, runner):
        from cli.commands.runs import runs_group
        with mock.patch("cli.commands.runs.api_get") as m:
            m.return_value = []
            result = runner.invoke(runs_group, ["list", "--status", "failed"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            m.assert_called_once_with(mock.ANY, "/api/runs?status=failed")


_RUN_FULL_ID = "abcd1234-5678-9012-3456-789012345678"
_RUN_PARTIAL_ID = "abcd1234"
_RUN_DETAIL = {
    "id": _RUN_FULL_ID, "agent_name": "my-agent", "status": "completed",
    "provider": "claude_code", "model": "opus", "duration": 30.5,
    "created_at": "2026-03-27T10:00:00", "steps": [],
}
_RUN_LIST = [{"id": _RUN_FULL_ID, "agent_name": "my-agent", "status": "completed", "duration": 30.5}]


def _mock_runs_get(ctx, path):
    if path == "/api/runs":
        return _RUN_LIST
    if path == f"/api/runs/{_RUN_FULL_ID}":
        return _RUN_DETAIL
    if path == f"/api/runs/{_RUN_FULL_ID}/logs":
        return [{"timestamp": "10:00:01", "type": "agent_log", "message": "Starting step 1"}]
    return None


class TestRunsGet:
    def test_shows_detail(self, runner):
        from cli.commands.runs import runs_group
        _detail = {
            "id": "run-1", "agent_name": "my-agent", "status": "completed",
            "provider": "claude_code", "model": "opus", "duration": 30.5,
            "created_at": "2026-03-27T10:00:00",
            "steps": [{"name": "Step 1", "status": "completed"}],
        }
        def _side(ctx, path):
            if path == "/api/runs":
                return [{"id": "run-1", "agent_name": "my-agent", "status": "completed", "duration": 30.5}]
            return _detail
        with mock.patch("cli.commands.runs.api_get", side_effect=_side):
            result = runner.invoke(runs_group, ["get", "run-1"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "run-1" in result.output

    def test_resolves_partial_id(self, runner):
        from cli.commands.runs import runs_group
        with mock.patch("cli.commands.runs.api_get", side_effect=_mock_runs_get):
            result = runner.invoke(runs_group, ["get", _RUN_PARTIAL_ID], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert _RUN_FULL_ID in result.output


class TestRunsCancel:
    def test_cancels(self, runner):
        from cli.commands.runs import runs_group
        with mock.patch("cli.commands.runs.api_get") as mg, \
             mock.patch("cli.commands.runs.api_post") as m:
            mg.return_value = [{"id": "run-1", "agent_name": "my-agent", "status": "running", "duration": 0}]
            m.return_value = {"status": "cancelled"}
            result = runner.invoke(runs_group, ["cancel", "run-1"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "Cancelled" in result.output or "cancelled" in result.output

    def test_cancel_resolves_partial_id(self, runner):
        from cli.commands.runs import runs_group
        with mock.patch("cli.commands.runs.api_get", side_effect=_mock_runs_get), \
             mock.patch("cli.commands.runs.api_post") as mp:
            mp.return_value = {"status": "cancelled"}
            result = runner.invoke(runs_group, ["cancel", _RUN_PARTIAL_ID], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            mp.assert_called_once_with(mock.ANY, f"/api/runs/{_RUN_FULL_ID}/cancel")

    def test_cancel_empty_id(self, runner):
        from cli.commands.runs import runs_group
        result = runner.invoke(runs_group, ["cancel", ""], obj={"api_url": "http://x"})
        assert result.exit_code != 0
        assert "Run ID is required." in result.output


class TestRunsApprove:
    def test_approve_resolves_partial_id(self, runner):
        from cli.commands.runs import runs_group
        with mock.patch("cli.commands.runs.api_get", side_effect=_mock_runs_get), \
             mock.patch("cli.commands.runs.api_post") as mp:
            mp.return_value = {"status": "approved"}
            result = runner.invoke(runs_group, ["approve", _RUN_PARTIAL_ID], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            mp.assert_called_once_with(mock.ANY, f"/api/runs/{_RUN_FULL_ID}/approve")

    def test_approve_empty_id(self, runner):
        from cli.commands.runs import runs_group
        result = runner.invoke(runs_group, ["approve", ""], obj={"api_url": "http://x"})
        assert result.exit_code != 0
        assert "Run ID is required." in result.output


class TestRunsLogs:
    def test_shows_logs(self, runner):
        from cli.commands.runs import runs_group
        _logs = [
            {"timestamp": "10:00:01", "type": "agent_log", "message": "Starting step 1"},
            {"timestamp": "10:00:05", "type": "agent_log", "message": "Done"},
        ]
        def _side(ctx, path):
            if path == "/api/runs":
                return [{"id": "run-1", "agent_name": "my-agent", "status": "completed", "duration": 10.0}]
            return _logs
        with mock.patch("cli.commands.runs.api_get", side_effect=_side):
            result = runner.invoke(runs_group, ["logs", "run-1"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "Starting step 1" in result.output

    def test_logs_resolves_partial_id(self, runner):
        from cli.commands.runs import runs_group
        with mock.patch("cli.commands.runs.api_get", side_effect=_mock_runs_get):
            result = runner.invoke(runs_group, ["logs", _RUN_PARTIAL_ID], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "Starting step 1" in result.output

    def test_logs_empty_id(self, runner):
        from cli.commands.runs import runs_group
        result = runner.invoke(runs_group, ["logs", ""], obj={"api_url": "http://x"})
        assert result.exit_code != 0
        assert "Run ID is required." in result.output
