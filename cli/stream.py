"""WebSocket streaming for run progress."""

from __future__ import annotations

import asyncio
import json
import time

import click
import websockets
from rich.console import Console

from cli.output import format_duration, print_success, print_error

_SPINNER_STYLE = "dots"

# What the watcher saw, so the caller can turn it into an exit code. A run's
# outcome and the watcher's fate are different facts: `detached` means the run
# is still going and nobody is looking, which is neither success nor failure.
COMPLETED = "completed"
FAILED = "failed"
DETACHED = "detached"
UNKNOWN = "unknown"


def follow_run(api_url: str, run_id: str, timeout: float = 7200.0) -> str:
    """Connect to the run WebSocket and report progress until the run ends.

    Returns one of ``COMPLETED``, ``FAILED``, ``DETACHED`` or ``UNKNOWN``.
    """
    ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/ws/runs/{run_id}"

    try:
        return asyncio.run(_stream(ws_url, run_id, api_url, timeout))
    except KeyboardInterrupt:
        # Ctrl-C detaches the watcher. It does not cancel the run: an unattended
        # batch is the point of the product, and killing hours of work because
        # somebody closed a terminal is the opposite of it. Cancelling is
        # `vadgr runs cancel`, which says so.
        click.echo("\n  Detached. The run continues.")
        click.echo(f"  Check it with: vadgr runs get {run_id}")
        click.echo(f"  Stop it with:  vadgr runs cancel {run_id}")
        return DETACHED


async def _stream(ws_url: str, run_id: str, api_url: str, timeout: float) -> str:
    console = Console()
    run_start = time.monotonic()

    try:
        async with websockets.connect(ws_url) as ws:
            status = console.status("Starting...", spinner=_SPINNER_STYLE)
            status.start()

            while True:
                elapsed = time.monotonic() - run_start
                if elapsed > timeout:
                    status.stop()
                    click.echo(f"  Timed out after {format_duration(timeout)}. Run continues in background.")
                    return DETACHED

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                except asyncio.TimeoutError:
                    continue

                event = json.loads(raw)
                etype = event.get("type", "")
                data = event.get("data", {})

                if etype == "agent_started":
                    name = data.get("name", "")
                    status.update(f"Running {name}..." if name else "Running...")

                elif etype == "run_completed":
                    status.stop()
                    total = format_duration(time.monotonic() - run_start)
                    print_success(f"Run completed ({total})")
                    click.echo()
                    _print_results_link(api_url, run_id)
                    return COMPLETED

                elif etype == "run_failed":
                    status.stop()
                    error = data.get("error", "Unknown error")
                    total = format_duration(time.monotonic() - run_start)
                    print_error(f"Run failed ({total}): {error}")
                    click.echo(f"  See the run: vadgr runs get {run_id}")
                    return FAILED

    except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError):
        click.echo("  Could not connect to run stream. Run continues in background.")
        click.echo(f"  See the run: vadgr runs get {run_id}")
        return UNKNOWN


def _print_results_link(api_url: str, run_id: str):
    click.echo(f"  See results: {api_url}/api/runs/{run_id}")
