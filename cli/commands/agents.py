"""Agent commands -- list, get, create, delete, run."""

from __future__ import annotations

import os

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

    inputs = data.get("input_schema", [])
    if inputs:
        click.echo(f"\nInputs:")
        for field in inputs:
            req = "required" if field.get("required") else "optional"
            desc = field.get("description", "")
            click.echo(f"  {field['name']} ({field.get('type', 'text')}, {req}) -- {desc}")

    outputs = data.get("output_schema", [])
    if outputs:
        click.echo(f"\nOutputs:")
        for field in outputs:
            desc = field.get("description", "")
            click.echo(f"  {field['name']} ({field.get('type', 'text')}) -- {desc}")


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

    input_dict = dict(kv.split("=", 1) for kv in inputs) if inputs else {}
    schema = agent.get("input_schema", [])

    # Interactive prompting when no flags provided and schema exists
    if not input_dict and schema:
        input_dict = _prompt_inputs(ctx, agent, schema)
    elif input_dict and schema:
        input_dict = _resolve_file_inputs(ctx, agent, schema, input_dict)

    body = {"inputs": input_dict}
    if provider:
        body["provider"] = provider
    if model:
        body["model"] = model

    result = api_post(ctx, f"/api/agents/{agent['id']}/run", body)
    run_id = result.get("run_id", result.get("id", "?"))
    print_success(f"Run started: {run_id}")
    click.echo(f"  View logs: forge runs logs {run_id}")


def _prompt_inputs(ctx, agent: dict, schema: list[dict]) -> dict:
    inputs = {}
    click.echo()
    for field in schema:
        name = field["name"]
        ftype = field.get("type", "text")
        required = field.get("required", False)
        desc = field.get("description", "")
        label = field.get("label", name)

        prompt_text = f"  {label}"
        if desc:
            prompt_text += f" ({desc})"

        if ftype in ("file", "archive", "directory") or ftype.startswith("."):
            # File input -- prompt for path, upload to API
            suffix = " [required]" if required else " [optional, press Enter to skip]"
            path = click.prompt(f"{prompt_text}{suffix}", default="", show_default=False)
            if not path:
                if required:
                    raise click.ClickException(f"Input '{name}' is required.")
                continue
            path = os.path.expanduser(path)
            if not os.path.isfile(path):
                raise click.ClickException(f"File not found: {path}")
            descriptor = _upload_file(ctx, agent["id"], name, path)
            inputs[name] = descriptor
        else:
            # Text input
            suffix = " [required]" if required else " [optional, press Enter to skip]"
            value = click.prompt(f"{prompt_text}{suffix}", default="", show_default=False)
            if not value:
                if required:
                    raise click.ClickException(f"Input '{name}' is required.")
                continue
            inputs[name] = value

    click.echo()
    return inputs


def _resolve_file_inputs(ctx, agent: dict, schema: list[dict], inputs: dict) -> dict:
    file_fields = {
        f["name"] for f in schema
        if f.get("type") in ("file", "archive", "directory") or (f.get("type", "").startswith("."))
    }
    resolved = {}
    for key, value in inputs.items():
        if key in file_fields and os.path.isfile(os.path.expanduser(value)):
            path = os.path.expanduser(value)
            resolved[key] = _upload_file(ctx, agent["id"], key, path)
        else:
            resolved[key] = value
    return resolved


def _upload_file(ctx, agent_id: str, field_name: str, file_path: str) -> dict:
    import urllib.request
    import mimetypes

    url = f"{ctx.obj['api_url']}/api/agents/{agent_id}/uploads"
    filename = os.path.basename(file_path)
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    boundary = "----ForgeUploadBoundary"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="field_name"\r\n\r\n{field_name}\r\n'.encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    with open(file_path, "rb") as f:
        body.extend(f.read())
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url, data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            import json
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        raise click.ClickException(f"Upload failed: {detail}")


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
