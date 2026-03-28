"""Tests for cli/commands/registry.py."""

from unittest import mock

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


class TestRegistryPack:
    def test_pack_success(self, runner, tmp_path):
        from cli.commands.registry import registry_group
        agent_dir = tmp_path / "my-agent"
        agent_dir.mkdir()
        (agent_dir / "agentic.md").write_text("# Test")

        with mock.patch("cli.commands.registry.registry_client") as m:
            m.pack.return_value = "/tmp/my-agent-0.1.0.agnt"
            result = runner.invoke(registry_group, ["pack", str(agent_dir)])
            assert result.exit_code == 0
            assert "Packed" in result.output
            m.pack.assert_called_once()

    def test_pack_missing_folder(self, runner):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, ["pack", "/nonexistent"])
        assert result.exit_code != 0


class TestRegistryPull:
    def test_pull_success(self, runner):
        from cli.commands.registry import registry_group
        with mock.patch("cli.commands.registry.registry_client") as m:
            m.pull.return_value = "/home/user/.forge/agents/test-agent"
            result = runner.invoke(registry_group, ["pull", "test-agent"])
            assert result.exit_code == 0
            assert "Installed" in result.output

    def test_pull_not_found(self, runner):
        from cli.commands.registry import registry_group
        with mock.patch("cli.commands.registry.registry_client") as m:
            m.pull.side_effect = ValueError("Agent 'nope' not found")
            result = runner.invoke(registry_group, ["pull", "nope"])
            assert result.exit_code != 0
            assert "not found" in result.output


class TestRegistryPush:
    def test_push_success(self, runner, tmp_path):
        from cli.commands.registry import registry_group
        agnt = tmp_path / "test.agnt"
        agnt.write_text("fake")
        with mock.patch("cli.commands.registry.registry_client") as m:
            m.push.return_value = "Published test@0.1.0"
            result = runner.invoke(registry_group, ["push", str(agnt)])
            assert result.exit_code == 0
            assert "Published" in result.output


class TestRegistrySearch:
    def test_search_found(self, runner):
        from cli.commands.registry import registry_group
        with mock.patch("cli.commands.registry.registry_client") as m:
            m.search.return_value = [
                {"name": "test-agent", "version": "0.1.0", "description": "A test"}
            ]
            result = runner.invoke(registry_group, ["search", "test"])
            assert result.exit_code == 0
            assert "test-agent" in result.output

    def test_search_empty(self, runner):
        from cli.commands.registry import registry_group
        with mock.patch("cli.commands.registry.registry_client") as m:
            m.search.return_value = []
            result = runner.invoke(registry_group, ["search", "nothing"])
            assert result.exit_code == 0
            assert "No agents found" in result.output


class TestRegistryAgents:
    def test_list_installed(self, runner):
        from cli.commands.registry import registry_group
        with mock.patch("cli.commands.registry.registry_client") as m:
            m.agents.return_value = [
                {"name": "my-agent", "version": "1.0.0", "steps": 3, "description": "Cool agent"}
            ]
            result = runner.invoke(registry_group, ["agents"])
            assert result.exit_code == 0
            assert "my-agent" in result.output

    def test_no_agents(self, runner):
        from cli.commands.registry import registry_group
        with mock.patch("cli.commands.registry.registry_client") as m:
            m.agents.return_value = []
            result = runner.invoke(registry_group, ["agents"])
            assert result.exit_code == 0
            assert "No agents installed" in result.output
