"""Tests for interactive run prompting."""

from unittest import mock

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


class TestShowInputs:
    def test_agents_get_shows_inputs(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as m:
            m.return_value = {
                "id": "abc", "name": "Test", "status": "ready",
                "provider": "claude_code", "description": "Does stuff",
                "steps": [{"name": "Step 1", "computer_use": False}],
                "input_schema": [
                    {"name": "data_file", "type": "file", "required": True, "description": "CSV data"},
                    {"name": "query", "type": "text", "required": True, "description": "What to analyze"},
                    {"name": "format", "type": "text", "required": False, "description": "Output format"},
                ],
                "output_schema": [
                    {"name": "report", "type": ".pdf", "required": True, "description": "Analysis report"},
                ],
            }
            result = runner.invoke(agents_group, ["get", "abc"], obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "data_file" in result.output
            assert "required" in result.output.lower()
            assert "report" in result.output


class TestInteractiveRun:
    def test_prompts_for_text_inputs(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as mg, \
             mock.patch("cli.commands.agents.api_post") as mp:
            mg.return_value = [{
                "id": "abc", "name": "test-agent", "status": "ready",
                "input_schema": [
                    {"name": "query", "type": "text", "required": True, "description": "Search query"},
                ],
            }]
            mp.return_value = {"run_id": "run-123"}

            result = runner.invoke(agents_group, ["run", "test-agent"],
                                   input="hello world\n", obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "run-123" in result.output

    def test_skips_prompts_when_flags_provided(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as mg, \
             mock.patch("cli.commands.agents.api_post") as mp:
            mg.return_value = [{
                "id": "abc", "name": "test-agent", "status": "ready",
                "input_schema": [
                    {"name": "query", "type": "text", "required": True, "description": "Search query"},
                ],
            }]
            mp.return_value = {"run_id": "run-456"}

            result = runner.invoke(agents_group, ["run", "test-agent", "-i", "query=from flags"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "run-456" in result.output

    def test_shows_missing_inputs_error(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as mg:
            mg.return_value = [{
                "id": "abc", "name": "test-agent", "status": "ready",
                "input_schema": [
                    {"name": "query", "type": "text", "required": True, "description": "Search query"},
                ],
            }]
            # Empty input (user just hits enter)
            result = runner.invoke(agents_group, ["run", "test-agent"],
                                   input="\n", obj={"api_url": "http://x"})
            assert result.exit_code != 0 or "required" in result.output.lower()
