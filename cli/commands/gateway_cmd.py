"""Gateway commands -- start, stop, status, and multi-machine management."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import click

from cli.commands.service import _session_kwargs, _read_pid, _write_pid, _pid_alive
from cli.output import print_success, print_info, print_warning, print_table, status_text

FORGE_HOME = Path(os.environ.get("FORGE_HOME", Path.home() / ".forge"))
PID_DIR = FORGE_HOME / "pids"
FORGE_REPO = Path(__file__).resolve().parent.parent.parent


@click.group("gateway")
def gateway_group():
    """Manage the messaging gateway and multi-machine connections."""


@gateway_group.command("start")
@click.option("--port", "-p", default=None, type=int, help="Webhook server port")
@click.option("--config", "-c", default=None, help="Path to gateway.yaml")
def start_gateway(port, config):
    """Start the messaging gateway server."""
    pid = _read_pid("gateway")
    if pid and _pid_alive(pid):
        print_warning("Gateway is already running.")
        raise SystemExit(1)

    PID_DIR.mkdir(parents=True, exist_ok=True)

    gateway_dir = FORGE_REPO / "gateway"
    if not (gateway_dir / "package.json").exists():
        print_warning("Gateway module not found. Expected gateway/package.json")
        raise SystemExit(1)

    env = {**os.environ}
    if port:
        env["AGENT_FORGE_PORT"] = str(port)
    if config:
        env["GATEWAY_CONFIG"] = config

    # Read API port from pid file (written by `vadgr start`)
    api_port_file = PID_DIR / "api.port"
    if api_port_file.exists():
        env.setdefault("AGENT_FORGE_PORT", api_port_file.read_text().strip())

    print_info("Starting gateway...")
    log_file = open(FORGE_HOME / "gateway.log", "w")

    # Check if built dist exists, prefer node over npx tsx for production
    if (gateway_dir / "dist" / "index.js").exists():
        cmd = ["node", "dist/index.js"]
    else:
        cmd = ["npx", "tsx", "src/index.ts"]

    proc = subprocess.Popen(
        cmd,
        cwd=str(gateway_dir),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        **_session_kwargs(),
    )
    _write_pid("gateway", proc.pid)

    time.sleep(3)
    if proc.poll() is not None:
        print_warning(f"Gateway failed to start. Check {FORGE_HOME / 'gateway.log'}")
        raise SystemExit(1)

    print_success("Gateway running (Discord adapter)")
    print_info("Bot will respond to @mentions and DMs")


@gateway_group.command("stop")
def stop_gateway():
    """Stop the messaging gateway."""
    pid = _read_pid("gateway")
    if pid:
        from cli.commands.service import _kill_tree
        _kill_tree(pid)
        print_info(f"Stopped gateway (PID {pid})")
        (PID_DIR / "gateway.pid").unlink(missing_ok=True)
    else:
        print_warning("Gateway is not running.")


@gateway_group.command("status")
def gateway_status():
    """Show gateway status."""
    pid = _read_pid("gateway")
    if pid and _pid_alive(pid):
        print_table(["Service", "PID", "Status"], [["gateway", str(pid), status_text("running")]])
    else:
        print_table(["Service", "PID", "Status"], [["gateway", "-", status_text("stopped")]])


# -- Multi-machine commands --


@gateway_group.command("add-machine")
@click.argument("machine_name")
def add_machine(machine_name):
    """Generate a token for a new machine to connect."""
    from api.services.gateway_setup import generate_machine_token

    try:
        entry = generate_machine_token(machine_name)
    except ValueError as e:
        print_warning(str(e))
        raise SystemExit(1)

    print_success(f"Token generated for '{machine_name}'")
    print_info("")
    print_info(f"  Token: {entry['token']}")
    print_info("")
    print_info(f"  Run on {machine_name}:")
    print_info(f"    vadgr gateway connect <gateway-host>:9443 --token {entry['token']} --name {machine_name}")
    print_info("")
    print_warning("Save this token now -- it will not be shown again.")


@gateway_group.command("remove-machine")
@click.argument("machine_name")
def remove_machine(machine_name):
    """Revoke a machine's access token."""
    from api.services.gateway_setup import revoke_machine_token

    if revoke_machine_token(machine_name):
        print_success(f"Token revoked for '{machine_name}'")
    else:
        print_warning(f"Machine '{machine_name}' not found.")


@gateway_group.command("machines")
def list_machines():
    """List registered machine tokens."""
    from api.services.gateway_setup import get_machines_config

    config = get_machines_config()
    machines = config.get("machines", [])

    if not machines:
        print_info("No machines registered. Use 'vadgr gateway add-machine <name>' to add one.")
        return

    rows = []
    for m in machines:
        rows.append([m["name"], m["token_masked"], m.get("created_at", "-")])

    print_table(["Machine", "Token", "Created"], rows)
    print_info(f"\nWebSocket port: {config.get('ws_port', 9443)}")


@gateway_group.command("connect")
@click.argument("gateway_url")
@click.option("--token", prompt=True, hide_input=True, help="Machine access token")
@click.option("--name", default=None, help="Machine name (defaults to hostname)")
def connect_machine(gateway_url, token, name):
    """Connect this machine to a remote gateway."""
    import socket

    machine_name = name or socket.gethostname()

    # Ensure URL has ws:// or wss:// prefix
    if not gateway_url.startswith("ws://") and not gateway_url.startswith("wss://"):
        gateway_url = f"wss://{gateway_url}"

    bridge_config = {
        "gateway_url": gateway_url,
        "machine_token": token,
        "machine_name": machine_name,
        "local_api_url": "http://localhost:8000",
    }

    config_path = FORGE_HOME / "bridge.json"
    FORGE_HOME.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(bridge_config, indent=2))
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass

    print_success(f"Bridge configured as '{machine_name}'")
    print_info(f"  Gateway: {gateway_url}")
    print_info(f"  Config:  {config_path}")
    print_info("")
    print_info("Start the bridge with: vadgr gateway bridge")


@gateway_group.command("bridge")
def start_bridge():
    """Start the bridge client (connects to remote gateway)."""
    bridge_config = FORGE_HOME / "bridge.json"
    if not bridge_config.exists():
        print_warning("No bridge config found. Run 'vadgr gateway connect' first.")
        raise SystemExit(1)

    pid = _read_pid("bridge")
    if pid and _pid_alive(pid):
        print_warning("Bridge is already running.")
        raise SystemExit(1)

    PID_DIR.mkdir(parents=True, exist_ok=True)

    gateway_dir = FORGE_REPO / "gateway"
    log_file = open(FORGE_HOME / "bridge.log", "w")

    if (gateway_dir / "dist" / "bridge.js").exists():
        cmd = ["node", "dist/bridge.js"]
    else:
        cmd = ["npx", "tsx", "src/bridge.ts"]

    proc = subprocess.Popen(
        cmd,
        cwd=str(gateway_dir),
        env=os.environ,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        **_session_kwargs(),
    )
    _write_pid("bridge", proc.pid)

    time.sleep(3)
    if proc.poll() is not None:
        print_warning(f"Bridge failed to start. Check {FORGE_HOME / 'bridge.log'}")
        raise SystemExit(1)

    print_success("Bridge connected to gateway")


@gateway_group.command("disconnect")
def disconnect_machine():
    """Stop the bridge and disconnect from remote gateway."""
    pid = _read_pid("bridge")
    if pid:
        from cli.commands.service import _kill_tree
        _kill_tree(pid)
        (PID_DIR / "bridge.pid").unlink(missing_ok=True)
        print_info("Bridge stopped.")
    else:
        print_info("Bridge is not running.")

    config_path = FORGE_HOME / "bridge.json"
    if config_path.exists():
        config_path.unlink()
        print_success("Disconnected. Bridge config removed.")
