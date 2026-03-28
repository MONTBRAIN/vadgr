"""Agent commands -- list, get, create, delete, run."""

from __future__ import annotations

import click

from cli.http import api_get, api_post, api_delete
from cli.output import print_table, print_kv, print_success, print_warning, format_status, status_text


@click.group("agents", invoke_without_command=True)
@click.pass_context
def agents_group(ctx):
    """Manage agents."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(list_agents)


@agents_group.command("list")
@click.pass_context
def list_agents(ctx):
    """List all agents."""
    data = api_get(ctx, "/api/agents")
    if not data:
        print_warning("No agents found. Create one with: forge agents create")
        return

    rows = []
    for a in data:
        steps = len(a.get("steps", []))
        cu = " [desktop]" if a.get("computer_use") else ""
        rows.append([a["id"][:8], a["name"], status_text(a["status"]), f"{steps}{cu}"])
    print_table(["ID", "Name", "Status", "Steps"], rows)


@agents_group.command("get")
@click.argument("agent_id")
@click.pass_context
def get_agent(ctx, agent_id: str):
    """Show agent details."""
    data = api_get(ctx, f"/api/agents/{agent_id}")
    print_kv([
        ("ID", data["id"]),
        ("Name", data["name"]),
        ("Status", format_status(data.get("status", "unknown"))),
        ("Provider", data.get("provider", "-")),
        ("Description", data.get("description", "-")),
    ])

    steps = data.get("steps", [])
    if steps:
        click.echo(f"\nSteps ({len(steps)}):")
        for i, s in enumerate(steps, 1):
            cu = " [desktop]" if s.get("computer_use") else ""
            click.echo(f"  {i}. {s['name']}{cu}")


@agents_group.command("create")
@click.option("--name", "-n", required=True)
@click.option("--description", "-d", required=True)
@click.option("--provider", "-p", default="claude_code")
@click.option("--model", "-m", default=None)
@click.pass_context
def create_agent(ctx, name: str, description: str, provider: str, model: str | None):
    """Create a new agent."""
    body = {"name": name, "description": description, "provider": provider}
    if model:
        body["model"] = model
    data = api_post(ctx, "/api/agents", body)
    print_success(f"Created: {data.get('name', name)} (ID: {data.get('id', '?')})")


@agents_group.command("delete")
@click.argument("agent_id")
@click.pass_context
def delete_agent(ctx, agent_id: str):
    """Delete an agent."""
    api_delete(ctx, f"/api/agents/{agent_id}")
    print_success(f"Deleted agent {agent_id}")


@agents_group.command("run")
@click.argument("name_or_id")
@click.option("--input", "-i", "inputs", multiple=True, help="key=value input pairs")
@click.option("--provider", "-p", default=None)
@click.option("--model", "-m", default=None)
@click.pass_context
def run_agent(ctx, name_or_id: str, inputs: tuple, provider: str | None, model: str | None):
    """Run an agent by name or ID."""
    agents = api_get(ctx, "/api/agents")
    agent = _resolve_agent(agents, name_or_id)
    if not agent:
        raise click.ClickException(f"No agent matching '{name_or_id}' found.")

    body = {}
    if inputs:
        body["inputs"] = dict(kv.split("=", 1) for kv in inputs)
    if provider:
        body["provider"] = provider
    if model:
        body["model"] = model

    result = api_post(ctx, f"/api/agents/{agent['id']}/run", body)
    run_id = result.get("run_id", result.get("id", "?"))
    print_success(f"Run started: {run_id}")
    click.echo(f"  View logs: forge runs logs {run_id}")


def _resolve_agent(agents: list[dict], name_or_id: str) -> dict | None:
    name_lower = name_or_id.lower()
    for a in agents:
        if a["id"] == name_or_id or a["id"].startswith(name_or_id):
            return a
    for a in agents:
        if a["name"].lower() == name_lower:
            return a
    for a in agents:
        if name_lower in a["name"].lower():
            return a
    return None
