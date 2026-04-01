"""Tests for packing and unpacking .agnt archives."""

import json
import zipfile
import pytest
from pathlib import Path

from registry.manifest import MANIFEST_FILENAME
from registry.packer import (
    pack,
    unpack,
    build_manifest,
    collect_files,
    _detect_steps,
    _detect_name,
    _should_exclude,
)


class TestShouldExclude:

    def test_excludes_git(self):
        assert _should_exclude(Path(".git/config")) is True

    def test_excludes_venv(self):
        assert _should_exclude(Path(".venv/bin/python")) is True

    def test_excludes_pycache(self):
        assert _should_exclude(Path("agent/__pycache__/foo.pyc")) is True

    def test_excludes_node_modules(self):
        assert _should_exclude(Path("node_modules/foo/index.js")) is True

    def test_excludes_output(self):
        assert _should_exclude(Path("output/run-1/logs.json")) is True

    def test_includes_normal_files(self):
        assert _should_exclude(Path("agentic.md")) is False
        assert _should_exclude(Path("agent/steps/step_01_test.md")) is False


class TestDetectSteps:

    def test_detects_steps_from_filenames(self, sample_agent_folder):
        steps = _detect_steps(sample_agent_folder)
        assert len(steps) == 2
        assert steps[0].name == "Gather Data"
        assert steps[0].computer_use is False
        assert steps[1].name == "Analyze Results"
        assert steps[1].computer_use is True

    def test_no_steps_dir(self, tmp_path):
        folder = tmp_path / "no-steps"
        folder.mkdir()
        assert _detect_steps(folder) == []

    def test_ignores_non_step_files(self, tmp_path):
        folder = tmp_path / "agent-with-extras"
        steps_dir = folder / "agent" / "steps"
        steps_dir.mkdir(parents=True)
        (steps_dir / "step_01_real-step.md").write_text("# Real\n")
        (steps_dir / "README.md").write_text("# Not a step\n")
        (steps_dir / ".gitkeep").write_text("")
        steps = _detect_steps(folder)
        assert len(steps) == 1
        assert steps[0].name == "Real Step"


class TestDetectName:

    def test_name_from_agentic_title(self, tmp_path):
        folder = tmp_path / "my-folder"
        folder.mkdir()
        (folder / "agentic.md").write_text("# Research Paper Generator\n")
        assert _detect_name(folder) == "research-paper-generator"

    def test_name_from_folder_name(self, tmp_path):
        folder = tmp_path / "cool-agent"
        folder.mkdir()
        (folder / "agentic.md").write_text("Some content without a title\n")
        assert _detect_name(folder) == "cool-agent"

    def test_name_sanitized(self, tmp_path):
        folder = tmp_path / "My Cool Agent!!!"
        folder.mkdir()
        (folder / "agentic.md").write_text("No title\n")
        name = _detect_name(folder)
        assert all(c.isalnum() or c == "-" for c in name)


class TestBuildManifest:

    def test_auto_detects_metadata(self, sample_agent_folder):
        m = build_manifest(sample_agent_folder)
        assert m.name == "test-agent"
        assert len(m.steps) == 2
        assert m.computer_use is True  # step 2 has computer_use

    def test_existing_manifest_merged(self, sample_agent_folder):
        manifest_path = sample_agent_folder / MANIFEST_FILENAME
        manifest_path.write_text(json.dumps({
            "manifest_version": 2,
            "name": "custom-name",
            "author": "santiago",
        }))
        m = build_manifest(sample_agent_folder)
        assert m.name == "custom-name"
        assert m.author == "santiago"
        assert len(m.steps) == 2  # still auto-detected

    def test_overrides_win(self, sample_agent_folder):
        m = build_manifest(sample_agent_folder, overrides={"name": "override-name"})
        assert m.name == "override-name"

    def test_reads_schema_json(self, sample_agent_folder):
        """build_manifest should include input/output schemas from schema.json."""
        schema = {
            "input_schema": [
                {"name": "cv_file", "type": "file", "required": True}
            ],
            "output_schema": [
                {"name": "report", "type": "file"}
            ],
            "samples": ["example input"],
        }
        (sample_agent_folder / "schema.json").write_text(json.dumps(schema))
        m = build_manifest(sample_agent_folder)
        assert len(m.input_schema) == 1
        assert m.input_schema[0]["name"] == "cv_file"
        assert len(m.output_schema) == 1
        assert m.samples == ["example input"]


class TestCollectFiles:

    def test_collects_agent_files(self, sample_agent_folder):
        files = collect_files(sample_agent_folder)
        names = [str(f) for f in files]
        assert "agentic.md" in names
        assert "CLAUDE.md" in names
        assert any("step_01" in n for n in names)

    def test_excludes_git_and_venv(self, sample_agent_folder):
        # Create excluded dirs
        (sample_agent_folder / ".git").mkdir()
        (sample_agent_folder / ".git" / "config").write_text("x")
        (sample_agent_folder / ".venv").mkdir()
        (sample_agent_folder / ".venv" / "bin" / "python").mkdir(parents=True)

        files = collect_files(sample_agent_folder)
        names = [str(f) for f in files]
        assert not any(".git" in n for n in names)
        assert not any(".venv" in n for n in names)


class TestPack:

    def test_pack_creates_agnt_file(self, sample_agent_folder, tmp_path):
        output = tmp_path / "out.agnt"
        result = pack(sample_agent_folder, output=output)
        assert result == output
        assert output.exists()
        assert zipfile.is_zipfile(output)

    def test_pack_contains_manifest_and_bundle(self, sample_agent_folder, tmp_path):
        output = pack(sample_agent_folder, output=tmp_path / "test.agnt")
        with zipfile.ZipFile(output) as zf:
            names = zf.namelist()
            assert MANIFEST_FILENAME in names
            assert "agent.bundle" in names
            data = json.loads(zf.read(MANIFEST_FILENAME))
            assert data["name"] == "test-agent"
            assert data["export_version"] == 2

    def test_pack_default_output_name(self, sample_agent_folder):
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(sample_agent_folder.parent)
            result = pack(sample_agent_folder)
            assert result.name == "test-agent-0.1.0.agnt"
            assert result.exists()
        finally:
            os.chdir(old_cwd)
            # cleanup
            (sample_agent_folder.parent / "test-agent-0.1.0.agnt").unlink(missing_ok=True)

    def test_pack_missing_folder_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            pack(tmp_path / "nonexistent")

    def test_pack_missing_agentic_raises(self, tmp_path):
        folder = tmp_path / "bad-agent"
        folder.mkdir()
        with pytest.raises(FileNotFoundError, match="agentic.md"):
            pack(folder)

    def test_pack_excludes_output_dir(self, sample_agent_folder, tmp_path):
        output_dir = sample_agent_folder / "output" / "run-1"
        output_dir.mkdir(parents=True)
        (output_dir / "logs.json").write_text("{}")

        result = pack(sample_agent_folder, output=tmp_path / "test.agnt")
        # Unpack and verify the excluded dir is not in the bundle
        dest = tmp_path / "verify"
        unpack(result, dest)
        assert not (dest / "output").exists()


class TestUnpack:

    def test_unpack_extracts_files(self, sample_agnt_file, tmp_path):
        dest = tmp_path / "unpacked"
        manifest = unpack(sample_agnt_file, dest)
        assert manifest.name == "test-agent"
        assert (dest / MANIFEST_FILENAME).exists()
        assert (dest / "agentic.md").exists()

    def test_unpack_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            unpack(tmp_path / "nope.agnt", tmp_path / "out")

    def test_unpack_invalid_zip_raises(self, tmp_path):
        bad = tmp_path / "bad.agnt"
        bad.write_text("not a zip")
        with pytest.raises(Exception):
            unpack(bad, tmp_path / "out")

    def test_unpack_missing_manifest_raises(self, tmp_path):
        agnt = tmp_path / "no-manifest.agnt"
        with zipfile.ZipFile(agnt, "w") as zf:
            zf.writestr("agentic.md", "# Test\n")
        with pytest.raises(ValueError, match="missing agent-forge.json"):
            unpack(agnt, tmp_path / "out")

    def test_pack_then_unpack_roundtrip(self, sample_agent_folder, tmp_path):
        agnt = pack(sample_agent_folder, output=tmp_path / "roundtrip.agnt")
        dest = tmp_path / "unpacked"
        manifest = unpack(agnt, dest)
        assert manifest.name == "test-agent"
        assert (dest / "agentic.md").exists()
        assert (dest / "agent" / "steps" / "step_01_gather-data.md").exists()
