"""TCP client for the Windows bridge daemon."""

import json
import logging
import os
import platform
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any

from computer_use.bridge.protocol import (
    HEADER_SIZE,
    decode_header,
    encode_message,
    get_port,
    make_request,
)

logger = logging.getLogger("computer_use.bridge.client")


def _is_wsl2_mirrored() -> bool:
    """Check if WSL2 is using mirrored networking mode.

    With mirrored networking, WSL2 shares the host's network stack so
    localhost reaches Windows directly -- no need for the gateway IP.
    """
    try:
        wslconfig = Path("/mnt/c/Users") / os.environ.get("USER", "") / ".wslconfig"
        if not wslconfig.exists():
            # Try via powershell
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", "$env:USERPROFILE"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                win_profile = result.stdout.strip()
                wsl_path = subprocess.run(
                    ["wslpath", "-u", win_profile],
                    capture_output=True, text=True,
                ).stdout.strip()
                wslconfig = Path(wsl_path) / ".wslconfig"

        if wslconfig.exists():
            content = wslconfig.read_text().lower()
            return "networkingmode=mirrored" in content.replace(" ", "")
    except Exception:
        pass
    return False


def _detect_windows_host() -> str:
    """Auto-detect the Windows host IP when running inside WSL2.

    On standard WSL2, 127.0.0.1 points to the Linux VM, not Windows.
    The Windows host IP is the default gateway (WSL2 vEthernet adapter).

    On mirrored networking (networkingMode=mirrored in .wslconfig),
    localhost reaches Windows directly, so 127.0.0.1 works.

    Returns '127.0.0.1' on non-WSL2 platforms.
    """
    try:
        if "microsoft" in platform.release().lower():
            if _is_wsl2_mirrored():
                logger.debug("WSL2 mirrored networking, using 127.0.0.1")
                return "127.0.0.1"

            # Default gateway is the Windows host on the WSL2 virtual network
            with open("/proc/net/route") as f:
                for line in f:
                    fields = line.strip().split()
                    if fields[1] == "00000000":  # default route
                        # Gateway is in hex, little-endian
                        gw_hex = fields[2]
                        gw_bytes = bytes.fromhex(gw_hex)
                        ip = f"{gw_bytes[3]}.{gw_bytes[2]}.{gw_bytes[1]}.{gw_bytes[0]}"
                        logger.debug("WSL2 detected, Windows host IP: %s", ip)
                        return ip
    except Exception:
        pass
    return "127.0.0.1"


class BridgeError(Exception):
    pass


class BridgeClient:
    """Connects to the Windows bridge daemon over TCP.

    On WSL2, auto-discovers the Windows host IP.
    Thread-safe. Reconnects automatically on socket errors (one retry).
    """

    def __init__(self, host: str | None = None, port: int | None = None):
        self._host = host or _detect_windows_host()
        self._port = port or get_port()
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            result = self.call("ping", timeout=2.0)
            return result.get("pong", False)
        except Exception:
            return False

    def call(self, method: str, params: dict | None = None, timeout: float = 10.0) -> dict:
        with self._lock:
            return self._call_locked(method, params, timeout, retry=True)

    def _call_locked(
        self, method: str, params: dict | None, timeout: float, retry: bool
    ) -> dict:
        try:
            self._ensure_connected(timeout)
            request = make_request(method, params)
            self._send(encode_message(request))
            response = self._receive(timeout)
            if not response.get("ok", False):
                raise BridgeError(response.get("error", "Unknown daemon error"))
            return response.get("result", {})
        except (socket.error, OSError, ConnectionError) as e:
            self._close_socket()
            if retry:
                logger.debug("Connection lost, retrying: %s", e)
                return self._call_locked(method, params, timeout, retry=False)
            raise BridgeError(f"Bridge connection failed: {e}") from e

    def _ensure_connected(self, timeout: float) -> None:
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((self._host, self._port))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        logger.debug("Connected to bridge at %s:%d", self._host, self._port)

    def _send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def _receive(self, timeout: float) -> dict:
        self._sock.settimeout(timeout)
        header = self._recv_exact(HEADER_SIZE)
        length = decode_header(header)
        payload = self._recv_exact(length)
        return json.loads(payload)

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Bridge daemon closed connection")
            buf.extend(chunk)
        return bytes(buf)

    def _close_socket(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def close(self) -> None:
        with self._lock:
            self._close_socket()

    def __del__(self):
        self._close_socket()
