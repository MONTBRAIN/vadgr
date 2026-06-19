"""Transport selection. ``VADGR_TRANSPORT`` picks the adapter (loopback default)."""

from __future__ import annotations

import json
import os
import socket
import sys
from typing import Optional

from .base import TransportProvider
from .loopback import LoopbackTransport
from .tailscale import TailscaleTransport

# The tailscaled LocalAPI endpoint differs by OS:
#   - Linux / macOS / WSL : a unix socket.
#   - native Windows      : a named pipe whose server *impersonates* the client to
#     authorize it, so the client must open the pipe allowing impersonation.
_TAILSCALED_SOCKET = os.environ.get(
    "VADGR_TAILSCALED_SOCKET", "/var/run/tailscale/tailscaled.sock"
)
_TAILSCALED_PIPE = os.environ.get(
    "VADGR_TAILSCALED_PIPE",
    r"\\.\pipe\ProtectedPrefix\Administrators\Tailscale\tailscaled",
)

_IS_WINDOWS = sys.platform.startswith("win")


def _unix_socket_roundtrip(socket_path: str, request: bytes) -> Optional[bytes]:
    """Send ``request`` over a unix-socket HTTP server; return the raw response."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            sock.connect(socket_path)
            sock.sendall(request)
            chunks = []
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
        return b"".join(chunks)
    except (OSError, socket.timeout):
        return None


def _windows_pipe_roundtrip(pipe_path: str, request: bytes) -> Optional[bytes]:
    """Send ``request`` over the Windows named pipe; return the raw response.

    tailscaled's Windows LocalAPI impersonates the named-pipe client to authorize
    it, so the pipe must be opened with ``SECURITY_SQOS_PRESENT |
    SECURITY_IMPERSONATION`` — Python's ``open()`` does not, so we ``CreateFileW``
    via ``ctypes`` (no third-party dep). Verified non-elevated against a live
    Windows ``tailscaled``.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None

    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    SECURITY_SQOS_PRESENT = 0x00100000
    SECURITY_IMPERSONATION = 0x00020000  # SecurityImpersonation(2) << 16
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except Exception:
        return None
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    k32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    k32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]

    handle = k32.CreateFileW(
        pipe_path, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING,
        SECURITY_SQOS_PRESENT | SECURITY_IMPERSONATION, None,
    )
    if not handle or handle == INVALID_HANDLE_VALUE:
        return None
    try:
        written = wintypes.DWORD(0)
        if not k32.WriteFile(handle, request, len(request), ctypes.byref(written), None):
            return None
        buf = ctypes.create_string_buffer(65536)
        read = wintypes.DWORD(0)
        chunks = []
        while True:
            ok = k32.ReadFile(handle, buf, 65536, ctypes.byref(read), None)
            if not ok or read.value == 0:
                break
            chunks.append(buf.raw[: read.value])
        return b"".join(chunks)
    finally:
        k32.CloseHandle(handle)


class TailscaledLocalAPI:
    """Talks to the ``tailscaled`` LocalAPI.

    Transport is per-OS — a **unix socket** on Linux/macOS/WSL, a **named pipe**
    on native Windows — but the request is identical: HTTP/1.0 with the fixed Host
    sentinel ``local-tailscaled.sock`` (HTTP/1.0 because the Go server chunks
    HTTP/1.1 bodies, which this minimal client does not decode).
    """

    def __init__(
        self,
        socket_path: str = _TAILSCALED_SOCKET,
        *,
        pipe_path: str = _TAILSCALED_PIPE,
        use_pipe: Optional[bool] = None,
    ):
        self._socket_path = socket_path
        self._pipe_path = pipe_path
        self._use_pipe = _IS_WINDOWS if use_pipe is None else use_pipe

    def _roundtrip(self, request: bytes) -> Optional[bytes]:
        if self._use_pipe:
            return _windows_pipe_roundtrip(self._pipe_path, request)
        return _unix_socket_roundtrip(self._socket_path, request)

    def _get(self, path: str) -> Optional[dict]:
        request = (
            f"GET {path} HTTP/1.0\r\n"
            "Host: local-tailscaled.sock\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        raw = self._roundtrip(request)
        if not raw:
            return None
        sep = raw.find(b"\r\n\r\n")
        if sep == -1:
            return None
        head, body = raw[:sep], raw[sep + 4 :]
        if b" 200 " not in head.split(b"\r\n", 1)[0]:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def status(self) -> Optional[dict]:
        return self._get("/localapi/v0/status")

    def whois(self, peer_ip: str) -> Optional[dict]:
        return self._get(f"/localapi/v0/whois?addr={peer_ip}")


def create_transport(name: Optional[str] = None) -> TransportProvider:
    """Build the configured transport. ``name`` overrides ``VADGR_TRANSPORT``."""
    selected = (name or os.environ.get("VADGR_TRANSPORT", "loopback")).strip().lower()
    if selected == "tailscale":
        return TailscaleTransport(local_api=TailscaledLocalAPI())
    if selected == "loopback":
        return LoopbackTransport()
    raise ValueError(
        f"Unknown VADGR_TRANSPORT={selected!r}. Expected 'loopback' or 'tailscale'."
    )
