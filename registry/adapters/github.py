"""GitHub-backed registry adapter.

Pull uses raw.githubusercontent.com (no auth needed for public repos).
Push creates a GitHub Release with the .agnt file as an asset.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from registry.adapters.base import RegistryAdapter

_TIMEOUT = 30
_GITHUB_API = "https://api.github.com"


class GitHubAdapter(RegistryAdapter):
    """Registry backed by a GitHub repo.

    Config keys:
        url: raw.githubusercontent.com URL for the repo (for GET)
        github_repo: "owner/repo" (for push via GitHub API)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._url = config.get("url", "").rstrip("/")
        self._repo = config.get("github_repo", "")
        self._token = self._resolve_token(config)

    @staticmethod
    def _resolve_token(config: dict) -> str:
        """Resolve GitHub token from config, env var, or gh CLI."""
        # Explicit token in config
        token = config.get("token") or ""
        if token:
            return token

        # GITHUB_TOKEN env var
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            return token

        # Try gh CLI auth
        try:
            import subprocess
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return ""

    def _headers(self, content_type: str = "application/json") -> dict:
        headers = {
            "User-Agent": "forge-registry/0.1",
            "Accept": "application/vnd.github+json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def fetch_index(self) -> dict:
        """GET index.json from raw.githubusercontent.com."""
        url = f"{self._url}/index.json"
        req = urllib.request.Request(url, headers={"User-Agent": "forge-registry/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"registry": {"name": self.name}, "agents": {}}
            raise RuntimeError(f"Failed to fetch index from {url}: {e}") from e

    def download_agent(self, download_url: str, dest: Path) -> Path:
        """Download .agnt from GitHub Release asset or raw URL."""
        headers = {"User-Agent": "forge-registry/0.1"}
        # GitHub Release assets need Accept header for binary download
        if "github.com" in download_url and "/releases/" in download_url:
            headers["Accept"] = "application/octet-stream"

        req = urllib.request.Request(download_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"Failed to download {download_url}: HTTP {e.code}"
            ) from e

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def push_agent(self, agnt_path: Path, manifest: dict) -> str:
        """Push .agnt to GitHub as a Release asset.

        1. Create or find a release tagged 'agents'
        2. Upload the .agnt file as a release asset
        3. Update index.json in the repo via Contents API
        """
        if not self._token:
            raise RuntimeError(
                "GitHub token required for push. Set GITHUB_TOKEN env var "
                "or add 'token' to registry config."
            )
        if not self._repo:
            raise RuntimeError(
                "github_repo not configured for this registry. "
                "Add 'github_repo: owner/repo' to registry config."
            )

        name = manifest["name"]
        version = manifest.get("version", "0.1.0")
        filename = f"{name}-{version}.agnt"
        tag = "agents"

        # Step 1: Get or create release
        release = self._get_or_create_release(tag)
        release_id = release["id"]
        upload_url = release["upload_url"].split("{")[0]  # strip {?name,label} template

        # Step 2: Upload asset
        asset_url = self._upload_asset(upload_url, release_id, filename, agnt_path)

        # Step 3: Update index.json
        self._update_index(name, version, manifest, asset_url)

        return f"Published {name}@{version} to {self._repo} ({asset_url})"

    def _get_or_create_release(self, tag: str) -> dict:
        """Get existing release by tag or create one."""
        url = f"{_GITHUB_API}/repos/{self._repo}/releases/tags/{tag}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        # Create release
        url = f"{_GITHUB_API}/repos/{self._repo}/releases"
        body = json.dumps({"tag_name": tag, "name": "Agent Registry", "body": "Agent .agnt packages"}).encode()
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())

    def _upload_asset(self, upload_url: str, release_id: int, filename: str, agnt_path: Path) -> str:
        """Upload .agnt as a release asset. Deletes existing asset with same name first."""
        # Check for existing asset with same name and delete it
        assets_url = f"{_GITHUB_API}/repos/{self._repo}/releases/{release_id}/assets"
        req = urllib.request.Request(assets_url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            assets = json.loads(resp.read())
        for asset in assets:
            if asset["name"] == filename:
                del_url = f"{_GITHUB_API}/repos/{self._repo}/releases/assets/{asset['id']}"
                del_req = urllib.request.Request(del_url, headers=self._headers(), method="DELETE")
                urllib.request.urlopen(del_req, timeout=_TIMEOUT)
                break

        # Upload new asset
        url = f"{upload_url}?name={filename}"
        file_data = agnt_path.read_bytes()
        headers = self._headers(content_type="application/zip")
        req = urllib.request.Request(url, data=file_data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
        return result["browser_download_url"]

    def _update_index(self, name: str, version: str, manifest: dict, asset_url: str) -> None:
        """Update index.json in the repo via GitHub Contents API."""
        path = "index.json"
        url = f"{_GITHUB_API}/repos/{self._repo}/contents/{path}"

        # Get current file (need sha for update)
        req = urllib.request.Request(url, headers=self._headers())
        current_sha = None
        current_index = {"registry": {"name": self.name}, "agents": {}}
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read())
                current_sha = data["sha"]
                import base64
                content = base64.b64decode(data["content"]).decode()
                current_index = json.loads(content)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

        # Update index
        current_index.setdefault("agents", {})
        current_index["agents"][name] = {
            "version": version,
            "description": manifest.get("description", ""),
            "author": manifest.get("author", ""),
            "download_url": asset_url,
        }

        import base64
        new_content = base64.b64encode(
            (json.dumps(current_index, indent=2) + "\n").encode()
        ).decode()

        body = {
            "message": f"publish {name}@{version}",
            "content": new_content,
        }
        if current_sha:
            body["sha"] = current_sha

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=self._headers(),
            method="PUT",
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT)
