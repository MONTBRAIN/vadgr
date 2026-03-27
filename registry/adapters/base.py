"""Abstract base class for registry adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class RegistryAdapter(ABC):
    """Interface that all registry backends must implement."""

    def __init__(self, config: dict):
        self.config = config
        self.name = config.get("name", "unnamed")

    @abstractmethod
    def fetch_index(self) -> dict:
        """Fetch the registry index. Returns parsed index.json content."""

    @abstractmethod
    def download_agent(self, download_url: str, dest: Path) -> Path:
        """Download a .agnt file to dest. Returns path to downloaded file."""

    @abstractmethod
    def push_agent(self, agnt_path: Path, manifest: dict) -> str:
        """Push a .agnt file to the registry. Returns a URL or confirmation message."""

    def search(self, query: str) -> list[dict]:
        """Search the index for agents matching the query."""
        index = self.fetch_index()
        agents = index.get("agents", {})
        query_lower = query.lower()
        results = []
        for name, info in agents.items():
            searchable = f"{name} {info.get('description', '')}".lower()
            if query_lower in searchable:
                results.append({"name": name, **info})
        return results

    def find_agent(self, name: str) -> Optional[dict]:
        """Look up a specific agent in the index by name."""
        index = self.fetch_index()
        agents = index.get("agents", {})
        if name in agents:
            return {"name": name, **agents[name]}
        return None
