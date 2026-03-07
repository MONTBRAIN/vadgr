"""Tests for WebSocket events."""

import pytest

from api.websocket.events import make_event


class TestEvents:

    def test_make_event_structure(self):
        event = make_event("task_started", {"node": "A"})
        assert event["type"] == "task_started"
        assert event["data"] == {"node": "A"}
        assert "timestamp" in event

    def test_make_event_empty_data(self):
        event = make_event("run_started")
        assert event["data"] == {}

    def test_all_event_types_are_valid_strings(self):
        valid_types = [
            "run_started", "task_started", "task_progress",
            "task_completed", "task_failed", "approval_required",
            "approval_response", "screenshot", "action_executed",
            "run_completed", "run_failed",
        ]
        for t in valid_types:
            event = make_event(t)
            assert event["type"] == t
