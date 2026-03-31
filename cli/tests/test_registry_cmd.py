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


class TestRegistryPullApiSync:
    """Regression test for issue #61: pulled agents must appear in `forge agents list`.

    `forge registry pull` installs files to ~/.forge/agents/ but must also
    register the agent with the API so `forge agents list` returns it.
    """

    def test_pull_registers_agent_with_api(self, runner):
        """After a successful pull, the agent should be imported into the API."""
        from cli.commands.registry import registry_group

        with mock.patch("cli.commands.registry.registry_client") as m_reg, \
             mock.patch("cli.commands.registry._import_to_api") as m_import:
            m_reg.pull.return_value = "/home/user/.forge/agents/test-agent"
            m_import.return_value = None

            result = runner.invoke(registry_group, ["pull", "test-agent"])

            assert result.exit_code == 0
            assert "Installed" in result.output
            m_import.assert_called_once()

    def test_pull_api_unavailable_still_succeeds(self, runner):
        """If the API is down, pull should still succeed (files installed) with a warning."""
        from cli.commands.registry import registry_group

        with mock.patch("cli.commands.registry.registry_client") as m_reg, \
             mock.patch("cli.commands.agents._upload_agnt") as m_upload:
            m_reg.pull.return_value = "/home/user/.forge/agents/test-agent"
            m_upload.side_effect = Exception("Connection refused")

            result = runner.invoke(registry_group, ["pull", "test-agent"])

            assert result.exit_code == 0
            assert "Installed" in result.output
            # Should warn that API registration failed
            assert "API registration failed" in result.output


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
