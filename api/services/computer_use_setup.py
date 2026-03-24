"""Service for managing computer use setup: venv, .mcp.json, cache toggle."""

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MCP_JSON_PATH = PROJECT_ROOT / ".mcp.json"
CU_VENV_DIR = PROJECT_ROOT / "computer_use" / ".venv"
CU_REQUIREMENTS = PROJECT_ROOT / "computer_use" / "requirements.txt"
DEPS_MARKER = ".deps_installed"


def _python_command() -> str:
    """Return the correct python command for the current platform."""
    if sys.platform == "win32":
        return "python"
    return "python3"


def _mcp_json_content(cache_enabled: bool = True) -> dict:
    """Build .mcp.json content with platform-correct values."""
    env = {"AGENT_FORGE_DEBUG": "1"}
    if not cache_enabled:
        env["AGENT_FORGE_CACHE_ENABLED"] = "0"
    return {
        "mcpServers": {
            "computer-use": {
                "command": _python_command(),
                "args": ["-m", "computer_use.mcp_server", "--transport", "stdio"],
                "cwd": str(PROJECT_ROOT),
                "env": env,
            }
        }
    }


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
    if sys.platform == "win32":
        return CU_VENV_DIR / "Scripts" / "pip"
    return CU_VENV_DIR / "bin" / "pip"


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

    # Write .mcp.json
    content = _mcp_json_content(cache_enabled=cache_enabled)
    MCP_JSON_PATH.write_text(json.dumps(content, indent=2) + "\n")
    logger.info("Wrote .mcp.json (cache_enabled=%s)", cache_enabled)

    return get_status()


def disable_computer_use() -> dict:
    """Remove .mcp.json to disable computer use. Keeps venv for re-enable."""
    if MCP_JSON_PATH.exists():
        MCP_JSON_PATH.unlink()
        logger.info("Removed .mcp.json")
    return get_status()


def update_cache_setting(cache_enabled: bool) -> dict:
    """Update cache setting in .mcp.json without touching venv."""
    if not MCP_JSON_PATH.exists():
        return get_status()

    content = _mcp_json_content(cache_enabled=cache_enabled)
    MCP_JSON_PATH.write_text(json.dumps(content, indent=2) + "\n")
    logger.info("Updated cache_enabled=%s in .mcp.json", cache_enabled)
    return get_status()
