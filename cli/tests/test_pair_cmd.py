"""Tests for `vadgr pair` -- URI builder + command rendering."""

from unittest import mock

from click.testing import CliRunner
import pytest

from cli.commands.pair_cmd import build_pair_uri, pair


_PAIR_RESPONSE = {
    "host": "my-box.tailnet-1234.ts.net",
    "port": 8000,
    "pairing_token": "abc123",
    "machine_name": "Work Box",
}


def test_build_pair_uri_encodes_all_params():
    uri = build_pair_uri(_PAIR_RESPONSE)
    assert uri.startswith("vadgr://pair?")
    assert "host=my-box.tailnet-1234.ts.net" in uri
    assert "port=8000" in uri
    assert "token=abc123" in uri
    # machine_name is URL-encoded (space -> +).
    assert "name=Work+Box" in uri


def test_build_pair_uri_never_uses_loopback():
    assert "127.0.0.1" not in build_pair_uri(_PAIR_RESPONSE)


@pytest.fixture
def runner():
    return CliRunner()


def test_pair_command_prints_token_and_address(runner):
    with mock.patch("cli.commands.pair_cmd.api_post") as m:
        m.return_value = _PAIR_RESPONSE
        result = runner.invoke(pair, [], obj={"api_url": "http://x"})
    assert result.exit_code == 0
    assert "abc123" in result.output
    assert "my-box.tailnet-1234.ts.net:8000" in result.output


def test_pair_command_falls_back_when_qr_lib_missing(runner):
    with mock.patch("cli.commands.pair_cmd.api_post") as m, \
         mock.patch("cli.commands.pair_cmd._render_qr", return_value=False):
        m.return_value = _PAIR_RESPONSE
        result = runner.invoke(pair, [], obj={"api_url": "http://x"})
    assert result.exit_code == 0
    assert "vadgr://pair?" in result.output


def test_pair_command_errors_on_bad_response(runner):
    with mock.patch("cli.commands.pair_cmd.api_post") as m:
        m.return_value = {"unexpected": True}
        result = runner.invoke(pair, [], obj={"api_url": "http://x"})
    assert result.exit_code != 0
