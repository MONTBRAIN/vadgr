"""Shared fixtures for registry tests."""

import json
import os
import zipfile
from pathlib import Path

import pytest


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
    """Return valid manifest dict."""
    return {
        "manifest_version": 1,
        "name": "test-agent",
        "version": "0.1.0",
        "description": "A test agent",
        "author": "tester",
        "provider": "claude_code",
        "computer_use": False,
        "steps": [
            {"name": "Gather Data", "computer_use": False},
            {"name": "Analyze Results", "computer_use": True},
        ],
    }


@pytest.fixture
def sample_agnt_file(tmp_path, sample_agent_folder, sample_manifest_data):
    """Create a valid .agnt zip file."""
    agnt_path = tmp_path / "test-agent-0.1.0.agnt"
    with zipfile.ZipFile(agnt_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(sample_manifest_data, indent=2))
        # Add files from the sample agent folder
        for path in sample_agent_folder.rglob("*"):
            if path.is_file():
                rel = path.relative_to(sample_agent_folder)
                zf.write(path, str(rel))
    return agnt_path


@pytest.fixture
def local_registry(tmp_path):
    """Create a local folder registry with one agent."""
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

    # Create the .agnt file
    agnt_path = agents_dir / "demo-agent-1.0.0.agnt"
    manifest = {
        "manifest_version": 1,
        "name": "demo-agent",
        "version": "1.0.0",
        "description": "A demo agent",
    }
    with zipfile.ZipFile(agnt_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("agentic.md", "# Demo Agent\n")

    return reg_dir
