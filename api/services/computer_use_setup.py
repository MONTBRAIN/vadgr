"""Service for managing computer use setup: venv, pip install, provider MCP configs.

The daemon lifecycle (Windows-side bridge on WSL2) is owned by the published
``vadgr-computer-use`` package. This module only installs the package, writes
MCP server configs for each supported CLI provider, and delegates daemon
management to the ``vadgr-cua`` console script.

Writes MCP server configuration for each supported CLI provider:
- Claude Code: .mcp.json (JSON, mcpServers key)
- Gemini CLI: .gemini/settings.json (JSON, mcpServers key)
- Codex CLI:  ~/.codex/config.toml (TOML, mcp_servers table, user-level only)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from api.utils.platform import python_command, venv_bin_dir, venv_pip

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MCP_JSON_PATH = PROJECT_ROOT / ".mcp.json"
GEMINI_SETTINGS_PATH = PROJECT_ROOT / ".gemini" / "settings.json"
CODEX_GLOBAL_CONFIG_PATH = Path.home() / ".codex" / "config.toml"
CU_VENV_DIR = PROJECT_ROOT / ".cu_venv"

CU_PACKAGE_SPEC = "vadgr-computer-use>=0.1.0,<0.2.0"
DEPS_MARKER = ".deps_installed"

MCP_SERVER_NAME = "vadgr-computer-use"

_DOCTOR_TIMEOUT = 10
_INSTALL_DAEMON_TIMEOUT = 60
_STOP_DAEMON_TIMEOUT = 15

_CODEX_MCP_SECTION_RE = re.compile(
    r'\n?\[mcp_servers\.(?:vadgr-)?computer-use(?:\.env)?\]\n(?:(?!\n\[)[^\n]*\n?)*',
)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _is_wsl2() -> bool:
    try:
        return "microsoft" in open("/proc/version").read().lower()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Venv + package install
# ---------------------------------------------------------------------------

def _pip_path() -> Path:
    return venv_pip(CU_VENV_DIR)


def _venv_healthy() -> bool:
    return CU_VENV_DIR.exists() and _pip_path().exists()


def _deps_need_install() -> bool:
    marker = CU_VENV_DIR / DEPS_MARKER
    if not marker.exists():
        return True
    current_hash = hashlib.md5(CU_PACKAGE_SPEC.encode()).hexdigest()
    return marker.read_text().strip() != current_hash


def _write_deps_marker() -> None:
    marker_hash = hashlib.md5(CU_PACKAGE_SPEC.encode()).hexdigest()
    (CU_VENV_DIR / DEPS_MARKER).write_text(marker_hash)


def _create_venv() -> None:
    logger.info("Creating computer_use venv at %s", CU_VENV_DIR)
    subprocess.run(
        [python_command(), "-m", "venv", "--clear", str(CU_VENV_DIR)],
        check=True, capture_output=True,
    )


def _pip_install_package() -> None:
    logger.info("Installing %s", CU_PACKAGE_SPEC)
    subprocess.run(
        [str(_pip_path()), "install", "-q", "--upgrade", CU_PACKAGE_SPEC],
        check=True, capture_output=True,
    )
    _write_deps_marker()


# ---------------------------------------------------------------------------
# Delegation to the vadgr-cua console script
# ---------------------------------------------------------------------------

def _vadgr_cua_bin() -> Path:
    """Full path to the ``vadgr-cua`` console script inside the venv."""
    return venv_bin_dir(CU_VENV_DIR) / "vadgr-cua"


def _run_cua(*args: str, timeout: int) -> Optional[subprocess.CompletedProcess]:
    """Run a vadgr-cua subcommand. Returns None if the CLI isn't available."""
    binary = _vadgr_cua_bin()
    if not binary.exists():
        return None
    try:
        return subprocess.run(
            [str(binary), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("vadgr-cua %s failed: %s", args[0] if args else "", e)
        return None


def _doctor_status() -> Optional[str]:
    """Query ``vadgr-cua doctor`` and return 'running', 'stopped', or None."""
    result = _run_cua("doctor", timeout=_DOCTOR_TIMEOUT)
    if result is None or result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return "running" if data.get("daemon_running") else "stopped"


def _install_daemon() -> None:
    """Front-load daemon deploy + launch so first MCP call doesn't pay the cost."""
    result = _run_cua("install-daemon", timeout=_INSTALL_DAEMON_TIMEOUT)
    if result is None or result.returncode != 0:
        logger.warning("vadgr-cua install-daemon did not complete cleanly")


def _stop_daemon() -> None:
    _run_cua("stop-daemon", timeout=_STOP_DAEMON_TIMEOUT)


# ---------------------------------------------------------------------------
# MCP config content builders
# ---------------------------------------------------------------------------

def _mcp_command_and_args() -> tuple[str, list[str]]:
    """Return (command, args) to launch the MCP server via the venv console script."""
    return str(_vadgr_cua_bin()), ["--transport", "stdio"]


def _mcp_json_content() -> dict:
    command, args = _mcp_command_and_args()
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "type": "stdio",
                "command": command,
                "args": args,
            }
        }
    }


def _gemini_settings_content() -> dict:
    """Gemini CLI settings: MCP servers plus fileFiltering override.

    Gemini CLI refuses to read files inside gitignored directories (like
    ``output/``), which breaks workflow execution. Disable that default.
    """
    content = _mcp_json_content()
    content["context"] = {
        "fileFiltering": {"respectGitIgnore": False},
    }
    return content


def _codex_mcp_section() -> str:
    """TOML section for the Codex user config.

    Codex CLI ignores project-level ``.codex/config.toml`` for MCP server
    discovery, so this is always written to ``~/.codex/config.toml``.
    Uses TOML literal strings (single quotes) for paths so that Windows
    backslashes are literal characters rather than escape sequences.
    """
    command, args = _mcp_command_and_args()
    args_json = json.dumps(args)
    return (
        f"[mcp_servers.{MCP_SERVER_NAME}]\n"
        f"command = '{command}'\n"
        f"args = {args_json}\n"
    )


# ---------------------------------------------------------------------------
# MCP config file writers
# ---------------------------------------------------------------------------

def _write_codex_global_config() -> None:
    CODEX_GLOBAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if CODEX_GLOBAL_CONFIG_PATH.exists():
        existing = CODEX_GLOBAL_CONFIG_PATH.read_text()

    cleaned = _CODEX_MCP_SECTION_RE.sub("", existing).rstrip("\n")
    section = _codex_mcp_section()
    if cleaned:
        result = cleaned + "\n\n" + section
    else:
        result = section
    CODEX_GLOBAL_CONFIG_PATH.write_text(result)


def _remove_codex_mcp_section() -> None:
    if not CODEX_GLOBAL_CONFIG_PATH.exists():
        return
    existing = CODEX_GLOBAL_CONFIG_PATH.read_text()
    cleaned = _CODEX_MCP_SECTION_RE.sub("", existing).strip("\n")
    if cleaned:
        CODEX_GLOBAL_CONFIG_PATH.write_text(cleaned + "\n")
    else:
        CODEX_GLOBAL_CONFIG_PATH.write_text("")


def _write_all_provider_configs() -> None:
    MCP_JSON_PATH.write_text(json.dumps(_mcp_json_content(), indent=2) + "\n")

    GEMINI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEMINI_SETTINGS_PATH.write_text(
        json.dumps(_gemini_settings_content(), indent=2) + "\n"
    )

    _write_codex_global_config()


def _remove_all_provider_configs() -> None:
    for path in (MCP_JSON_PATH, GEMINI_SETTINGS_PATH):
        if path.exists():
            path.unlink()
            logger.info("Removed %s", path.name)
    _remove_codex_mcp_section()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_status() -> dict:
    enabled = False
    if MCP_JSON_PATH.exists():
        try:
            data = json.loads(MCP_JSON_PATH.read_text())
            enabled = MCP_SERVER_NAME in data.get("mcpServers", {})
        except (json.JSONDecodeError, OSError):
            pass

    daemon = _doctor_status() if (_is_wsl2() and enabled) else None

    return {
        "enabled": enabled,
        "venv_ready": CU_VENV_DIR.exists(),
        "daemon": daemon,
        "platform": "wsl2" if _is_wsl2() else "native",
    }


def enable_computer_use() -> dict:
    """Create venv, install vadgr-computer-use, write MCP configs, warm the daemon."""
    if not _venv_healthy():
        _create_venv()

    if _deps_need_install():
        _pip_install_package()

    _write_all_provider_configs()
    logger.info("Wrote MCP configs for all providers")

    if _is_wsl2():
        _install_daemon()

    return get_status()


def disable_computer_use() -> dict:
    if _is_wsl2():
        _stop_daemon()
    _remove_all_provider_configs()
    return get_status()
