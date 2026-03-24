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

    old_max_width = mod._MAX_WIDTH
    mod._engine = mock_engine
    mod._MAX_WIDTH = 1024
    mod._scale_x = 1.0
    mod._scale_y = 1.0
    mod._display_w = 0
    mod._display_h = 0
    mod._offset_x = 0
    mod._offset_y = 0
    yield
    mod._engine = None
    mod._MAX_WIDTH = old_max_width
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
    def test_get_screen_size_returns_display_dims_before_screenshot(self, mock_engine):
        """Before any screenshot, get_screen_size computes display dims from _MAX_WIDTH."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import get_screen_size

        # Fixture sets _MAX_WIDTH=1024, engine returns (1920,1080).
        # Display should be 1024 x int(1080 * 1024/1920) = 1024x576
        mod._display_w = 0
        mod._display_h = 0
        result = get_screen_size()
        assert result == "1024x576"

    def test_get_screen_size_returns_display_dims_after_screenshot(self, mock_engine):
        """After screenshot(), get_screen_size returns the downscaled dimensions."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot, get_screen_size

        # Engine returns 1920x1080, _MAX_WIDTH=1024 -> downscale to 1024x576
        screenshot()
        result = get_screen_size()
        assert result == f"{mod._display_w}x{mod._display_h}"
        assert mod._display_w == 1024

    def test_get_screen_size_no_downscale_when_small(self, mock_engine):
        """If the real screen is smaller than _MAX_WIDTH, return real size."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import get_screen_size

        mod._display_w = 0
        mod._MAX_WIDTH = 1366
        mock_engine.get_screen_size.return_value = (1024, 768)
        result = get_screen_size()
        assert result == "1024x768"

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


class TestScreenshotRegionScalePreservation:
    """Regression tests: screenshot_region must NOT clobber the global scale state."""

    def test_region_preserves_scale_factors(self, mock_engine):
        """After screenshot() sets scale, screenshot_region() must not reset it."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot, screenshot_region

        screenshot()
        scale_x_before = mod._scale_x
        scale_y_before = mod._scale_y
        assert scale_x_before > 1.0, "Precondition: screenshot should set scale > 1"

        screenshot_region(100, 200, 50, 30)

        assert mod._scale_x == scale_x_before
        assert mod._scale_y == scale_y_before

    def test_region_preserves_display_dims(self, mock_engine):
        """screenshot_region() must not change _display_w/_display_h."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot, screenshot_region

        screenshot()
        dw_before = mod._display_w
        dh_before = mod._display_h

        screenshot_region(100, 200, 50, 30)

        assert mod._display_w == dw_before
        assert mod._display_h == dh_before

    def test_click_after_region_uses_correct_scale(self, mock_engine):
        """Full integration: screenshot -> region -> click should use the original scale."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot, screenshot_region, click

        screenshot()
        scale_x = mod._scale_x  # 1920/1024 = 1.875

        screenshot_region(100, 200, 50, 30)

        click(100, 200)
        expected_x = int(100 * scale_x)
        expected_y = int(200 * scale_x)  # scale_x == scale_y for uniform downscale
        mock_engine.click.assert_called_once_with(expected_x, expected_y)

    def test_region_preserves_offset(self, mock_engine):
        """screenshot_region() must not change _offset_x/_offset_y."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot, screenshot_region

        mock_engine.screenshot.return_value = ScreenState(
            image_bytes=_make_png(1920, 1080),
            width=1920,
            height=1080,
            offset_x=200,
            offset_y=100,
        )
        screenshot()
        assert mod._offset_x == 200
        assert mod._offset_y == 100

        screenshot_region(50, 50, 100, 100)

        assert mod._offset_x == 200
        assert mod._offset_y == 100

    def test_multiple_regions_dont_drift(self, mock_engine):
        """Calling screenshot_region repeatedly must not degrade scale accuracy."""
        import computer_use.mcp_server as mod
        from computer_use.mcp_server import screenshot, screenshot_region

        screenshot()
        original_scale_x = mod._scale_x

        for _ in range(5):
            screenshot_region(10, 10, 50, 50)

        assert mod._scale_x == original_scale_x


class TestTemplateTools:
    """Tests for the action template MCP tools."""

    @pytest.fixture(autouse=True)
    def _setup_cache(self, mock_engine):
        """Give the mock engine a real cache for template operations."""
        from computer_use.core.spatial_cache import MuscleMemoryCache
        mock_engine._cache = MuscleMemoryCache(":memory:")
        yield
        mock_engine._cache.close()

    def test_create_template(self):
        import computer_use.mcp_server as mod
        result = mod.create_template(
            name="test-save",
            app_name="notepad.exe",
            steps=[
                {"action": "key_press", "text": "ctrl+s", "wait_ms": 200},
            ],
        )
        assert "created" in result
        assert "test-save" in result

    def test_create_template_invalid_action(self):
        import computer_use.mcp_server as mod
        result = mod.create_template(
            name="bad",
            app_name="app.exe",
            steps=[{"action": "fly"}],
        )
        assert "Error" in result

    def test_list_templates(self):
        import computer_use.mcp_server as mod
        mod.create_template("a", "app.exe", [{"action": "wait"}])
        mod.create_template("b", "app.exe", [{"action": "wait"}, {"action": "click", "hint": "OK"}])
        result = mod.list_templates()
        assert "2" in result  # "Templates (2):"
        assert "a" in result
        assert "b" in result

    def test_list_templates_empty(self):
        import computer_use.mcp_server as mod
        result = mod.list_templates()
        assert "No templates" in result

    def test_list_templates_filtered(self):
        import computer_use.mcp_server as mod
        mod.create_template("x", "app1.exe", [{"action": "wait"}])
        mod.create_template("y", "app2.exe", [{"action": "wait"}])
        result = mod.list_templates(app_name="app1.exe")
        assert "x" in result
        assert "y" not in result

    def test_delete_template(self):
        import computer_use.mcp_server as mod
        mod.create_template("del-me", "app.exe", [{"action": "wait"}])
        result = mod.delete_template("del-me")
        assert "deleted" in result

    def test_delete_nonexistent(self):
        import computer_use.mcp_server as mod
        result = mod.delete_template("nope")
        assert "not found" in result

    def test_execute_template_not_found(self):
        import computer_use.mcp_server as mod
        # execute_template calls engine.execute_template which needs the real method
        # Since mock_engine is a MagicMock, engine.execute_template will return a MagicMock
        # We need to configure it
        mock_engine = mod._engine
        mock_engine.execute_template.return_value = {
            "completed": 0, "total": 0, "last_hint": "",
            "stopped": True, "reason": "template 'nope' not found",
        }
        result = mod.execute_template("nope")
        assert "stopped" in result
        assert "not found" in result

    def test_execute_template_success(self):
        import computer_use.mcp_server as mod
        mock_engine = mod._engine
        mock_engine.execute_template.return_value = {
            "completed": 3, "total": 3, "last_hint": "",
            "stopped": False, "reason": "",
        }
        result = mod.execute_template("my-template")
        assert "complete" in result
        assert "3/3" in result


class TestCacheDisabledGuards:
    """Tests for MCP tool behavior when engine cache is disabled."""

    @pytest.fixture(autouse=True)
    def _disable_cache(self, mock_engine):
        """Set engine._cache to None to simulate cache_enabled=False."""
        mock_engine._cache = None
        yield

    def test_create_template_returns_error(self):
        import computer_use.mcp_server as mod
        result = mod.create_template("test", "app.exe", [{"action": "wait"}])
        assert "cache is disabled" in result

    def test_list_templates_returns_empty(self):
        import computer_use.mcp_server as mod
        result = mod.list_templates()
        assert "cache is disabled" in result

    def test_delete_template_returns_error(self):
        import computer_use.mcp_server as mod
        result = mod.delete_template("test")
        assert "cache is disabled" in result


class TestGetEngineEnvVar:
    """Tests that _get_engine reads AGENT_FORGE_CACHE_ENABLED env var."""

    def test_cache_disabled_via_env(self):
        import computer_use.mcp_server as mod
        mod._engine = None  # force re-init

        with (
            patch.dict("os.environ", {"AGENT_FORGE_CACHE_ENABLED": "0"}),
            patch("computer_use.core.engine.detect_platform") as mock_detect,
            patch("computer_use.core.engine.get_backend") as mock_get_backend,
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            mock_detect.return_value = Platform.WSL2
            backend = MagicMock()
            backend.is_available.return_value = True
            backend.get_accessibility_info.return_value = {"available": True, "api_name": "Mock", "notes": ""}
            capture = MagicMock()
            capture.get_screen_size.return_value = (1920, 1080)
            capture.get_scale_factor.return_value = 1.0
            backend.get_screen_capture.return_value = capture
            backend.get_action_executor.return_value = MagicMock()
            backend.get_foreground_window.return_value = None
            mock_get_backend.return_value = backend

            engine = mod._get_engine()
            assert engine._cache is None

        mod._engine = None  # clean up

    def test_cache_enabled_by_default(self):
        import computer_use.mcp_server as mod
        mod._engine = None

        with (
            patch.dict("os.environ", {}, clear=False),
            patch("computer_use.core.engine.detect_platform") as mock_detect,
            patch("computer_use.core.engine.get_backend") as mock_get_backend,
            patch("computer_use.core.engine.yaml"),
            patch("computer_use.core.engine._default_cache_path", return_value=":memory:"),
        ):
            # Remove the env var if it exists
            import os
            os.environ.pop("AGENT_FORGE_CACHE_ENABLED", None)

            mock_detect.return_value = Platform.WSL2
            backend = MagicMock()
            backend.is_available.return_value = True
            backend.get_accessibility_info.return_value = {"available": True, "api_name": "Mock", "notes": ""}
            capture = MagicMock()
            capture.get_screen_size.return_value = (1920, 1080)
            capture.get_scale_factor.return_value = 1.0
            backend.get_screen_capture.return_value = capture
            backend.get_action_executor.return_value = MagicMock()
            backend.get_foreground_window.return_value = None
            mock_get_backend.return_value = backend

            engine = mod._get_engine()
            assert engine._cache is not None

        mod._engine = None


class TestEngineSingleton:
    def test_lazy_init(self):
        import computer_use.mcp_server as mod

        mod._engine = None
        assert mod._engine is None
