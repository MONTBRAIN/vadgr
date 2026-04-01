"""Tests for settings commands and computer use gate on run."""

from unittest import mock

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


class TestComputerUseEnable:
    def test_enable(self, runner):
        from cli.commands.info import computer_use
        with mock.patch("cli.commands.info.api_put") as mp:
            mp.return_value = {"enabled": True}
            result = runner.invoke(computer_use, ["enable"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "enabled" in result.output.lower()

    def test_disable(self, runner):
        from cli.commands.info import computer_use
        with mock.patch("cli.commands.info.api_put") as mp:
            mp.return_value = {"enabled": False}
            result = runner.invoke(computer_use, ["disable"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "disabled" in result.output.lower()

    def test_status(self, runner):
        from cli.commands.info import computer_use
        with mock.patch("cli.commands.info.api_get") as mg:
            mg.return_value = {"enabled": True}
            result = runner.invoke(computer_use, ["status"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "enabled" in result.output.lower()


class TestComputerUseTimeout:
    """Regression test for issue #67: enable times out but says API is not running."""

    def test_timeout_shows_timeout_message_not_api_down(self, runner):
        """When the API request times out, the error should say timeout, not 'API is not running'."""
        import socket

        from cli.commands.info import computer_use
        with mock.patch("cli.commands.info.api_put") as mp:
            mp.side_effect = click.ClickException(
                "Request timed out. The operation may still be running -- check with: forge computer-use status"
            )
            result = runner.invoke(computer_use, ["enable"], obj={"api_url": "http://x"})
            assert result.exit_code != 0
            assert "timed out" in result.output.lower()
            assert "API is not running" not in result.output


class TestRunBlocksWithoutComputerUse:
    def test_blocks_desktop_agent_when_disabled(self, runner):
        from cli.commands.agents import agents_group

        def mock_get(ctx, path):
            if path == "/api/agents":
                return [{"id": "abc", "name": "desktop-agent", "status": "ready",
                         "computer_use": True, "input_schema": []}]
            if path == "/api/settings/computer-use":
                return {"enabled": False}
            return {}

        with mock.patch("cli.commands.agents.api_get", side_effect=mock_get):
            result = runner.invoke(agents_group, ["run", "desktop-agent", "--background"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code != 0
            assert "computer use" in result.output.lower() or "computer use" in (result.exception or "")

    def test_allows_non_desktop_agent(self, runner):
        from cli.commands.agents import agents_group

        def mock_get(ctx, path):
            if path == "/api/agents":
                return [{"id": "abc", "name": "cli-agent", "status": "ready",
                         "computer_use": False, "input_schema": []}]
            return {}

        with mock.patch("cli.commands.agents.api_get", side_effect=mock_get), \
             mock.patch("cli.commands.agents.api_post") as mp:
            mp.return_value = {"run_id": "run-123"}
            result = runner.invoke(agents_group, ["run", "cli-agent", "--background"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
