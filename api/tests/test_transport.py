"""Adapter-contract tests for the transport providers.

Both adapters are exercised against the same behavioural contract
(transport.md's table) so substitutability holds. Tailscale uses a faked
LocalAPI -- no live tailnet.
"""

import pytest

from api.transport import (
    LoopbackTransport,
    TailscaleTransport,
    TransportProvider,
    create_transport,
)


# --- Loopback ---------------------------------------------------------------


def test_loopback_binds_to_loopback_never_wildcard():
    t = LoopbackTransport()
    assert t.bind_host() == "127.0.0.1"
    assert t.bind_host() != "0.0.0.0"


def test_loopback_never_advertises_a_host():
    # Can't pair a remote phone to localhost -> None so pair refuses.
    assert LoopbackTransport().advertise_host() is None


def test_loopback_is_always_available():
    assert LoopbackTransport().is_available() is True


@pytest.mark.parametrize(
    "ip,allowed",
    [
        ("127.0.0.1", True),
        ("127.0.0.5", True),
        ("100.101.102.103", False),
        ("192.168.1.10", False),
        ("not-an-ip", False),
    ],
)
def test_loopback_authorizes_only_loopback(ip, allowed):
    assert LoopbackTransport().is_authorized_source(ip) is allowed


def test_loopback_status_shape():
    s = LoopbackTransport().status()
    assert s["name"] == "loopback"
    assert s["available"] is True
    assert s["advertise_host"] is None


def test_loopback_satisfies_protocol():
    assert isinstance(LoopbackTransport(), TransportProvider)


# --- Tailscale (faked LocalAPI) ---------------------------------------------


class FakeLocalAPI:
    def __init__(self, status=None, known_peers=None):
        self._status = status
        self._known_peers = set(known_peers or [])

    def status(self):
        return self._status

    def whois(self, peer_ip):
        return {"Node": {"Name": "phone"}} if peer_ip in self._known_peers else None


_UP_STATUS = {
    "BackendState": "Running",
    "Self": {
        "TailscaleIPs": ["100.101.102.103", "fd7a:115c::1"],
        "DNSName": "my-box.tailnet-1234.ts.net.",
    },
}


def test_tailscale_binds_to_tailnet_ip_never_wildcard_or_loopback():
    t = TailscaleTransport(FakeLocalAPI(status=_UP_STATUS))
    assert t.bind_host() == "100.101.102.103"
    assert t.bind_host() != "0.0.0.0"
    assert t.bind_host() != "127.0.0.1"


def test_tailscale_advertises_magicdns_never_loopback():
    t = TailscaleTransport(FakeLocalAPI(status=_UP_STATUS))
    host = t.advertise_host()
    assert host == "my-box.tailnet-1234.ts.net"
    assert host != "127.0.0.1"


def test_tailscale_advertises_ip_when_no_magicdns():
    status = {"BackendState": "Running", "Self": {"TailscaleIPs": ["100.1.2.3"]}}
    assert TailscaleTransport(FakeLocalAPI(status=status)).advertise_host() == "100.1.2.3"


def test_tailscale_unavailable_when_socket_down():
    t = TailscaleTransport(FakeLocalAPI(status=None))
    assert t.is_available() is False
    assert t.advertise_host() is None


def test_tailscale_unavailable_when_logged_out():
    status = {"BackendState": "NeedsLogin", "Self": {"TailscaleIPs": ["100.1.2.3"]}}
    assert TailscaleTransport(FakeLocalAPI(status=status)).is_available() is False


def test_tailscale_bind_host_raises_when_unavailable():
    with pytest.raises(RuntimeError):
        TailscaleTransport(FakeLocalAPI(status=None)).bind_host()


def test_tailscale_authorizes_peer_via_whois():
    api = FakeLocalAPI(status=_UP_STATUS, known_peers={"100.64.5.6"})
    t = TailscaleTransport(api)
    assert t.is_authorized_source("100.64.5.6") is True


def test_tailscale_falls_back_to_cgnat_range_when_whois_empty():
    # WhoIs returns nothing but the address is in 100.64.0.0/10.
    t = TailscaleTransport(FakeLocalAPI(status=_UP_STATUS))
    assert t.is_authorized_source("100.99.99.99") is True


def test_tailscale_rejects_non_tailnet_source():
    t = TailscaleTransport(FakeLocalAPI(status=_UP_STATUS))
    assert t.is_authorized_source("192.168.1.50") is False
    assert t.is_authorized_source("8.8.8.8") is False
    assert t.is_authorized_source("garbage") is False


def test_tailscale_status_shape():
    s = TailscaleTransport(FakeLocalAPI(status=_UP_STATUS)).status()
    assert s["name"] == "tailscale"
    assert s["available"] is True
    assert s["advertise_host"] == "my-box.tailnet-1234.ts.net"


def test_tailscale_satisfies_protocol():
    assert isinstance(TailscaleTransport(FakeLocalAPI()), TransportProvider)


# --- Factory ----------------------------------------------------------------


def test_factory_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("VADGR_TRANSPORT", raising=False)
    assert isinstance(create_transport(), LoopbackTransport)


def test_factory_selects_tailscale():
    assert isinstance(create_transport("tailscale"), TailscaleTransport)


def test_factory_reads_env(monkeypatch):
    monkeypatch.setenv("VADGR_TRANSPORT", "tailscale")
    assert isinstance(create_transport(), TailscaleTransport)


def test_factory_rejects_unknown():
    with pytest.raises(ValueError):
        create_transport("headscale")


# --- TailscaledLocalAPI wire behaviour --------------------------------------
# The adapter contract tests above use a faked LocalAPI; these exercise the real
# socket client against a stand-in tailscaled. The Go server emits a
# Transfer-Encoding: chunked body on HTTP/1.1, which the minimal client does not
# decode -- so the request must be HTTP/1.0 (close-delimited body).

import json
import socket
import threading

from api.transport.factory import TailscaledLocalAPI

_FAKE_STATUS = {"BackendState": "Running", "Self": {"TailscaleIPs": ["100.0.0.1"]}}


def _respond_like_tailscaled(srv):
    """Serve one request: chunked on HTTP/1.1 (as Go does), raw body on HTTP/1.0."""
    try:
        conn, _ = srv.accept()
    except OSError:
        return
    with conn:
        req = b""
        while b"\r\n\r\n" not in req:
            chunk = conn.recv(4096)
            if not chunk:
                break
            req += chunk
        body = json.dumps(_FAKE_STATUS).encode()
        request_line = req.split(b"\r\n", 1)[0]
        if b"HTTP/1.1" in request_line:
            payload = (
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n"
                + f"{len(body):x}".encode()
                + b"\r\n"
                + body
                + b"\r\n0\r\n\r\n"
            )
        else:
            payload = (
                b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n" + body
            )
        conn.sendall(payload)
    srv.close()


def test_localapi_parses_real_tailscaled_response(tmp_path):
    """Regression: a healthy tailscaled must yield a parsed dict. Fails if the
    client requests HTTP/1.1 (the stand-in then chunks and the body won't parse)."""
    sock_path = str(tmp_path / "tailscaled.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    srv.settimeout(5.0)
    thread = threading.Thread(target=_respond_like_tailscaled, args=(srv,), daemon=True)
    thread.start()

    result = TailscaledLocalAPI(socket_path=sock_path).status()

    thread.join(timeout=5.0)
    assert result == _FAKE_STATUS
