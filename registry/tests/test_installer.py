"""Tests for installing and managing local agents."""

import json
import zipfile
import pytest
from pathlib import Path

from registry.installer import (
    install,
    uninstall,
    list_installed,
    get_installed,
    _peek_manifest,
)
from registry.manifest import MANIFEST_FILENAME


class TestPeekManifest:

    def test_reads_manifest_from_agnt(self, sample_agnt_file):
        m = _peek_manifest(sample_agnt_file)
        assert m.name == "test-agent"
        assert m.version == "0.1.0"

    def test_invalid_agnt_raises(self, tmp_path):
        bad = tmp_path / "bad.agnt"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("agentic.md", "# No manifest\n")
        with pytest.raises(ValueError, match="missing agent-forge.json"):
            _peek_manifest(bad)


class TestInstall:

    def test_install_creates_agent_dir(self, sample_agnt_file, tmp_path):
        agents_dir = tmp_path / "agents"
        result = install(sample_agnt_file, agents_dir=agents_dir)
        assert result == agents_dir / "test-agent"
        assert result.is_dir()
        assert (result / MANIFEST_FILENAME).exists()
        assert (result / "agentic.md").exists()

    def test_install_refuses_overwrite_without_force(self, sample_agnt_file, tmp_path):
        agents_dir = tmp_path / "agents"
        install(sample_agnt_file, agents_dir=agents_dir)
        with pytest.raises(FileExistsError, match="already installed"):
            install(sample_agnt_file, agents_dir=agents_dir)

    def test_install_force_overwrites(self, sample_agnt_file, tmp_path):
        agents_dir = tmp_path / "agents"
        install(sample_agnt_file, agents_dir=agents_dir)
        # Modify a file to verify overwrite
        (agents_dir / "test-agent" / "marker.txt").write_text("old")
        install(sample_agnt_file, agents_dir=agents_dir, force=True)
        assert not (agents_dir / "test-agent" / "marker.txt").exists()

    def test_install_creates_agents_dir_if_missing(self, sample_agnt_file, tmp_path):
        agents_dir = tmp_path / "deep" / "nested" / "agents"
        result = install(sample_agnt_file, agents_dir=agents_dir)
        assert result.is_dir()


class TestUninstall:

    def test_uninstall_removes_agent(self, sample_agnt_file, tmp_path):
        agents_dir = tmp_path / "agents"
        install(sample_agnt_file, agents_dir=agents_dir)
        assert (agents_dir / "test-agent").exists()
        assert uninstall("test-agent", agents_dir=agents_dir) is True
        assert not (agents_dir / "test-agent").exists()

    def test_uninstall_nonexistent_returns_false(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        assert uninstall("nope", agents_dir=agents_dir) is False


class TestListInstalled:

    def test_list_empty(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        assert list_installed(agents_dir) == []

    def test_list_nonexistent_dir(self, tmp_path):
        assert list_installed(tmp_path / "nope") == []

    def test_list_shows_installed_agents(self, sample_agnt_file, tmp_path):
        agents_dir = tmp_path / "agents"
        install(sample_agnt_file, agents_dir=agents_dir)
        agents = list_installed(agents_dir)
        assert len(agents) == 1
        assert agents[0]["name"] == "test-agent"
        assert agents[0]["version"] == "0.1.0"
        assert agents[0]["path"] == str(agents_dir / "test-agent")

    def test_list_skips_dirs_without_manifest(self, tmp_path):
        agents_dir = tmp_path / "agents"
        (agents_dir / "bad-agent").mkdir(parents=True)
        (agents_dir / "bad-agent" / "agentic.md").write_text("no manifest")
        assert list_installed(agents_dir) == []

    def test_list_skips_corrupt_manifest(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agent_dir = agents_dir / "corrupt"
        agent_dir.mkdir(parents=True)
        (agent_dir / MANIFEST_FILENAME).write_text("{bad json!!!")
        assert list_installed(agents_dir) == []

    def test_list_multiple_agents(self, tmp_path):
        agents_dir = tmp_path / "agents"
        for name in ["alpha", "beta", "gamma"]:
            agent_dir = agents_dir / name
            agent_dir.mkdir(parents=True)
            manifest = {"manifest_version": 2, "name": name, "version": "1.0.0"}
            (agent_dir / MANIFEST_FILENAME).write_text(json.dumps(manifest))
        agents = list_installed(agents_dir)
        assert len(agents) == 3
        names = [a["name"] for a in agents]
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names


class TestGetInstalled:

    def test_get_found(self, sample_agnt_file, tmp_path):
        agents_dir = tmp_path / "agents"
        install(sample_agnt_file, agents_dir=agents_dir)
        agent = get_installed("test-agent", agents_dir)
        assert agent is not None
        assert agent["name"] == "test-agent"

    def test_get_not_found(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        assert get_installed("nope", agents_dir) is None
