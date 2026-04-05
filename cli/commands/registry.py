"""Registry commands -- pack, pull, push, search, agents, serve, add, use, list, remove."""

from __future__ import annotations

import click

from registry import registry_client
from registry.config import load_config, save_config, CONFIG_PATH
from cli.output import print_table, print_success, print_warning, print_info, status_text


@click.group("registry")
def registry_group():
    """Package manager for vadgr agents."""
    pass


@registry_group.command()
@click.argument("folder", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None)
def pack(folder: str, output: str | None):
    """Package an agent folder into a .agnt archive."""
    try:
        result = registry_client.pack(folder, output)
        print_success(f"Packed: {result}")
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e))


@registry_group.command()
@click.argument("name")
@click.option("--registry", "-r", default=None)
@click.option("--force", "-f", is_flag=True)
@click.pass_context
def pull(ctx, name: str, registry: str | None, force: bool):
    """Download and install an agent from a registry."""
    import tempfile
    from pathlib import Path

    archive_path = Path(tempfile.mktemp(suffix=".agnt"))
    try:
        result = registry_client.pull(
            name, registry_name=registry, force=force, keep_archive=archive_path,
        )
        print_success(f"Installed: {name} -> {result}")
    except (ValueError, FileExistsError, FileNotFoundError, RuntimeError) as e:
        archive_path.unlink(missing_ok=True)
        raise click.ClickException(str(e))

    _import_to_api(ctx, name, archive_path)


@registry_group.command()
@click.argument("agnt_file", type=click.Path(exists=True))
@click.option("--registry", "-r", default=None)
def push(agnt_file: str, registry: str | None):
    """Publish a .agnt file to a registry."""
    try:
        result = registry_client.push(agnt_file, registry_name=registry)
        print_success(result)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise click.ClickException(str(e))


@registry_group.command()
@click.argument("query")
@click.option("--registry", "-r", default=None)
def search(query: str, registry: str | None):
    """Search for agents in registries."""
    try:
        results = registry_client.search(query, registry_name=registry)
    except ValueError as e:
        raise click.ClickException(str(e))

    if not results:
        print_warning("No agents found.")
        return

    rows = []
    for a in results:
        rows.append([a.get("name", ""), a.get("version", ""), a.get("description", "")])
    print_table(["Name", "Version", "Description"], rows)


@registry_group.command("agents")
def list_agents():
    """List locally installed agents."""
    installed = registry_client.agents()
    if not installed:
        print_warning("No agents installed.")
        return

    rows = []
    for a in installed:
        rows.append([a.get("name", ""), a.get("version", ""), str(a.get("steps", 0)), a.get("description", "")])
    print_table(["Name", "Version", "Steps", "Description"], rows)


@registry_group.command()
@click.option("--port", default=9876, type=int)
@click.option("--dir", "directory", default="./registry-data", type=click.Path())
@click.option("--token", default="")
def serve(port: int, directory: str, token: str):
    """Start a self-hosted registry server."""
    from pathlib import Path
    from registry.server import run_server
    run_server(port=port, directory=Path(directory), token=token)


@registry_group.command("add")
@click.argument("name")
@click.option("--type", "reg_type", required=True, type=click.Choice(["github", "http", "local"]))
@click.option("--url", default=None)
@click.option("--path", default=None)
@click.option("--github-repo", default=None)
@click.option("--token", default=None)
def add_registry(name: str, reg_type: str, url: str | None, path: str | None,
                 github_repo: str | None, token: str | None):
    """Add a registry to your config."""
    config = load_config()
    registries = config.get("registries", [])

    if any(r["name"] == name for r in registries):
        raise click.ClickException(f"Registry '{name}' already exists. Remove it first.")

    entry = {"name": name, "type": reg_type}
    if url:
        entry["url"] = url
    if path:
        entry["path"] = path
    if github_repo:
        entry["github_repo"] = github_repo
        if not url:
            entry["url"] = f"https://raw.githubusercontent.com/{github_repo}/master"
    if token:
        entry["token"] = token

    registries.append(entry)
    config["registries"] = registries
    save_config(config)
    print_success(f"Added registry '{name}' ({reg_type})")


@registry_group.command("use")
@click.argument("name")
def use_registry(name: str):
    """Set a registry as the active default."""
    config = load_config()
    registries = config.get("registries", [])

    found = False
    for reg in registries:
        if reg["name"] == name:
            reg["default"] = True
            found = True
        else:
            reg.pop("default", None)

    if not found:
        raise click.ClickException(f"Registry '{name}' not found. Add it first with: vadgr registry add")

    config["registries"] = registries
    save_config(config)
    print_success(f"Now using registry '{name}'")


@registry_group.command("list")
def list_registries():
    """List configured registries."""
    config = load_config()
    registries = config.get("registries", [])

    if not registries:
        print_warning("No registries configured.")
        return

    rows = []
    for r in registries:
        active = status_text("active") if r.get("default") else ""
        location = r.get("url", r.get("path", r.get("github_repo", "-")))
        rows.append([r["name"], r["type"], location, active])
    print_table(["Name", "Type", "URL", ""], rows)


@registry_group.command("remove")
@click.argument("name")
def remove_registry(name: str):
    """Remove a registry from your config."""
    config = load_config()
    registries = config.get("registries", [])

    target = None
    for r in registries:
        if r["name"] == name:
            target = r
            break

    if not target:
        raise click.ClickException(f"Registry '{name}' not found.")

    if target.get("default"):
        raise click.ClickException(f"Cannot remove '{name}' because it is the active default. Switch first with: vadgr registry use <other>")

    registries.remove(target)
    config["registries"] = registries
    save_config(config)
    print_success(f"Removed registry '{name}'")


# -- Helpers --

def _import_to_api(ctx, name: str, archive_path):
    """Register a pulled agent with the API so it appears in `forge agents list`."""
    from pathlib import Path

    try:
        from cli.commands.agents import _upload_agnt
        from cli.output import wait_with_spinner
        import time

        data = _upload_agnt(ctx, str(archive_path))
        agent_id = data.get("id", "?")
        agent_name = data.get("name", name)
        print_info(f"Registering {agent_name} with API...")
        time.sleep(1)

        _agent_done = lambda r: r.get("status") not in ("creating", "updating", "importing")
        result = wait_with_spinner(
            ctx, f"/api/agents/{agent_id}", _agent_done,
            f"Setting up {agent_name}...",
        )

        if result.get("status") == "ready":
            print_success(f"{agent_name} is ready (ID: {agent_id[:8]})")
        else:
            print_warning(f"{agent_name} finished with status: {result.get('status')}")
    except Exception as exc:
        print_warning(
            f"Agent files installed but API registration failed: {exc}\n"
            f"  Is the API running? Start it with: vadgr start\n"
            f"  Then import manually with: vadgr agents import {archive_path}"
        )
        return

    # Only clean up the archive on success; on failure it stays for manual import
    Path(archive_path).unlink(missing_ok=True)
