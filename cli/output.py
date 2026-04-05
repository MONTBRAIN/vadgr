"""Formatting helpers for CLI output, powered by Rich."""

from __future__ import annotations

import time
from io import StringIO

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from cli.client import api_get

_STATUS_STYLES = {
    "ready": "pale_green3",
    "running": "light_sky_blue1",
    "creating": "khaki1",
    "queued": "khaki1",
    "awaiting_approval": "khaki1",
    "completed": "pale_green3",
    "failed": "indian_red1",
    "cancelled": "indian_red1",
    "error": "indian_red1",
    "available": "pale_green3",
    "not found": "indian_red1",
    "not running": "indian_red1",
    "stopped": "indian_red1",
}

_LABEL_WIDTH = 12


def _render(renderable) -> str:
    buf = StringIO()
    Console(file=buf, width=120, highlight=False, force_terminal=True).print(renderable)
    return buf.getvalue()


def format_table(headers: list[str], rows: list[list]) -> Table:
    table = Table(show_edge=False, pad_edge=False, box=None)
    for h in headers:
        table.add_column(h, header_style="dim", style="white")
    for row in rows:
        table.add_row(*[c if isinstance(c, Text) else str(c) for c in row])
    return table


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    return _render(format_table(headers, rows))


def print_table(headers: list[str], rows: list[list[str]]):
    click.echo(_render(format_table(headers, rows)), nl=False)


def format_status(status: str) -> str:
    style = _STATUS_STYLES.get(status, "white")
    text = Text(status)
    text.stylize(style)
    return _render(text).strip()


def status_text(status: str) -> Text:
    style = _STATUS_STYLES.get(status, "white")
    text = Text(status)
    text.stylize(style)
    return text


def print_kv(pairs: list[tuple[str, str]]):
    if not pairs:
        return
    lines = []
    for label, value in pairs:
        lines.append(f"  {label + ':':<{_LABEL_WIDTH + 1}} {value}")
    click.echo("\n".join(lines))


def _styled(markup: str) -> str:
    buf = StringIO()
    Console(file=buf, highlight=False, force_terminal=True).print(markup)
    return buf.getvalue()


def print_success(msg: str):
    click.echo(_styled(f"[pale_green3]\\[vadgr][/] {msg}"), nl=False)


def print_info(msg: str):
    click.echo(_styled(f"[light_sky_blue1]\\[vadgr][/] {msg}"), nl=False)


def print_warning(msg: str):
    click.echo(_styled(f"[khaki1]\\[vadgr][/] {msg}"), nl=False)


def print_error(msg: str):
    click.echo(_styled(f"[indian_red1]\\[vadgr][/] {msg}"), nl=False)


def format_duration(seconds: float) -> str:
    import math
    s = max(0, math.ceil(seconds)) if seconds > 0 else 0
    if s < 60:
        return f"{s}s"
    m = s // 60
    s = s % 60
    return f"{m}m {s}s"


_SPINNER_STYLE = "dots"
_DEFAULT_POLL_INTERVAL = 3.0
_DEFAULT_TIMEOUT = 600.0


def wait_with_spinner(ctx, path: str, done_fn, message: str,
                      interval: float = _DEFAULT_POLL_INTERVAL,
                      timeout: float = _DEFAULT_TIMEOUT):
    """Poll an API endpoint with a spinner until done_fn(response) is True."""
    console = Console()
    elapsed = 0.0

    with console.status(message, spinner=_SPINNER_STYLE):
        while elapsed < timeout:
            try:
                result = api_get(ctx, path)
                if done_fn(result):
                    return result
            except click.ClickException:
                pass  # API temporarily unreachable, retry
            time.sleep(interval)
            elapsed += interval

    raise click.ClickException(f"Operation timed out after {timeout:.0f}s")
