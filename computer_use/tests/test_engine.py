"""Tests for the ComputerUseEngine with mocked backends."""

from unittest.mock import MagicMock, patch

import pytest

from computer_use.core.engine import ComputerUseEngine
from computer_use.core.types import Platform, Region, ScreenState


@pytest.fixture
def mock_backend():
    """Create a fully mocked platform backend."""
    backend = MagicMock()
    backend.is_available.return_value = True
    backend.get_accessibility_info.return_value = {
        "available": True,
        "api_name": "Mock",
        "notes": "",
    }

    capture = MagicMock()
    capture.capture_full.return_value = ScreenState(
        image_bytes=b"\x89PNG_MOCK",
        width=1920,
        height=1080,
    )
    capture.capture_region.return_value = ScreenState(
        image_bytes=b"\x89PNG_REGION",
        width=200,
        height=100,
    )
    capture.get_screen_size.return_value = (1920, 1080)
    capture.get_scale_factor.return_value = 1.0

    executor = MagicMock()

    backend.get_screen_capture.return_value = capture
    backend.get_action_executor.return_value = executor

    return backend, capture, executor


class TestEngine:
    def _make_engine(self, mock_backend):
        backend, capture, executor = mock_backend
        with (
            patch("computer_use.core.engine.detect_platform", return_value=Platform.WSL2),
            patch("computer_use.core.engine.get_backend", return_value=backend),
            patch("computer_use.core.engine.yaml"),
        ):
            engine = ComputerUseEngine()
        return engine, capture, executor

    def test_screenshot(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        screen = engine.screenshot()
        assert screen.width == 1920
        assert screen.height == 1080
        capture.capture_full.assert_called_once()

    def test_screenshot_region(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        screen = engine.screenshot_region(10, 20, 200, 100)
        assert screen.width == 200
        capture.capture_region.assert_called_once()

    def test_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.click(500, 300)
        executor.click.assert_called_once_with(500, 300)

    def test_double_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.double_click(100, 200)
        executor.double_click.assert_called_once_with(100, 200)

    def test_right_click(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.right_click(100, 200)
        executor.click.assert_called_once_with(100, 200, button="right")

    def test_type_text(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.type_text("hello")
        executor.type_text.assert_called_once_with("hello")

    def test_key_press(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.key_press("ctrl", "c")
        executor.key_press.assert_called_once_with(["ctrl", "c"])

    def test_scroll(self, mock_backend):
        engine, _, executor = self._make_engine(mock_backend)
        engine.scroll(100, 200, -3)
        executor.scroll.assert_called_once_with(100, 200, -3)

    def test_get_platform(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        assert engine.get_platform() == Platform.WSL2

    def test_get_screen_size(self, mock_backend):
        engine, capture, _ = self._make_engine(mock_backend)
        assert engine.get_screen_size() == (1920, 1080)

    def test_get_platform_info(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        info = engine.get_platform_info()
        assert info["platform"] == "wsl2"
        assert info["backend_available"] is True

    def test_run_task_without_provider_raises(self, mock_backend):
        engine, _, _ = self._make_engine(mock_backend)
        with pytest.raises(Exception):
            engine.run_task("Open Notepad")
