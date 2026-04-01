"""Root CLI group for Agent Forge."""

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

from cli.commands.agents import agents_group
from cli.commands.info import health, providers, computer_use
from cli.commands.registry import registry_group
from cli.commands.runs import runs_group
from cli.commands.service import start, stop, restart, status, logs, update, api_only

_DEFAULT_API_URL = f"http://127.0.0.1:{os.environ.get('AGENT_FORGE_PORT', '8000')}"


@click.group()
@click.option("--api-url", default=_DEFAULT_API_URL, envvar="FORGE_API_URL", hidden=True)
@click.pass_context
def cli(ctx, api_url: str):
    """Agent Forge CLI."""
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url


# Command groups
cli.add_command(agents_group)
cli.add_command(runs_group)
cli.add_command(registry_group)

# Info commands
cli.add_command(health)
cli.add_command(providers)
cli.add_command(computer_use)

# Service commands
cli.add_command(start)
cli.add_command(stop)
cli.add_command(restart)
cli.add_command(status)
cli.add_command(logs)
cli.add_command(update)
cli.add_command(api_only, "api")


# Top-level aliases
@cli.command("ps")
@click.pass_context
def ps(ctx):
    """List all agents (alias for 'agents list')."""
    from cli.commands.agents import list_agents
    ctx.invoke(list_agents)


@cli.command("run")
@click.argument("name_or_id")
@click.option("--input", "-i", "inputs", multiple=True)
@click.option("--provider", "-p", default=None)
@click.option("--model", "-m", default=None)
@click.option("--background", "-b", is_flag=True)
@click.pass_context
def run_alias(ctx, name_or_id, inputs, provider, model, background):
    """Run an agent (alias for 'agents run')."""
    from cli.commands.agents import run_agent
    ctx.invoke(run_agent, name_or_id=name_or_id, inputs=inputs, provider=provider, model=model, background=background)
