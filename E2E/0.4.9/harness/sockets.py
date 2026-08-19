"""The wire client. Connects to the run sockets and records what arrives.

The runbook requires every socket the product serves to be driven by a real
client, and the closing rule compares frame type counts per socket across
passes. Nothing else in this harness opens a socket, so a claim about frames
had no artifact behind it.

It speaks the protocol with the standard library only: the upgrade handshake
and the frame parser are written here. That is deliberate twice over. It is an
implementation independent of the server's, so the framing is checked by
something other than the code under test, and it needs nothing installed, so
every operating system in the matrix can run the same cell.

It records; it never asserts. The runbook's cells read the record and decide.

    python3 harness/sockets.py record.json \\
        --host 127.0.0.1 --port 8891 --run run-abc [--token T] [--seconds 30]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import sys
import time
from collections import Counter

ROUTES = {
    # The CLI's socket. On loopback it needs no token.
    "cli": "/api/ws/runs/{run}",
    # The phone's socket. Off loopback it needs a device token.
    "phone": "/api/runs/{run}/stream",
}

TEXT, BINARY, CLOSE, PING, PONG = 0x1, 0x2, 0x8, 0x9, 0xA


def handshake(sock, host, port, path, headers):
    """Send the upgrade and read the response head. Returns the status line."""
    key = base64.b64encode(os.urandom(16)).decode()
    lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}:{port}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
    ]
    lines += [f"{name}: {value}" for name, value in headers.items()]
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())

    head = b""
    while b"\r\n\r\n" not in head:
        chunk = sock.recv(4096)
        if not chunk:
            break
        head += chunk
    first = head.split(b"\r\n", 1)[0].decode(errors="replace")
    status = 0
    parts = first.split()
    if len(parts) > 1 and parts[1].isdigit():
        status = int(parts[1])
    return status, first, head.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in head else b""


def frames(sock, buffer, deadline):
    """Yield (opcode, payload) until the socket closes or the deadline passes."""
    def pull(count):
        nonlocal buffer
        while len(buffer) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            sock.settimeout(remaining)
            try:
                chunk = sock.recv(65536)
            except (socket.timeout, TimeoutError):
                return None
            if not chunk:
                return None
            buffer += chunk
        head, buffer = buffer[:count], buffer[count:]
        return head

    while True:
        head = pull(2)
        if head is None:
            return
        opcode = head[0] & 0x0F
        masked = bool(head[1] & 0x80)
        length = head[1] & 0x7F
        if length == 126:
            extra = pull(2)
            if extra is None:
                return
            length = struct.unpack(">H", extra)[0]
        elif length == 127:
            extra = pull(8)
            if extra is None:
                return
            length = struct.unpack(">Q", extra)[0]
        mask = pull(4) if masked else b""
        if masked and mask is None:
            return
        payload = pull(length) if length else b""
        if payload is None:
            return
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        yield opcode, payload
        if opcode == CLOSE:
            return


def read_socket(host, port, path, token, seconds, headers):
    record = {
        "path": path,
        "token_supplied": bool(token),
        "opened": False,
        "http_status": None,
        "status_line": None,
        "frames": 0,
        "frame_types": {},
        "close_code": None,
        "close_reason": None,
        "error": None,
    }
    target = path + (f"?token={token}" if token else "")
    types = Counter()
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=10)
        status, line, rest = handshake(sock, host, port, target, headers)
        record["http_status"] = status
        record["status_line"] = line
        if status != 101:
            return record
        record["opened"] = True
        deadline = time.monotonic() + seconds
        for opcode, payload in frames(sock, rest, deadline):
            if opcode == CLOSE:
                if len(payload) >= 2:
                    record["close_code"] = struct.unpack(">H", payload[:2])[0]
                    record["close_reason"] = payload[2:].decode(errors="replace")
                break
            if opcode in (PING, PONG):
                types["ping" if opcode == PING else "pong"] += 1
                continue
            record["frames"] += 1
            if opcode == BINARY:
                types["binary"] += 1
                continue
            text = payload.decode(errors="replace")
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                types["text/not-json"] += 1
                continue
            types[str(body.get("type") or body.get("phase") or "text/untyped")] += 1
    except Exception as error:  # recorded, never raised: the cell reads the record
        record["error"] = f"{type(error).__name__}: {error}"
    finally:
        if sock is not None:
            sock.close()
    record["frame_types"] = dict(sorted(types.items()))
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--token", default=None)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--route", choices=sorted(ROUTES), default=None)
    parser.add_argument("--header", action="append", default=[],
                        help="extra request header, as Name: value")
    args = parser.parse_args()

    headers = {}
    for item in args.header:
        name, _, value = item.partition(":")
        headers[name.strip()] = value.strip()

    record = {}
    for name in ([args.route] if args.route else sorted(ROUTES)):
        record[name] = read_socket(
            args.host, args.port, ROUTES[name].format(run=args.run),
            args.token, args.seconds, headers,
        )

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)

    for name, entry in record.items():
        state = "opened" if entry["opened"] else f"refused {entry['http_status']}"
        detail = entry["close_code"] or entry["error"] or ""
        print(f"{name:6} {state:12} frames={entry['frames']:3} "
              f"{entry['frame_types']} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
