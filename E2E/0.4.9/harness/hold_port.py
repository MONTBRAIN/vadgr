"""Hold a port in one of the two shapes that break a port search.

Neither shape is exotic and both are reachable by a real user, so both are
cells. The point of this helper is that one Python file reproduces on every
operating system what Windows does on its own.

  listening   a socket that is bound and listening but never accepts. Its
              backlog fills on the first probe and refuses every one after, so
              two connects in a row disagree and a search that asks by
              connecting can hand back the port it was just told was taken.

  reserved    a socket that is bound and *not* listening. Nothing answers a
              connect, so a probe that asks by connecting reports the port free
              forever, while a bind fails. This is the shape Windows creates by
              itself: Hyper-V and WSL reserve port ranges with no listener
              behind them, and `VADGR_PORT=8861` on such a host killed the
              daemon on every attempt with no warning printed.

Usage:
    python3 hold_port.py <port> [listening|reserved]

It prints one JSON line describing what it holds, then waits. The caller reads
that line to know the port is held before it drives the product.
"""

import json
import socket
import sys
import time


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    port = int(sys.argv[1])
    shape = sys.argv[2] if len(sys.argv) > 2 else "reserved"
    if shape not in ("listening", "reserved"):
        print(f"unknown shape {shape!r}; expected 'listening' or 'reserved'")
        return 2

    sock = socket.socket()
    # No SO_REUSEADDR: the point is to make the port genuinely unavailable to
    # another process, which is what the daemon will try to be.
    sock.bind(("127.0.0.1", port))
    if shape == "listening":
        # A backlog of one, and nothing is ever accepted.
        sock.listen(1)

    print(
        json.dumps(
            {
                "port": port,
                "shape": shape,
                "listening": shape == "listening",
                "connect_answers": shape == "listening",
                "bindable_by_others": False,
            }
        ),
        flush=True,
    )

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
