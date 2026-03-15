"""Tests for LogWriter — per-step JSONL log persistence."""

import json
import pytest

from api.services.log_writer import LogWriter


@pytest.fixture
def log_writer(tmp_path):
    return LogWriter(base_dir=tmp_path)


class TestAppendRunEvent:

    def test_creates_execution_jsonl(self, log_writer, tmp_path):
        event = {"type": "run_started", "data": {}, "timestamp": "2026-03-15T18:00:00Z"}
        rel_path = log_writer.append_run_event("run-1", event)

        assert rel_path == "output/run-1/agent_logs"
        path = tmp_path / "output" / "run-1" / "agent_logs" / "execution.jsonl"
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0]) == event

    def test_appends_multiple_run_events(self, log_writer, tmp_path):
        e1 = {"type": "run_started", "data": {}, "timestamp": "2026-03-15T18:00:00Z"}
        e2 = {"type": "run_completed", "data": {"outputs": {}}, "timestamp": "2026-03-15T18:05:00Z"}
        log_writer.append_run_event("run-1", e1)
        log_writer.append_run_event("run-1", e2)

        path = tmp_path / "output" / "run-1" / "agent_logs" / "execution.jsonl"
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "run_started"
        assert json.loads(lines[1])["type"] == "run_completed"


class TestAppendStepEvent:

    def test_creates_step_file(self, log_writer, tmp_path):
        event = {"type": "agent_started", "data": {"name": "Analyze"}, "timestamp": "2026-03-15T18:01:00Z"}
        log_writer.append_step_event("run-1", 1, "Analyze Dependencies", event)

        path = tmp_path / "output" / "run-1" / "agent_logs" / "step_01_analyze-dependencies.jsonl"
        assert path.exists()
        parsed = json.loads(path.read_text().strip())
        assert parsed["type"] == "agent_started"

    def test_appends_multiple_events_to_same_step(self, log_writer, tmp_path):
        events = [
            {"type": "agent_started", "data": {}, "timestamp": "2026-03-15T18:01:00Z"},
            {"type": "agent_log", "data": {"message": "Working..."}, "timestamp": "2026-03-15T18:01:05Z"},
            {"type": "agent_completed", "data": {}, "timestamp": "2026-03-15T18:02:00Z"},
        ]
        for e in events:
            log_writer.append_step_event("run-1", 2, "Review Code", e)

        path = tmp_path / "output" / "run-1" / "agent_logs" / "step_02_review-code.jsonl"
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_sanitizes_step_name(self, log_writer, tmp_path):
        event = {"type": "agent_started", "data": {}, "timestamp": "2026-03-15T18:01:00Z"}
        log_writer.append_step_event("run-1", 3, "Create PR & Push", event)

        path = tmp_path / "output" / "run-1" / "agent_logs" / "step_03_create-pr-&-push.jsonl"
        assert path.exists()


class TestReadLogs:

    def test_read_run_log(self, log_writer):
        e1 = {"type": "run_started", "data": {}, "timestamp": "2026-03-15T18:00:00Z"}
        e2 = {"type": "run_completed", "data": {}, "timestamp": "2026-03-15T18:05:00Z"}
        log_writer.append_run_event("run-1", e1)
        log_writer.append_run_event("run-1", e2)

        events = log_writer.read_run_log("run-1")
        assert len(events) == 2
        assert events[0]["type"] == "run_started"
        assert events[1]["type"] == "run_completed"

    def test_read_step_log(self, log_writer):
        event = {"type": "agent_log", "data": {"message": "hi"}, "timestamp": "2026-03-15T18:01:00Z"}
        log_writer.append_step_event("run-1", 1, "Analyze", event)

        events = log_writer.read_step_log("run-1", "step_01_analyze.jsonl")
        assert len(events) == 1
        assert events[0]["data"]["message"] == "hi"

    def test_read_returns_empty_for_missing_run(self, log_writer):
        assert log_writer.read_run_log("nonexistent") == []

    def test_read_step_returns_empty_for_missing_file(self, log_writer):
        assert log_writer.read_step_log("run-1", "step_99_nope.jsonl") == []


class TestListStepLogs:

    def test_lists_step_files(self, log_writer):
        e = {"type": "agent_log", "data": {}, "timestamp": "2026-03-15T18:01:00Z"}
        log_writer.append_step_event("run-1", 1, "Analyze", e)
        log_writer.append_step_event("run-1", 2, "Review", e)
        log_writer.append_run_event("run-1", e)  # execution.jsonl should not be listed

        step_files = log_writer.list_step_logs("run-1")
        assert "step_01_analyze.jsonl" in step_files
        assert "step_02_review.jsonl" in step_files
        assert "execution.jsonl" not in step_files

    def test_list_returns_empty_for_missing_run(self, log_writer):
        assert log_writer.list_step_logs("nonexistent") == []
