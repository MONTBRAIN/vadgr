"""Shared fixtures for registry tests."""

import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

from registry.manifest import MANIFEST_FILENAME


@pytest.fixture
def sample_agent_folder(tmp_path):
    """Create a minimal valid agent folder structure."""
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()
    (agent_dir / "agentic.md").write_text("# Test Agent\n\nA test workflow.\n")
    (agent_dir / "CLAUDE.md").write_text("# Test Agent Rules\n")
    (agent_dir / "README.md").write_text("# Test Agent\n")

    steps_dir = agent_dir / "agent" / "steps"
    steps_dir.mkdir(parents=True)
    (steps_dir / "step_01_gather-data.md").write_text("# Step 1: Gather Data\n")
    (steps_dir / "step_02_analyze-results.md").write_text(
        "# Step 2: Analyze Results\n\nUses computer_use for screen interaction.\n"
    )

    prompts_dir = agent_dir / "agent" / "Prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "01_Data_Analyst.md").write_text("# Data Analyst Prompt\n")

    return agent_dir


@pytest.fixture
def sample_manifest_data():
    """Return valid manifest dict (v2 format)."""
    return {
        "manifest_version": 2,
        "export_version": 2,
        "name": "test-agent",
        "version": "0.1.0",
        "description": "A test agent",
        "author": "tester",
        "provider": "claude_code",
        "model": "claude-sonnet-4-6",
        "computer_use": False,
        "steps": [
            {"name": "Gather Data", "computer_use": False},
            {"name": "Analyze Results", "computer_use": True},
        ],
        "samples": [],
        "input_schema": [],
        "output_schema": [],
    }


def _create_bundle_bytes(agent_folder: Path) -> bytes:
    """Helper: create a git bundle from an agent folder."""
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        for path in agent_folder.rglob("*"):
            if path.is_file():
                rel = path.relative_to(agent_folder)
                dst = repo / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)

        git = ["git", "-C", str(repo)]
        subprocess.run([*git, "init"], check=True, capture_output=True)
        subprocess.run([*git, "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            [*git, "-c", "user.name=Test", "-c", "user.email=test@test",
             "commit", "-m", "test"],
            check=True, capture_output=True,
        )
        bundle_path = repo / "agent.bundle"
        subprocess.run(
            [*git, "bundle", "create", str(bundle_path), "--all"],
            check=True, capture_output=True,
        )
        return bundle_path.read_bytes()


@pytest.fixture
def sample_agnt_file(tmp_path, sample_agent_folder, sample_manifest_data):
    """Create a valid .agnt zip file (v2: agent-forge.json + agent.bundle)."""
    agnt_path = tmp_path / "test-agent-0.1.0.agnt"
    bundle_bytes = _create_bundle_bytes(sample_agent_folder)
    with zipfile.ZipFile(agnt_path, "w") as zf:
        zf.writestr(MANIFEST_FILENAME, json.dumps(sample_manifest_data, indent=2))
        zf.writestr("agent.bundle", bundle_bytes)
    return agnt_path


@pytest.fixture
def local_registry(tmp_path, sample_agent_folder):
    """Create a local folder registry with one agent (v2 format)."""
    reg_dir = tmp_path / "my-registry"
    reg_dir.mkdir()
    agents_dir = reg_dir / "agents"
    agents_dir.mkdir()

    index = {
        "registry": {"name": "test-local"},
        "agents": {
            "demo-agent": {
                "version": "1.0.0",
                "description": "A demo agent",
                "author": "tester",
                "download_url": "agents/demo-agent-1.0.0.agnt",
            }
        },
    }
    (reg_dir / "index.json").write_text(json.dumps(index, indent=2))

    # Create a v2 .agnt file with git bundle
    agnt_path = agents_dir / "demo-agent-1.0.0.agnt"

    # Create a minimal agent folder for the bundle
    demo_dir = tmp_path / "demo-agent-src"
    demo_dir.mkdir()
    (demo_dir / "agentic.md").write_text("# Demo Agent\n")

    bundle_bytes = _create_bundle_bytes(demo_dir)
    manifest = {
        "manifest_version": 2,
        "export_version": 2,
        "name": "demo-agent",
        "version": "1.0.0",
        "description": "A demo agent",
    }
    with zipfile.ZipFile(agnt_path, "w") as zf:
        zf.writestr(MANIFEST_FILENAME, json.dumps(manifest, indent=2))
        zf.writestr("agent.bundle", bundle_bytes)

    return reg_dir
