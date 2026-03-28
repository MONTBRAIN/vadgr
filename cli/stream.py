"""WebSocket streaming for run progress."""

from __future__ import annotations

import asyncio
import json
import re

import click
import websockets
from rich.console import Console

_SPINNER_STYLE = "dots"
_STEP_PATTERN = re.compile(r"---\s*Step\s+(\d+)[:/]\s*(.*?)\s*---", re.IGNORECASE)
_STEP_ALT_PATTERN = re.compile(r"---\s*Step\s+(\d+)\s*complete", re.IGNORECASE)


def follow_run(api_url: str, run_id: str, timeout: float = 600.0):
    """Connect to the run WebSocket and show step progress until done."""
    ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/ws/runs/{run_id}"

    try:
        asyncio.run(_stream(ws_url, run_id, timeout))
    except KeyboardInterrupt:
        click.echo(f"\n  Detached. Run continues in background.")
        click.echo(f"  View logs: forge runs logs {run_id}")


async def _stream(ws_url: str, run_id: str, timeout: float):
    console = Console()
    current_step = ""

    try:
        async with websockets.connect(ws_url) as ws:
            with console.status("Starting...", spinner=_SPINNER_STYLE) as status:
                start = asyncio.get_event_loop().time()

                while True:
                    elapsed = asyncio.get_event_loop().time() - start
                    if elapsed > timeout:
                        click.echo(f"  Timed out after {timeout:.0f}s. Run continues in background.")
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
                            step_num = step_match.group(1)
                            step_name = step_match.group(2).strip()
                            current_step = f"Step {step_num}: {step_name}"
                            status.update(f"{current_step}...")

                    elif etype == "run_completed":
                        break

                    elif etype == "run_failed":
                        error = data.get("error", "Unknown error")
                        click.echo(f"  Run failed: {error}")
                        click.echo(f"  View logs: forge runs logs {run_id}")
                        return

            click.echo(f"  Run completed")

    except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError):
        click.echo(f"  Could not connect to run stream. Run continues in background.")
        click.echo(f"  View logs: forge runs logs {run_id}")
