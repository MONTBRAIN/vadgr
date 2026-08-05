"""The daemon's launcher: open every address it answers on, then serve.

``python -m uvicorn`` binds exactly one ``--host``, and this daemon needs two:

* **the transport's own address** - the tailnet 100.x a phone reaches it on,
  and the address the pairing QR advertises. Binding loopback while advertising
  the tailnet is how a QR ends up pointing at a socket that does not exist.
* **loopback** - what gate 0 recognises, and therefore what keeps the on-box
  CLI working without a device token. Drop it and ``vadgr runs list`` on the
  machine itself answers ``401 MISSING_TOKEN``.

``0.0.0.0`` would cover both in one flag and is never the answer: this process
runs with the owner's credentials and drives a real browser they are logged
into, so the difference between "reachable by authenticated tailnet peers" and
"reachable by whoever is on the cafe wifi" is the whole security posture. Two
named addresses are the opposite of every interface, not a weaker version of
one.

Usage (what ``vadgr start`` spawns)::

    python -m api.serve --host 100.67.110.10 --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import argparse
import socket
import sys

import uvicorn

_BACKLOG = 2048
_IS_WINDOWS = sys.platform.startswith("win")


def _listen_socket(host: str, port: int) -> socket.socket:
    """A bound, listening socket for one address. Raises OSError if the address
    is not assigned to this machine -- which is a real failure, not something to
    paper over: it means the transport named an address the host does not have."""
    family, socktype, proto, _, sockaddr = socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )[0]
    sock = socket.socket(family, socktype, proto)
    if not _IS_WINDOWS:
        # POSIX: rebind through TIME_WAIT after a restart. **Not on Windows**,
        # where the same flag means "let another process steal this address"
        # instead -- the two platforms share a name for opposite behaviours, and
        # a daemon holding the owner's credentials must not be hijackable.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(sockaddr)
    sock.listen(_BACKLOG)
    sock.set_inheritable(True)
    return sock


def resolve_hosts(hosts: list[str]) -> list[str]:
    """The addresses to bind, de-duplicated in order.

    A loopback transport names 127.0.0.1 and so does the gate-0 requirement, so
    the common case is one socket, not two of the same.
    """
    ordered: list[str] = []
    for host in hosts:
        if host and host not in ordered:
            ordered.append(host)
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="api.serve")
    parser.add_argument("--host", action="append", default=[],
                        help="An address to bind. Repeatable. Never 0.0.0.0.")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args(argv)

    hosts = resolve_hosts(args.host) or ["127.0.0.1"]
    if "0.0.0.0" in hosts:
        # Refused rather than clamped: someone asked for every interface, and
        # quietly giving them something else would hide the request.
        print("api.serve refuses to bind 0.0.0.0 -- name each address instead.",
              file=sys.stderr)
        return 2

    sockets = [_listen_socket(host, args.port) for host in hosts]
    config = uvicorn.Config("api.main:app", host=hosts[0], port=args.port)
    uvicorn.Server(config).run(sockets=sockets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
