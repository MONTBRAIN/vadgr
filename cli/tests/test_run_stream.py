"""Tests for run streaming and --background flag."""

import json
from unittest import mock

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


class TestStepParsing:
    def test_detects_step_start(self):
        from cli.stream import _STEP_PATTERN
        msg = "--- Step 1: Review CV ---"
        match = _STEP_PATTERN.search(msg)
        assert match
        assert match.group(1) == "1"
        assert "Review CV" in match.group(2)

    def test_detects_step_with_slash(self):
        from cli.stream import _STEP_PATTERN
        msg = "--- Step 2/3: Generate Report ---"
        match = _STEP_PATTERN.search(msg)
        assert match
        assert match.group(1) == "2"

    def test_ignores_regular_log(self):
        from cli.stream import _STEP_PATTERN
        msg = "Reading file contents..."
        assert _STEP_PATTERN.search(msg) is None


class TestRunWithBackground:
    def test_background_flag_skips_stream(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as mg, \
             mock.patch("cli.commands.agents.api_post") as mp:
            mg.return_value = [{
                "id": "abc", "name": "test", "status": "ready",
                "input_schema": [],
            }]
            mp.return_value = {"run_id": "run-999"}
            result = runner.invoke(agents_group, ["run", "test", "--background"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "run-999" in result.output

    def test_without_background_calls_follow(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get") as mg, \
             mock.patch("cli.commands.agents.api_post") as mp, \
             mock.patch("cli.commands.agents.follow_run") as mf:
            mg.return_value = [{
                "id": "abc", "name": "test", "status": "ready",
                "input_schema": [],
            }]
            mp.return_value = {"run_id": "run-999"}
            result = runner.invoke(agents_group, ["run", "test"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            mf.assert_called_once_with("http://x", "run-999")
