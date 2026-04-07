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
        run_status = status_text(r.get("status", "?"))
        # Show which step failed for failed runs
        outputs = r.get("outputs") or {}
        if r.get("status") == "failed" and isinstance(outputs, dict):
            error = outputs.get("error", "")
            # Extract step number from error like "Step 3 (Test CLI) failed: ..."
            if error.startswith("Step "):
                parts = error.split(")", 1)
                if parts:
                    run_status = f"failed ({parts[0]})"
        rows.append([r["id"][:8], agent, run_status, str(duration)])
    print_table(["Run ID", "Agent", "Status", "Duration"], rows)


@runs_group.command("get")
@click.argument("run_id")
@click.pass_context
def get_run(ctx, run_id: str):
    """Show run details."""
    run_id = _resolve_run_id(ctx, run_id)
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

    # Show error detail and resume hint for failed runs
    if data.get("status") == "failed":
        outputs = data.get("outputs") or {}
        if isinstance(outputs, dict) and outputs.get("error"):
            click.echo(f"\nError: {outputs['error']}")
        click.echo(f"\nResume with: vadgr runs resume {data['id'][:8]}")


@runs_group.command("cancel")
@click.argument("run_id")
@click.pass_context
def cancel_run(ctx, run_id: str):
    """Cancel a running run."""
    run_id = _resolve_run_id(ctx, run_id)
    api_post(ctx, f"/api/runs/{run_id}/cancel")
    print_success(f"Cancelled run {run_id}")


@runs_group.command("approve")
@click.argument("run_id")
@click.pass_context
def approve_run(ctx, run_id: str):
    """Approve a run waiting at an approval gate."""
    run_id = _resolve_run_id(ctx, run_id)
    api_post(ctx, f"/api/runs/{run_id}/approve")
    print_success(f"Approved run {run_id}")


@runs_group.command("resume")
@click.argument("run_id")
@click.pass_context
def resume_run(ctx, run_id: str):
    """Resume a failed run from its last completed step."""
    run_id = _resolve_run_id(ctx, run_id)
    data = api_post(ctx, f"/api/runs/{run_id}/resume")
    if isinstance(data, dict):
        msg = data.get("message", "")
        if "Already" in msg:
            print_warning(msg)
        else:
            print_success(f"Resuming run {run_id}")
    else:
        print_success(f"Resume requested for {run_id}")


@runs_group.command("logs")
@click.argument("run_id")
@click.pass_context
def run_logs(ctx, run_id: str):
    """Show run logs."""
    run_id = _resolve_run_id(ctx, run_id)
    data = api_get(ctx, f"/api/runs/{run_id}/logs")
    if not data:
        print_warning("No logs yet.")
        return

    for entry in data:
        ts = entry.get("timestamp", "")
        msg = entry.get("message", entry.get("data", ""))
        click.echo(f"[{ts}] {msg}")


def _resolve_run_id(ctx, run_id: str) -> str:
    """Resolve a partial run ID to a full UUID."""
    if not run_id:
        raise click.ClickException("Run ID is required.")
    runs = api_get(ctx, "/api/runs")
    if not runs:
        raise click.ClickException("No runs found.")
    for r in runs:
        if r["id"] == run_id or r["id"].startswith(run_id):
            return r["id"]
    raise click.ClickException(f"No run matching '{run_id}' found.")
