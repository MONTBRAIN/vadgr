"""Tests for the Click CLI commands."""

import json
import zipfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from cli.commands.registry import registry_group as cli


@pytest.fixture
def runner():
    return CliRunner()


class TestPackCommand:

    def test_pack_valid_folder(self, runner, sample_agent_folder, tmp_path):
        output = tmp_path / "test.agnt"
        result = runner.invoke(cli, ["pack", str(sample_agent_folder), "-o", str(output)])
        assert result.exit_code == 0
        assert "Packed:" in result.output
        assert output.exists()

    def test_pack_missing_folder(self, runner, tmp_path):
        result = runner.invoke(cli, ["pack", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0

    def test_pack_folder_without_agentic(self, runner, tmp_path):
        folder = tmp_path / "bad"
        folder.mkdir()
        result = runner.invoke(cli, ["pack", str(folder)])
        assert result.exit_code != 0
        assert "agentic.md" in result.output


class TestPullCommand:

    @patch("registry.registry_client.pull")
    def test_pull_success(self, mock_pull, runner):
        mock_pull.return_value = "/home/user/.forge/agents/test-agent"
        result = runner.invoke(cli, ["pull", "test-agent"])
        assert result.exit_code == 0
        assert "Installed:" in result.output

    @patch("registry.registry_client.pull")
    def test_pull_not_found(self, mock_pull, runner):
        mock_pull.side_effect = ValueError("Agent 'nope' not found")
        result = runner.invoke(cli, ["pull", "nope"])
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("registry.registry_client.pull")
    def test_pull_already_installed(self, mock_pull, runner):
        mock_pull.side_effect = FileExistsError("already installed")
        result = runner.invoke(cli, ["pull", "test-agent"])
        assert result.exit_code != 0
        assert "already installed" in result.output

    @patch("registry.registry_client.pull")
    def test_pull_with_force(self, mock_pull, runner):
        mock_pull.return_value = "/home/user/.forge/agents/test-agent"
        result = runner.invoke(cli, ["pull", "test-agent", "--force"])
        assert result.exit_code == 0
        mock_pull.assert_called_once()
        args, kwargs = mock_pull.call_args
        assert args == ("test-agent",)
        assert kwargs["registry_name"] is None
        assert kwargs["force"] is True

    @patch("registry.registry_client.pull")
    def test_pull_specific_registry(self, mock_pull, runner):
        mock_pull.return_value = "/path/to/agent"
        result = runner.invoke(cli, ["pull", "test-agent", "-r", "my-registry"])
        assert result.exit_code == 0
        mock_pull.assert_called_once()
        args, kwargs = mock_pull.call_args
        assert args == ("test-agent",)
        assert kwargs["registry_name"] == "my-registry"
        assert kwargs["force"] is False


class TestPushCommand:

    @patch("registry.registry_client.push")
    def test_push_success(self, mock_push, runner, sample_agnt_file):
        mock_push.return_value = "Published test-agent@0.1.0"
        result = runner.invoke(cli, ["push", str(sample_agnt_file)])
        assert result.exit_code == 0
        assert "Published" in result.output

    def test_push_missing_file(self, runner, tmp_path):
        result = runner.invoke(cli, ["push", str(tmp_path / "nope.agnt")])
        assert result.exit_code != 0

    @patch("registry.registry_client.push")
    def test_push_no_token(self, mock_push, runner, sample_agnt_file):
        mock_push.side_effect = RuntimeError("GitHub token required")
        result = runner.invoke(cli, ["push", str(sample_agnt_file)])
        assert result.exit_code != 0
        assert "token" in result.output.lower()


class TestSearchCommand:

    @patch("registry.registry_client.search")
    def test_search_with_results(self, mock_search, runner):
        mock_search.return_value = [
            {"name": "data-analysis", "version": "1.0.0", "description": "Analyze data"},
            {"name": "data-viz", "version": "0.2.0", "description": "Visualize data"},
        ]
        result = runner.invoke(cli, ["search", "data"])
        assert result.exit_code == 0
        assert "data-analysis" in result.output
        assert "data-viz" in result.output

    @patch("registry.registry_client.search")
    def test_search_no_results(self, mock_search, runner):
        mock_search.return_value = []
        result = runner.invoke(cli, ["search", "nonexistent"])
        assert result.exit_code == 0
        assert "No agents found" in result.output


class TestAgentsCommand:

    @patch("registry.registry_client.agents")
    def test_agents_with_installed(self, mock_agents, runner):
        mock_agents.return_value = [
            {"name": "research", "version": "1.0.0", "steps": 3, "description": "Research agent"},
        ]
        result = runner.invoke(cli, ["agents"])
        assert result.exit_code == 0
        assert "research" in result.output
        assert "1.0.0" in result.output

    @patch("registry.registry_client.agents")
    def test_agents_empty(self, mock_agents, runner):
        mock_agents.return_value = []
        result = runner.invoke(cli, ["agents"])
        assert result.exit_code == 0
        assert "No agents installed" in result.output


class TestPackE2E:
    """End-to-end test: pack a real example agent from forge/examples/."""

    def test_pack_research_paper_example(self, runner, tmp_path):
        example_path = Path("/home/santiago/MakeHistory/Agent-Forge/forge/examples/research-paper")
        if not example_path.exists():
            pytest.skip("forge/examples/research-paper not found")
        output = tmp_path / "research-paper.agnt"
        result = runner.invoke(cli, ["pack", str(example_path), "-o", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        # Verify contents
        with zipfile.ZipFile(output) as zf:
            assert "agent-forge.json" in zf.namelist()
            assert "agent.bundle" in zf.namelist()
            manifest = json.loads(zf.read("agent-forge.json"))
            assert "research-paper" in manifest["name"]
