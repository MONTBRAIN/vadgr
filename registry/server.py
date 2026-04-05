"""Minimal registry HTTP server for self-hosting.

Usage:
    python -m registry.server [--port 9876] [--dir ./my-registry]

Implements the registry protocol:
    GET  /index.json              -- agent catalog
    GET  /agents/{name}.agnt      -- download agent
    POST /agents/{name}.agnt      -- upload agent (requires Bearer token)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_PORT = 9876
DEFAULT_DIR = Path.cwd() / "registry-data"


class RegistryHandler(BaseHTTPRequestHandler):
    """HTTP handler for the registry protocol."""

    def _registry_dir(self) -> Path:
        return self.server.registry_dir  # type: ignore[attr-defined]

    def _auth_token(self) -> str:
        return self.server.auth_token  # type: ignore[attr-defined]

    def _check_auth(self) -> bool:
        """Validate Bearer token if server has one configured."""
        token = self._auth_token()
        if not token:
            return True  # No auth configured
        auth_header = self.headers.get("Authorization", "")
        return auth_header == f"Bearer {token}"

    def do_GET(self):
        """Serve index.json and .agnt files."""
        parsed = urlparse(self.path)
        path = parsed.path.lstrip("/")

        if path == "index.json":
            self._serve_file(self._registry_dir() / "index.json", "application/json")
        elif path.startswith("agents/") and path.endswith(".agnt"):
            # Validate no path traversal
            filename = Path(path).name
            agnt_path = self._registry_dir() / "agents" / filename
            self._serve_file(agnt_path, "application/octet-stream")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        """Accept .agnt uploads."""
        if not self._check_auth():
            self.send_error(401, "Unauthorized")
            return

        parsed = urlparse(self.path)
        path = parsed.path.lstrip("/")

        if not (path.startswith("agents/") and path.endswith(".agnt")):
            self.send_error(404, "Not Found")
            return

        # Read the uploaded file
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error(400, "Empty body")
            return

        MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
        if content_length > MAX_UPLOAD_SIZE:
            self.send_error(413, "File too large")
            return

        data = self.rfile.read(content_length)

        # Verify SHA256 if provided
        expected_sha = self.headers.get("X-Content-SHA256")
        if expected_sha:
            actual_sha = hashlib.sha256(data).hexdigest()
            if actual_sha != expected_sha.lower():
                self.send_error(400, f"SHA256 mismatch: expected {expected_sha}, got {actual_sha}")
                return

        # Save the file
        filename = Path(path).name
        agents_dir = self._registry_dir() / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        dest = agents_dir / filename
        dest.write_bytes(data)

        # Update index.json from the .agnt manifest
        self._update_index(dest, filename)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "file": filename}).encode())

    def _serve_file(self, file_path: Path, content_type: str):
        """Serve a file from disk."""
        if not file_path.exists():
            self.send_error(404, "Not Found")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _update_index(self, agnt_path: Path, filename: str):
        """Update index.json after an upload."""
        import zipfile

        from registry.manifest import MANIFEST_FILENAME
        try:
            with zipfile.ZipFile(agnt_path, "r") as zf:
                if MANIFEST_FILENAME not in zf.namelist():
                    return
                manifest = json.loads(zf.read(MANIFEST_FILENAME))
        except Exception:
            return

        name = manifest.get("name", "unknown")
        version = manifest.get("version", "0.1.0")
        sha256 = hashlib.sha256(agnt_path.read_bytes()).hexdigest()

        index_path = self._registry_dir() / "index.json"
        index = {"registry": {"name": "self-hosted"}, "agents": {}}
        if index_path.exists():
            index = json.loads(index_path.read_text())

        index.setdefault("agents", {})
        index["agents"][name] = {
            "version": version,
            "description": manifest.get("description", ""),
            "author": manifest.get("author", ""),
            "download_url": f"agents/{filename}",
            "sha256": sha256,
        }

        index_path.write_text(json.dumps(index, indent=2) + "\n")

    def log_message(self, format, *args):
        """Log to stderr with prefix."""
        sys.stderr.write(f"[registry-server] {format % args}\n")


def run_server(port: int = DEFAULT_PORT, directory: Path = DEFAULT_DIR, token: str = ""):
    """Start the registry HTTP server."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    server = HTTPServer(("0.0.0.0", port), RegistryHandler)
    server.registry_dir = directory  # type: ignore[attr-defined]
    server.auth_token = token  # type: ignore[attr-defined]

    print(f"Registry server running on http://0.0.0.0:{port}")
    print(f"Data directory: {directory}")
    if token:
        print("Authentication: Bearer token required for uploads")
    else:
        print("Authentication: NONE (anyone can upload)")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vadgr registry server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--dir", type=str, default=str(DEFAULT_DIR), help="Data directory")
    parser.add_argument("--token", type=str, default="", help="Bearer token for upload auth")
    args = parser.parse_args()
    run_server(port=args.port, directory=Path(args.dir), token=args.token)
