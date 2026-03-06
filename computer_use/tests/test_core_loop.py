"""Tests for the autonomous execution loop."""

from unittest.mock import MagicMock, patch

from computer_use.core.types import Action, ActionType, Element, Region, ScreenState
from computer_use.providers.base import AgentDecision
from computer_use.core.loop import run_core_loop, MAX_CONSECUTIVE_FAILURES


def _make_screen():
    return ScreenState(image_bytes=b"fake", width=1920, height=1080)


def _make_decision(action_type=ActionType.CLICK, complete=False, confidence=0.9):
    return AgentDecision(
        action=Action(action_type=action_type, x=500, y=300),
        reasoning="clicking the button",
        is_task_complete=complete,
        confidence=confidence,
    )


def _make_mocks():
    capture = MagicMock()
    capture.capture_full.return_value = _make_screen()
    executor = MagicMock()
    provider = MagicMock()
    return capture, executor, provider


@patch("computer_use.core.loop.time.sleep")
class TestTaskCompletion:
    def test_stops_when_task_marked_complete(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision(complete=True)

        results = run_core_loop(capture, executor, None, provider, "do stuff", max_steps=10)

        assert len(results) == 1
        assert results[0].success is True
        executor.execute_action.assert_not_called()

    def test_runs_up_to_max_steps(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision()
        provider.verify_action.return_value = (True, "ok")

        results = run_core_loop(capture, executor, None, provider, "do stuff", max_steps=3)

        assert len(results) == 3
        assert executor.execute_action.call_count == 3


@patch("computer_use.core.loop.time.sleep")
class TestActionExecution:
    def test_executes_decided_action(self, _sleep):
        capture, executor, provider = _make_mocks()
        decision = _make_decision(ActionType.TYPE_TEXT)
        provider.decide_action.return_value = decision
        provider.verify_action.return_value = (True, "ok")

        results = run_core_loop(capture, executor, None, provider, "type hello", max_steps=1)

        executor.execute_action.assert_called_once_with(decision.action)
        assert results[0].success is True

    def test_records_action_failure(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision()
        executor.execute_action.side_effect = Exception("click failed")

        results = run_core_loop(capture, executor, None, provider, "click it", max_steps=1)

        assert len(results) == 1
        assert results[0].success is False
        assert "click failed" in results[0].error


@patch("computer_use.core.loop.time.sleep")
class TestConsecutiveFailures:
    def test_aborts_after_max_consecutive_action_failures(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision()
        executor.execute_action.side_effect = Exception("boom")

        results = run_core_loop(capture, executor, None, provider, "task", max_steps=10)

        assert len(results) == MAX_CONSECUTIVE_FAILURES

    def test_aborts_after_max_consecutive_provider_failures(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.side_effect = Exception("api down")

        results = run_core_loop(capture, executor, None, provider, "task", max_steps=10)

        assert len(results) == 0
        assert provider.decide_action.call_count == MAX_CONSECUTIVE_FAILURES

    def test_resets_failure_counter_on_success(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.verify_action.return_value = (True, "ok")

        fail_decision = _make_decision()
        ok_decision = _make_decision()
        complete_decision = _make_decision(complete=True)

        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("temporary fail")
            if call_count == 3:
                return ok_decision
            return complete_decision

        provider.decide_action.side_effect = side_effect

        results = run_core_loop(capture, executor, None, provider, "task", max_steps=10)

        assert any(r.success for r in results)


@patch("computer_use.core.loop.time.sleep")
class TestVerification:
    def test_verification_failure_marks_step_unsuccessful(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision()
        provider.verify_action.return_value = (False, "nothing changed")

        results = run_core_loop(
            capture, executor, None, provider, "task", max_steps=1, verify=True
        )

        assert results[0].success is False
        assert "nothing changed" in results[0].error

    def test_skips_verification_when_disabled(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision()

        results = run_core_loop(
            capture, executor, None, provider, "task", max_steps=1, verify=False
        )

        provider.verify_action.assert_not_called()
        assert results[0].success is True

    def test_verification_exception_assumes_success(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision()
        provider.verify_action.side_effect = Exception("timeout")

        results = run_core_loop(
            capture, executor, None, provider, "task", max_steps=1, verify=True
        )

        assert results[0].success is True


@patch("computer_use.core.loop.time.sleep")
class TestGrounding:
    def test_passes_elements_to_provider(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision(complete=True)

        locator = MagicMock()
        locator.is_available.return_value = True
        elements = [
            Element(name="OK", role="button", region=Region(x=10, y=20, width=50, height=25),
                    confidence=0.95, source="accessibility")
        ]
        locator.find_all_elements.return_value = elements

        run_core_loop(capture, executor, locator, provider, "task", max_steps=1)

        call_kwargs = provider.decide_action.call_args
        assert call_kwargs.kwargs.get("elements") == elements or call_kwargs[1].get("elements") == elements

    def test_continues_without_elements_on_grounding_error(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.decide_action.return_value = _make_decision(complete=True)

        locator = MagicMock()
        locator.is_available.return_value = True
        locator.find_all_elements.side_effect = Exception("atspi crash")

        results = run_core_loop(capture, executor, locator, provider, "task", max_steps=1)

        assert len(results) == 1


@patch("computer_use.core.loop.time.sleep")
class TestHistory:
    def test_builds_history_across_steps(self, _sleep):
        capture, executor, provider = _make_mocks()
        provider.verify_action.return_value = (True, "ok")

        call_num = 0
        def decide(*args, **kwargs):
            nonlocal call_num
            call_num += 1
            if call_num >= 3:
                return _make_decision(complete=True)
            return _make_decision()

        provider.decide_action.side_effect = decide

        results = run_core_loop(capture, executor, None, provider, "task", max_steps=5)

        # The third call (complete) should have history from the first two steps
        assert provider.decide_action.call_count == 3
        # History is a mutable list passed by reference, so we check the final state
        last_call = provider.decide_action.call_args_list[2]
        history_arg = last_call.kwargs.get("history") or last_call[1].get("history")
        assert len(history_arg) == 2
        assert history_arg[0]["step"] == 1
        assert history_arg[1]["step"] == 2
