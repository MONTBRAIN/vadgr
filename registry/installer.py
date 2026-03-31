"""Install and manage locally installed agents."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from registry.config import get_agents_dir, load_config
from registry.manifest import Manifest, load_manifest, validate_manifest
from registry.packer import unpack


def install(
    agnt_path: Path,
    agents_dir: Optional[Path] = None,
    force: bool = False,
) -> Path:
    """Install a .agnt archive to the local agents directory.

    Args:
        agnt_path: Path to the .agnt file.
        agents_dir: Override agents directory. Defaults to ~/.forge/agents/.
        force: Overwrite if agent already installed.

    Returns:
        Path to the installed agent directory.

    Raises:
        FileExistsError: If agent already installed and force=False.
        ValueError: If .agnt is invalid.
    """
    dest_root = agents_dir or get_agents_dir()
    dest_root.mkdir(parents=True, exist_ok=True)

    # Peek at manifest to get the agent name
    manifest = _peek_manifest(agnt_path)
    install_dir = dest_root / manifest.name

    if install_dir.exists():
        if not force:
            raise FileExistsError(
                f"Agent '{manifest.name}' already installed at {install_dir}. "
                f"Use --force to overwrite."
            )
        shutil.rmtree(install_dir)

    unpack(agnt_path, install_dir)
    return install_dir


def uninstall(name: str, agents_dir: Optional[Path] = None) -> bool:
    """Remove an installed agent by name.

    Returns True if removed, False if not found.
    """
    dest_root = agents_dir or get_agents_dir()
    install_dir = dest_root / name
    if install_dir.exists():
        shutil.rmtree(install_dir)
        return True
    return False


def list_installed(agents_dir: Optional[Path] = None) -> list[dict]:
    """List all locally installed agents.

    Returns a list of dicts with agent metadata from each agent-forge.json.
    """
    from registry.manifest import MANIFEST_FILENAME

    dest_root = agents_dir or get_agents_dir()
    if not dest_root.exists():
        return []

    agents = []
    for entry in sorted(dest_root.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / MANIFEST_FILENAME
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path) as f:
                data = json.load(f)
            manifest = validate_manifest(data)
            agents.append({
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "author": manifest.author,
                "provider": manifest.provider,
                "computer_use": manifest.computer_use,
                "steps": len(manifest.steps),
                "path": str(entry),
            })
        except (json.JSONDecodeError, ValueError, OSError):
            # Skip agents with corrupt manifests
            continue

    return agents


def get_installed(name: str, agents_dir: Optional[Path] = None) -> Optional[dict]:
    """Get metadata for a specific installed agent."""
    for agent in list_installed(agents_dir):
        if agent["name"] == name:
            return agent
    return None


def _peek_manifest(agnt_path: Path) -> Manifest:
    """Read manifest from a .agnt archive without extracting everything."""
    import zipfile
    from registry.manifest import MANIFEST_FILENAME

    with zipfile.ZipFile(agnt_path, "r") as zf:
        if MANIFEST_FILENAME not in zf.namelist():
            raise ValueError(f"Invalid .agnt: missing {MANIFEST_FILENAME} in {agnt_path}")
        data = json.loads(zf.read(MANIFEST_FILENAME))
        return validate_manifest(data)
