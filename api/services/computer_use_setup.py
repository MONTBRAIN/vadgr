"""Service for managing computer use setup: venv, provider MCP configs, cache toggle.

Writes MCP server configuration for each supported CLI provider:
- Claude Code: .mcp.json (JSON, mcpServers key)
- Gemini CLI: .gemini/settings.json (JSON, mcpServers key)
- Codex CLI: .codex/config.toml (TOML, mcp_servers table)
"""

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path

from api.utils.platform import python_command, venv_pip, venv_python

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MCP_JSON_PATH = PROJECT_ROOT / ".mcp.json"
GEMINI_SETTINGS_PATH = PROJECT_ROOT / ".gemini" / "settings.json"
CODEX_CONFIG_PATH = PROJECT_ROOT / ".codex" / "config.toml"
CU_VENV_DIR = PROJECT_ROOT / "computer_use" / ".venv"
CU_REQUIREMENTS = PROJECT_ROOT / "computer_use" / "requirements.txt"
DEPS_MARKER = ".deps_installed"


def _python_command() -> str:
    """Return the correct python command for the current platform."""
    return python_command()


def _cu_venv_python() -> str:
    """Return the full path to the Python inside the computer_use venv.

    CLI tools (Codex, Gemini) start MCP servers independently -- they
    don't inherit our PATH, so bare ``python`` resolves to the system
    Python which lacks the MCP dependencies.  Using the full venv path
    works on both Windows (Scripts/python) and Linux (bin/python).
    """
    return str(venv_python(CU_VENV_DIR))


def _mcp_json_content(cache_enabled: bool = True) -> dict:
    """Build .mcp.json content with platform-correct values."""
    env = {"AGENT_FORGE_DEBUG": "1"}
    if not cache_enabled:
        env["AGENT_FORGE_CACHE_ENABLED"] = "0"
    return {
        "mcpServers": {
            "computer-use": {
                "command": _cu_venv_python(),
                "args": ["-m", "computer_use.mcp_server", "--transport", "stdio"],
                "cwd": str(PROJECT_ROOT),
                "env": env,
            }
        }
    }


def _gemini_settings_content(cache_enabled: bool = True) -> dict:
    """Build .gemini/settings.json content. Same mcpServers format as .mcp.json."""
    return _mcp_json_content(cache_enabled=cache_enabled)


def _codex_config_content(cache_enabled: bool = True) -> str:
    """Build .codex/config.toml content with MCP server configuration.

    Uses TOML literal strings (single quotes) for ``cwd`` so that Windows
    backslashes are treated as literal characters, not escape sequences.
    """
    python = _cu_venv_python()
    cwd = str(PROJECT_ROOT)
    lines = [
        '[mcp_servers.computer-use]',
        f"command = '{python}'",
        'args = ["-m", "computer_use.mcp_server", "--transport", "stdio"]',
        f"cwd = '{cwd}'",
        '',
        '[mcp_servers.computer-use.env]',
        'AGENT_FORGE_DEBUG = "1"',
    ]
    if not cache_enabled:
        lines.append('AGENT_FORGE_CACHE_ENABLED = "0"')
    lines.append('')  # trailing newline
    return '\n'.join(lines)


def _write_all_provider_configs(cache_enabled: bool = True) -> None:
    """Write MCP config files for all supported providers."""
    # Claude Code: .mcp.json
    content = _mcp_json_content(cache_enabled=cache_enabled)
    MCP_JSON_PATH.write_text(json.dumps(content, indent=2) + "\n")

    # Gemini CLI: .gemini/settings.json
    GEMINI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    gemini_content = _gemini_settings_content(cache_enabled=cache_enabled)
    GEMINI_SETTINGS_PATH.write_text(json.dumps(gemini_content, indent=2) + "\n")

    # Codex CLI: .codex/config.toml
    CODEX_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODEX_CONFIG_PATH.write_text(_codex_config_content(cache_enabled=cache_enabled))


def _remove_all_provider_configs() -> None:
    """Remove MCP config files for all supported providers."""
    for path in (MCP_JSON_PATH, GEMINI_SETTINGS_PATH, CODEX_CONFIG_PATH):
        if path.exists():
            path.unlink()
            logger.info("Removed %s", path.name)


def get_status() -> dict:
    """Check current computer use status."""
    mcp_exists = MCP_JSON_PATH.exists()
    venv_exists = CU_VENV_DIR.exists()

    enabled = False
    cache_enabled = True

    if mcp_exists:
        try:
            data = json.loads(MCP_JSON_PATH.read_text())
            cu_server = data.get("mcpServers", {}).get("computer-use")
            enabled = cu_server is not None
            if cu_server:
                env = cu_server.get("env", {})
                cache_enabled = env.get("AGENT_FORGE_CACHE_ENABLED", "1") != "0"
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "enabled": enabled,
        "cache_enabled": cache_enabled,
        "venv_ready": venv_exists,
    }


def _deps_need_install() -> bool:
    """Check if pip install is needed by comparing requirements hash to marker."""
    if not CU_REQUIREMENTS.exists():
        return False
    marker = CU_VENV_DIR / DEPS_MARKER
    if not marker.exists():
        return True
    current_hash = hashlib.md5(CU_REQUIREMENTS.read_bytes()).hexdigest()
    return marker.read_text().strip() != current_hash


def _write_deps_marker() -> None:
    """Write marker file with current requirements hash after successful install."""
    if CU_REQUIREMENTS.exists():
        reqs_hash = hashlib.md5(CU_REQUIREMENTS.read_bytes()).hexdigest()
        (CU_VENV_DIR / DEPS_MARKER).write_text(reqs_hash)


def _pip_path() -> Path:
    """Return expected pip binary path inside the venv."""
    return venv_pip(CU_VENV_DIR)


def _venv_healthy() -> bool:
    """Check if the venv exists and has a working pip binary."""
    return CU_VENV_DIR.exists() and _pip_path().exists()


def enable_computer_use(cache_enabled: bool = True) -> dict:
    """Set up computer use: create venv if needed, write .mcp.json."""
    # Create venv if missing or broken (no pip)
    if not _venv_healthy():
        logger.info("Creating computer_use venv...")
        python = _python_command()
        subprocess.run(
            [python, "-m", "venv", "--clear", str(CU_VENV_DIR)],
            check=True, capture_output=True,
        )

    # Install/update deps only when requirements changed
    if _deps_need_install():
        pip = str(_pip_path())
        logger.info("Installing computer_use dependencies...")
        subprocess.run(
            [pip, "install", "-q", "-r", str(CU_REQUIREMENTS)],
            check=True, capture_output=True,
        )
        _write_deps_marker()

    # Write MCP configs for all providers
    _write_all_provider_configs(cache_enabled=cache_enabled)
    logger.info("Wrote MCP configs for all providers (cache_enabled=%s)", cache_enabled)

    return get_status()


def disable_computer_use() -> dict:
    """Remove all provider MCP configs to disable computer use. Keeps venv for re-enable."""
    _remove_all_provider_configs()
    return get_status()


def update_cache_setting(cache_enabled: bool) -> dict:
    """Update cache setting in all provider MCP configs without touching venv."""
    if not MCP_JSON_PATH.exists():
        return get_status()

    _write_all_provider_configs(cache_enabled=cache_enabled)
    logger.info("Updated cache_enabled=%s in all provider MCP configs", cache_enabled)
    return get_status()
