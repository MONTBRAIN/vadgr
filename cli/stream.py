"""WebSocket streaming for run progress."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import click
import websockets
from rich.console import Console

from cli.output import format_duration, print_success, print_error

_SPINNER_STYLE = "dots"
_STEP_PATTERN = re.compile(r"---\s*Step\s+(\d+)[:/]\s*(.*?)\s*---", re.IGNORECASE)
_FORGE_PID_DIR = Path.home() / ".forge" / "pids"
_STEP_COMPLETE_PAD = 40


def follow_run(api_url: str, run_id: str, timeout: float = 600.0):
    """Connect to the run WebSocket and show step progress until done."""
    ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/ws/runs/{run_id}"

    try:
        asyncio.run(_stream(ws_url, run_id, api_url, timeout))
    except KeyboardInterrupt:
        click.echo(f"\n  Detached. Run continues in background.")
        click.echo(f"  View logs: forge runs logs {run_id}")


async def _stream(ws_url: str, run_id: str, api_url: str, timeout: float):
    console = Console()
    current_step = None
    step_start = None
    run_start = time.monotonic()

    try:
        async with websockets.connect(ws_url) as ws:
            with console.status("Starting...", spinner=_SPINNER_STYLE) as status:

                while True:
                    elapsed = time.monotonic() - run_start
                    if elapsed > timeout:
                        click.echo(f"  Timed out after {format_duration(timeout)}. Run continues in background.")
                        break

                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    except asyncio.TimeoutError:
                        continue

                    event = json.loads(raw)
                    etype = event.get("type", "")
                    data = event.get("data", {})

                    if etype == "agent_started":
                        name = data.get("name", "")
                        status.update(f"Running {name}...")

                    elif etype == "agent_log":
                        msg = data.get("message", "")
                        step_match = _STEP_PATTERN.search(msg)
                        if step_match:
                            _print_step_done(current_step, step_start)
                            step_num = step_match.group(1)
                            step_name = step_match.group(2).strip()
                            # Strip [CLI] / [Desktop] suffix
                            step_name = re.sub(r"\s*\[(CLI|Desktop)\]\s*$", "", step_name)
                            current_step = f"Step {step_num}: {step_name}"
                            step_start = time.monotonic()
                            status.update(f"{current_step}...")

                    elif etype == "run_completed":
                        _print_step_done(current_step, step_start)
                        total = format_duration(time.monotonic() - run_start)
                        print_success(f"Run completed ({total})")
                        click.echo()
                        _print_results_link(api_url, run_id)
                        return

                    elif etype == "run_failed":
                        _print_step_done(current_step, step_start)
                        error = data.get("error", "Unknown error")
                        total = format_duration(time.monotonic() - run_start)
                        print_error(f"Run failed ({total}): {error}")
                        click.echo(f"  View logs: forge runs logs {run_id}")
                        return

    except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError):
        click.echo(f"  Could not connect to run stream. Run continues in background.")
        click.echo(f"  View logs: forge runs logs {run_id}")


def _print_step_done(step_name: str | None, step_start: float | None):
    if not step_name or not step_start:
        return
    duration = format_duration(time.monotonic() - step_start)
    padded = step_name.ljust(_STEP_COMPLETE_PAD)
    click.echo(f"  {padded} done ({duration})")


def _print_results_link(api_url: str, run_id: str):
    port = _get_frontend_port()
    if port:
        click.echo(f"  See results: http://localhost:{port}/runs/{run_id}")
    else:
        click.echo(f"  See results: {api_url}/api/runs/{run_id}")


def _get_frontend_port() -> int | None:
    pid_file = _FORGE_PID_DIR / "frontend.pid"
    if not pid_file.exists():
        return None
    try:
        import os
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return 3000  # Default frontend port
    except (ValueError, ProcessLookupError, PermissionError):
        return None
