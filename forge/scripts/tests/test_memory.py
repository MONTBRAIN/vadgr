"""Tests for forge persistent memory utility."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from forge.scripts.src.memory import (
    read_memory,
    write_memory,
    list_memories,
    clear_memory,
    repo_key,
    MEMORY_DIR,
)


@pytest.fixture
def memory_dir(tmp_path, monkeypatch):
    """Use a temp directory instead of ~/.forge/memory/."""
    mem = tmp_path / "memory"
    monkeypatch.setattr("forge.scripts.src.memory.MEMORY_DIR", mem)
    return mem


class TestWriteMemory:

    def test_creates_file_with_frontmatter(self, memory_dir):
        path = write_memory("test-agent", content="- fact one\n- fact two")
        assert path.exists()
        text = path.read_text()
        assert "---" in text
        assert "agent: test-agent" in text
        assert "key: global" in text
        assert "- fact one" in text

    def test_creates_agent_directory(self, memory_dir):
        write_memory("new-agent", content="hello")
        assert (memory_dir / "new-agent").is_dir()

    def test_custom_key(self, memory_dir):
        write_memory("my-agent", key="repo-myapp", content="stack: python")
        path = memory_dir / "my-agent" / "repo-myapp.md"
        assert path.exists()
        assert "key: repo-myapp" in path.read_text()

    def test_overwrites_existing(self, memory_dir):
        write_memory("agent", content="old stuff")
        write_memory("agent", content="new stuff")
        text = (memory_dir / "agent" / "global.md").read_text()
        assert "new stuff" in text
        assert "old stuff" not in text

    def test_max_lines_truncates(self, memory_dir):
        long_content = "\n".join(f"- line {i}" for i in range(100))
        write_memory("agent", content=long_content, max_lines=10)
        text = (memory_dir / "agent" / "global.md").read_text()
        # Frontmatter + content: content lines should be <= 10
        body_lines = text.split("---")[-1].strip().splitlines()
        assert len(body_lines) <= 10

    def test_returns_path(self, memory_dir):
        result = write_memory("agent", content="test")
        assert isinstance(result, Path)
        assert result.name == "global.md"


class TestReadMemory:

    def test_reads_content_without_frontmatter(self, memory_dir):
        write_memory("agent", content="- pytest\n- vitest")
        result = read_memory("agent")
        assert "- pytest" in result
        assert "- vitest" in result
        assert "---" not in result
        assert "agent:" not in result

    def test_returns_none_when_missing(self, memory_dir):
        assert read_memory("nonexistent") is None

    def test_reads_custom_key(self, memory_dir):
        write_memory("agent", key="cua-hints", content="# VS Code\n- terminal")
        result = read_memory("agent", key="cua-hints")
        assert "VS Code" in result
        assert "terminal" in result

    def test_returns_none_for_missing_key(self, memory_dir):
        write_memory("agent", content="global stuff")
        assert read_memory("agent", key="nonexistent") is None


class TestListMemories:

    def test_lists_all_keys(self, memory_dir):
        write_memory("agent", content="global")
        write_memory("agent", key="repo-app", content="app info")
        write_memory("agent", key="cua-hints", content="hints")
        result = list_memories("agent")
        keys = [m["key"] for m in result]
        assert "global" in keys
        assert "repo-app" in keys
        assert "cua-hints" in keys

    def test_returns_frontmatter_metadata(self, memory_dir):
        write_memory("agent", content="test")
        result = list_memories("agent")
        assert len(result) == 1
        assert result[0]["agent"] == "agent"
        assert result[0]["key"] == "global"
        assert "updated" in result[0]

    def test_empty_for_unknown_agent(self, memory_dir):
        assert list_memories("nope") == []


class TestClearMemory:

    def test_clears_one_key(self, memory_dir):
        write_memory("agent", content="global")
        write_memory("agent", key="extra", content="extra")
        count = clear_memory("agent", key="extra")
        assert count == 1
        assert read_memory("agent") is not None
        assert read_memory("agent", key="extra") is None

    def test_clears_all(self, memory_dir):
        write_memory("agent", content="global")
        write_memory("agent", key="extra", content="extra")
        count = clear_memory("agent")
        assert count == 2
        assert read_memory("agent") is None
        assert read_memory("agent", key="extra") is None

    def test_returns_zero_for_unknown(self, memory_dir):
        assert clear_memory("nope") == 0


class TestRepoKey:

    def test_converts_path_to_key(self):
        assert repo_key("/home/user/my-app") == "repo-home-user-my-app"

    def test_handles_home_shortcut(self):
        result = repo_key("~/projects/cool-app")
        assert "repo-" in result
        assert "/" not in result

    def test_handles_windows_path(self):
        result = repo_key("C:\\Users\\me\\project")
        assert "/" not in result
        assert "\\" not in result
        assert "repo-" in result


class TestForgeHomeEnvVar:

    def test_memory_dir_respects_forge_home_env(self, tmp_path, monkeypatch):
        """MEMORY_DIR should derive from FORGE_HOME env var when set."""
        custom_home = tmp_path / "custom-forge"
        monkeypatch.setenv("FORGE_HOME", str(custom_home))
        import importlib
        import forge.scripts.src.memory as mem_mod
        importlib.reload(mem_mod)
        try:
            assert mem_mod.MEMORY_DIR == custom_home / "memory"
        finally:
            monkeypatch.delenv("FORGE_HOME", raising=False)
            importlib.reload(mem_mod)

    def test_memory_dir_defaults_to_dot_forge(self, monkeypatch):
        """Without FORGE_HOME, MEMORY_DIR should default to ~/.forge/memory."""
        monkeypatch.delenv("FORGE_HOME", raising=False)
        import importlib
        import forge.scripts.src.memory as mem_mod
        importlib.reload(mem_mod)
        assert mem_mod.MEMORY_DIR == Path.home() / ".forge" / "memory"
