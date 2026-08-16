from unittest import mock

import click
from click.testing import CliRunner

from cli.client import ApiClientError
from cli.commands.provider import (
    _launch_authorization_url,
    _poll_oauth,
    model_default,
    model_list,
    provider_login,
)


def _row(provider="openai", name="OpenAI", *, default=True):
    return {
        "id": provider,
        "name": name,
        "connected": True,
        "is_default": default,
        "default_model": "model-one" if default else None,
        "models": [{"id": "model-one", "name": "Model One"}],
    }


def test_anthropic_skips_method_choice_and_never_echoes_the_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    with mock.patch("cli.commands.provider.api_post", return_value={
        "id": "pa_one", "status": "authenticated"
    }) as post, mock.patch(
        "cli.commands.provider.api_put",
        return_value=_row("anthropic", "Anthropic"),
    ), mock.patch(
        "cli.commands.provider.api_get",
        return_value=[_row("anthropic", "Anthropic")],
    ):
        result = runner.invoke(
            provider_login,
            ["anthropic"],
            input="secret-test-key\n",
            obj={"api_url": "http://x"},
        )

    assert result.exit_code == 0
    assert "Sign in to OpenAI" not in result.output
    assert "secret-test-key" not in result.output
    assert "choose a model" not in result.output.lower()
    assert post.call_args.args[2] == {
        "method": "api_key",
        "api_key": "secret-test-key",
    }


def test_openai_chatgpt_flow_has_one_method_question_and_no_internal_questions():
    runner = CliRunner()
    attempt = {
        "id": "pa_oauth",
        "status": "pending",
        "authorization_url": "https://auth.example/authorize",
    }
    with mock.patch("cli.commands.provider.api_post", return_value=attempt), \
         mock.patch("cli.commands.provider._poll_oauth", return_value={
             "id": "pa_oauth", "status": "authenticated"
         }), \
         mock.patch("cli.commands.provider.api_put", return_value=_row()), \
         mock.patch("cli.commands.provider.api_get", return_value=[_row()]):
        result = runner.invoke(
            provider_login,
            ["openai"],
            input="1\n",
            obj={"api_url": "http://x"},
        )

    assert result.exit_code == 0
    assert result.output.count("Select") == 1
    assert "Continue with ChatGPT" in result.output
    assert "Ready: OpenAI, Model One" in result.output
    for internal in ("choose a model", "run a check", "save", "continue to pairing"):
        assert internal not in result.output.lower()


def test_wsl_browser_launch_passes_the_complete_url_over_stdin():
    authorization_url = "https://auth.example/authorize?client_id=one&state=two"
    completed = mock.Mock(returncode=0)

    with mock.patch("cli.commands.provider._is_wsl", return_value=True), \
         mock.patch("cli.commands.provider.shutil.which", return_value="powershell.exe"), \
         mock.patch("cli.commands.provider.subprocess.run", return_value=completed) as run, \
         mock.patch("cli.commands.provider.click.launch") as native_launch:
        assert _launch_authorization_url(authorization_url)

    assert authorization_url not in run.call_args.args[0]
    assert run.call_args.kwargs["input"] == authorization_url
    native_launch.assert_not_called()


def test_oauth_prints_the_authorization_url_when_browser_launch_fails():
    runner = CliRunner()
    attempt = {
        "id": "pa_oauth",
        "status": "pending",
        "authorization_url": "https://auth.example/authorize",
    }

    @click.command()
    @click.pass_context
    def command(ctx):
        _poll_oauth(ctx, attempt)

    with mock.patch("cli.commands.provider._launch_authorization_url", return_value=False), \
         mock.patch("cli.commands.provider.api_get", return_value={
             "id": "pa_oauth", "status": "authenticated"
         }):
        result = runner.invoke(command, [], obj={"api_url": "http://x"})

    assert result.exit_code == 0
    assert "Open this URL:" in result.output
    assert attempt["authorization_url"] in result.output


def test_explicit_openai_api_key_method_still_uses_the_protected_prompt(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    with mock.patch("cli.commands.provider.api_post", return_value={
        "id": "pa_key", "status": "authenticated"
    }) as post, mock.patch(
        "cli.commands.provider.api_put",
        return_value=_row(),
    ), mock.patch(
        "cli.commands.provider.api_get",
        return_value=[_row()],
    ):
        result = runner.invoke(
            provider_login,
            ["openai", "--auth", "api-key"],
            input="secret-from-prompt\n",
            obj={"api_url": "http://x"},
        )

    assert result.exit_code == 0
    assert "OpenAI API key" in result.output
    assert "secret-from-prompt" not in result.output
    assert post.call_args.args[2]["api_key"] == "secret-from-prompt"


def test_provider_login_never_calls_the_pairing_route(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-from-environment")
    runner = CliRunner()
    paths = []

    def post(_ctx, path, body=None, timeout=None):
        paths.append(path)
        return {"id": "pa_gemini", "status": "authenticated"}

    with mock.patch("cli.commands.provider.api_post", side_effect=post), \
         mock.patch("cli.commands.provider.api_put", return_value=_row("gemini", "Google Gemini")), \
         mock.patch("cli.commands.provider.api_get", return_value=[_row("gemini", "Google Gemini")]):
        result = runner.invoke(
            provider_login,
            ["gemini"],
            obj={"api_url": "http://x"},
        )

    assert result.exit_code == 0
    assert "/api/auth/pair" not in paths


def test_later_connection_reports_that_the_existing_default_remains(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-from-environment")
    runner = CliRunner()
    openai = _row()
    gemini = _row("gemini", "Google Gemini", default=False)
    with mock.patch("cli.commands.provider.api_post", return_value={
        "id": "pa_gemini", "status": "authenticated"
    }), mock.patch(
        "cli.commands.provider.api_put",
        return_value=gemini,
    ), mock.patch(
        "cli.commands.provider.api_get",
        return_value=[openai, gemini],
    ):
        result = runner.invoke(
            provider_login,
            ["gemini"],
            obj={"api_url": "http://x"},
        )

    assert result.exit_code == 0
    assert "Connected: Google Gemini" in result.output
    assert "Default remains: OpenAI / model-one" in result.output


def test_provider_outage_retries_the_same_staged_attempt(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-from-environment")
    runner = CliRunner()
    outage = ApiClientError(
        "provider unavailable",
        status=503,
        code="PROVIDER_UNAVAILABLE",
        details={"category": "provider_unavailable"},
    )
    with mock.patch("cli.commands.provider.api_post", return_value={
        "id": "pa_gemini", "status": "authenticated"
    }) as post, mock.patch(
        "cli.commands.provider.api_put",
        side_effect=[outage, _row("gemini", "Google Gemini")],
    ) as put, mock.patch(
        "cli.commands.provider.api_get",
        return_value=[_row("gemini", "Google Gemini")],
    ):
        result = runner.invoke(
            provider_login,
            ["gemini"],
            input="1\n",
            obj={"api_url": "http://x"},
        )

    assert result.exit_code == 0
    assert "Try again" in result.output
    assert post.call_count == 1
    assert put.call_count == 2
    assert put.call_args_list[0].args[2] == put.call_args_list[1].args[2]


def test_chatgpt_failure_can_switch_to_an_api_key_without_reselecting_method():
    runner = CliRunner()
    outage = ApiClientError(
        "quota exhausted",
        status=503,
        code="PROVIDER_UNAVAILABLE",
        details={"category": "quota_exhausted"},
    )
    attempts = [
        {"id": "pa_oauth", "status": "pending", "authorization_url": "https://x"},
        {"id": "pa_key", "status": "authenticated"},
    ]
    with mock.patch("cli.commands.provider.api_post", side_effect=attempts), \
         mock.patch("cli.commands.provider._poll_oauth", return_value={
             "id": "pa_oauth", "status": "authenticated"
         }), \
         mock.patch("cli.commands.provider.api_put", side_effect=[outage, _row()]), \
         mock.patch("cli.commands.provider.api_get", return_value=[_row()]):
        result = runner.invoke(
            provider_login,
            ["openai"],
            input="1\n2\nreplacement-secret\n",
            obj={"api_url": "http://x"},
        )

    assert result.exit_code == 0
    assert result.output.count("Sign in to OpenAI") == 1
    assert "Use an API key" in result.output
    assert "replacement-secret" not in result.output


def test_model_list_is_the_union_and_default_is_explicit():
    rows = [
        _row("openai", "OpenAI", default=True),
        _row("gemini", "Google Gemini", default=False),
    ]
    runner = CliRunner()
    with mock.patch("cli.commands.provider.api_get", return_value=rows):
        listed = runner.invoke(model_list, [], obj={"api_url": "http://x"})
    assert listed.exit_code == 0
    assert "OpenAI" in listed.output
    assert "Google Gemini" in listed.output

    with mock.patch("cli.commands.provider.api_get", return_value=rows), \
         mock.patch("cli.commands.provider.api_put", return_value={
             "provider": "gemini", "model": "model-one"
         }) as put:
        changed = runner.invoke(
            model_default,
            ["gemini/model-one"],
            obj={"api_url": "http://x"},
        )
    assert changed.exit_code == 0
    assert put.call_args.args[2] == {"provider": "gemini", "model": "model-one"}
