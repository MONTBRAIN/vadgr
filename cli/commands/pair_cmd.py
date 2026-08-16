"""``vadgr pair`` -- mint a pairing code and render a terminal QR.

The only pairing surface on the machine. Hits ``POST /api/auth/pair``, builds
the shared ``vadgr://pair`` deep link, and renders it as a Unicode QR in the
terminal (headless boxes have no GUI, and there is no web dashboard). The phone
scans it; the code is also printed, grouped, for someone to type instead.
"""

from __future__ import annotations

from urllib.parse import urlencode

import click

from cli.client import api_get, api_post
from cli.commands.provider import connect_provider
from cli.output import print_error, print_kv, print_success


def build_pair_uri(pair: dict) -> str:
    """The cross-repo deep link. Param names MUST match vadgr-mobile's scanner
    (host/port/token/name) -- the value in ``token`` is the pairing code."""
    query = urlencode(
        {
            "host": pair["host"],
            "port": str(pair["port"]),
            "token": pair["pairing_token"],
            "name": pair["machine_name"],
        }
    )
    return f"vadgr://pair?{query}"


def _render_qr(data: str) -> bool:
    """Print a Unicode QR for *data*. Returns False if ``qrcode`` is missing."""
    try:
        import qrcode
    except ImportError:
        return False
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    return True


@click.command()
@click.pass_context
def pair(ctx):
    """Pair a mobile device: mint a one-time code and show a QR to scan."""
    providers = api_get(ctx, "/api/providers")
    if not any(provider.get("is_default") for provider in providers):
        click.echo("Before this machine can pair, connect a model provider.\n")
        connect_provider(ctx)
    data = api_post(ctx, "/api/auth/pair")
    # `pairing_token` is the field name on the wire, and it is the invariant --
    # only the value it carries is now a short code.
    if not isinstance(data, dict) or "pairing_token" not in data:
        print_error("Pairing failed: unexpected response from the API.")
        raise SystemExit(1)

    uri = build_pair_uri(data)
    click.echo()
    if not _render_qr(uri):
        print_error(
            "Install 'qrcode' to render the QR in the terminal (pip install qrcode)."
        )
        click.echo("Pairing URI (encode this in a QR or enter manually):")
        click.echo(f"  {uri}")
    click.echo()
    print_kv(
        [
            ("Machine", data["machine_name"]),
            ("Address", f"{data['host']}:{data['port']}"),
            ("Pairing code", data["pairing_token"]),
        ]
    )
    click.echo()
    print_success(
        "Scan with the Vadgr mobile app, or type the code. "
        "One-time, valid for 5 minutes."
    )
