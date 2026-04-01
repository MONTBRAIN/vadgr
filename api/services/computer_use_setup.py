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
# Codex CLI ignores project-level .codex/config.toml for MCP servers.
# It only reads the user-level global config.
CODEX_GLOBAL_CONFIG_PATH = Path.home() / ".codex" / "config.toml"
CU_VENV_DIR = PROJECT_ROOT / "computer_use" / ".venv"
CU_REQUIREMENTS = PROJECT_ROOT / "computer_use" / "requirements.txt"
DEPS_MARKER = ".deps_installed"

# Regex to strip [mcp_servers.computer-use] and [mcp_servers.computer-use.env]
# blocks from a TOML file.  A TOML section header is a '[' at the start of a
# line, so we match everything until the next section header or EOF.
import re
_CODEX_MCP_SECTION_RE = re.compile(
    r'\n?\[mcp_servers\.computer-use(?:\.env)?\]\n(?:(?!\n\[)[^\n]*\n?)*',
)


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
    env = {"AGENT_FORGE_DEBUG": "1", "PYTHONPATH": str(PROJECT_ROOT)}
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
    """Build .gemini/settings.json content.

    Includes mcpServers (same as .mcp.json) plus context.fileFiltering
    to disable respectGitIgnore -- Gemini CLI refuses to read files in
    gitignored directories (like output/), which breaks workflow execution.
    """
    content = _mcp_json_content(cache_enabled=cache_enabled)
    content["context"] = {
        "fileFiltering": {
            "respectGitIgnore": False,
        },
    }
    return content


def _codex_mcp_section(cache_enabled: bool = True) -> str:
    """Build the [mcp_servers.computer-use] TOML section for Codex.

    Uses TOML literal strings (single quotes) for paths so that Windows
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
        f'PYTHONPATH = "{cwd}"',
    ]
    if not cache_enabled:
        lines.append('AGENT_FORGE_CACHE_ENABLED = "0"')
    lines.append('')  # trailing newline
    return '\n'.join(lines)


def _write_codex_global_config(cache_enabled: bool = True) -> None:
    """Merge computer-use MCP section into ~/.codex/config.toml.

    Reads existing content, strips any previous computer-use section,
    then appends the new one. Preserves all other Codex settings.
    """
    CODEX_GLOBAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if CODEX_GLOBAL_CONFIG_PATH.exists():
        existing = CODEX_GLOBAL_CONFIG_PATH.read_text()

    # Remove old computer-use sections (both main and .env sub-table)
    cleaned = _CODEX_MCP_SECTION_RE.sub('', existing).rstrip('\n')

    section = _codex_mcp_section(cache_enabled=cache_enabled)
    if cleaned:
        result = cleaned + '\n\n' + section
    else:
        result = section
    CODEX_GLOBAL_CONFIG_PATH.write_text(result)


def _remove_codex_mcp_section() -> None:
    """Remove only the computer-use MCP section from ~/.codex/config.toml."""
    if not CODEX_GLOBAL_CONFIG_PATH.exists():
        return
    existing = CODEX_GLOBAL_CONFIG_PATH.read_text()
    cleaned = _CODEX_MCP_SECTION_RE.sub('', existing).strip('\n')
    if cleaned:
        CODEX_GLOBAL_CONFIG_PATH.write_text(cleaned + '\n')
    else:
        CODEX_GLOBAL_CONFIG_PATH.write_text('')


def _write_all_provider_configs(cache_enabled: bool = True) -> None:
    """Write MCP config files for all supported providers."""
    # Claude Code: .mcp.json (project-level)
    content = _mcp_json_content(cache_enabled=cache_enabled)
    MCP_JSON_PATH.write_text(json.dumps(content, indent=2) + "\n")

    # Gemini CLI: .gemini/settings.json (project-level)
    GEMINI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    gemini_content = _gemini_settings_content(cache_enabled=cache_enabled)
    GEMINI_SETTINGS_PATH.write_text(json.dumps(gemini_content, indent=2) + "\n")

    # Codex CLI: ~/.codex/config.toml (global -- Codex ignores project-level MCP)
    _write_codex_global_config(cache_enabled=cache_enabled)


def _remove_all_provider_configs() -> None:
    """Remove MCP config files for all supported providers."""
    for path in (MCP_JSON_PATH, GEMINI_SETTINGS_PATH):
        if path.exists():
            path.unlink()
            logger.info("Removed %s", path.name)
    # Codex: only remove our section, don't delete the global config
    _remove_codex_mcp_section()


_DAEMON_PORT = 19542
_DAEMON_LAUNCH_WAIT = 3
_DAEMON_LAUNCH_RETRIES = 5


def _is_wsl2() -> bool:
    try:
        return "microsoft" in open("/proc/version").read().lower()
    except Exception:
        return False


def _get_bridge_client():
    from computer_use.bridge.client import BridgeClient
    return BridgeClient()


def _probe_daemon() -> str:
    try:
        client = _get_bridge_client()
        if client.is_available():
            return "running"
        return "degraded"
    except Exception:
        return "stopped"


def _get_windows_userprofile() -> str | None:
    """Get the active Windows user's profile directory as a WSL path."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "$env:USERPROFILE"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            wsl_path = subprocess.run(
                ["wslpath", "-u", result.stdout.strip()],
                capture_output=True, text=True,
            ).stdout.strip()
            return wsl_path
    except Exception:
        pass
    return None


def _find_windows_python() -> str | None:
    """Find a Python install on the active Windows user's account."""
    import glob

    # First try the active Windows user's Python install
    profile = _get_windows_userprofile()
    if profile:
        user_pattern = f"{profile}/AppData/Local/Programs/Python/Python3*/python.exe"
        matches = sorted(glob.glob(user_pattern), reverse=True)
        if matches:
            return matches[0].replace("/mnt/c/", "C:\\").replace("/", "\\")

    # Fallback: any user's Python (multi-user machines)
    all_users_pattern = "/mnt/c/Users/*/AppData/Local/Programs/Python/Python3*/python.exe"
    matches = sorted(glob.glob(all_users_pattern), reverse=True)
    if matches:
        return matches[0].replace("/mnt/c/", "C:\\").replace("/", "\\")

    # Last resort: ask PowerShell
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "(Get-Command python).Source"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _deploy_and_launch_daemon(win_python: str) -> None:
    bridge_dir = str(PROJECT_ROOT / "computer_use" / "bridge")
    deploy_dir = _get_windows_userprofile()

    if not deploy_dir:
        return

    import shutil
    for fname in ("daemon.py", "spatial_cache.py"):
        src = os.path.join(bridge_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(deploy_dir, fname))

    # Convert to Windows path
    try:
        win_dir = subprocess.run(
            ["wslpath", "-w", deploy_dir],
            capture_output=True, text=True,
        ).stdout.strip()
    except Exception:
        return

    # Use pythonw.exe for hidden window
    pythonw = win_python.replace("python.exe", "pythonw.exe")

    logger.info("Launching daemon: %s daemon.py", pythonw)
    try:
        subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-Command",
                f'Start-Process -FilePath "{pythonw}" '
                f'-ArgumentList "daemon.py" '
                f'-WorkingDirectory "{win_dir}" '
                f'-WindowStyle Hidden',
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.warning("Failed to launch daemon: %s", e)


def _start_daemon() -> bool:
    if not _is_wsl2():
        return False

    win_python = _find_windows_python()
    if not win_python:
        logger.warning("Windows Python not found, cannot start daemon")
        return False

    _deploy_and_launch_daemon(win_python)

    import time
    time.sleep(_DAEMON_LAUNCH_WAIT)
    for _ in range(_DAEMON_LAUNCH_RETRIES):
        if _probe_daemon() == "running":
            logger.info("Daemon started successfully")
            return True
        time.sleep(1)

    logger.warning("Daemon launched but not responding")
    return False


def _stop_daemon():
    if not _is_wsl2():
        return
    try:
        # Kill by port (catches healthy daemons)
        subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                f"Get-NetTCPConnection -LocalPort {_DAEMON_PORT} -State Listen "
                f"-ErrorAction SilentlyContinue | "
                f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}",
            ],
            capture_output=True, timeout=10,
        )
        # Also kill any pythonw.exe running daemon.py (catches zombies that
        # crashed before binding to the port)
        subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                'Get-CimInstance Win32_Process -Filter "Name=\'pythonw.exe\'" '
                "| Where-Object { $_.CommandLine -like '*daemon.py*' } "
                "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }",
            ],
            capture_output=True, timeout=10,
        )
        logger.info("Daemon stopped")
    except Exception as e:
        logger.warning("Failed to stop daemon: %s", e)


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

    daemon = _probe_daemon() if (_is_wsl2() and enabled) else None

    return {
        "enabled": enabled,
        "cache_enabled": cache_enabled,
        "venv_ready": venv_exists,
        "daemon": daemon,
        "platform": "wsl2" if _is_wsl2() else "native",
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

    # Manage daemon on WSL2
    if _is_wsl2():
        state = _probe_daemon()
        if state == "degraded":
            _stop_daemon()
            _start_daemon()
        elif state == "stopped":
            _start_daemon()

    # Write MCP configs for all providers
    _write_all_provider_configs(cache_enabled=cache_enabled)
    logger.info("Wrote MCP configs for all providers (cache_enabled=%s)", cache_enabled)

    return get_status()


def disable_computer_use() -> dict:
    """Remove all provider MCP configs and stop daemon. Keeps venv for re-enable."""
    if _is_wsl2():
        _stop_daemon()
    _remove_all_provider_configs()
    return get_status()


def update_cache_setting(cache_enabled: bool) -> dict:
    """Update cache setting in all provider MCP configs without touching venv."""
    if not MCP_JSON_PATH.exists():
        return get_status()

    _write_all_provider_configs(cache_enabled=cache_enabled)
    logger.info("Updated cache_enabled=%s in all provider MCP configs", cache_enabled)
    return get_status()
