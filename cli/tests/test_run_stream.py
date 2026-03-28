"""Tests for run streaming and --background flag."""

import json
from unittest import mock

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


class TestStepDetection:
    def test_detects_step_from_data_fields(self):
        from cli.stream import _extract_step
        data = {"step_num": 1, "step_name": "Review CV", "message": "--- Step 1: Review CV [CLI] ---"}
        num, name = _extract_step(data, current_num=None)
        assert num == 1
        assert name == "Review CV"

    def test_detects_new_step(self):
        from cli.stream import _extract_step
        data = {"step_num": 2, "step_name": "Generate Report", "message": "something"}
        num, name = _extract_step(data, current_num=1)
        assert num == 2
        assert name == "Generate Report"

    def test_returns_none_for_same_step(self):
        from cli.stream import _extract_step
        data = {"step_num": 1, "step_name": "Review CV", "message": "Reading file..."}
        num, name = _extract_step(data, current_num=1)
        assert num is None
        assert name is None

    def test_returns_none_without_step_fields(self):
        from cli.stream import _extract_step
        data = {"message": "Just a regular log line"}
        num, name = _extract_step(data, current_num=1)
        assert num is None
        assert name is None

    def test_handles_missing_step_name(self):
        from cli.stream import _extract_step
        data = {"step_num": 3, "message": "--- Step 3 ---"}
        num, name = _extract_step(data, current_num=2)
        assert num == 3
        assert name == "Step 3"

    def test_long_step_name_truncated(self):
        from cli.stream import _extract_step
        long_name = "Check LinkedIn Jobs. Exclude for updates the ones that does not appeared in extracted info from CV."
        data = {"step_num": 2, "step_name": long_name}
        num, name = _extract_step(data, current_num=1)
        assert num == 2
        assert len(name) <= 50


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
