"""WebSocket streaming for run progress."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import click
import websockets
from rich.console import Console

from cli.output import format_duration, print_success, print_error

_SPINNER_STYLE = "dots"
_FORGE_PID_DIR = Path.home() / ".forge" / "pids"
_STEP_COMPLETE_PAD = 40
_MAX_STEP_NAME_LEN = 45


def _extract_step(data: dict, current_num: int | None) -> tuple[int | None, str | None]:
    """Extract step number and name from event data. Returns (None, None) if not a new step."""
    step_num = data.get("step_num")
    if step_num is None or step_num == current_num:
        return None, None

    step_name = data.get("step_name") or f"Step {step_num}"
    if len(step_name) > _MAX_STEP_NAME_LEN:
        step_name = step_name[:_MAX_STEP_NAME_LEN - 3] + "..."
    return step_num, step_name


def follow_run(api_url: str, run_id: str, timeout: float = 7200.0):
    """Connect to the run WebSocket and show step progress until done."""
    ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/ws/runs/{run_id}"

    try:
        asyncio.run(_stream(ws_url, run_id, api_url, timeout))
    except KeyboardInterrupt:
        click.echo(f"\n  Cancelling run...")
        try:
            from cli.client import api_post
            ctx = click.Context(click.Command("cancel"))
            ctx.ensure_object(dict)
            ctx.obj["api_url"] = api_url
            api_post(ctx, f"/api/runs/{run_id}/cancel")
            click.echo(f"  Run cancelled.")
        except Exception:
            click.echo(f"  Could not cancel. Check: vadgr runs get {run_id}")


async def _stream(ws_url: str, run_id: str, api_url: str, timeout: float):
    console = Console()
    current_step_num = None
    current_step_label = None
    step_start = None
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

                elif etype == "step_completed":
                    status.stop()
                    step_num = data.get("step_num", "?")
                    step_name = data.get("step_name", "")
                    step_status = data.get("status", "completed")
                    duration = data.get("duration", 0)
                    if len(step_name) > _MAX_STEP_NAME_LEN:
                        step_name = step_name[:_MAX_STEP_NAME_LEN - 3] + "..."
                    label = f"Step {step_num}: {step_name}"
                    padded = label.ljust(_STEP_COMPLETE_PAD)
                    result_text = "done" if step_status == "completed" else "FAILED"
                    click.echo(f"  {padded} {result_text} ({format_duration(duration)})")
                    current_step_num = None
                    current_step_label = None
                    status.start()

                elif etype == "agent_log":
                    new_num, new_name = _extract_step(data, current_step_num)
                    if new_num is not None:
                        current_step_num = new_num
                        current_step_label = f"Step {new_num}: {new_name}"
                        step_start = time.monotonic()
                        status.update(f"{current_step_label}...")

                elif etype == "run_completed":
                    status.stop()
                    total = format_duration(time.monotonic() - run_start)
                    print_success(f"Run completed ({total})")
                    click.echo()
                    _print_results_link(api_url, run_id)
                    return

                elif etype == "run_failed":
                    status.stop()
                    error = data.get("error", "Unknown error")
                    total = format_duration(time.monotonic() - run_start)
                    print_error(f"Run failed ({total}): {error}")
                    click.echo(f"  View logs: vadgr runs logs {run_id}")
                    return

    except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError):
        click.echo(f"  Could not connect to run stream. Run continues in background.")
        click.echo(f"  View logs: vadgr runs logs {run_id}")


def _print_step_done(step_label: str, step_start: float | None):
    if not step_start:
        return
    duration = format_duration(time.monotonic() - step_start)
    padded = step_label.ljust(_STEP_COMPLETE_PAD)
    click.echo(f"  {padded} done ({duration})")


def _print_results_link(api_url: str, run_id: str):
    port = _get_frontend_port()
    if port:
        click.echo(f"  See results: http://localhost:{port}/runs/{run_id}")
    else:
        click.echo(f"  See results: {api_url}/api/runs/{run_id}")


def _get_frontend_port() -> int | None:
    import os
    import urllib.request

    # Read from port file first (set by vadgr start)
    try:
        from cli.commands.service import _read_active_port
        port = _read_active_port("frontend", int(os.environ.get("AGENT_FORGE_FRONTEND_PORT", "3000")))
    except Exception:
        port = int(os.environ.get("AGENT_FORGE_FRONTEND_PORT", "3000"))

    try:
        urllib.request.urlopen(f"http://localhost:{port}", timeout=1)
        return port
    except Exception:
        pass
    return None
