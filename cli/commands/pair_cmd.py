"""``vadgr pair`` -- mint a pairing token and render a terminal QR.

Hits the same ``POST /api/auth/pair`` endpoint the frontend card uses, builds
the shared ``vadgr://pair`` deep link, and renders it as a Unicode QR in the
terminal (for headless boxes with no GUI). The phone scans it; the raw token is
also printed for manual entry.
"""

from __future__ import annotations

from urllib.parse import urlencode

import click

from cli.client import api_post
from cli.output import print_error, print_kv, print_success


def build_pair_uri(pair: dict) -> str:
    """The cross-repo deep link. Param names MUST match vadgr-mobile's scanner
    and the frontend's ``buildPairUri`` (host/port/token/name)."""
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
    """Pair a mobile device: mint a one-time token and show a QR to scan."""
    data = api_post(ctx, "/api/auth/pair")
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
            ("Pairing token", data["pairing_token"]),
        ]
    )
    click.echo()
    print_success("Scan with the Vadgr mobile app. This token is one-time and short-lived.")
