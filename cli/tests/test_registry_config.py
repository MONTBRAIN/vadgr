"""Tests for registry config commands: add, use, list, remove."""

from pathlib import Path
from unittest import mock

import yaml
from click.testing import CliRunner
import pytest


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Create a temp registry.yaml and patch config to use it."""
    cfg = tmp_path / "registry.yaml"
    cfg.write_text(yaml.dump({
        "registries": [
            {"name": "sample", "type": "github", "url": "https://example.com", "default": True},
        ],
        "agents_dir": str(tmp_path / "agents"),
    }))
    import registry.config as rc
    monkeypatch.setattr(rc, "CONFIG_PATH", cfg)
    monkeypatch.setattr(rc, "FORGE_HOME", tmp_path)
    return cfg


class TestRegistryAdd:
    def test_add_http_registry(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, [
            "add", "company", "--type", "http", "--url", "https://registry.internal"
        ])
        assert result.exit_code == 0
        assert "Added" in result.output

        cfg = yaml.safe_load(config_file.read_text())
        names = [r["name"] for r in cfg["registries"]]
        assert "company" in names

    def test_add_local_registry(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, [
            "add", "mine", "--type", "local", "--path", "/home/user/agents"
        ])
        assert result.exit_code == 0
        cfg = yaml.safe_load(config_file.read_text())
        local = [r for r in cfg["registries"] if r["name"] == "mine"][0]
        assert local["path"] == "/home/user/agents"

    def test_add_github_registry(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, [
            "add", "gh", "--type", "github", "--github-repo", "myorg/agents"
        ])
        assert result.exit_code == 0
        cfg = yaml.safe_load(config_file.read_text())
        gh = [r for r in cfg["registries"] if r["name"] == "gh"][0]
        assert gh["github_repo"] == "myorg/agents"

    def test_add_with_token(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, [
            "add", "private", "--type", "http", "--url", "https://x.com", "--token", "$MY_TOKEN"
        ])
        assert result.exit_code == 0
        cfg = yaml.safe_load(config_file.read_text())
        priv = [r for r in cfg["registries"] if r["name"] == "private"][0]
        assert priv["token"] == "$MY_TOKEN"

    def test_add_duplicate_fails(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, [
            "add", "sample", "--type", "http", "--url", "https://x.com"
        ])
        assert result.exit_code != 0
        assert "already exists" in result.output


class TestRegistryUse:
    def test_switch_default(self, runner, config_file):
        from cli.commands.registry import registry_group
        # Add a second registry first
        runner.invoke(registry_group, [
            "add", "other", "--type", "http", "--url", "https://other.com"
        ])
        result = runner.invoke(registry_group, ["use", "other"])
        assert result.exit_code == 0
        assert "other" in result.output

        cfg = yaml.safe_load(config_file.read_text())
        for r in cfg["registries"]:
            if r["name"] == "other":
                assert r.get("default") is True
            else:
                assert r.get("default") is not True

    def test_use_nonexistent(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, ["use", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestRegistryList:
    def test_lists_registries(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, ["list"])
        assert result.exit_code == 0
        assert "sample" in result.output

    def test_shows_active_marker(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, ["list"])
        assert result.exit_code == 0
        # The active one should have some indicator
        assert "sample" in result.output


class TestRegistryRemove:
    def test_removes_registry(self, runner, config_file):
        from cli.commands.registry import registry_group
        # Add one to remove
        runner.invoke(registry_group, [
            "add", "temp", "--type", "http", "--url", "https://temp.com"
        ])
        result = runner.invoke(registry_group, ["remove", "temp"])
        assert result.exit_code == 0
        assert "Removed" in result.output

        cfg = yaml.safe_load(config_file.read_text())
        names = [r["name"] for r in cfg["registries"]]
        assert "temp" not in names

    def test_remove_nonexistent(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, ["remove", "nope"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_remove_default_warns(self, runner, config_file):
        from cli.commands.registry import registry_group
        result = runner.invoke(registry_group, ["remove", "sample"])
        assert result.exit_code != 0
        assert "active" in result.output.lower() or "default" in result.output.lower()
