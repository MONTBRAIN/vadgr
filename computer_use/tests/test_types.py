"""Tests for core data types."""

from computer_use.core.types import (
    Action,
    ActionType,
    Element,
    Platform,
    Region,
    ScreenState,
    StepResult,
)


class TestRegion:
    def test_center(self):
        r = Region(x=10, y=20, width=100, height=50)
        assert r.center == (60, 45)

    def test_center_origin(self):
        r = Region(x=0, y=0, width=200, height=100)
        assert r.center == (100, 50)

    def test_frozen(self):
        r = Region(x=0, y=0, width=10, height=10)
        try:
            r.x = 5
            assert False, "Should raise"
        except AttributeError:
            pass


class TestElement:
    def test_creation(self):
        region = Region(x=100, y=200, width=80, height=30)
        el = Element(
            name="Save",
            role="button",
            region=region,
            confidence=0.95,
            source="accessibility",
        )
        assert el.name == "Save"
        assert el.role == "button"
        assert el.confidence == 0.95
        assert el.region.center == (140, 215)

    def test_default_properties(self):
        region = Region(x=0, y=0, width=10, height=10)
        el = Element(
            name="test", role="text", region=region, confidence=1.0, source="vision"
        )
        assert el.properties == {}


class TestAction:
    def test_click(self):
        a = Action(action_type=ActionType.CLICK, x=500, y=300)
        assert a.action_type == ActionType.CLICK
        assert a.x == 500
        assert a.y == 300

    def test_type_text(self):
        a = Action(action_type=ActionType.TYPE_TEXT, text="hello world")
        assert a.text == "hello world"

    def test_key_press(self):
        a = Action(action_type=ActionType.KEY_PRESS, keys=["ctrl", "c"])
        assert a.keys == ["ctrl", "c"]

    def test_scroll(self):
        a = Action(action_type=ActionType.SCROLL, x=100, y=200, scroll_amount=-3)
        assert a.scroll_amount == -3

    def test_drag(self):
        a = Action(
            action_type=ActionType.DRAG,
            x=10, y=20,
            target_x=300, target_y=400,
            duration=0.5,
        )
        assert a.target_x == 300
        assert a.duration == 0.5

    def test_wait(self):
        a = Action(action_type=ActionType.WAIT, duration=2.0)
        assert a.duration == 2.0

    def test_defaults(self):
        a = Action(action_type=ActionType.CLICK)
        assert a.x is None
        assert a.text is None
        assert a.keys is None
        assert a.scroll_amount == 0
        assert a.duration == 0.0


class TestScreenState:
    def test_creation(self):
        s = ScreenState(
            image_bytes=b"\x89PNG",
            width=1920,
            height=1080,
        )
        assert s.width == 1920
        assert s.height == 1080
        assert s.scale_factor == 1.0
        assert s.timestamp > 0


class TestPlatform:
    def test_values(self):
        assert Platform.WINDOWS.value == "windows"
        assert Platform.MACOS.value == "macos"
        assert Platform.LINUX.value == "linux"
        assert Platform.WSL2.value == "wsl2"


class TestActionType:
    def test_all_types(self):
        expected = {
            "click", "double_click", "right_click", "type_text",
            "key_press", "scroll", "move", "drag", "wait",
        }
        actual = {at.value for at in ActionType}
        assert actual == expected
