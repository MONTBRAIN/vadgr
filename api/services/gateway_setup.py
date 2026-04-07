"""Gateway setup service -- manages Discord and multi-machine gateway configuration.

Secrets are stored in ~/.forge/gateway.json with mode 0600.
Tokens are NEVER returned to the client -- only a masked version.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORGE_HOME = Path(os.environ.get("FORGE_HOME", Path.home() / ".forge"))
CONFIG_PATH = FORGE_HOME / "gateway.json"
PID_DIR = FORGE_HOME / "pids"
FORGE_REPO = Path(__file__).resolve().parent.parent.parent
GATEWAY_DIR = FORGE_REPO / "gateway"

TOKEN_MASK = "****"
TOKEN_MIN_LENGTH = 20


def _read_config() -> dict[str, Any]:
    """Read gateway config from disk."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_config(config: dict[str, Any]) -> None:
    """Write gateway config to disk with restrictive permissions."""
    FORGE_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass  # Windows doesn't support chmod the same way


def _mask_token(token: str) -> str:
    """Return masked version of token for display."""
    if len(token) < 8:
        return TOKEN_MASK
    return token[:4] + TOKEN_MASK + token[-4:]


def _gateway_pid() -> int | None:
    """Read gateway PID from pid file."""
    pid_file = PID_DIR / "gateway.pid"
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        # Check if process is alive
        os.kill(pid, 0)
        return pid
    except (ValueError, OSError):
        return None


def get_status() -> dict[str, Any]:
    """Get gateway status. Tokens are masked."""
    config = _read_config()
    discord = config.get("discord", {})
    pid = _gateway_pid()

    return {
        "discord": {
            "enabled": discord.get("enabled", False),
            "has_token": bool(discord.get("token")),
            "token_masked": _mask_token(discord["token"]) if discord.get("token") else None,
            "bot_id": discord.get("bot_id"),
        },
        "gateway_running": pid is not None,
        "gateway_pid": pid,
    }


def update_discord(enabled: bool, token: str | None = None) -> dict[str, Any]:
    """Enable/disable Discord gateway. Token is stored server-side only.

    If token is the masked placeholder, keep the existing token.
    """
    config = _read_config()
    discord = config.get("discord", {})

    discord["enabled"] = enabled

    # Only update token if a real new one was provided (not masked placeholder)
    if token and TOKEN_MASK not in token and len(token) >= TOKEN_MIN_LENGTH:
        discord["token"] = token
    elif token == "":
        # Explicitly cleared by user
        discord.pop("token", None)
    # When token is None (not provided), keep existing token

    config["discord"] = discord
    _write_config(config)

    # Restart gateway if running
    pid = _gateway_pid()
    if pid:
        _stop_gateway(pid)

    if enabled and discord.get("token"):
        _start_gateway()

    return get_status()


def _start_gateway() -> None:
    """Start the gateway process."""
    if not (GATEWAY_DIR / "package.json").exists():
        return

    config = _read_config()
    discord_token = config.get("discord", {}).get("token")
    if not discord_token:
        return

    PID_DIR.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "DISCORD_BOT_TOKEN": discord_token}

    # Read API port
    api_port_file = PID_DIR / "api.port"
    if api_port_file.exists():
        env["AGENT_FORGE_PORT"] = api_port_file.read_text().strip()

    log_path = FORGE_HOME / "gateway.log"

    if (GATEWAY_DIR / "dist" / "index.js").exists():
        cmd = ["node", "dist/index.js"]
    else:
        cmd = ["npx", "tsx", "src/index.ts"]

    # Platform-specific process group handling
    kwargs: dict[str, Any] = {}
    if hasattr(os, "setsid"):
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=str(GATEWAY_DIR),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    (PID_DIR / "gateway.pid").write_text(str(proc.pid))


def _stop_gateway(pid: int) -> None:
    """Stop the gateway process."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    pid_file = PID_DIR / "gateway.pid"
    pid_file.unlink(missing_ok=True)


# -- Multi-machine token management --

MACHINE_TOKEN_PREFIX = "vdgr_"
MACHINE_TOKEN_BYTES = 48
DEFAULT_WS_PORT = 9443


def generate_machine_token(machine_name: str) -> dict[str, Any]:
    """Generate a new machine token and add to gateway.json.

    Returns the token entry (with the full token visible -- this is the
    only time the user sees the raw token).
    """
    token = MACHINE_TOKEN_PREFIX + secrets.token_urlsafe(MACHINE_TOKEN_BYTES)
    config = _read_config()
    machines = config.setdefault("machines", {})
    machines.setdefault("ws_port", DEFAULT_WS_PORT)
    tokens: list[dict[str, Any]] = machines.setdefault("tokens", [])

    # Prevent duplicate names
    for entry in tokens:
        if entry.get("name") == machine_name:
            raise ValueError(f"Machine '{machine_name}' already exists. Remove it first.")

    entry = {
        "token": token,
        "name": machine_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tokens.append(entry)
    _write_config(config)
    return entry


def revoke_machine_token(machine_name: str) -> bool:
    """Remove a machine token by name. Returns True if found and removed."""
    config = _read_config()
    machines = config.get("machines", {})
    tokens: list[dict[str, Any]] = machines.get("tokens", [])

    original_len = len(tokens)
    tokens = [t for t in tokens if t.get("name") != machine_name]

    if len(tokens) == original_len:
        return False

    machines["tokens"] = tokens
    config["machines"] = machines
    _write_config(config)
    return True


def list_machine_tokens() -> list[dict[str, Any]]:
    """List machine tokens (masked). Never returns raw tokens."""
    config = _read_config()
    machines = config.get("machines", {})
    tokens: list[dict[str, Any]] = machines.get("tokens", [])

    result = []
    for entry in tokens:
        result.append({
            "name": entry.get("name", "unknown"),
            "token_masked": _mask_token(entry.get("token", "")),
            "created_at": entry.get("created_at"),
        })
    return result


def get_machines_config() -> dict[str, Any]:
    """Get the machines section of gateway.json (tokens masked)."""
    config = _read_config()
    machines = config.get("machines", {})
    return {
        "ws_port": machines.get("ws_port", DEFAULT_WS_PORT),
        "machines": list_machine_tokens(),
    }
