"""Tests for the autonomous execution loop with mocked dependencies."""

from unittest.mock import MagicMock

from computer_use.core.loop import run_core_loop
from computer_use.core.types import Action, ActionType, ScreenState
from computer_use.providers.base import AgentDecision


def _make_screen():
    return ScreenState(image_bytes=b"\x89PNG", width=1920, height=1080)


class TestCoreLoop:
    def test_completes_when_llm_says_done(self):
        capture = MagicMock()
        capture.capture_full.return_value = _make_screen()

        executor = MagicMock()
        locator = MagicMock()
        locator.is_available.return_value = False

        provider = MagicMock()
        provider.decide_action.return_value = AgentDecision(
            action=Action(action_type=ActionType.WAIT, duration=0),
            reasoning="Task is complete",
            is_task_complete=True,
            confidence=1.0,
        )

        results = run_core_loop(
            capture=capture,
            executor=executor,
            locator=locator,
            provider=provider,
            task="Test task",
            max_steps=10,
            verify=False,
        )

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].reasoning == "Task is complete"
        # Should NOT have called executor (task was complete on first check)
        executor.execute_action.assert_not_called()

    def test_executes_actions_until_done(self):
        capture = MagicMock()
        capture.capture_full.return_value = _make_screen()

        executor = MagicMock()
        locator = MagicMock()
        locator.is_available.return_value = False

        # First call: click, second call: done
        provider = MagicMock()
        provider.decide_action.side_effect = [
            AgentDecision(
                action=Action(action_type=ActionType.CLICK, x=100, y=200),
                reasoning="Clicking start button",
                is_task_complete=False,
                confidence=0.9,
            ),
            AgentDecision(
                action=Action(action_type=ActionType.WAIT, duration=0),
                reasoning="Done",
                is_task_complete=True,
                confidence=1.0,
            ),
        ]

        results = run_core_loop(
            capture=capture,
            executor=executor,
            locator=locator,
            provider=provider,
            task="Click start",
            max_steps=10,
            verify=False,
        )

        assert len(results) == 2
        assert results[0].action_taken.action_type == ActionType.CLICK
        assert results[1].success is True
        executor.execute_action.assert_called_once()

    def test_stops_at_max_steps(self):
        capture = MagicMock()
        capture.capture_full.return_value = _make_screen()

        executor = MagicMock()
        locator = MagicMock()
        locator.is_available.return_value = False

        # Always returns a click, never completes
        provider = MagicMock()
        provider.decide_action.return_value = AgentDecision(
            action=Action(action_type=ActionType.CLICK, x=50, y=50),
            reasoning="Still working",
            is_task_complete=False,
            confidence=0.5,
        )

        results = run_core_loop(
            capture=capture,
            executor=executor,
            locator=locator,
            provider=provider,
            task="Never-ending task",
            max_steps=3,
            verify=False,
        )

        assert len(results) == 3

    def test_stops_after_consecutive_failures(self):
        capture = MagicMock()
        capture.capture_full.return_value = _make_screen()

        executor = MagicMock()
        executor.execute_action.side_effect = RuntimeError("Action failed")

        locator = MagicMock()
        locator.is_available.return_value = False

        provider = MagicMock()
        provider.decide_action.return_value = AgentDecision(
            action=Action(action_type=ActionType.CLICK, x=50, y=50),
            reasoning="Trying to click",
            is_task_complete=False,
            confidence=0.5,
        )

        results = run_core_loop(
            capture=capture,
            executor=executor,
            locator=locator,
            provider=provider,
            task="Failing task",
            max_steps=10,
            verify=False,
        )

        # Should stop after 3 consecutive failures (MAX_CONSECUTIVE_FAILURES)
        assert len(results) == 3
        assert all(not r.success for r in results)

    def test_verification_calls_provider(self):
        capture = MagicMock()
        capture.capture_full.return_value = _make_screen()

        executor = MagicMock()
        locator = MagicMock()
        locator.is_available.return_value = False

        provider = MagicMock()
        provider.decide_action.side_effect = [
            AgentDecision(
                action=Action(action_type=ActionType.CLICK, x=100, y=200),
                reasoning="Click a button",
                is_task_complete=False,
                confidence=0.9,
            ),
            AgentDecision(
                action=Action(action_type=ActionType.WAIT, duration=0),
                reasoning="Done",
                is_task_complete=True,
                confidence=1.0,
            ),
        ]
        provider.verify_action.return_value = (True, "Button was clicked")

        results = run_core_loop(
            capture=capture,
            executor=executor,
            locator=locator,
            provider=provider,
            task="Click button",
            max_steps=10,
            verify=True,
        )

        assert len(results) == 2
        provider.verify_action.assert_called_once()
        assert results[0].success is True
