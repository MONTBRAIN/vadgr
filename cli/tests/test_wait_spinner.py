"""Tests for wait_with_spinner and new agent commands (update, import, export)."""

from pathlib import Path
from unittest import mock
import json
import zipfile

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
            result = wait_with_spinner(ctx, "/api/agents/1",
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
                wait_with_spinner(ctx, "/api/agents/1",
                                  lambda r: r["status"] == "ready",
                                  "Working...", interval=0.01, timeout=0.05)


class TestCreateWithSpinner:
    def test_create_waits_for_ready(self, runner):
        from cli.commands.agents import agents_group

        with mock.patch("cli.commands.agents.api_post") as mp, \
             mock.patch("cli.commands.agents.wait_with_spinner") as mw:
            mp.return_value = {"id": "abc-123", "name": "test", "status": "creating"}
            mw.return_value = {"id": "abc-123", "name": "test", "status": "ready"}

            result = runner.invoke(agents_group, ["create", "--name", "test", "--description", "desc"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "ready" in result.output.lower() or "test" in result.output
            mw.assert_called_once()


class TestUpdateCommand:
    def _mock_get(self, ctx, path):
        if path == "/api/agents":
            return [{"id": "abc", "name": "test", "status": "ready"}]
        return {"id": "abc", "name": "test", "status": "ready"}

    def test_update_name(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get", side_effect=self._mock_get), \
             mock.patch("cli.commands.agents.api_put") as mp:
            mp.return_value = {"id": "abc", "name": "new-name", "status": "ready"}
            result = runner.invoke(agents_group, ["update", "abc", "--name", "new-name"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "Updated" in result.output

    def test_update_description_triggers_spinner(self, runner):
        from cli.commands.agents import agents_group
        with mock.patch("cli.commands.agents.api_get", side_effect=self._mock_get), \
             mock.patch("cli.commands.agents.api_put") as mp, \
             mock.patch("cli.commands.agents.wait_with_spinner") as mw:
            mp.return_value = {"id": "abc", "name": "test", "status": "updating"}
            mw.return_value = {"id": "abc", "name": "test", "status": "ready"}
            result = runner.invoke(agents_group, ["update", "abc", "--description", "new desc"],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            mw.assert_called_once()


class TestImportCommand:
    def test_import_agnt_file(self, runner, tmp_path):
        from cli.commands.agents import agents_group

        agnt = tmp_path / "test.agnt"
        with zipfile.ZipFile(agnt, "w") as zf:
            zf.writestr("agent-forge.json", json.dumps({"name": "imported"}))
            zf.writestr("agent.bundle", b"fake")

        with mock.patch("cli.commands.agents._upload_agnt") as mu, \
             mock.patch("cli.commands.agents.wait_with_spinner") as mw:
            mu.return_value = {"id": "imp-123", "name": "imported", "status": "importing"}
            mw.return_value = {"id": "imp-123", "name": "imported", "status": "ready"}
            result = runner.invoke(agents_group, ["import", str(agnt)],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert "imported" in result.output


class TestExportCommand:
    def test_export_writes_file(self, runner, tmp_path):
        from cli.commands.agents import agents_group

        def mock_get(ctx, path):
            if path == "/api/agents":
                return [{"id": "abc-123", "name": "test", "status": "ready"}]
            return {"id": "abc-123", "name": "test", "status": "ready"}

        output = tmp_path / "exported.agnt"
        with mock.patch("cli.commands.agents.api_get", side_effect=mock_get), \
             mock.patch("cli.commands.agents._download_binary") as md:
            md.return_value = b"fake zip content"
            result = runner.invoke(agents_group, ["export", "abc-123", "-o", str(output)],
                                   obj={"api_url": "http://x"})
            assert result.exit_code == 0
            assert output.exists()
            assert "Exported" in result.output
