"""Tests for manifest schema and validation."""

import json
import pytest
from pathlib import Path

from registry.manifest import (
    Manifest,
    StepEntry,
    validate_manifest,
    load_manifest,
    write_manifest,
    MANIFEST_VERSION,
)


class TestManifestValidation:

    def test_valid_manifest(self, sample_manifest_data):
        m = validate_manifest(sample_manifest_data)
        assert m.name == "test-agent"
        assert m.version == "0.1.0"
        assert m.manifest_version == MANIFEST_VERSION
        assert m.export_version == 2
        assert len(m.steps) == 2

    def test_minimal_manifest(self):
        m = validate_manifest({"manifest_version": 1, "name": "my-agent"})
        assert m.name == "my-agent"
        assert m.version == "0.1.0"  # default
        assert m.description == ""
        assert m.steps == []

    def test_v2_manifest_has_api_fields(self):
        m = validate_manifest({
            "manifest_version": 2, "name": "new-agent",
            "samples": ["example"], "input_schema": [{"name": "x"}],
        })
        assert m.samples == ["example"]
        assert m.input_schema == [{"name": "x"}]
        assert m.model == "claude-sonnet-4-6"

    def test_missing_name_raises(self):
        with pytest.raises(ValueError, match="Invalid manifest"):
            validate_manifest({"manifest_version": 1})

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="Invalid manifest"):
            validate_manifest({"manifest_version": 1, "name": ""})

    def test_invalid_name_chars_raises(self):
        with pytest.raises(ValueError, match="kebab-case"):
            validate_manifest({"manifest_version": 1, "name": "My Agent!"})

    def test_name_normalized_to_lowercase(self):
        m = validate_manifest({"manifest_version": 1, "name": "My-Agent"})
        assert m.name == "my-agent"

    def test_unsupported_manifest_version_raises(self):
        with pytest.raises(ValueError, match="Unsupported manifest version"):
            validate_manifest({"manifest_version": 99, "name": "test"})

    def test_extra_fields_ignored(self):
        data = {"manifest_version": 1, "name": "test", "unknown_field": "hi"}
        m = validate_manifest(data)
        assert m.name == "test"

    def test_steps_parsed(self, sample_manifest_data):
        m = validate_manifest(sample_manifest_data)
        assert m.steps[0].name == "Gather Data"
        assert m.steps[0].computer_use is False
        assert m.steps[1].name == "Analyze Results"
        assert m.steps[1].computer_use is True

    def test_computer_use_default_false(self):
        m = validate_manifest({"manifest_version": 1, "name": "test"})
        assert m.computer_use is False


class TestManifestIO:

    def test_load_manifest(self, tmp_path, sample_manifest_data):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(sample_manifest_data))
        m = load_manifest(path)
        assert m.name == "test-agent"

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "nope.json")

    def test_load_invalid_json_raises(self, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text("{bad json!!!")
        with pytest.raises(json.JSONDecodeError):
            load_manifest(path)

    def test_write_and_read_roundtrip(self, tmp_path, sample_manifest_data):
        m = validate_manifest(sample_manifest_data)
        path = tmp_path / "out" / "manifest.json"
        write_manifest(m, path)
        assert path.exists()
        m2 = load_manifest(path)
        assert m2.name == m.name
        assert m2.version == m.version
        assert len(m2.steps) == len(m.steps)
