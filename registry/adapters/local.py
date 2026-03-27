"""Local filesystem registry adapter."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from registry.adapters.base import RegistryAdapter


class LocalAdapter(RegistryAdapter):
    """Registry backed by a local folder.

    Folder structure:
        my-registry/
            index.json
            agents/
                research-paper-0.1.0.agnt
                data-analysis-1.0.0.agnt
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._root = Path(config.get("path", config.get("url", ""))).expanduser()

    @property
    def root(self) -> Path:
        return self._root

    def fetch_index(self) -> dict:
        """Read index.json from the local folder."""
        index_path = self._root / "index.json"
        if not index_path.exists():
            return {"registry": {"name": self.name}, "agents": {}}
        with open(index_path) as f:
            return json.load(f)

    def download_agent(self, download_url: str, dest: Path) -> Path:
        """Copy .agnt file from local registry to dest."""
        # download_url is relative to the registry root
        source = self._root / download_url
        if not source.is_file():
            raise FileNotFoundError(f"Agent file not found: {source}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return dest

    def push_agent(self, agnt_path: Path, manifest: dict) -> str:
        """Copy .agnt file into the local registry and update index.json."""
        agents_dir = self._root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        name = manifest["name"]
        version = manifest.get("version", "0.1.0")
        filename = f"{name}-{version}.agnt"
        dest = agents_dir / filename

        shutil.copy2(agnt_path, dest)

        # Update index.json
        index = self.fetch_index()
        index.setdefault("registry", {"name": self.name})
        index.setdefault("agents", {})
        index["agents"][name] = {
            "version": version,
            "description": manifest.get("description", ""),
            "author": manifest.get("author", ""),
            "download_url": f"agents/{filename}",
        }

        index_path = self._root / "index.json"
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
            f.write("\n")

        return f"Published {name}@{version} to local registry at {self._root}"
