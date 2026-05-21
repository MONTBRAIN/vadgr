"""Decommission tests for the 0.2.0 gateway removal milestone.

These tests verify that the Discord gateway has been fully removed from the
codebase per ARCHITECTURE.md sections 4.4 and 10.2.  They are intentionally
narrow: each one pins one piece of the removal so the deletion can't silently
regress.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_gateway_directory_removed():
    """vadgr/gateway/ must not exist."""
    assert not (REPO_ROOT / "gateway").exists(), (
        "gateway/ directory still present"
    )


def test_gateway_cli_module_removed():
    """cli/commands/gateway_cmd.py must not exist."""
    assert not (REPO_ROOT / "cli" / "commands" / "gateway_cmd.py").exists()


def test_gateway_cli_import_fails():
    """`cli.commands.gateway_cmd` must not be importable."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("cli.commands.gateway_cmd")


def test_gateway_service_module_removed():
    """api/services/gateway_setup.py must not exist."""
    assert not (REPO_ROOT / "api" / "services" / "gateway_setup.py").exists()


def test_gateway_service_import_fails():
    """`api.services.gateway_setup` must not be importable."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("api.services.gateway_setup")


def test_no_gateway_routes_registered():
    """API must not register any /gateway or /messaging-gateway routes."""
    from api.main import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    offending = [p for p in paths if "gateway" in p.lower()]
    assert offending == [], f"gateway routes still registered: {offending}"


def test_no_gateway_cli_command():
    """`vadgr gateway` must not be a registered Click subcommand."""
    from click.testing import CliRunner

    from cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["gateway", "--help"])
    # Click returns exit code 2 with "No such command" when the command is gone.
    assert result.exit_code != 0
    assert "gateway" not in (cli.commands or {})


def test_frontend_messaging_gateway_hook_removed():
    """frontend/src/hooks/useMessagingGateway.ts must not exist."""
    assert not (
        REPO_ROOT / "frontend" / "src" / "hooks" / "useMessagingGateway.ts"
    ).exists()


def test_frontend_settings_has_no_gateway_references():
    """frontend/src/pages/Settings.tsx must contain no gateway references."""
    settings_path = REPO_ROOT / "frontend" / "src" / "pages" / "Settings.tsx"
    assert settings_path.exists(), "Settings.tsx missing"
    text = settings_path.read_text()
    lowered = text.lower()
    assert "gateway" not in lowered, "Settings.tsx still references gateway"
    assert "discord" not in lowered, "Settings.tsx still references discord"
    assert "messaging-gateway" not in lowered


def test_readme_has_no_gateway_section():
    """README.md must not mention the gateway module."""
    readme = (REPO_ROOT / "README.md").read_text()
    lowered = readme.lower()
    assert "gateway/" not in lowered, "README still references gateway/ path"
    # Allow incidental wording like "API gateway" elsewhere; pin the
    # specific phrases that describe the deleted module.
    assert "messaging integration" not in lowered or "discord" not in lowered, (
        "README still describes Discord messaging integration"
    )
    assert "discord gateway" not in lowered
