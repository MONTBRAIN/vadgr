"""Tests for action execution routing."""

import time
from unittest.mock import MagicMock, patch

from computer_use.core.actions import ActionExecutor
from computer_use.core.types import Action, ActionType


class MockExecutor(ActionExecutor):
    """Concrete executor that records calls for testing."""

    def __init__(self):
        self.calls = []

    def move_mouse(self, x, y):
        self.calls.append(("move_mouse", x, y))

    def click(self, x, y, button="left"):
        self.calls.append(("click", x, y, button))

    def double_click(self, x, y):
        self.calls.append(("double_click", x, y))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def key_press(self, keys):
        self.calls.append(("key_press", keys))

    def scroll(self, x, y, amount):
        self.calls.append(("scroll", x, y, amount))

    def drag(self, start_x, start_y, end_x, end_y, duration=0.5):
        self.calls.append(("drag", start_x, start_y, end_x, end_y, duration))


class TestActionRouter:
    def test_click(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.CLICK, x=100, y=200)
        ex.execute_action(action)
        assert ex.calls == [("click", 100, 200, "left")]

    def test_double_click(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.DOUBLE_CLICK, x=50, y=60)
        ex.execute_action(action)
        assert ex.calls == [("double_click", 50, 60)]

    def test_right_click(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.RIGHT_CLICK, x=10, y=20)
        ex.execute_action(action)
        assert ex.calls == [("click", 10, 20, "right")]

    def test_type_text(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.TYPE_TEXT, text="hello world")
        ex.execute_action(action)
        assert ex.calls == [("type_text", "hello world")]

    def test_key_press(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.KEY_PRESS, keys=["ctrl", "s"])
        ex.execute_action(action)
        assert ex.calls == [("key_press", ["ctrl", "s"])]

    def test_scroll(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.SCROLL, x=100, y=200, scroll_amount=-3)
        ex.execute_action(action)
        assert ex.calls == [("scroll", 100, 200, -3)]

    def test_move(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.MOVE, x=500, y=300)
        ex.execute_action(action)
        assert ex.calls == [("move_mouse", 500, 300)]

    def test_drag(self):
        ex = MockExecutor()
        action = Action(
            action_type=ActionType.DRAG,
            x=10, y=20, target_x=300, target_y=400, duration=1.0,
        )
        ex.execute_action(action)
        assert ex.calls == [("drag", 10, 20, 300, 400, 1.0)]

    def test_wait(self):
        ex = MockExecutor()
        action = Action(action_type=ActionType.WAIT, duration=0.01)
        start = time.time()
        ex.execute_action(action)
        elapsed = time.time() - start
        assert elapsed >= 0.01
        assert ex.calls == []  # wait doesn't call any executor method
