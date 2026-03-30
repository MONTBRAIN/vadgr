"""Generic HTTP registry adapter."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from registry.adapters.base import RegistryAdapter
from registry.security import (
    compute_sha256,
    create_ssl_context,
    resolve_token,
    validate_download_url,
)

_TIMEOUT = 30  # seconds


class HTTPAdapter(RegistryAdapter):
    """Registry backed by any HTTP server implementing the registry protocol.

    Expected server endpoints:
        GET  /index.json              -- agent catalog
        GET  /agents/{name}.agnt      -- download agent
        POST /agents/{name}.agnt      -- upload agent (optional)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._url = config.get("url", "").rstrip("/")
        self._token = resolve_token(config.get("token"))
        self._ssl_verify = config.get("ssl_verify", True)
        self._ssl_ctx = create_ssl_context(verify=self._ssl_verify)

    def _headers(self) -> dict:
        headers = {"User-Agent": "forge-registry/0.1"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get(self, url: str) -> bytes:
        """HTTP GET with optional auth and TLS verification."""
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT, context=self._ssl_ctx) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to reach {url}: {e.reason}") from e

    def fetch_index(self) -> dict:
        """GET /index.json from the registry."""
        data = self._get(f"{self._url}/index.json")
        return json.loads(data)

    def download_agent(self, download_url: str, dest: Path) -> Path:
        """Download a .agnt file. download_url can be relative or absolute."""
        if download_url.startswith("http://") or download_url.startswith("https://"):
            url = download_url
        else:
            url = f"{self._url}/{download_url}"

        validate_download_url(url)

        data = self._get(url)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def push_agent(self, agnt_path: Path, manifest: dict) -> str:
        """POST the .agnt file to the registry server."""
        name = manifest["name"]
        version = manifest.get("version", "0.1.0")
        url = f"{self._url}/agents/{name}-{version}.agnt"

        sha256 = compute_sha256(agnt_path)

        file_data = agnt_path.read_bytes()
        headers = self._headers()
        headers["Content-Type"] = "application/octet-stream"
        headers["X-Content-SHA256"] = sha256

        req = urllib.request.Request(url, data=file_data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60, context=self._ssl_ctx) as resp:
                return f"Published {name}@{version} to {self._url}"
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"Push failed (HTTP {e.code}): {e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to reach {url}: {e.reason}") from e
