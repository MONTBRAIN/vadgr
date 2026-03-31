"""High-level registry operations that orchestrate adapters."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from registry.adapters import create_adapter
from registry.adapters.base import RegistryAdapter
from registry.config import load_config, get_agents_dir, get_default_registry
from registry.installer import install as install_agent, list_installed
from registry.manifest import validate_manifest
from registry.packer import pack as pack_agent
from registry.security import verify_sha256


def _get_adapter(registry_name: Optional[str] = None) -> RegistryAdapter:
    """Get an adapter for the named registry, or the default."""
    config = load_config()
    if registry_name:
        for reg in config.get("registries", []):
            if reg.get("name") == registry_name:
                return create_adapter(reg)
        raise ValueError(f"Registry '{registry_name}' not found in config")
    default = get_default_registry(config)
    if not default:
        raise ValueError("No registries configured")
    return create_adapter(default)


def pack(folder: str, output: Optional[str] = None) -> str:
    """Pack an agent folder into a .agnt file.

    Returns the path to the created .agnt file.
    """
    result = pack_agent(Path(folder), output=Path(output) if output else None)
    return str(result)


def pull(
    name: str,
    registry_name: Optional[str] = None,
    force: bool = False,
    keep_archive: Optional[Path] = None,
) -> str:
    """Pull an agent from a registry and install it locally.

    Searches the specified registry (or default) for the agent by name,
    downloads the .agnt file, and installs it to ~/.forge/agents/.

    If *keep_archive* is given, the downloaded .agnt file is copied there
    before the temporary directory is cleaned up.

    Returns the path to the installed agent.
    """
    import shutil

    adapter = _get_adapter(registry_name)
    agent_info = adapter.find_agent(name)
    if not agent_info:
        raise ValueError(f"Agent '{name}' not found in registry '{adapter.name}'")

    download_url = agent_info.get("download_url")
    if not download_url:
        raise ValueError(f"Agent '{name}' has no download URL in the registry")

    config = load_config()
    agents_dir = get_agents_dir(config)

    with tempfile.TemporaryDirectory() as tmpdir:
        agnt_path = Path(tmpdir) / f"{name}.agnt"
        adapter.download_agent(download_url, agnt_path)

        # Verify integrity if SHA256 is available in the index
        expected_hash = agent_info.get("sha256")
        if expected_hash:
            verify_sha256(agnt_path, expected_hash)

        install_dir = install_agent(agnt_path, agents_dir=agents_dir, force=force)

        if keep_archive:
            shutil.copy2(agnt_path, keep_archive)

    return str(install_dir)


def push(
    agnt_path: str,
    registry_name: Optional[str] = None,
) -> str:
    """Push a .agnt file to a registry.

    Returns a confirmation message or URL.
    """
    path = Path(agnt_path)
    if not path.is_file():
        raise FileNotFoundError(f".agnt file not found: {agnt_path}")

    # Read manifest from the .agnt
    import json
    import zipfile
    from registry.manifest import MANIFEST_FILENAME
    with zipfile.ZipFile(path) as zf:
        if MANIFEST_FILENAME not in zf.namelist():
            raise ValueError(f"Invalid .agnt file: missing {MANIFEST_FILENAME}")
        manifest_data = json.loads(zf.read(MANIFEST_FILENAME))
    validate_manifest(manifest_data)

    adapter = _get_adapter(registry_name)
    return adapter.push_agent(path, manifest_data)


def search(
    query: str,
    registry_name: Optional[str] = None,
) -> list[dict]:
    """Search for agents across registries.

    If registry_name is given, searches only that registry.
    Otherwise searches all configured registries.
    """
    if registry_name:
        adapter = _get_adapter(registry_name)
        return adapter.search(query)

    # Search all registries
    config = load_config()
    all_results = []
    seen_names = set()
    for reg in config.get("registries", []):
        try:
            adapter = create_adapter(reg)
            results = adapter.search(query)
            for r in results:
                if r["name"] not in seen_names:
                    r["registry"] = reg.get("name", "unknown")
                    all_results.append(r)
                    seen_names.add(r["name"])
        except Exception:
            continue  # Skip unreachable registries
    return all_results


def agents() -> list[dict]:
    """List all locally installed agents."""
    config = load_config()
    return list_installed(get_agents_dir(config))
