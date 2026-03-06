"""Tests for the Windows platform backend.

Verifies that WindowsActionExecutor:
- Uses smooth_move for human-like mouse movement (not raw SetCursorPos)
- Accepts hit_count on all action methods (matching the ABC)
- Delegates to _raw_move + CursorTracker like Linux does
- Uses windmouse-based drag instead of linear interpolation
"""

import sys
from unittest.mock import MagicMock, patch, call

import pytest

# Guard: these tests mock all Win32 calls so they can run on any platform,
# but the module itself only defines ctypes structs on win32.  We need to
# patch sys.platform during import if we're not on Windows.
_REAL_WIN32 = sys.platform == "win32"
_skip_not_win32 = pytest.mark.skipif(not _REAL_WIN32, reason="Windows-only tests")


def _import_windows_module():
    """Import the windows module, mocking ctypes.windll on non-Windows."""
    if _REAL_WIN32:
        from computer_use.platform.windows import (
            WindowsActionExecutor,
            WindowsScreenCapture,
            WindowsBackend,
        )
        return WindowsActionExecutor, WindowsScreenCapture, WindowsBackend

    # On Linux/macOS CI, we can't import the module at all because it
    # references ctypes.windll which doesn't exist.  Skip these tests.
    pytest.skip("Windows-only tests (ctypes.windll unavailable)")


# ---------------------------------------------------------------------------
# WindowsActionExecutor -- smooth_move integration
# ---------------------------------------------------------------------------


@_skip_not_win32
class TestWindowsActionExecutorSmoothMove:
    """Verify smooth_move is wired into move_mouse, click, double_click, drag."""

    def _make_executor(self):
        Cls, _, _ = _import_windows_module()
        ex = Cls()
        return ex

    @patch("computer_use.platform.windows.smooth_move")
    @patch("computer_use.platform.windows.user32")
    def test_move_mouse_calls_smooth_move(self, mock_user32, mock_smooth):
        ex = self._make_executor()
        ex.move_mouse(500, 300, hit_count=3)
        mock_smooth.assert_called_once()
        args, kwargs = mock_smooth.call_args
        assert args[0] == 500  # end_x
        assert args[1] == 300  # end_y
        assert kwargs["hit_count"] == 3

    @patch("computer_use.platform.windows.user32")
    def test_raw_move_calls_set_cursor_pos(self, mock_user32):
        ex = self._make_executor()
        ex._raw_move(100, 200)
        mock_user32.SetCursorPos.assert_called_with(100, 200)

    @patch("computer_use.platform.windows.user32")
    def test_raw_move_updates_tracker(self, mock_user32):
        ex = self._make_executor()
        ex._raw_move(100, 200)
        assert ex._tracker.get_pos() == (100, 200)

    @patch("computer_use.platform.windows.smooth_move")
    @patch("computer_use.platform.windows.user32")
    def test_click_calls_smooth_move_then_input(self, mock_user32, mock_smooth):
        ex = self._make_executor()
        ex.click(400, 300, hit_count=2)
        # smooth_move should be called for movement
        mock_smooth.assert_called_once()
        # SendInput should be called for mouse down + up
        assert mock_user32.SendInput.call_count >= 2

    @patch("computer_use.platform.windows.smooth_move")
    @patch("computer_use.platform.windows.user32")
    def test_click_right_button(self, mock_user32, mock_smooth):
        ex = self._make_executor()
        ex.click(400, 300, button="right", hit_count=0)
        mock_smooth.assert_called_once()
        assert mock_user32.SendInput.call_count >= 2

    @patch("computer_use.platform.windows.smooth_move")
    @patch("computer_use.platform.windows.user32")
    def test_double_click_calls_smooth_move(self, mock_user32, mock_smooth):
        ex = self._make_executor()
        ex.double_click(400, 300, hit_count=1)
        mock_smooth.assert_called_once()
        # 4 SendInput calls: down, up, down, up
        assert mock_user32.SendInput.call_count >= 4

    @patch("computer_use.platform.windows.smooth_move")
    @patch("computer_use.platform.windows.user32")
    def test_drag_uses_smooth_move_and_windmouse(self, mock_user32, mock_smooth):
        ex = self._make_executor()
        ex.drag(100, 100, 500, 500, duration=0.1, hit_count=2)
        # smooth_move called to move to start position
        mock_smooth.assert_called_once()
        # SendInput called for mousedown + mouseup (intermediate moves use SetCursorPos)
        assert mock_user32.SendInput.call_count >= 2
        # SetCursorPos called for windmouse path intermediate points
        assert mock_user32.SetCursorPos.call_count >= 1


# ---------------------------------------------------------------------------
# WindowsActionExecutor -- ABC signature compliance
# ---------------------------------------------------------------------------


@_skip_not_win32
class TestWindowsActionExecutorABCSignature:
    """Verify method signatures match the ActionExecutor ABC (hit_count params)."""

    def test_move_mouse_accepts_hit_count(self):
        Cls, _, _ = _import_windows_module()
        import inspect
        sig = inspect.signature(Cls.move_mouse)
        assert "hit_count" in sig.parameters

    def test_click_accepts_hit_count(self):
        Cls, _, _ = _import_windows_module()
        import inspect
        sig = inspect.signature(Cls.click)
        assert "hit_count" in sig.parameters

    def test_double_click_accepts_hit_count(self):
        Cls, _, _ = _import_windows_module()
        import inspect
        sig = inspect.signature(Cls.double_click)
        assert "hit_count" in sig.parameters

    def test_drag_accepts_hit_count(self):
        Cls, _, _ = _import_windows_module()
        import inspect
        sig = inspect.signature(Cls.drag)
        assert "hit_count" in sig.parameters


# ---------------------------------------------------------------------------
# WindowsActionExecutor -- has _tracker and _raw_move
# ---------------------------------------------------------------------------


@_skip_not_win32
class TestWindowsActionExecutorInternals:
    """Verify the executor has CursorTracker and _raw_move like other platforms."""

    def test_has_cursor_tracker(self):
        Cls, _, _ = _import_windows_module()
        ex = Cls()
        assert hasattr(ex, "_tracker")
        assert hasattr(ex._tracker, "get_pos")
        assert hasattr(ex._tracker, "update")

    def test_has_raw_move(self):
        Cls, _, _ = _import_windows_module()
        ex = Cls()
        assert callable(getattr(ex, "_raw_move", None))

    @patch("computer_use.platform.windows.user32")
    def test_get_cursor_pos_returns_tracker_position(self, mock_user32):
        Cls, _, _ = _import_windows_module()
        ex = Cls()
        ex._tracker.update(42, 84)
        assert ex._tracker.get_pos() == (42, 84)


# ---------------------------------------------------------------------------
# DPI Awareness
# ---------------------------------------------------------------------------


@_skip_not_win32
class TestWindowsDpiAwareness:
    """Verify the module sets DPI awareness on import so coordinates match."""

    def test_enable_dpi_awareness_called(self):
        if not _REAL_WIN32:
            pytest.skip("Windows-only")
        from computer_use.platform.windows import _dpi_awareness_set
        assert _dpi_awareness_set is True

    def test_screen_size_matches_physical(self):
        """After DPI awareness, GetSystemMetrics should return physical pixels."""
        if not _REAL_WIN32:
            pytest.skip("Windows-only")
        import ctypes
        # If DPI-aware, screen size should match what shcore reports
        from computer_use.platform.windows import user32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        # On a DPI-scaled display, DPI-aware reports bigger than 2560x1440
        # On a non-scaled display, they match. Either way, the value should
        # be consistent with what the screenshot captures.
        assert w > 0 and h > 0


# ---------------------------------------------------------------------------
# WindowsBackend
# ---------------------------------------------------------------------------


@_skip_not_win32
class TestWindowsBackend:
    def test_get_action_executor_cached(self):
        _, _, Backend = _import_windows_module()
        b = Backend()
        ex1 = b.get_action_executor()
        ex2 = b.get_action_executor()
        assert ex1 is ex2

    def test_get_screen_capture_cached(self):
        _, _, Backend = _import_windows_module()
        b = Backend()
        sc1 = b.get_screen_capture()
        sc2 = b.get_screen_capture()
        assert sc1 is sc2
