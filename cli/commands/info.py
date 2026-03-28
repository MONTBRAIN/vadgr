"""Info commands -- health, providers."""

from __future__ import annotations

import click

from cli.http import api_get
from cli.output import print_kv, format_status


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
