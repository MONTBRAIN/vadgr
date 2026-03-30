"""Manifest schema and validation for .agnt packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

MANIFEST_VERSION = 1


class StepEntry(BaseModel):
    """A single step in the agent workflow."""

    name: str
    computer_use: bool = False


class Manifest(BaseModel):
    """Schema for manifest.json inside a .agnt package."""

    manifest_version: int = MANIFEST_VERSION
    name: str = Field(..., min_length=1, max_length=64)
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    license: str = ""
    provider: str = "claude_code"
    computer_use: bool = False
    steps: list[StepEntry] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_is_kebab(cls, v: str) -> str:
        """Agent names must be lowercase kebab-case."""
        cleaned = v.strip().lower()
        if not all(c.isalnum() or c == "-" for c in cleaned):
            raise ValueError(
                f"Agent name must be kebab-case (lowercase alphanumeric + hyphens), got: {v!r}"
            )
        return cleaned

    @field_validator("manifest_version")
    @classmethod
    def version_supported(cls, v: int) -> int:
        if v != MANIFEST_VERSION:
            raise ValueError(
                f"Unsupported manifest version {v}, expected {MANIFEST_VERSION}"
            )
        return v


def validate_manifest(data: dict) -> Manifest:
    """Parse and validate a manifest dict. Raises ValueError on failure."""
    try:
        return Manifest(**data)
    except Exception as e:
        raise ValueError(f"Invalid manifest: {e}") from e


def load_manifest(path: Path) -> Manifest:
    """Load and validate manifest.json from a file path."""
    with open(path) as f:
        data = json.load(f)
    return validate_manifest(data)


def write_manifest(manifest: Manifest, path: Path) -> None:
    """Write a manifest to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest.model_dump(), f, indent=2)
        f.write("\n")
