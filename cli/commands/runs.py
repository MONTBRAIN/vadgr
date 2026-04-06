"""Run commands -- list, get, cancel, approve, logs."""

from __future__ import annotations

import click

from cli.client import api_get, api_post
from cli.output import print_table, print_kv, print_success, print_warning, format_status, status_text


@click.group("runs", invoke_without_command=True)
@click.pass_context
def runs_group(ctx):
    """Manage runs."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(list_runs)


@runs_group.command("list")
@click.option("--status", "-s", default=None, help="Filter by status")
@click.pass_context
def list_runs(ctx, status: str | None):
    """List all runs."""
    path = "/api/runs"
    if status:
        path = f"{path}?status={status}"
    data = api_get(ctx, path)
    if not data:
        print_warning("No runs found.")
        return

    rows = []
    for r in data:
        agent = r.get("agent_name", r.get("agent_id", "-"))
        duration = r.get("duration", "-")
        if isinstance(duration, (int, float)):
            duration = f"{duration:.0f}s"
        rows.append([r["id"][:8], agent, status_text(r.get("status", "?")), str(duration)])
    print_table(["Run ID", "Agent", "Status", "Duration"], rows)


@runs_group.command("get")
@click.argument("run_id")
@click.pass_context
def get_run(ctx, run_id: str):
    """Show run details."""
    if not run_id:
        raise click.ClickException("Run ID is required.")
    data = api_get(ctx, f"/api/runs/{run_id}")
    if not isinstance(data, dict):
        raise click.ClickException(f"Run '{run_id}' not found.")
    duration = data.get("duration", "-")
    if isinstance(duration, (int, float)):
        duration = f"{duration:.1f}s"
    print_kv([
        ("Run ID", data["id"]),
        ("Agent", data.get("agent_name", "-")),
        ("Status", format_status(data.get("status", "unknown"))),
        ("Provider", data.get("provider", "-")),
        ("Model", data.get("model", "-")),
        ("Duration", str(duration)),
    ])

    steps = data.get("steps", [])
    if steps:
        click.echo(f"\nSteps:")
        for i, s in enumerate(steps, 1):
            click.echo(f"  {i}. {s.get('name', '?')} -- {format_status(s.get('status', '?'))}")


@runs_group.command("cancel")
@click.argument("run_id")
@click.pass_context
def cancel_run(ctx, run_id: str):
    """Cancel a running run."""
    api_post(ctx, f"/api/runs/{run_id}/cancel")
    print_success(f"Cancelled run {run_id}")


@runs_group.command("approve")
@click.argument("run_id")
@click.pass_context
def approve_run(ctx, run_id: str):
    """Approve a run waiting at an approval gate."""
    api_post(ctx, f"/api/runs/{run_id}/approve")
    print_success(f"Approved run {run_id}")


@runs_group.command("logs")
@click.argument("run_id")
@click.pass_context
def run_logs(ctx, run_id: str):
    """Show run logs."""
    data = api_get(ctx, f"/api/runs/{run_id}/logs")
    if not data:
        print_warning("No logs yet.")
        return

    for entry in data:
        ts = entry.get("timestamp", "")
        msg = entry.get("message", entry.get("data", ""))
        click.echo(f"[{ts}] {msg}")
