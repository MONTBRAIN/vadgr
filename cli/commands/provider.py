"""Provider connection and machine-default commands."""

from __future__ import annotations

import os
import time
from typing import Iterable

import click

from cli.client import ApiClientError, api_delete, api_get, api_post, api_put
from cli.output import print_info, print_success

_PROVIDERS = {
    "openai": ("OpenAI", "ChatGPT or API key"),
    "gemini": ("Google Gemini", "API key"),
    "anthropic": ("Anthropic", "API key"),
}

_KEY_ENVIRONMENTS = {
    "openai": ("OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


def _choose_provider() -> str:
    click.echo("Choose a provider")
    choices = list(_PROVIDERS)
    for index, provider in enumerate(choices, 1):
        name, detail = _PROVIDERS[provider]
        click.echo(f"  {index}. {name}  {detail}")
    selected = click.prompt("Select", type=click.IntRange(1, len(choices)),
                            show_choices=False)
    return choices[selected - 1]


def _choose_openai_method() -> str:
    click.echo("\nSign in to OpenAI")
    click.echo("  1. Continue with ChatGPT")
    click.echo("  2. Use an API key")
    selected = click.prompt("Select", type=click.IntRange(1, 2), show_choices=False)
    return "chatgpt" if selected == 1 else "api-key"


def _detected_key(provider: str) -> tuple[str, str] | None:
    for name in _KEY_ENVIRONMENTS[provider]:
        value = os.environ.get(name)
        if value:
            return name, value
    return None


def _api_key(provider: str) -> str:
    detected = _detected_key(provider)
    if detected:
        print_info(f"Using {detected[0]}.")
        return detected[1]
    return click.prompt(f"{_PROVIDERS[provider][0]} API key", hide_input=True,
                        confirmation_prompt=False)


def _poll_oauth(ctx: click.Context, attempt: dict) -> dict:
    authorization_url = attempt.get("authorization_url")
    if not authorization_url:
        raise click.ClickException("The daemon did not return an authorization URL.")
    click.echo("\nOpening your browser...")
    if click.launch(authorization_url) != 0:
        click.echo(f"Open this URL:\n  {authorization_url}")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        current = api_get(ctx, f"/api/provider-auth/{attempt['id']}")
        if current.get("status") == "authenticated":
            return current
        if current.get("status") in {"failed", "cancelled"}:
            code = current.get("error_code", "sign-in failed")
            raise click.ClickException(f"OpenAI sign-in failed: {code}.")
        time.sleep(0.5)
    raise click.ClickException("OpenAI sign-in timed out.")


def _pick_replacement(models: Iterable[str]) -> str:
    models = list(models)
    if not models:
        raise click.ClickException("The new credential has no compatible model.")
    click.echo("\nChoose a replacement for the current default")
    for index, model in enumerate(models, 1):
        click.echo(f"  {index}. {model}")
    selected = click.prompt("Select", type=click.IntRange(1, len(models)),
                            show_choices=False)
    return models[selected - 1]


def _recovery_action(provider: str, auth: str, error: ApiClientError) -> str:
    category = error.details.get("category", "connection failed")
    reason = str(category).replace("_", " ")
    click.echo(f"\n{_PROVIDERS[provider][0]} could not complete the connection: {reason}.")
    choices = [("retry", "Try again")]
    if provider == "openai" and auth == "chatgpt":
        choices.append(("api-key", "Use an API key"))
    elif error.code == "INVALID_CREDENTIALS":
        choices.append(("new-key", "Enter another API key"))
    choices.extend([
        ("provider", "Choose another provider"),
        ("exit", "Exit"),
    ])
    for index, (_, label) in enumerate(choices, 1):
        marker = ">" if index == 1 else " "
        click.echo(f"{marker} {index}. {label}")
    selected = click.prompt("Select", type=click.IntRange(1, len(choices)),
                            show_choices=False)
    return choices[selected - 1][0]


def connect_provider(ctx: click.Context, provider: str | None = None,
                     auth: str | None = None,
                     replacement_default_model: str | None = None) -> dict:
    provider = provider or _choose_provider()
    if provider not in _PROVIDERS:
        raise click.UsageError(f"Unknown provider: {provider}")
    if provider == "openai":
        auth = auth or _choose_openai_method()
        if auth not in {"chatgpt", "api-key"}:
            raise click.UsageError("OpenAI supports --auth chatgpt or --auth api-key.")
    else:
        if auth not in {None, "api-key"}:
            raise click.UsageError(f"{_PROVIDERS[provider][0]} supports API keys only.")
        auth = "api-key"

    if auth == "chatgpt":
        attempt = api_post(
            ctx,
            f"/api/providers/{provider}/auth-attempts",
            {"method": "oauth", "flow": "browser"},
        )
        _poll_oauth(ctx, attempt)
    else:
        attempt = api_post(
            ctx,
            f"/api/providers/{provider}/auth-attempts",
            {
                "method": "api_key",
                "api_key": _api_key(provider),
            },
        )

    print_info("Checking the connection...")
    body = {"attempt_id": attempt["id"]}
    if replacement_default_model:
        body["replacement_default_model"] = replacement_default_model
    while True:
        try:
            row = api_put(
                ctx,
                f"/api/providers/{provider}/connection",
                body,
                timeout=120,
            )
            break
        except ApiClientError as error:
            if error.code == "DEFAULT_MODEL_UNAVAILABLE" and not body.get(
                "replacement_default_model"
            ):
                body["replacement_default_model"] = _pick_replacement(
                    error.details.get("models", [])
                )
                continue
            if error.code not in {"INVALID_CREDENTIALS", "PROVIDER_UNAVAILABLE"}:
                raise
            action = _recovery_action(provider, auth, error)
            if action == "retry":
                continue
            if action == "api-key":
                return connect_provider(ctx, "openai", "api-key")
            if action == "new-key":
                return connect_provider(ctx, provider, "api-key")
            if action == "provider":
                return connect_provider(ctx)
            raise click.ClickException("The provider connection was not saved.")

    rows = api_get(ctx, "/api/providers")
    default = next((item for item in rows if item.get("is_default")), None)
    if row.get("is_default"):
        model_id = row.get("default_model", "unknown")
        model_name = next(
            (model["name"] for model in row.get("models", [])
             if model.get("id") == model_id),
            model_id,
        )
        print_success(f"Ready: {row['name']}, {model_name}")
    else:
        print_success(f"Connected: {row['name']}")
        click.echo(f"Models available: {len(row.get('models', []))}")
        if default:
            click.echo(
                f"Default remains: {default['name']} / "
                f"{default.get('default_model', 'unknown')}"
            )
    return row


@click.group("provider")
def provider_group():
    """Connect and manage model providers."""


@provider_group.command("login")
@click.argument("provider", required=False,
                type=click.Choice(list(_PROVIDERS), case_sensitive=False))
@click.option("--auth", type=click.Choice(["chatgpt", "api-key"]), default=None)
@click.option("--replacement-default-model", default=None, hidden=True)
@click.pass_context
def provider_login(ctx, provider: str | None, auth: str | None,
                   replacement_default_model: str | None):
    """Connect or reauthenticate one provider."""
    connect_provider(ctx, provider, auth, replacement_default_model)


@provider_group.command("status")
@click.option("--refresh", "refresh_provider", flag_value="all", default=None)
@click.argument("provider", required=False,
                type=click.Choice(list(_PROVIDERS), case_sensitive=False))
@click.pass_context
def provider_status(ctx, refresh_provider: str | None, provider: str | None):
    """Show connected providers and their model catalogs."""
    if refresh_provider:
        rows = api_get(ctx, "/api/providers")
        targets = [provider] if provider else [row["id"] for row in rows if row.get("connected")]
        for target in targets:
            api_post(ctx, f"/api/providers/{target}/catalog-refresh", timeout=120)
    _print_provider_rows(api_get(ctx, "/api/providers"), provider)


@provider_group.command("logout")
@click.argument("provider", type=click.Choice(list(_PROVIDERS), case_sensitive=False))
@click.pass_context
def provider_logout(ctx, provider: str):
    """Disconnect one non-default provider."""
    api_delete(ctx, f"/api/providers/{provider}/connection")
    print_success(f"Disconnected: {_PROVIDERS[provider][0]}")


@click.group("model")
def model_group():
    """List models and select the machine default."""


@model_group.command("list")
@click.pass_context
def model_list(ctx):
    """List models from every connected provider."""
    _print_provider_rows(api_get(ctx, "/api/providers"), connected_only=True)


@model_group.command("default")
@click.argument("selection", required=False)
@click.pass_context
def model_default(ctx, selection: str | None):
    """Set the machine default after a live check."""
    rows = [row for row in api_get(ctx, "/api/providers") if row.get("connected")]
    choices = [
        (row["id"], model["id"], row["name"], model["name"])
        for row in rows
        for model in row.get("models", [])
    ]
    if not choices:
        raise click.ClickException("No connected models are available.")
    if selection:
        provider, separator, model = selection.partition("/")
        if not separator or not any(item[:2] == (provider, model) for item in choices):
            raise click.UsageError("MODEL must be a connected provider/model pair.")
    else:
        click.echo("Choose the machine default")
        for index, (_, _, provider_name, model_name) in enumerate(choices, 1):
            click.echo(f"  {index}. {provider_name} / {model_name}")
        selected = click.prompt("Select", type=click.IntRange(1, len(choices)),
                                show_choices=False)
        provider, model, _, _ = choices[selected - 1]
    print_info("Checking the model...")
    result = api_put(ctx, "/api/default-model", {"provider": provider, "model": model},
                     timeout=120)
    print_success(f"Default: {result['provider']} / {result['model']}")


def _print_provider_rows(rows: list[dict], provider: str | None = None,
                         connected_only: bool = False):
    shown = [row for row in rows
             if (not provider or row.get("id") == provider)
             and (not connected_only or row.get("connected"))]
    if not shown:
        click.echo("No connected providers.")
        return
    for row in shown:
        state = "connected" if row.get("connected") else "not connected"
        suffix = " (default)" if row.get("is_default") else ""
        stale = " (stale)" if row.get("catalog_stale") else ""
        click.echo(f"{row['name']}: {state}{suffix}{stale}")
        for model in row.get("models", []):
            click.echo(f"  {model['id']}  {model['name']}")
