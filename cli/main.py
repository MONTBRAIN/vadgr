"""Root CLI group for Vadgr."""

from __future__ import annotations

import os
import sys

import click

# Enable ANSI colors on Windows (PowerShell/cmd.exe)
if sys.platform == "win32":
    try:
        import colorama
        colorama.just_fix_windows_console()
    except ImportError:
        pass

from cli.commands.info import health, providers, computer_use
from cli.commands.pair_cmd import pair
from cli.commands.provider import model_group, provider_group
from cli.commands.runs import runs_group
from cli.commands.service import start, stop, restart, status, logs, update

_DEFAULT_API_PORT = os.environ.get("VADGR_PORT", "8000")


def _resolve_api_url() -> str:
    """Determine the API URL by checking port files first, then env/defaults."""
    try:
        from cli.commands.service import _read_active_port
        port = _read_active_port("api", int(_DEFAULT_API_PORT))
    except Exception:
        port = int(_DEFAULT_API_PORT)
    return f"http://127.0.0.1:{port}"


@click.group()
@click.option("--api-url", default=None, envvar="VADGR_API_URL", hidden=True)
@click.pass_context
def cli(ctx, api_url: str | None):
    """vadgr CLI."""
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url or _resolve_api_url()


# Command groups
cli.add_command(runs_group)

# Info commands
cli.add_command(health)
cli.add_command(providers)
cli.add_command(computer_use)
cli.add_command(pair)
cli.add_command(provider_group)
cli.add_command(model_group)

# Service commands
cli.add_command(start)
cli.add_command(stop)
cli.add_command(restart)
cli.add_command(status)
cli.add_command(logs)
cli.add_command(update)
# `vadgr api` used to be the "API without the dashboard" variant. Nothing else
# starts any more, so it is the same command under its old name.
cli.add_command(start, "api")


@cli.command("run")
@click.argument("task")
@click.option("--provider", "-p", default=None, help="Provider to run on (needs --model)")
@click.option("--model", "-m", default=None, help="Model to run (needs --provider)")
@click.option("--background", "-b", is_flag=True, help="Start it and return")
@click.option("--json", "as_json", is_flag=True, help="Print the run row as JSON")
@click.pass_context
def run(ctx, task: str, provider: str | None, model: str | None, background: bool,
        as_json: bool):
    """Start a run from a task sentence and watch it.

    Exit code is the run's outcome: 0 completed, 1 failed. `--background` exits
    0 once the run is accepted, because the outcome is not known yet.
    """
    import json as _json

    from cli import stream
    from cli.client import api_post
    from cli.output import print_success
    from cli.stream import follow_run

    if not task.strip():
        raise click.UsageError("TASK must not be empty.")
    if bool(provider) != bool(model):
        raise click.UsageError("--provider and --model must be given together.")

    body: dict = {"task": task}
    if provider:
        body["provider"] = provider
        body["model"] = model

    result = api_post(ctx, "/api/runs", body)
    run_id = result.get("id", "?")

    if as_json:
        click.echo(_json.dumps(result, indent=2))
    else:
        print_success(f"Run started: {run_id}")

    if background:
        click.echo(f"  Watch it with: vadgr runs get {run_id}")
        return

    outcome = follow_run(ctx.obj["api_url"], run_id)
    # Not a ClickException: the outcome was already reported, and a second error
    # line would read as the CLI having failed rather than the run.
    if outcome == stream.FAILED:
        ctx.exit(1)
    if outcome == stream.DETACHED:
        ctx.exit(130)
