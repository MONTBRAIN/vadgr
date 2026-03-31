"""Pack agent folders into .agnt archives and unpack them."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from registry.config import PACK_EXCLUDE_DIRS
from registry.manifest import (
    MANIFEST_FILENAME,
    Manifest,
    StepEntry,
    validate_manifest,
)


def _should_exclude(rel_path: Path) -> bool:
    """Check if a relative path should be excluded from the .agnt archive."""
    for part in rel_path.parts:
        if part in PACK_EXCLUDE_DIRS:
            return True
    return False


def _detect_steps(folder: Path) -> list[StepEntry]:
    """Auto-detect steps from agent/steps/ filenames.

    Parses filenames like step_01_gather-data.md into StepEntry objects.
    Same pattern used by api/routes/agents.py:_steps_from_disk.
    """
    steps_dir = folder / "agent" / "steps"
    if not steps_dir.is_dir():
        return []

    pattern = re.compile(r"^step_(\d+)_(.+)\.md$")
    entries = []
    for f in sorted(steps_dir.iterdir()):
        match = pattern.match(f.name)
        if not match:
            continue
        kebab_name = match.group(2)
        # Convert kebab-case to title: "gather-data" -> "Gather Data"
        name = kebab_name.replace("-", " ").title()
        # Check if the step file mentions computer use
        content = f.read_text(errors="replace").lower()
        uses_cu = "computer_use" in content or "computer use" in content
        entries.append(StepEntry(name=name, computer_use=uses_cu))
    return entries


def _detect_computer_use(steps: list[StepEntry]) -> bool:
    """Return True if any step uses computer use."""
    return any(s.computer_use for s in steps)


def _detect_name(folder: Path) -> str:
    """Infer agent name from folder name or agentic.md title."""
    # Try first line of agentic.md for a markdown title
    agentic = folder / "agentic.md"
    if agentic.exists():
        first_line = agentic.read_text(errors="replace").split("\n", 1)[0].strip()
        if first_line.startswith("#"):
            title = first_line.lstrip("#").strip()
            # Convert to kebab-case
            kebab = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            if kebab:
                return kebab
    # Fall back to folder name
    return re.sub(r"[^a-z0-9]+", "-", folder.name.lower()).strip("-") or "unnamed-agent"


def build_manifest(folder: Path, overrides: Optional[dict] = None) -> Manifest:
    """Build a manifest from an agent folder, merging with any existing agent-forge.json."""
    existing = {}
    manifest_path = folder / MANIFEST_FILENAME
    if manifest_path.exists():
        with open(manifest_path) as f:
            existing = json.load(f)

    # Pick up input/output schemas from schema.json (written by the API)
    schema_path = folder / "schema.json"
    if schema_path.exists():
        try:
            with open(schema_path) as f:
                schema_data = json.load(f)
            for key in ("input_schema", "output_schema", "samples"):
                if schema_data.get(key) and not existing.get(key):
                    existing[key] = schema_data[key]
        except (json.JSONDecodeError, OSError):
            pass

    steps = _detect_steps(folder)

    auto = {
        "manifest_version": 2,
        "name": _detect_name(folder),
        "computer_use": _detect_computer_use(steps),
        "steps": [s.model_dump() for s in steps],
    }

    # Merge priority: overrides > existing manifest > auto-detected
    merged = {**auto, **existing}
    if overrides:
        merged.update(overrides)

    return validate_manifest(merged)


def collect_files(folder: Path) -> list[Path]:
    """Collect all files in the folder that should be included in the .agnt archive."""
    files = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        if _should_exclude(rel):
            continue
        files.append(rel)
    return files


def _create_git_bundle(folder: Path, files: list[Path], name: str) -> bytes:
    """Create a git bundle from agent files.

    Initialises a temporary git repo, copies the agent files in, commits,
    and returns the raw bytes of a ``git bundle create --all``.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Copy agent files into the temp repo
        for rel in files:
            src = folder / rel
            dst = repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        git = ["git", "-C", str(repo)]
        subprocess.run([*git, "init"], check=True, capture_output=True)
        subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            [*git, "-c", "user.name=Agent Forge", "-c", "user.email=agent-forge@local",
             "commit", "-m", f"Registry pack of {name}"],
            check=True, capture_output=True,
        )

        bundle_path = repo / "agent.bundle"
        subprocess.run(
            [*git, "bundle", "create", str(bundle_path), "--all"],
            check=True, capture_output=True,
        )
        return bundle_path.read_bytes()


def pack(folder: Path, output: Optional[Path] = None) -> Path:
    """Package an agent folder into a .agnt archive.

    The archive uses the API-compatible format: ``agent-forge.json`` manifest
    plus an ``agent.bundle`` git bundle so that the resulting ``.agnt`` file
    can be imported directly via ``forge agents import``.

    Args:
        folder: Path to the agent folder (must contain agentic.md).
        output: Optional output path. Defaults to {name}-{version}.agnt in cwd.

    Returns:
        Path to the created .agnt file.

    Raises:
        FileNotFoundError: If folder doesn't exist or agentic.md is missing.
        ValueError: If manifest validation fails.
    """
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Agent folder not found: {folder}")
    if not (folder / "agentic.md").exists():
        raise FileNotFoundError(
            f"Not a valid agent folder (missing agentic.md): {folder}"
        )

    manifest = build_manifest(folder)
    files = collect_files(folder)

    if output is None:
        output = Path.cwd() / f"{manifest.name}-{manifest.version}.agnt"
    output = Path(output).resolve()

    bundle_bytes = _create_git_bundle(folder, files, manifest.name)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_FILENAME, json.dumps(manifest.model_dump(), indent=2) + "\n")
        zf.writestr("agent.bundle", bundle_bytes)

    return output


def unpack(agnt_path: Path, dest: Path) -> Manifest:
    """Unpack a .agnt archive to a destination directory.

    Args:
        agnt_path: Path to the .agnt file.
        dest: Directory to extract into (will be created).

    Returns:
        The parsed Manifest from the archive.

    Raises:
        FileNotFoundError: If .agnt file doesn't exist.
        ValueError: If archive is invalid or manifest is bad.
    """
    agnt_path = Path(agnt_path).resolve()
    if not agnt_path.is_file():
        raise FileNotFoundError(f".agnt file not found: {agnt_path}")

    with zipfile.ZipFile(agnt_path, "r") as zf:
        names = zf.namelist()

        if MANIFEST_FILENAME not in names:
            raise ValueError(f"Invalid .agnt archive: missing {MANIFEST_FILENAME}")
        if "agent.bundle" not in names:
            raise ValueError(f"Invalid .agnt archive: missing agent.bundle")

        manifest_data = json.loads(zf.read(MANIFEST_FILENAME))
        manifest = validate_manifest(manifest_data)

        dest = Path(dest)
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = Path(tmpdir) / "agent.bundle"
            bundle_path.write_bytes(zf.read("agent.bundle"))
            subprocess.run(
                ["git", "clone", str(bundle_path), str(dest)],
                check=True, capture_output=True,
            )

        # Write manifest into dest so list_installed can find it
        (dest / MANIFEST_FILENAME).write_text(
            json.dumps(manifest_data, indent=2) + "\n"
        )
        return manifest
