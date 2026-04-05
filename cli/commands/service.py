"""Service commands -- start, stop, restart, status, logs, update, api."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import click

from cli.output import print_info, print_success, print_warning, print_error, print_table, status_text

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

FORGE_HOME = Path(os.environ.get("FORGE_HOME", Path.home() / ".forge"))
FORGE_REPO = Path(os.environ.get("FORGE_REPO", _PROJECT_ROOT))
PID_DIR = FORGE_HOME / "pids"

_API_STARTUP_TIMEOUT = 30
_FRONTEND_PORT_TIMEOUT = 5.0
_FRONTEND_PORT_POLL = 0.25


def _default_port(env_key: str, default: int) -> int:
    return int(os.environ.get(env_key, str(default)))


# -- Helpers --

def _pid_alive(pid: int) -> bool:
    """Check if a process is alive. Works on both Unix and Windows."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _read_pid(service: str) -> int | None:
    pidfile = PID_DIR / f"{service}.pid"
    if not pidfile.exists():
        return None
    text = pidfile.read_text().strip()
    if not text.isdigit():
        pidfile.unlink(missing_ok=True)
        return None
    pid = int(text)
    if _pid_alive(pid):
        return pid
    pidfile.unlink(missing_ok=True)
    return None


def _write_pid(service: str, pid: int):
    PID_DIR.mkdir(parents=True, exist_ok=True)
    (PID_DIR / f"{service}.pid").write_text(str(pid))


def _kill_tree(pid: int):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True)
        return
    try:
        result = subprocess.run(["pgrep", "-P", str(pid)],
                                capture_output=True, text=True)
        for child in result.stdout.split():
            if child.strip().isdigit():
                _kill_tree(int(child.strip()))
    except FileNotFoundError:
        pass
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def _port_in_use(port: int) -> bool:
    import socket
    # Check both IPv4 and IPv6 loopback -- Vite on Windows 11 often binds
    # to ::1 only, so checking just 127.0.0.1 would miss it.
    for addr in ("127.0.0.1", "::1"):
        family = socket.AF_INET6 if ":" in addr else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex((addr, port)) == 0:
                return True
    return False


def _find_free_port(default: int, max_attempts: int = 20) -> int | None:
    """Find a free port starting from *default*, incrementing on conflict."""
    for offset in range(max_attempts):
        candidate = default + offset
        if not _port_in_use(candidate):
            return candidate
    return None


def _kill_port(port: int):
    if sys.platform == "win32":
        subprocess.run(["powershell", "-Command",
                        f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                        f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}"],
                       capture_output=True)
    else:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)


def _wait_for_api(port: int, timeout: int = _API_STARTUP_TIMEOUT) -> bool:
    for _ in range(timeout):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
            urllib.request.urlopen(req, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def _wait_for_frontend(port: int, timeout: int = 10) -> bool:
    for _ in range(timeout):
        try:
            # Use "localhost" instead of "127.0.0.1" so the OS resolves to
            # whichever loopback address Vite actually bound (IPv4 or IPv6).
            req = urllib.request.Request(f"http://localhost:{port}")
            urllib.request.urlopen(req, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def _detect_frontend_port(log_path: Path, default: int,
                          timeout: float = _FRONTEND_PORT_TIMEOUT) -> int:
    elapsed = 0.0
    while elapsed < timeout:
        if log_path.exists():
            match = re.search(r"localhost:(\d+)", log_path.read_text())
            if match:
                return int(match.group(1))
        time.sleep(_FRONTEND_PORT_POLL)
        elapsed += _FRONTEND_PORT_POLL
    return default


def _find_node() -> str | None:
    found = shutil.which("node")
    if found:
        return found
    nvm_dir = os.environ.get("NVM_DIR", str(Path.home() / ".nvm"))
    nvm_sh = Path(nvm_dir) / "nvm.sh"
    if nvm_sh.exists():
        try:
            result = subprocess.run(
                ["bash", "-c", f'source "{nvm_sh}" && which node'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None


def _find_npm() -> str | None:
    """Find npm executable. Used to launch frontend via 'npm run dev'."""
    found = shutil.which("npm")
    if found:
        return found
    node = _find_node()
    if not node:
        return None
    node_dir = Path(node).parent
    for name in ("npm.cmd", "npm.exe", "npm"):
        candidate = node_dir / name
        if candidate.exists():
            return str(candidate)
    return None


def _get_api_python() -> str:
    if sys.platform == "win32":
        p = FORGE_REPO / "api" / ".venv" / "Scripts" / "python.exe"
    else:
        p = FORGE_REPO / "api" / ".venv" / "bin" / "python"
    if not p.exists():
        raise click.ClickException(f"API venv not found at {p}. Run setup first.")
    return str(p)


def _build_env(api_port: int, frontend_port: int) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(FORGE_REPO)
    env["AGENT_FORGE_PORT"] = str(api_port)
    env["AGENT_FORGE_FRONTEND_PORT"] = str(frontend_port)
    return env


def _session_kwargs() -> dict:
    """Kwargs for Popen to fully detach background processes from the terminal.

    Without stdin=DEVNULL, child processes inherit the terminal stdin and
    compete with the shell for input, corrupting typing and copy/paste.
    """
    if sys.platform == "win32":
        return {"stdin": subprocess.DEVNULL, "creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {"stdin": subprocess.DEVNULL, "start_new_session": True}


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest()


# -- Commands --

@click.command()
@click.option("--api-port", default=None, type=int, help="API server port")
@click.option("--frontend-port", default=None, type=int, help="Frontend server port")
def start(api_port, frontend_port):
    """Start API and frontend servers."""
    api_port = api_port or _default_port("AGENT_FORGE_PORT", 8000)
    frontend_port = frontend_port or _default_port("AGENT_FORGE_FRONTEND_PORT", 3000)
    PID_DIR.mkdir(parents=True, exist_ok=True)

    if _read_pid("api"):
        print_warning("vadgr is already running. Use 'vadgr stop' first.")
        raise SystemExit(1)

    # Find free ports, auto-incrementing if default is busy
    if _port_in_use(api_port):
        original = api_port
        api_port = _find_free_port(api_port)
        if api_port is None:
            print_warning(f"No free port found starting from {original}.")
            raise SystemExit(1)
        print_info(f"Port {original} busy, using {api_port}")

    if _port_in_use(frontend_port):
        original = frontend_port
        frontend_port = _find_free_port(frontend_port)
        if frontend_port is None:
            print_warning(f"No free port found starting from {original}.")
            raise SystemExit(1)
        print_info(f"Port {original} busy, using {frontend_port}")

    env = _build_env(api_port, frontend_port)

    # Start API
    print_info(f"Starting API server (port {api_port})...")
    api_log = open(FORGE_HOME / "api.log", "w")
    api_proc = subprocess.Popen(
        [_get_api_python(), "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(api_port)],
        cwd=str(FORGE_REPO), env=env,
        stdout=api_log, stderr=subprocess.STDOUT,
        **_session_kwargs(),
    )
    _write_pid("api", api_proc.pid)

    time.sleep(1)
    if api_proc.poll() is not None:
        print_warning(f"API process died. Port {api_port} may be in use. Check {FORGE_HOME / 'api.log'}")
        (PID_DIR / "api.pid").unlink(missing_ok=True)
        raise SystemExit(1)

    if not _wait_for_api(api_port):
        print_warning(f"API failed to start. Check {FORGE_HOME / 'api.log'}")
        raise SystemExit(1)

    # Start frontend via npm run dev (not npx -- npx resolution varies across Node versions)
    frontend_dir = FORGE_REPO / "frontend"
    npm = _find_npm()
    if not npm:
        print_warning("npm not found. Frontend will not start.")
        print_success(f"API is running at http://localhost:{api_port}")
        return

    print_info("Starting frontend...")
    fe_log = open(FORGE_HOME / "frontend.log", "w")
    fe_proc = subprocess.Popen(
        [npm, "run", "dev"], cwd=str(frontend_dir),
        env=env, stdout=fe_log, stderr=subprocess.STDOUT,
        **_session_kwargs(),
    )
    _write_pid("frontend", fe_proc.pid)

    actual_fe = _detect_frontend_port(FORGE_HOME / "frontend.log", frontend_port)

    # Verify frontend is actually responding, not just alive
    if not _wait_for_frontend(actual_fe):
        print_warning(f"Frontend failed to start. Check {FORGE_HOME / 'frontend.log'}")
        print_success(f"API is running at http://localhost:{api_port}")
        return

    print_success("vadgr is running!")
    print_success(f"  Frontend: http://localhost:{actual_fe}")
    print_success(f"  API:      http://localhost:{api_port}")
    click.echo()
    print_info("Run 'vadgr stop' to stop, 'vadgr logs' to see API logs.")


@click.command()
def stop():
    """Stop all services."""
    api_port = _default_port("AGENT_FORGE_PORT", 8000)
    frontend_port = _default_port("AGENT_FORGE_FRONTEND_PORT", 3000)
    service_ports = {"api": api_port, "frontend": frontend_port}

    stopped = False
    for service in ("api", "frontend"):
        pid = _read_pid(service)
        if pid:
            _kill_tree(pid)
            print_info(f"Stopped {service} (PID {pid})")
            (PID_DIR / f"{service}.pid").unlink(missing_ok=True)
            stopped = True
        elif _port_in_use(service_ports[service]):
            _kill_port(service_ports[service])
            print_info(f"Stopped {service} on port {service_ports[service]}")
            (PID_DIR / f"{service}.pid").unlink(missing_ok=True)
            stopped = True
    if not stopped:
        print_warning("vadgr is not running.")
    else:
        print_success("vadgr stopped.")


@click.command()
@click.option("--api-port", default=None, type=int)
@click.option("--frontend-port", default=None, type=int)
@click.pass_context
def restart(ctx, api_port, frontend_port):
    """Restart all services."""
    ctx.invoke(stop)
    time.sleep(1)
    ctx.invoke(start, api_port=api_port, frontend_port=frontend_port)


@click.command()
def status():
    """Show service status."""
    rows = []
    for service in ("api", "frontend"):
        pid = _read_pid(service)
        if pid:
            rows.append([service, str(pid), status_text("running")])
        else:
            rows.append([service, "-", status_text("stopped")])

    # Check daemon status via API if available
    try:
        from cli.client import api_get, is_api_running
        ctx = click.get_current_context()
        if is_api_running(ctx):
            cu = api_get(ctx, "/api/settings/computer-use")
            daemon = cu.get("daemon")
            if daemon:
                rows.append(["daemon", "-", status_text(daemon)])
    except Exception:
        pass

    print_table(["Service", "PID", "Status"], rows)


@click.command()
@click.option("--service", "-s", type=click.Choice(["api", "frontend"]), default="api")
@click.option("--follow/--no-follow", "-f", default=True)
@click.option("--lines", "-n", default=50, type=int)
def logs(service, follow, lines):
    """Tail service logs."""
    log_path = FORGE_HOME / f"{service}.log"
    if not log_path.exists():
        print_warning(f"No logs found for {service}. Is vadgr running?")
        raise SystemExit(1)

    if not follow:
        for line in log_path.read_text().splitlines()[-lines:]:
            click.echo(line)
        return

    try:
        proc = subprocess.run(["tail", "-f", "-n", str(lines), str(log_path)])
    except KeyboardInterrupt:
        pass


@click.command()
def update():
    """Pull latest code and reinstall deps if changed."""
    print_info("Updating vadgr...")

    api_req = FORGE_REPO / "api" / "requirements.txt"
    fe_pkg = FORGE_REPO / "frontend" / "package.json"
    cli_req = FORGE_REPO / "cli" / "requirements.txt"
    old_api = _file_hash(api_req)
    old_fe = _file_hash(fe_pkg)
    old_cli = _file_hash(cli_req)

    result = subprocess.run(
        ["git", "pull", "--ff-only", "origin", "master"],
        cwd=str(FORGE_REPO), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print_warning(f"Could not pull: {result.stderr.strip()}")
        return
    click.echo(result.stdout.strip())

    if _file_hash(api_req) != old_api:
        print_info("API deps changed, reinstalling...")
        subprocess.run([_get_api_python().replace("python", "pip"),
                        "install", "-q", "-r", str(api_req)], check=True)

    if _file_hash(cli_req) != old_cli:
        print_info("CLI deps changed, reinstalling...")
        cli_pip = str(FORGE_REPO / "cli" / ".venv" / "bin" / "pip")
        subprocess.run([cli_pip, "install", "-q", "-r", str(cli_req)], check=True)

    if _file_hash(fe_pkg) != old_fe:
        print_info("Frontend deps changed, reinstalling...")
        npx_parent = _find_node()
        if npx_parent:
            npm = str(Path(npx_parent).parent / "npm")
            subprocess.run([npm, "install", "--silent"],
                           cwd=str(FORGE_REPO / "frontend"), check=True)

    if _read_pid("api"):
        print_info("Restarting services...")
        # Can't invoke stop/start here cleanly, tell user
        click.echo("Run 'vadgr restart' to apply changes.")
    else:
        print_success("Update complete. Run 'vadgr start' to start.")


@click.command("api")
@click.option("--port", default=None, type=int, help="API server port")
def api_only(port):
    """Start API server only (no frontend)."""
    port = port or _default_port("AGENT_FORGE_PORT", 8000)
    PID_DIR.mkdir(parents=True, exist_ok=True)

    if _read_pid("api"):
        print_warning("API is already running. Use 'vadgr stop' first.")
        raise SystemExit(1)

    if _port_in_use(port):
        original = port
        port = _find_free_port(port)
        if port is None:
            print_warning(f"No free port found starting from {original}.")
            raise SystemExit(1)
        print_info(f"Port {original} busy, using {port}")

    env = _build_env(port, 3000)
    print_info(f"Starting API server (port {port})...")

    api_log = open(FORGE_HOME / "api.log", "w")
    api_proc = subprocess.Popen(
        [_get_api_python(), "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(FORGE_REPO), env=env,
        stdout=api_log, stderr=subprocess.STDOUT,
        **_session_kwargs(),
    )
    _write_pid("api", api_proc.pid)

    if _wait_for_api(port):
        print_success(f"API is running at http://localhost:{port}")
    else:
        print_warning(f"API failed to start. Check {FORGE_HOME / 'api.log'}")
