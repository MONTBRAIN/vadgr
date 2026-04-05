"""Agent commands -- list, get, create, update, delete, run, import, export."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import click

from cli.client import api_get, api_post, api_put, api_delete
from cli.output import (
    print_table, print_kv, print_success, print_warning, print_info,
    format_status, status_text, wait_with_spinner,
)
from cli.stream import follow_run

_AGENT_DONE = lambda r: r.get("status") not in ("creating", "updating", "importing")


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
        print_warning("No agents found. Create one with: vadgr agents create")
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
    agent_id = _resolve_id(ctx, agent_id)
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
    agent_id = data.get("id", "?")
    print_info(f"Creating {name}...")

    result = wait_with_spinner(
        ctx, f"/api/agents/{agent_id}", _AGENT_DONE,
        f"Generating workflow for {name}...",
    )

    if result.get("status") == "ready":
        print_success(f"{name} is ready (ID: {agent_id})")
    else:
        print_warning(f"{name} finished with status: {result.get('status')} (ID: {agent_id})")


@agents_group.command("update")
@click.argument("agent_id")
@click.option("--name", "-n", default=None)
@click.option("--description", "-d", default=None)
@click.pass_context
def update_agent(ctx, agent_id: str, name: str | None, description: str | None):
    """Update an agent."""
    agent_id = _resolve_id(ctx, agent_id)
    body = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    if not body:
        raise click.ClickException("Nothing to update. Use --name or --description.")

    data = api_put(ctx, f"/api/agents/{agent_id}", body)
    agent_name = data.get("name", agent_id)

    if data.get("status") in ("updating",):
        print_info(f"Updating {agent_name}...")
        result = wait_with_spinner(
            ctx, f"/api/agents/{agent_id}", _AGENT_DONE,
            f"Regenerating workflow for {agent_name}...",
        )
        if result.get("status") == "ready":
            print_success(f"{agent_name} updated and ready")
        else:
            print_warning(f"{agent_name} finished with status: {result.get('status')}")
    else:
        print_success(f"Updated {agent_name}")


@agents_group.command("delete")
@click.argument("agent_id")
@click.pass_context
def delete_agent(ctx, agent_id: str):
    """Delete an agent."""
    agent_id = _resolve_id(ctx, agent_id)
    api_delete(ctx, f"/api/agents/{agent_id}")
    print_success(f"Deleted agent {agent_id}")


@agents_group.command("run")
@click.argument("name_or_id")
@click.option("--input", "-i", "inputs", multiple=True, help="key=value input pairs")
@click.option("--provider", "-p", default=None)
@click.option("--model", "-m", default=None)
@click.option("--background", "-b", is_flag=True, help="Return immediately without following progress")
@click.pass_context
def run_agent(ctx, name_or_id: str, inputs: tuple, provider: str | None, model: str | None,
              background: bool):
    """Run an agent by name or ID."""
    agents = api_get(ctx, "/api/agents")
    agent = _resolve_agent(agents, name_or_id)
    if not agent:
        raise click.ClickException(f"No agent matching '{name_or_id}' found.")

    if agent.get("computer_use"):
        try:
            cu_status = api_get(ctx, "/api/settings/computer-use")
            if not cu_status.get("enabled"):
                raise click.ClickException(
                    f"'{agent['name']}' requires computer use but it is disabled.\n"
                    f"  Enable it with: vadgr computer-use enable"
                )
        except click.ClickException:
            raise

    input_dict = dict(kv.split("=", 1) for kv in inputs) if inputs else {}
    schema = agent.get("input_schema", [])

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

    if background:
        click.echo(f"  View logs: vadgr runs logs {run_id}")
        return

    follow_run(ctx.obj["api_url"], run_id)


@agents_group.command("import")
@click.argument("agnt_file", type=click.Path(exists=True))
@click.pass_context
def import_agent(ctx, agnt_file: str):
    """Import an agent from a .agnt archive."""
    import time
    data = _upload_agnt(ctx, agnt_file)
    agent_id = data.get("id", "?")
    agent_name = data.get("name", "imported agent")
    print_info(f"Importing {agent_name}...")
    time.sleep(1)  # Give the API a moment to start the background task

    result = wait_with_spinner(
        ctx, f"/api/agents/{agent_id}", _AGENT_DONE,
        f"Setting up {agent_name}...",
    )

    if result.get("status") == "ready":
        print_success(f"{agent_name} imported and ready (ID: {agent_id})")
    else:
        print_warning(f"{agent_name} finished with status: {result.get('status')} (ID: {agent_id})")


@agents_group.command("export")
@click.argument("agent_id")
@click.option("--output", "-o", "output_path", default=None, type=click.Path())
@click.pass_context
def export_agent(ctx, agent_id: str, output_path: str | None):
    """Export an agent as a .agnt archive."""
    agent_id = _resolve_id(ctx, agent_id)
    data = _download_binary(ctx, f"/api/agents/{agent_id}/export")
    if not output_path:
        output_path = f"{agent_id[:8]}.agnt"
    with open(output_path, "wb") as f:
        f.write(data)
    print_success(f"Exported to {output_path}")


# -- Helpers --

def _resolve_id(ctx, name_or_id: str) -> str:
    """Resolve a short ID or name to a full agent UUID."""
    agents = api_get(ctx, "/api/agents")
    agent = _resolve_agent(agents, name_or_id)
    if not agent:
        raise click.ClickException(f"No agent matching '{name_or_id}' found.")
    return agent["id"]


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


def _prompt_inputs(ctx, agent: dict, schema: list[dict]) -> dict:
    inputs = {}
    click.echo()
    for field in schema:
        name = field["name"]
        ftype = field.get("type", "text")
        required = field.get("required", False)
        desc = field.get("description", "")
        label = field.get("label") or name

        prompt_text = f"  {label}"
        if desc:
            prompt_text += f" ({desc})"

        if ftype in ("file", "archive", "directory") or ftype.startswith("."):
            suffix = " [required]" if required else " [optional, press Enter to skip]"
            path = click.prompt(f"{prompt_text}{suffix}", default="", show_default=False)
            path = path.strip().strip("'\"")
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
            resolved[key] = _upload_file(ctx, agent["id"], key, os.path.expanduser(value))
        else:
            resolved[key] = value
    return resolved


def _upload_file(ctx, agent_id: str, field_name: str, file_path: str) -> dict:
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
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise click.ClickException(f"Upload failed: {e.read().decode()}")


def _upload_agnt(ctx, file_path: str) -> dict:
    url = f"{ctx.obj['api_url']}/api/agents/import"
    filename = os.path.basename(file_path)

    boundary = "----ForgeImportBoundary"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.extend(f"Content-Type: application/zip\r\n\r\n".encode())
    with open(file_path, "rb") as f:
        body.extend(f.read())
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        url, data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise click.ClickException(f"Import failed: {e.read().decode()}")


def _download_binary(ctx, path: str) -> bytes:
    url = f"{ctx.obj['api_url']}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/zip"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise click.ClickException(f"Download failed (HTTP {e.code})")
