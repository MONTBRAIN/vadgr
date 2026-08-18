"""Tests for wait_with_spinner."""

from unittest import mock

import click
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


class TestWaitWithSpinner:
    def test_returns_when_done(self):
        from cli.output import wait_with_spinner

        ctx = click.Context(click.Command("test"))
        ctx.ensure_object(dict)
        ctx.obj["api_url"] = "http://x"

        call_count = 0
        def mock_get(ctx, path):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return {"status": "ready", "name": "my-agent"}
            return {"status": "creating", "name": "my-agent"}

        with mock.patch("cli.output.api_get", mock_get):
            result = wait_with_spinner(ctx, "/api/runs/1",
                                       lambda r: r["status"] not in ("creating", "updating", "importing"),
                                       "Working...", interval=0.01, timeout=5)
        assert result["status"] == "ready"
        assert call_count >= 2

    def test_raises_on_timeout(self):
        from cli.output import wait_with_spinner

        ctx = click.Context(click.Command("test"))
        ctx.ensure_object(dict)
        ctx.obj["api_url"] = "http://x"

        with mock.patch("cli.output.api_get", return_value={"status": "creating"}):
            with pytest.raises(click.ClickException, match="timed out"):
                wait_with_spinner(ctx, "/api/runs/1",
                                  lambda r: r["status"] == "ready",
                                  "Working...", interval=0.01, timeout=0.05)
