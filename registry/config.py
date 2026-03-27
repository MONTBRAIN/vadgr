"""Registry configuration and path constants."""

import os
from pathlib import Path
from typing import Optional

import yaml

FORGE_HOME = Path(os.environ.get("FORGE_HOME", Path.home() / ".forge"))
AGENTS_DIR = FORGE_HOME / "agents"
CONFIG_PATH = FORGE_HOME / "registry.yaml"

DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/MONTBRAIN/forge-registry/main"
)
DEFAULT_REGISTRY_REPO = "MONTBRAIN/forge-registry"

# Directories excluded when packing an agent folder into .agnt
PACK_EXCLUDE_DIRS = frozenset({
    "__pycache__",
    ".git",
    ".venv",
    "node_modules",
    "output",
    ".pytest_cache",
})


def _default_config() -> dict:
    """Return the default configuration when no config file exists."""
    return {
        "registries": [
            {
                "name": "official",
                "url": DEFAULT_REGISTRY_URL,
                "type": "github",
                "github_repo": DEFAULT_REGISTRY_REPO,
                "default": True,
            },
        ],
        "agents_dir": str(AGENTS_DIR),
    }


def load_config(config_path: Optional[Path] = None) -> dict:
    """Load registry config from disk, falling back to defaults."""
    path = config_path or CONFIG_PATH
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        # Merge with defaults for any missing keys
        defaults = _default_config()
        for key in defaults:
            data.setdefault(key, defaults[key])
        return data
    return _default_config()


def save_config(config: dict, config_path: Optional[Path] = None) -> None:
    """Write registry config to disk."""
    path = config_path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False)


def get_agents_dir(config: Optional[dict] = None) -> Path:
    """Return the agents installation directory."""
    if config and "agents_dir" in config:
        return Path(config["agents_dir"]).expanduser()
    return AGENTS_DIR


def get_default_registry(config: Optional[dict] = None) -> Optional[dict]:
    """Return the registry marked as default, or the first one."""
    cfg = config or load_config()
    registries = cfg.get("registries", [])
    for reg in registries:
        if reg.get("default"):
            return reg
    return registries[0] if registries else None


def get_registry_by_name(name: str, config: Optional[dict] = None) -> Optional[dict]:
    """Find a registry by name."""
    cfg = config or load_config()
    for reg in cfg.get("registries", []):
        if reg.get("name") == name:
            return reg
    return None
