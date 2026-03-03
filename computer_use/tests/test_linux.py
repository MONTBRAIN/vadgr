"""Tests for the Linux platform backend."""

import os
import subprocess
from unittest.mock import MagicMock, patch, mock_open, PropertyMock

import pytest

from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.types import Region, ScreenState


# -- Display session detection --


class TestIsWayland:
    def test_wayland_display_set(self):
        from computer_use.platform.linux import _is_wayland

        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}):
            assert _is_wayland() is True

    def test_xdg_session_type_wayland(self):
        from computer_use.platform.linux import _is_wayland

        env = {"XDG_SESSION_TYPE": "wayland"}
        with patch.dict(os.environ, env, clear=True):
            assert _is_wayland() is True

    def test_x11_session(self):
        from computer_use.platform.linux import _is_wayland

        env = {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
        with patch.dict(os.environ, env, clear=True):
            assert _is_wayland() is False

    def test_no_display_vars(self):
        from computer_use.platform.linux import _is_wayland

        with patch.dict(os.environ, {}, clear=True):
            assert _is_wayland() is False


# -- Screenshot capture factory --


class TestCreateScreenCapture:
    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    def test_x11_returns_mss_capture(self, _mock):
        from computer_use.platform.linux import _create_screen_capture, MssScreenCapture

        capture = _create_screen_capture()
        assert isinstance(capture, MssScreenCapture)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", side_effect=lambda cmd: "/usr/bin/grim" if cmd == "grim" else None)
    def test_wayland_prefers_grim_when_it_works(self, _which, _wayland):
        from computer_use.platform.linux import _create_screen_capture, GrimScreenCapture

        with patch.object(GrimScreenCapture, "capture_full"):
            capture = _create_screen_capture()
            assert isinstance(capture, GrimScreenCapture)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", side_effect=lambda cmd: "/usr/bin/gnome-screenshot" if cmd == "gnome-screenshot" else None)
    def test_wayland_falls_back_to_gnome_screenshot(self, _which, _wayland):
        from computer_use.platform.linux import _create_screen_capture, GnomeScreenCapture

        with patch.object(GnomeScreenCapture, "capture_full"):
            capture = _create_screen_capture()
            assert isinstance(capture, GnomeScreenCapture)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", return_value="/usr/bin/grim")
    def test_wayland_skips_broken_tool(self, _which, _wayland):
        """If grim is installed but fails, fall back to gnome-screenshot."""
        from computer_use.platform.linux import (
            _create_screen_capture, GrimScreenCapture, GnomeScreenCapture,
        )

        def which_both(cmd):
            return f"/usr/bin/{cmd}" if cmd in ("grim", "gnome-screenshot") else None

        with (
            patch("shutil.which", side_effect=which_both),
            patch.object(GrimScreenCapture, "capture_full", side_effect=ScreenCaptureError("nope")),
            patch.object(GnomeScreenCapture, "capture_full"),
        ):
            capture = _create_screen_capture()
            assert isinstance(capture, GnomeScreenCapture)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("shutil.which", return_value=None)
    def test_wayland_no_tools_raises(self, _which, _wayland):
        from computer_use.platform.linux import _create_screen_capture

        with pytest.raises(ScreenCaptureError, match="No working Wayland screenshot tool"):
            _create_screen_capture()


# -- Grim capture (wlroots Wayland) --


class TestGrimScreenCapture:
    def _make_capture(self):
        from computer_use.platform.linux import GrimScreenCapture
        return GrimScreenCapture()

    @patch("subprocess.run")
    def test_capture_full_reads_png(self, mock_run):
        fake_png = b"\x89PNG\r\n\x1a\nfake"
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_png, stderr=b"")

        with patch("builtins.open", mock_open(read_data=fake_png)):
            with patch("computer_use.platform.linux.GrimScreenCapture._read_image_size", return_value=(1920, 1080)):
                capture = self._make_capture()
                state = capture.capture_full()

        assert state.width == 1920
        assert state.height == 1080
        assert state.image_bytes == fake_png

    @patch("subprocess.run")
    def test_capture_full_handles_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"grim failed")

        capture = self._make_capture()
        with pytest.raises(ScreenCaptureError, match="grim failed"):
            capture.capture_full()


# -- Gnome screenshot capture --


class TestGnomeScreenCapture:
    def _make_capture(self):
        from computer_use.platform.linux import GnomeScreenCapture
        return GnomeScreenCapture()

    @patch("subprocess.run")
    def test_capture_full_reads_png(self, mock_run):
        fake_png = b"\x89PNG\r\n\x1a\nfake"
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch("builtins.open", mock_open(read_data=fake_png)):
            with patch("computer_use.platform.linux.GnomeScreenCapture._read_image_size", return_value=(2560, 1440)):
                capture = self._make_capture()
                state = capture.capture_full()

        assert state.width == 2560
        assert state.height == 1440
        assert state.image_bytes == fake_png

    @patch("subprocess.run")
    def test_capture_full_handles_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b"cannot capture")

        capture = self._make_capture()
        with pytest.raises(ScreenCaptureError, match="gnome-screenshot failed"):
            capture.capture_full()


# -- Mss capture (X11) --


class TestMssScreenCapture:
    @patch("computer_use.platform.linux.mss_import")
    def test_capture_full(self, mock_mss_mod):
        from computer_use.platform.linux import MssScreenCapture

        fake_screenshot = MagicMock()
        fake_screenshot.width = 1920
        fake_screenshot.height = 1080
        fake_screenshot.size = (1920, 1080)
        fake_screenshot.bgra = b"\x00" * (1920 * 1080 * 4)

        mock_instance = MagicMock()
        mock_instance.monitors = [{}, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_instance.grab.return_value = fake_screenshot
        mock_mss_mod.mss.return_value = mock_instance

        capture = MssScreenCapture()
        state = capture.capture_full()

        assert state.width == 1920
        assert state.height == 1080
        assert len(state.image_bytes) > 0


# -- Backend integration --


class TestLinuxBackend:
    @patch("shutil.which", return_value="/usr/bin/xdotool")
    def test_is_available_with_xdotool(self, _mock):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is True

    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_not_available_without_xdotool_on_x11(self, _which, _wayland):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is False

    @patch("computer_use.platform.linux._create_screen_capture")
    def test_get_screen_capture_delegates_to_factory(self, mock_factory):
        from computer_use.platform.linux import LinuxBackend

        mock_capture = MagicMock()
        mock_factory.return_value = mock_capture

        backend = LinuxBackend()
        result = backend.get_screen_capture()
        assert result is mock_capture
        mock_factory.assert_called_once()


# -- Scale factor detection --


class TestScaleFactor:
    def test_reads_gdk_scale(self):
        from computer_use.platform.linux import _get_scale_factor

        with patch.dict(os.environ, {"GDK_SCALE": "2"}):
            assert _get_scale_factor() == 2.0

    def test_defaults_to_one(self):
        with patch.dict(os.environ, {}, clear=True):
            from computer_use.platform.linux import _get_scale_factor
            assert _get_scale_factor() == 1.0

    def test_handles_bad_value(self):
        from computer_use.platform.linux import _get_scale_factor

        with patch.dict(os.environ, {"GDK_SCALE": "not_a_number"}):
            assert _get_scale_factor() == 1.0


# -- Mutter RemoteDesktop executor --


def _mock_mutter_session():
    """Create mock DBus session for MutterRemoteDesktopExecutor testing."""
    mock_bus = MagicMock()

    # Chain of object/interface mocks
    mock_session = MagicMock()
    mock_session_props = MagicMock()
    mock_session_props.Get.return_value = "test-session-id"

    mock_sc_session = MagicMock()
    mock_sc_session.RecordMonitor.return_value = "/org/gnome/Mutter/ScreenCast/Stream/u1"

    def get_object(service, path):
        obj = MagicMock()
        if "RemoteDesktop/Session" in path:
            obj_iface = MagicMock()
            def iface_selector(name):
                if "Properties" in name:
                    return mock_session_props
                return mock_session
            obj_iface.side_effect = iface_selector
            # dbus.Interface(obj, name) should return the right mock
        elif "ScreenCast/Session" in path:
            pass
        return obj

    mock_bus.get_object = MagicMock(side_effect=get_object)

    return mock_bus, mock_session


class TestMutterRemoteDesktopExecutor:
    def _make_executor(self):
        from computer_use.platform.linux import MutterRemoteDesktopExecutor

        with patch("computer_use.platform.linux.MutterRemoteDesktopExecutor._setup_session"):
            ex = MutterRemoteDesktopExecutor()
            # Wire up a mock session manually
            ex._session = MagicMock()
            ex._stream_path = "/org/gnome/Mutter/ScreenCast/Stream/u1"
            ex._key_map = ex._key_map  # already built from ecodes
            return ex

    def test_move_mouse_absolute(self):
        ex = self._make_executor()
        ex.move_mouse(500, 400)
        ex._session.NotifyPointerMotionAbsolute.assert_called_once()
        args = ex._session.NotifyPointerMotionAbsolute.call_args[0]
        assert args[0] == ex._stream_path

    def test_click(self):
        ex = self._make_executor()
        ex.click(300, 200)
        # Should move + button press + release
        ex._session.NotifyPointerMotionAbsolute.assert_called()
        btn_calls = ex._session.NotifyPointerButton.call_args_list
        assert len(btn_calls) == 2  # press and release

    def test_right_click(self):
        ex = self._make_executor()
        ex.click(300, 200, button="right")
        btn_calls = ex._session.NotifyPointerButton.call_args_list
        # Button 273 = BTN_RIGHT
        assert any("273" in str(c) for c in btn_calls)

    def test_double_click(self):
        ex = self._make_executor()
        ex.double_click(300, 200)
        btn_calls = ex._session.NotifyPointerButton.call_args_list
        # 4 calls: press, release, press, release
        assert len(btn_calls) == 4

    def test_key_press(self):
        ex = self._make_executor()
        ex.key_press(["ctrl", "c"])
        keycode_calls = ex._session.NotifyKeyboardKeycode.call_args_list
        # ctrl down, c down, c up, ctrl up
        assert len(keycode_calls) == 4

    def test_type_text_short_uses_keys(self):
        ex = self._make_executor()
        ex.type_text("ab")
        keycode_calls = ex._session.NotifyKeyboardKeycode.call_args_list
        assert len(keycode_calls) >= 4  # a down/up, b down/up

    @patch("subprocess.run")
    def test_type_text_long_types_each_char(self, mock_run):
        ex = self._make_executor()
        ex.type_text("hello")

        # Should NOT use clipboard (no subprocess calls)
        mock_run.assert_not_called()
        # Each char gets a key down + key up event
        keycode_calls = ex._session.NotifyKeyboardKeycode.call_args_list
        assert len(keycode_calls) >= 10  # 5 chars * 2 events each

    def test_type_text_newline_sends_enter(self):
        ex = self._make_executor()
        ex.type_text("a\nb")

        calls = ex._session.NotifyKeyboardKeycode.call_args_list
        # a(down,up) + enter(down,up) + b(down,up) = 6 events
        assert len(calls) >= 6
        # NotifyKeyboardKeycode(keycode, down) -- positional args
        pressed_keys = [c[0][0] for c in calls if c[0][1]]
        assert 28 in pressed_keys  # 28 = enter

    def test_type_text_uppercase_uses_shift(self):
        ex = self._make_executor()
        ex.type_text("Hi")

        calls = ex._session.NotifyKeyboardKeycode.call_args_list
        # H needs shift: shift(down) + h(down) + h(up) + shift(up) + i(down) + i(up) = 6
        assert len(calls) >= 6
        pressed_keys = [c[0][0] for c in calls if c[0][1]]
        assert 42 in pressed_keys  # 42 = shift

    def test_type_text_space_works(self):
        ex = self._make_executor()
        ex.type_text("a b")

        calls = ex._session.NotifyKeyboardKeycode.call_args_list
        # a(down,up) + space(down,up) + b(down,up) = 6 events
        assert len(calls) >= 6
        pressed_keys = [c[0][0] for c in calls if c[0][1]]
        assert 57 in pressed_keys  # 57 = space

    def test_scroll(self):
        ex = self._make_executor()
        ex.scroll(400, 300, -3)
        axis_calls = ex._session.NotifyPointerAxisDiscrete.call_args_list
        assert len(axis_calls) == 3

    def test_drag(self):
        ex = self._make_executor()
        ex.drag(100, 100, 500, 500, duration=0.1)
        # Should have button press + multiple moves + button release
        ex._session.NotifyPointerMotionAbsolute.assert_called()
        btn_calls = ex._session.NotifyPointerButton.call_args_list
        assert len(btn_calls) == 2  # press and release

    def test_close_stops_session(self):
        ex = self._make_executor()
        session = ex._session
        ex.close()
        session.Stop.assert_called_once()
        assert ex._session is None


class TestIsMutterAvailable:
    @patch("computer_use.platform.linux.dbus_import")
    def test_available_when_dbus_works(self, mock_dbus):
        from computer_use.platform.linux import _is_mutter_available
        assert _is_mutter_available() is True

    @patch("computer_use.platform.linux.dbus_import", None)
    def test_not_available_without_dbus(self):
        from computer_use.platform.linux import _is_mutter_available
        assert _is_mutter_available() is False

    @patch("computer_use.platform.linux.dbus_import")
    def test_not_available_on_error(self, mock_dbus):
        from computer_use.platform.linux import _is_mutter_available
        mock_dbus.SessionBus.side_effect = Exception("no bus")
        assert _is_mutter_available() is False


# -- Evdev action executor --


def _mock_evdev():
    """Create mock evdev module and devices for testing."""
    from computer_use.platform.linux import ecodes

    # Mock mouse with ABS support (like VBox tablet)
    mouse = MagicMock()
    mouse.name = "VirtualBox USB Tablet"
    mouse.path = "/dev/input/event5"
    abs_x_info = MagicMock(max=32767)
    abs_y_info = MagicMock(max=32767)
    mouse.capabilities.return_value = {
        ecodes.EV_ABS: [
            (ecodes.ABS_X, abs_x_info),
            (ecodes.ABS_Y, abs_y_info),
        ],
        ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE],
        ecodes.EV_REL: [ecodes.REL_WHEEL],
    }

    # Mock keyboard
    kbd = MagicMock()
    kbd.name = "AT Translated Set 2 keyboard"
    kbd.path = "/dev/input/event2"
    kbd.capabilities.return_value = {
        ecodes.EV_KEY: list(range(ecodes.KEY_A, ecodes.KEY_Z + 1)),
    }

    return mouse, kbd


class TestEvdevActionExecutor:
    def _make_executor(self):
        from computer_use.platform.linux import EvdevActionExecutor
        mouse, kbd = _mock_evdev()
        return EvdevActionExecutor(mouse, kbd, screen_w=1920, screen_h=1080)

    def test_move_mouse_abs(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.move_mouse(960, 540)

        # Filter for EV_ABS events only
        calls = ex._mouse.write.call_args_list
        abs_x_call = [c for c in calls if c[0][0] == ecodes.EV_ABS and c[0][1] == ecodes.ABS_X]
        abs_y_call = [c for c in calls if c[0][0] == ecodes.EV_ABS and c[0][1] == ecodes.ABS_Y]
        assert len(abs_x_call) == 1
        assert len(abs_y_call) == 1
        # Center of 1920 screen on 0-32767 range should be ~16383
        assert abs(abs_x_call[0][0][2] - 16383) < 2

    def test_click_sends_button_events(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.click(100, 100)

        calls = ex._mouse.write.call_args_list
        btn_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # Should have press (1) and release (0)
        assert any(c[0][2] == 1 for c in btn_calls)  # press
        assert any(c[0][2] == 0 for c in btn_calls)  # release

    def test_right_click(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.click(100, 100, button="right")

        calls = ex._mouse.write.call_args_list
        btn_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY and c[0][1] == ecodes.BTN_RIGHT]
        assert len(btn_calls) == 2  # press + release

    def test_double_click(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.double_click(100, 100)

        calls = ex._mouse.write.call_args_list
        btn_presses = [c for c in calls if c[0][0] == ecodes.EV_KEY and c[0][2] == 1]
        assert len(btn_presses) == 2  # two clicks

    def test_scroll(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.scroll(100, 100, -3)

        calls = ex._mouse.write.call_args_list
        wheel_calls = [c for c in calls if c[0][0] == ecodes.EV_REL and c[0][1] == ecodes.REL_WHEEL]
        assert len(wheel_calls) == 3
        assert all(c[0][2] == -1 for c in wheel_calls)

    def test_key_press(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.key_press(["ctrl", "c"])

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # Ctrl down, C down, C up, Ctrl up
        assert len(key_calls) == 4

    def test_type_text_short_uses_keys(self):
        """Short text (<=3 chars) should type char-by-char, not clipboard."""
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.type_text("hi")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        assert len(key_calls) >= 4  # h down/up, i down/up

    @patch("subprocess.run")
    def test_type_text_long_types_each_char(self, mock_run):
        """Long text should type each character individually, not clipboard paste."""
        from computer_use.platform.linux import ecodes
        mock_run.return_value = MagicMock(returncode=0)

        ex = self._make_executor()
        ex.type_text("hello")

        # Should NOT use clipboard
        mock_run.assert_not_called()
        # Each char gets key down + key up + syn events
        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        assert len(key_calls) >= 10  # 5 chars * 2 (press + release)

    def test_type_text_newline_sends_enter(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.type_text("a\nb")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # a(down,up) + enter(down,up) + b(down,up) = 6 key events
        assert len(key_calls) >= 6
        pressed_keycodes = [c[0][1] for c in key_calls if c[0][2] == 1]
        assert ecodes.KEY_ENTER in pressed_keycodes

    def test_type_text_uppercase_uses_shift(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.type_text("Hi")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # H needs shift: shift(down) + h(down) + h(up) + shift(up) + i(down) + i(up) = 6
        assert len(key_calls) >= 6
        pressed_keycodes = [c[0][1] for c in key_calls if c[0][2] == 1]
        assert ecodes.KEY_LEFTSHIFT in pressed_keycodes

    def test_type_text_space_works(self):
        from computer_use.platform.linux import ecodes
        ex = self._make_executor()
        ex.type_text("a b")

        calls = ex._kbd.write.call_args_list
        key_calls = [c for c in calls if c[0][0] == ecodes.EV_KEY]
        # a(down,up) + space(down,up) + b(down,up) = 6 key events
        assert len(key_calls) >= 6
        pressed_keycodes = [c[0][1] for c in key_calls if c[0][2] == 1]
        assert ecodes.KEY_SPACE in pressed_keycodes


# -- Action executor factory --


class TestCreateActionExecutor:
    @patch("computer_use.platform.linux._is_wayland", return_value=False)
    def test_x11_returns_xdotool(self, _mock):
        from computer_use.platform.linux import _create_action_executor, LinuxActionExecutor
        ex = _create_action_executor()
        assert isinstance(ex, LinuxActionExecutor)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=True)
    def test_wayland_gnome_returns_mutter(self, _mutter, _wayland):
        from computer_use.platform.linux import _create_action_executor, MutterRemoteDesktopExecutor
        with patch("computer_use.platform.linux.MutterRemoteDesktopExecutor._setup_session"):
            ex = _create_action_executor()
            assert isinstance(ex, MutterRemoteDesktopExecutor)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux._find_evdev_mouse")
    @patch("computer_use.platform.linux._find_evdev_keyboard")
    def test_wayland_no_mutter_returns_evdev(self, mock_kbd, mock_mouse, _mutter, _wayland):
        from computer_use.platform.linux import _create_action_executor, EvdevActionExecutor

        mouse, kbd = _mock_evdev()
        mock_mouse.return_value = mouse
        mock_kbd.return_value = kbd

        ex = _create_action_executor()
        assert isinstance(ex, EvdevActionExecutor)

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux._find_evdev_mouse", return_value=None)
    @patch("computer_use.platform.linux._find_evdev_keyboard", return_value=None)
    def test_wayland_no_mutter_no_evdev_falls_back(self, _kbd, _mouse, _mutter, _wayland):
        from computer_use.platform.linux import _create_action_executor, LinuxActionExecutor
        ex = _create_action_executor()
        assert isinstance(ex, LinuxActionExecutor)


# -- Backend is_available --


class TestLinuxBackendAvailability:
    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=True)
    def test_available_on_wayland_with_mutter(self, _mutter, _wayland):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is True

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux.evdev_import", new_callable=lambda: MagicMock)
    def test_available_on_wayland_with_evdev(self, _evdev, _mutter, _wayland):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is True

    @patch("computer_use.platform.linux._is_wayland", return_value=True)
    @patch("computer_use.platform.linux._is_mutter_available", return_value=False)
    @patch("computer_use.platform.linux.evdev_import", None)
    @patch("shutil.which", return_value=None)
    def test_not_available_wayland_nothing(self, _which, _mutter, _wayland):
        from computer_use.platform.linux import LinuxBackend
        assert LinuxBackend().is_available() is False


# -- Foreground window detection --


class TestForegroundWindowXdotool:
    """Tests for X11 foreground window detection via xdotool."""

    @patch("subprocess.run")
    def test_parses_xdotool_output(self, mock_run):
        from computer_use.platform.linux import _query_foreground_window_xdotool

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="My Window Title\nX=100\nY=200\nWIDTH=800\nHEIGHT=600\n1234\n",
        )
        with patch("builtins.open", mock_open(read_data="firefox\n")):
            result = _query_foreground_window_xdotool()
        assert result is not None
        assert result.app_name == "firefox"
        assert result.title == "My Window Title"
        assert result.x == 100
        assert result.y == 200
        assert result.width == 800
        assert result.height == 600
        assert result.pid == 1234

    @patch("subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        from computer_use.platform.linux import _query_foreground_window_xdotool

        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _query_foreground_window_xdotool() is None

    @patch("subprocess.run", side_effect=Exception("timeout"))
    def test_returns_none_on_exception(self, _run):
        from computer_use.platform.linux import _query_foreground_window_xdotool

        assert _query_foreground_window_xdotool() is None


class TestForegroundWindowWayland:
    """Tests for Wayland foreground window detection via AT-SPI2."""

    def _make_mock_window(self, app_name, title, pid, active, x, y, w, h):
        """Build a mock AT-SPI2 window accessible."""
        window = MagicMock()
        window.get_name.return_value = title
        window.get_process_id.return_value = pid

        rect = MagicMock()
        rect.x, rect.y, rect.width, rect.height = x, y, w, h
        window.get_extents.return_value = rect

        ss = MagicMock()
        ss.contains.side_effect = lambda st: (
            active if st.value_name == "ATSPI_STATE_ACTIVE" else False
        )
        window.get_state_set.return_value = ss
        return window

    def _make_mock_app(self, name, windows):
        app = MagicMock()
        app.get_name.return_value = name
        app.get_child_count.return_value = len(windows)
        app.get_child_at_index.side_effect = lambda i: windows[i]
        return app

    @patch("computer_use.platform.linux._query_foreground_window_wayland")
    def test_dispatch_uses_wayland_on_wayland(self, mock_wayland):
        from computer_use.platform.linux import (
            _query_foreground_window, _fg_window_cache,
        )
        import computer_use.platform.linux as linux_mod

        # Clear the cache
        linux_mod._fg_window_cache = None
        mock_wayland.return_value = MagicMock(app_name="firefox")

        with patch("computer_use.platform.linux._is_wayland", return_value=True):
            result = _query_foreground_window()
        assert result.app_name == "firefox"
        mock_wayland.assert_called_once()

    @patch("computer_use.platform.linux._query_foreground_window_xdotool")
    def test_dispatch_uses_xdotool_on_x11(self, mock_xdotool):
        from computer_use.platform.linux import _query_foreground_window
        import computer_use.platform.linux as linux_mod

        linux_mod._fg_window_cache = None
        mock_xdotool.return_value = MagicMock(app_name="gedit")

        with patch("computer_use.platform.linux._is_wayland", return_value=False):
            result = _query_foreground_window()
        assert result.app_name == "gedit"
        mock_xdotool.assert_called_once()

    @patch("computer_use.platform.linux._query_foreground_window_xdotool")
    @patch("computer_use.platform.linux._query_foreground_window_wayland")
    def test_dispatch_falls_back_to_xdotool_when_wayland_returns_none(
        self, mock_wayland, mock_xdotool,
    ):
        from computer_use.platform.linux import _query_foreground_window
        import computer_use.platform.linux as linux_mod

        linux_mod._fg_window_cache = None
        mock_wayland.return_value = None
        mock_xdotool.return_value = MagicMock(app_name="xterm")

        with patch("computer_use.platform.linux._is_wayland", return_value=True):
            result = _query_foreground_window()
        assert result.app_name == "xterm"

    def test_picks_last_active_window(self):
        """When multiple windows are ACTIVE, the last one in the tree wins."""
        from computer_use.platform.linux import _query_foreground_window_wayland

        win_chrome = self._make_mock_window(
            "chrome", "Google Chrome", 100, True, 0, 0, 1920, 1080,
        )
        win_terminal = self._make_mock_window(
            "gnome-terminal-", "Terminal", 200, True, 0, 0, 800, 600,
        )
        app_chrome = self._make_mock_app("Google Chrome", [win_chrome])
        app_terminal = self._make_mock_app("gnome-terminal-server", [win_terminal])

        desktop = MagicMock()
        desktop.get_child_count.return_value = 2
        desktop.get_child_at_index.side_effect = [app_chrome, app_terminal]

        mock_atspi = MagicMock()
        mock_atspi.init.return_value = None
        mock_atspi.get_desktop.return_value = desktop
        mock_atspi.CoordType.SCREEN = "SCREEN"

        # Mock StateType so .contains() comparison works
        active_state = MagicMock()
        active_state.value_name = "ATSPI_STATE_ACTIVE"
        mock_atspi.StateType.ACTIVE = active_state

        mock_gi = MagicMock()
        mock_gi.repository.Atspi = mock_atspi

        with patch.dict("sys.modules", {"gi": mock_gi, "gi.repository": mock_gi.repository}):
            result = _query_foreground_window_wayland()

        assert result is not None
        # Last active window wins — terminal is last in tree
        assert result.pid == 200

    def test_returns_none_when_no_active_windows(self):
        from computer_use.platform.linux import _query_foreground_window_wayland

        win = self._make_mock_window("app", "Window", 100, False, 0, 0, 800, 600)
        app = self._make_mock_app("SomeApp", [win])

        desktop = MagicMock()
        desktop.get_child_count.return_value = 1
        desktop.get_child_at_index.side_effect = [app]

        mock_atspi = MagicMock()
        mock_atspi.init.return_value = None
        mock_atspi.get_desktop.return_value = desktop
        mock_atspi.CoordType.SCREEN = "SCREEN"

        active_state = MagicMock()
        active_state.value_name = "ATSPI_STATE_ACTIVE"
        mock_atspi.StateType.ACTIVE = active_state

        mock_gi = MagicMock()
        mock_gi.repository.Atspi = mock_atspi

        with patch.dict("sys.modules", {"gi": mock_gi, "gi.repository": mock_gi.repository}):
            result = _query_foreground_window_wayland()

        assert result is None

    def test_returns_none_when_atspi_not_available(self):
        from computer_use.platform.linux import _query_foreground_window_wayland

        with patch.dict("sys.modules", {"gi": None}):
            result = _query_foreground_window_wayland()
        assert result is None

    def test_reads_app_name_from_proc_comm(self):
        from computer_use.platform.linux import _query_foreground_window_wayland

        win = self._make_mock_window("", "My App", 42, True, 10, 20, 500, 400)
        app = self._make_mock_app("MyApp", [win])

        desktop = MagicMock()
        desktop.get_child_count.return_value = 1
        desktop.get_child_at_index.side_effect = [app]

        mock_atspi = MagicMock()
        mock_atspi.init.return_value = None
        mock_atspi.get_desktop.return_value = desktop
        mock_atspi.CoordType.SCREEN = "SCREEN"

        active_state = MagicMock()
        active_state.value_name = "ATSPI_STATE_ACTIVE"
        mock_atspi.StateType.ACTIVE = active_state

        mock_gi = MagicMock()
        mock_gi.repository.Atspi = mock_atspi

        with patch.dict("sys.modules", {"gi": mock_gi, "gi.repository": mock_gi.repository}):
            with patch("builtins.open", mock_open(read_data="firefox\n")):
                result = _query_foreground_window_wayland()

        assert result is not None
        assert result.app_name == "firefox"
        assert result.title == "My App"
        assert result.x == 10
        assert result.width == 500
