"""Click CLI for the Agent Forge registry."""

from __future__ import annotations

import click

from registry import registry_client


@click.group()
def cli():
    """forge registry -- package manager for Agent Forge agents."""
    pass


@cli.command()
@click.argument("folder", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None, help="Output .agnt file path.")
def pack(folder: str, output: str | None):
    """Package an agent folder into a .agnt archive."""
    try:
        result = registry_client.pack(folder, output)
        click.echo(f"Packed: {result}")
    except (FileNotFoundError, ValueError) as e:
        raise click.ClickException(str(e))


@cli.command()
@click.argument("name")
@click.option("--registry", "-r", default=None, help="Registry name to pull from.")
@click.option("--force", "-f", is_flag=True, help="Overwrite if already installed.")
def pull(name: str, registry: str | None, force: bool):
    """Download and install an agent from a registry."""
    try:
        result = registry_client.pull(name, registry_name=registry, force=force)
        click.echo(f"Installed: {name} -> {result}")
    except (ValueError, FileExistsError, FileNotFoundError, RuntimeError) as e:
        raise click.ClickException(str(e))


@cli.command()
@click.argument("agnt_file", type=click.Path(exists=True))
@click.option("--registry", "-r", default=None, help="Registry name to push to.")
def push(agnt_file: str, registry: str | None):
    """Publish a .agnt file to a registry."""
    try:
        result = registry_client.push(agnt_file, registry_name=registry)
        click.echo(result)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise click.ClickException(str(e))


@cli.command()
@click.argument("query")
@click.option("--registry", "-r", default=None, help="Search a specific registry.")
def search(query: str, registry: str | None):
    """Search for agents in registries."""
    try:
        results = registry_client.search(query, registry_name=registry)
    except ValueError as e:
        raise click.ClickException(str(e))

    if not results:
        click.echo("No agents found.")
        return

    # Print table
    click.echo(f"{'Name':<30} {'Version':<10} {'Description'}")
    click.echo("-" * 72)
    for agent in results:
        name = agent.get("name", "")
        version = agent.get("version", "")
        desc = agent.get("description", "")
        if len(desc) > 40:
            desc = desc[:37] + "..."
        click.echo(f"{name:<30} {version:<10} {desc}")


@cli.command(name="agents")
def list_agents():
    """List locally installed agents."""
    installed = registry_client.agents()

    if not installed:
        click.echo("No agents installed.")
        click.echo("Use 'forge search <query>' to find agents.")
        click.echo("Use 'forge pull <name>' to install one.")
        return

    click.echo(f"{'Name':<25} {'Version':<10} {'Steps':<7} {'Description'}")
    click.echo("-" * 72)
    for agent in installed:
        name = agent.get("name", "")
        version = agent.get("version", "")
        steps = str(agent.get("steps", 0))
        desc = agent.get("description", "")
        if len(desc) > 35:
            desc = desc[:32] + "..."
        click.echo(f"{name:<25} {version:<10} {steps:<7} {desc}")
