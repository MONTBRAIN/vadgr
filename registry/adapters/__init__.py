"""Registry adapters for different backend types (GitHub, HTTP, local)."""

from registry.adapters.base import RegistryAdapter
from registry.adapters.github import GitHubAdapter
from registry.adapters.http import HTTPAdapter
from registry.adapters.local import LocalAdapter


def create_adapter(registry: dict) -> RegistryAdapter:
    """Factory: create the right adapter based on registry config type."""
    reg_type = registry.get("type", "")

    if reg_type == "local" or "path" in registry:
        return LocalAdapter(registry)
    elif reg_type == "github" or "github_repo" in registry:
        return GitHubAdapter(registry)
    else:
        return HTTPAdapter(registry)
