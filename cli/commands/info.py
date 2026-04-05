"""Info commands -- health, providers, computer-use."""

from __future__ import annotations

import click

from rich.console import Console

from cli.client import api_get, api_put
from cli.output import print_kv, print_success, print_warning, format_status


@click.command()
@click.pass_context
def health(ctx):
    """Check API health."""
    data = api_get(ctx, "/api/health")
    print_kv([
        ("Status", format_status(data.get("status", "unknown"))),
        ("Version", data.get("version", "unknown")),
        ("Platform", data.get("platform", "unknown")),
    ])
    modules = data.get("modules", {})
    if modules:
        click.echo("\nModules:")
        for mod, available in modules.items():
            status = "available" if available else "not found"
            click.echo(f"  {mod}: {format_status(status)}")


@click.command()
@click.pass_context
def providers(ctx):
    """List available providers and models."""
    data = api_get(ctx, "/api/providers")
    if not data:
        click.echo("No providers configured.")
        return

    for p in data:
        available = "available" if p.get("available") else "not found"
        click.echo(f"  {p['name']} ({p['id']}) -- {format_status(available)}")
        for m in p.get("models", []):
            click.echo(f"    - {m['name']} ({m['id']})")
        click.echo()


@click.group("computer-use")
def computer_use():
    """Manage computer use (desktop automation)."""
    pass


@computer_use.command("enable")
@click.pass_context
def cu_enable(ctx):
    """Enable computer use."""
    console = Console()
    with console.status("Setting up computer use (this may take a minute)...", spinner="dots"):
        result = api_put(ctx, "/api/settings/computer-use", {"enabled": True}, timeout=120)
    daemon = result.get("daemon", "")
    if daemon == "running":
        print_success(f"Computer use enabled (Windows daemon running on port 19542)")
    elif daemon == "degraded":
        print_warning("Computer use enabled but daemon is not responding. Try: vadgr computer-use disable && vadgr computer-use enable")
    elif daemon == "stopped":
        print_warning("Computer use enabled but daemon failed to start.")
    else:
        print_success("Computer use enabled")


@computer_use.command("disable")
@click.pass_context
def cu_disable(ctx):
    """Disable computer use."""
    console = Console()
    with console.status("Disabling computer use...", spinner="dots"):
        api_put(ctx, "/api/settings/computer-use", {"enabled": False})
    print_success("Computer use disabled")


@computer_use.command("status")
@click.pass_context
def cu_status(ctx):
    """Check computer use status."""
    data = api_get(ctx, "/api/settings/computer-use")
    enabled = data.get("enabled", False)
    status = "enabled" if enabled else "disabled"
    click.echo(f"  Computer use: {format_status(status)}")
    daemon = data.get("daemon")
    if daemon:
        click.echo(f"  Daemon: {format_status(daemon)}")
