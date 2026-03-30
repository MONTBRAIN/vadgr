"""Tests for step result JSON reading in the executor."""

import json
from pathlib import Path

import pytest


class TestReadStepResult:
    def test_reads_completed_result(self, tmp_path):
        from api.engine.executor import _read_step_result

        result_file = tmp_path / "step_01_result.json"
        result_file.write_text(json.dumps({"status": "completed", "summary": "Done"}))

        result = _read_step_result(str(tmp_path), 1)
        assert result["status"] == "completed"
        assert result["summary"] == "Done"

    def test_reads_failed_result(self, tmp_path):
        from api.engine.executor import _read_step_result

        result_file = tmp_path / "step_02_result.json"
        result_file.write_text(json.dumps({"status": "failed", "error": "No tools available"}))

        result = _read_step_result(str(tmp_path), 2)
        assert result["status"] == "failed"
        assert "No tools" in result["error"]

    def test_missing_file_returns_completed(self, tmp_path):
        from api.engine.executor import _read_step_result

        result = _read_step_result(str(tmp_path), 1)
        assert result["status"] == "completed"

    def test_invalid_json_returns_completed(self, tmp_path):
        from api.engine.executor import _read_step_result

        result_file = tmp_path / "step_01_result.json"
        result_file.write_text("not json")

        result = _read_step_result(str(tmp_path), 1)
        assert result["status"] == "completed"

    def test_missing_status_field_returns_completed(self, tmp_path):
        from api.engine.executor import _read_step_result

        result_file = tmp_path / "step_01_result.json"
        result_file.write_text(json.dumps({"summary": "no status here"}))

        result = _read_step_result(str(tmp_path), 1)
        assert result["status"] == "completed"
