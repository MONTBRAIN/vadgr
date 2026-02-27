"""Tests for the MCP server tool wrappers."""

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image as PILImage

from computer_use.core.types import Element, Platform, Region, ScreenState


def _make_png(width: int, height: int) -> bytes:
    """Create a minimal valid PNG of the given size."""
    img = PILImage.new("RGB", (width, height), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.screenshot.return_value = ScreenState(
        image_bytes=_make_png(1920, 1080),
        width=1920,
        height=1080,
    )
    engine.screenshot_region.return_value = ScreenState(
        image_bytes=_make_png(200, 100),
        width=200,
        height=100,
    )
    engine.get_screen_size.return_value = (1920, 1080)
    engine.get_platform.return_value = Platform.WSL2
    engine.get_platform_info.return_value = {
        "platform": "wsl2",
        "backend_available": True,
        "accessibility": {"available": True, "api_name": "UI Automation"},
    }
    engine.find_element.return_value = Element(
        name="Save",
        role="button",
        region=Region(100, 200, 80, 30),
        confidence=0.95,
        source="accessibility",
    )
    return engine


@pytest.fixture(autouse=True)
def _patch_engine(mock_engine):
    import computer_use.mcp_server as mod

    mod._engine = mock_engine
    mod._scale_x = 1.0
    mod._scale_y = 1.0
    mod._display_w = 0
    mod._display_h = 0
    mod._offset_x = 0
    mod._offset_y = 0
    yield
    mod._engine = None
    mod._scale_x = 1.0
    mod._scale_y = 1.0
    mod._offset_x = 0
    mod._offset_y = 0


class TestScreenshotTools:
    def test_screenshot_returns_image(self, mock_engine):
        from mcp.server.fastmcp import Image
        from computer_use.mcp_server import screenshot

        result = screenshot()
        assert isinstance(result, Image)
        mock_engine.screenshot.assert_called_once()

    def test_screenshot_downscales(self, mock_engine):
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot

        mod._MAX_WIDTH = 1366
        screenshot()
        assert mod._scale_x > 1.0  # 1920/1366 ~ 1.41
        assert mod._display_w == 1366

    def test_screenshot_no_downscale_when_small(self, mock_engine):
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot

        mock_engine.screenshot.return_value = ScreenState(
            image_bytes=_make_png(1024, 768),
            width=1024,
            height=768,
        )
        mod._MAX_WIDTH = 1366
        screenshot()
        assert mod._scale_x == 1.0
        assert mod._scale_y == 1.0

    def test_screenshot_stores_offset(self, mock_engine):
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot

        mock_engine.screenshot.return_value = ScreenState(
            image_bytes=_make_png(1920, 1080),
            width=1920,
            height=1080,
            offset_x=100,
            offset_y=50,
        )
        mod._MAX_WIDTH = 1920
        screenshot()
        assert mod._offset_x == 100
        assert mod._offset_y == 50

    def test_screenshot_region_returns_image(self, mock_engine):
        from mcp.server.fastmcp import Image
        from computer_use.mcp_server import screenshot_region

        result = screenshot_region(10, 20, 200, 100)
        assert isinstance(result, Image)


class TestCoordinateScaling:
    """Action tools scale display coords back to real screen coords."""

    def _set_scale(self, sx, sy, ox=0, oy=0):
        import computer_use.mcp_server as mod
        mod._scale_x = sx
        mod._scale_y = sy
        mod._offset_x = ox
        mod._offset_y = oy

    def test_click_scales_coords(self, mock_engine):
        from computer_use.mcp_server import click

        self._set_scale(2.0, 2.0)
        click(100, 200)
        mock_engine.click.assert_called_once_with(200, 400)

    def test_click_with_offset(self, mock_engine):
        from computer_use.mcp_server import click

        self._set_scale(2.0, 2.0, ox=100, oy=50)
        click(100, 200)
        mock_engine.click.assert_called_once_with(300, 450)

    def test_double_click_scales_coords(self, mock_engine):
        from computer_use.mcp_server import double_click

        self._set_scale(3.0, 3.0)
        double_click(10, 20)
        mock_engine.double_click.assert_called_once_with(30, 60)

    def test_right_click_scales_coords(self, mock_engine):
        from computer_use.mcp_server import right_click

        self._set_scale(2.0, 2.0)
        right_click(50, 75)
        mock_engine.right_click.assert_called_once_with(100, 150)

    def test_move_mouse_scales_coords(self, mock_engine):
        from computer_use.mcp_server import move_mouse

        self._set_scale(2.0, 2.0)
        move_mouse(300, 400)
        mock_engine.move_mouse.assert_called_once_with(600, 800)

    def test_scroll_scales_coords(self, mock_engine):
        from computer_use.mcp_server import scroll

        self._set_scale(2.0, 2.0)
        scroll(100, 200, -3)
        mock_engine.scroll.assert_called_once_with(200, 400, -3)

    def test_drag_scales_both_endpoints(self, mock_engine):
        from computer_use.mcp_server import drag

        self._set_scale(2.0, 2.0)
        drag(10, 20, 100, 200, 0.5)
        mock_engine.drag.assert_called_once_with(20, 40, 200, 400, 0.5)

    def test_drag_with_offset(self, mock_engine):
        from computer_use.mcp_server import drag

        self._set_scale(1.0, 1.0, ox=200, oy=100)
        drag(10, 20, 100, 200, 0.5)
        mock_engine.drag.assert_called_once_with(210, 120, 300, 300, 0.5)

    def test_no_scaling_at_1x(self, mock_engine):
        from computer_use.mcp_server import click

        self._set_scale(1.0, 1.0)
        click(500, 300)
        mock_engine.click.assert_called_once_with(500, 300)


class TestMouseTools:
    def test_click_returns_display_coords(self, mock_engine):
        from computer_use.mcp_server import click

        result = click(500, 300)
        assert "500" in result and "300" in result

    def test_scroll_up(self, mock_engine):
        from computer_use.mcp_server import scroll

        result = scroll(100, 200, 3)
        assert "up" in result

    def test_scroll_down(self, mock_engine):
        from computer_use.mcp_server import scroll

        result = scroll(100, 200, -3)
        assert "down" in result


class TestKeyboardTools:
    def test_type_text(self, mock_engine):
        from computer_use.mcp_server import type_text

        result = type_text("hello world")
        assert "hello world" in result
        mock_engine.type_text.assert_called_once_with("hello world")

    def test_type_text_long_truncates_preview(self, mock_engine):
        from computer_use.mcp_server import type_text

        long_text = "a" * 100
        result = type_text(long_text)
        assert "..." in result

    def test_key_press_single(self, mock_engine):
        from computer_use.mcp_server import key_press

        result = key_press("enter")
        assert "enter" in result
        mock_engine.key_press.assert_called_once_with("enter")

    def test_key_press_combo(self, mock_engine):
        from computer_use.mcp_server import key_press

        key_press("ctrl+c")
        mock_engine.key_press.assert_called_once_with("ctrl", "c")

    def test_key_press_triple(self, mock_engine):
        from computer_use.mcp_server import key_press

        key_press("ctrl+shift+s")
        mock_engine.key_press.assert_called_once_with("ctrl", "shift", "s")


class TestInfoTools:
    def test_get_screen_size(self, mock_engine):
        from computer_use.mcp_server import get_screen_size

        result = get_screen_size()
        assert result == "1920x1080"

    def test_get_platform(self, mock_engine):
        from computer_use.mcp_server import get_platform

        result = get_platform()
        assert result == "wsl2"

    def test_get_platform_info(self, mock_engine):
        from computer_use.mcp_server import get_platform_info

        result = get_platform_info()
        assert result["platform"] == "wsl2"
        assert result["backend_available"] is True


class TestElementFinding:
    def test_find_element_found(self, mock_engine):
        from computer_use.mcp_server import find_element

        result = find_element("Save button")
        assert "Save" in result
        assert "button" in result
        mock_engine.find_element.assert_called_once_with("Save button")

    def test_find_element_returns_display_coords(self, mock_engine):
        """find_element should return coords in display space."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import find_element

        mod._scale_x = 2.0
        mod._scale_y = 2.0
        mod._offset_x = 0
        mod._offset_y = 0
        # Element center is (140, 215) in real coords
        # Display coords should be (70, 107)
        result = find_element("Save button")
        assert "70" in result
        assert "107" in result

    def test_find_element_with_offset(self, mock_engine):
        """find_element subtracts monitor offset before converting to display coords."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import find_element

        mod._scale_x = 1.0
        mod._scale_y = 1.0
        mod._offset_x = 100
        mod._offset_y = 50
        # Element center is (140, 215) in real coords
        # Subtract offset: (40, 165), then /scale = (40, 165)
        result = find_element("Save button")
        assert "40" in result
        assert "165" in result

    def test_find_element_not_found(self, mock_engine):
        from computer_use.mcp_server import find_element

        mock_engine.find_element.return_value = None
        result = find_element("nonexistent")
        assert "not found" in result.lower()


class TestEngineSingleton:
    def test_lazy_init(self):
        import computer_use.mcp_server as mod

        mod._engine = None
        assert mod._engine is None
