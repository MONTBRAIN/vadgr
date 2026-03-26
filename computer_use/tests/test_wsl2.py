"""Tests for the WSL2 platform backend."""

import subprocess
from unittest.mock import MagicMock, patch, mock_open, PropertyMock, call

import pytest

from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.types import Region, ScreenState
from computer_use.platform.wsl2 import (
    wsl_to_win_path,
    win_to_wsl_path,
    PersistentPowerShell,
    WSL2ScreenCapture,
    WSL2ActionExecutor,
    WSL2Backend,
    _get_windows_temp_dir,
    _run_ps,
    _run_ps_subprocess,
    POWERSHELL,
    VK_CODES,
    SENDKEYS_MAP,
    MODIFIER_MAP,
)


# --- Path conversion ---


class TestWslToWinPath:
    def test_mnt_drive_path(self):
        assert wsl_to_win_path("/mnt/c/Users/test") == "C:\\Users\\test"

    def test_mnt_drive_with_subdirs(self):
        assert wsl_to_win_path("/mnt/d/some/deep/path") == "D:\\some\\deep\\path"

    def test_non_mnt_path_unchanged(self):
        assert wsl_to_win_path("/home/user/file.txt") == "/home/user/file.txt"

    def test_mnt_root(self):
        assert wsl_to_win_path("/mnt/c") == "C:"

    def test_drive_letter_uppercased(self):
        assert wsl_to_win_path("/mnt/e/data") == "E:\\data"


class TestWinToWslPath:
    def test_windows_drive_path(self):
        assert win_to_wsl_path("C:\\Users\\test") == "/mnt/c/Users/test"

    def test_drive_letter_lowered(self):
        assert win_to_wsl_path("D:\\Files") == "/mnt/d/Files"

    def test_no_colon_unchanged(self):
        assert win_to_wsl_path("/some/unix/path") == "/some/unix/path"

    def test_short_string_no_colon(self):
        assert win_to_wsl_path("X") == "X"

    def test_empty_string(self):
        assert win_to_wsl_path("") == ""


# --- PersistentPowerShell ---


class TestPersistentPowerShell:
    def _make_mock_proc(self, poll_return=None):
        proc = MagicMock()
        proc.poll.return_value = poll_return
        proc.pid = 12345
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        return proc

    @patch("computer_use.platform.wsl2.subprocess.Popen")
    def test_run_reads_until_sentinel(self, mock_popen):
        proc = self._make_mock_proc()
        mock_popen.return_value = proc

        ps = PersistentPowerShell()

        # Capture every sentinel written to stdin (DPI init + run call)
        sentinels = []

        def fake_write(text):
            for line in text.strip().split("\n"):
                if line.startswith("Write-Output '"):
                    sentinels.append(line.split("'")[1])

        proc.stdin.write.side_effect = fake_write

        # readline must serve the DPI init sentinel first (from _start),
        # then the actual output lines + sentinel for the run() call.
        def readline_gen():
            # Wait for DPI init sentinel to be captured, then yield it
            while not sentinels:
                pass
            yield sentinels[0] + "\n"
            # Now the run() call lines
            yield "output line 1\n"
            yield "output line 2\n"
            while len(sentinels) < 2:
                pass
            yield sentinels[1] + "\n"

        gen = readline_gen()
        proc.stdout.readline.side_effect = lambda: next(gen)

        result = ps.run("Get-Date")
        assert result == "output line 1\noutput line 2"

    @patch("computer_use.platform.wsl2.subprocess.Popen")
    def test_shutdown_terminates_process(self, mock_popen):
        proc = self._make_mock_proc()
        mock_popen.return_value = proc

        # DPI init sentinel: capture and immediately return it
        sentinels = []

        def capture_write(text):
            for line in text.strip().split("\n"):
                if line.startswith("Write-Output '"):
                    sentinels.append(line.split("'")[1])

        proc.stdin.write.side_effect = capture_write

        def readline_gen():
            while not sentinels:
                pass
            yield sentinels[0] + "\n"

        gen = readline_gen()
        proc.stdout.readline.side_effect = lambda: next(gen)

        ps = PersistentPowerShell()
        # Force start
        ps._start()
        assert ps._started is True

        ps.shutdown()
        proc.stdin.close.assert_called_once()
        proc.terminate.assert_called_once()
        assert ps._proc is None
        assert ps._started is False

    @patch("computer_use.platform.wsl2.subprocess.Popen")
    def test_restart_on_broken_pipe(self, mock_popen):
        first_proc = self._make_mock_proc()
        second_proc = self._make_mock_proc()
        mock_popen.side_effect = [first_proc, second_proc]

        # first_proc: DPI init write succeeds, DPI init readline returns sentinel,
        # then run() write raises BrokenPipeError
        first_sentinels = []
        first_write_count = [0]

        def first_write(text):
            first_write_count[0] += 1
            for line in text.strip().split("\n"):
                if line.startswith("Write-Output '"):
                    first_sentinels.append(line.split("'")[1])
            # DPI init write (call 1) succeeds; run() write (call 2) fails
            if first_write_count[0] >= 2:
                raise BrokenPipeError("pipe broken")

        first_proc.stdin.write.side_effect = first_write

        def first_readline_gen():
            while not first_sentinels:
                pass
            yield first_sentinels[0] + "\n"

        first_gen = first_readline_gen()
        first_proc.stdout.readline.side_effect = lambda: next(first_gen)

        # second_proc: DPI init + run() both succeed
        second_sentinels = []

        def second_write(text):
            for line in text.strip().split("\n"):
                if line.startswith("Write-Output '"):
                    second_sentinels.append(line.split("'")[1])

        second_proc.stdin.write.side_effect = second_write

        def second_readline_gen():
            # DPI init sentinel
            while not second_sentinels:
                pass
            yield second_sentinels[0] + "\n"
            # run() sentinel
            while len(second_sentinels) < 2:
                pass
            yield second_sentinels[1] + "\n"

        second_gen = second_readline_gen()
        second_proc.stdout.readline.side_effect = lambda: next(second_gen)

        ps = PersistentPowerShell()
        result = ps.run("test")
        assert result == ""
        # First proc should have been killed during restart
        first_proc.kill.assert_called()

    @patch("computer_use.platform.wsl2.subprocess.Popen")
    @patch("computer_use.platform.wsl2.time.monotonic")
    def test_timeout_raises_runtime_error(self, mock_monotonic, mock_popen):
        proc = self._make_mock_proc()
        mock_popen.return_value = proc

        # DPI init: capture sentinel and return it via readline
        sentinels = []

        def capture_write(text):
            for line in text.strip().split("\n"):
                if line.startswith("Write-Output '"):
                    sentinels.append(line.split("'")[1])

        proc.stdin.write.side_effect = capture_write

        readline_calls = [0]

        def fake_readline():
            readline_calls[0] += 1
            # First readline: return DPI init sentinel
            if readline_calls[0] == 1:
                return sentinels[0] + "\n" if sentinels else "\n"
            # Subsequent readlines: never return (simulates slow script)
            return "waiting...\n"

        proc.stdout.readline.side_effect = fake_readline

        ps = PersistentPowerShell()

        # monotonic: first call for deadline, then past deadline on loop check
        mock_monotonic.side_effect = [0.0, 100.0]

        with pytest.raises(RuntimeError, match="timed out"):
            ps.run("slow-script", timeout=5.0)

    @patch("computer_use.platform.wsl2.subprocess.Popen")
    def test_process_death_raises(self, mock_popen):
        proc = self._make_mock_proc(poll_return=None)
        mock_popen.return_value = proc

        # DPI init: capture sentinel and return it
        sentinels = []

        def capture_write(text):
            for line in text.strip().split("\n"):
                if line.startswith("Write-Output '"):
                    sentinels.append(line.split("'")[1])

        proc.stdin.write.side_effect = capture_write

        readline_calls = [0]

        def fake_readline():
            readline_calls[0] += 1
            if readline_calls[0] == 1 and sentinels:
                return sentinels[0] + "\n"
            return "waiting...\n"

        proc.stdout.readline.side_effect = fake_readline

        ps = PersistentPowerShell()

        # Process dies mid-read
        call_count = [0]

        def poll_side_effect():
            call_count[0] += 1
            if call_count[0] <= 2:
                return None  # alive during startup checks
            return 1  # dead during readline loop

        proc.poll.side_effect = poll_side_effect

        with pytest.raises(RuntimeError, match="died unexpectedly"):
            ps.run("doomed-script")

    @patch("computer_use.platform.wsl2.subprocess.Popen")
    def test_is_alive_true_when_running(self, mock_popen):
        proc = self._make_mock_proc(poll_return=None)
        mock_popen.return_value = proc

        sentinels = []
        proc.stdin.write.side_effect = lambda text: [
            sentinels.append(line.split("'")[1])
            for line in text.strip().split("\n")
            if line.startswith("Write-Output '")
        ]
        proc.stdout.readline.side_effect = lambda: (
            sentinels[-1] + "\n" if sentinels else "\n"
        )

        ps = PersistentPowerShell()
        ps._start()
        assert ps.is_alive is True

    @patch("computer_use.platform.wsl2.subprocess.Popen")
    def test_is_alive_false_when_dead(self, mock_popen):
        proc = self._make_mock_proc(poll_return=1)
        mock_popen.return_value = proc

        sentinels = []
        proc.stdin.write.side_effect = lambda text: [
            sentinels.append(line.split("'")[1])
            for line in text.strip().split("\n")
            if line.startswith("Write-Output '")
        ]
        proc.stdout.readline.side_effect = lambda: (
            sentinels[-1] + "\n" if sentinels else "\n"
        )

        ps = PersistentPowerShell()
        ps._start()
        assert ps.is_alive is False

    def test_is_alive_false_when_not_started(self):
        ps = PersistentPowerShell()
        assert ps.is_alive is False


# --- WSL2ScreenCapture ---


class TestWSL2ScreenCapture:
    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", return_value="1920,1080,0,0")
    @patch("builtins.open", mock_open(read_data=b"fake-png-data"))
    @patch("os.unlink")
    def test_capture_full_parses_dimensions(self, _unlink, mock_ps, _temp):
        cap = WSL2ScreenCapture()
        # Also mock get_scale_factor to avoid calling _run_ps again
        with patch.object(cap, "get_scale_factor", return_value=1.0):
            state = cap.capture_full()

        assert state.width == 1920
        assert state.height == 1080
        assert state.offset_x == 0
        assert state.offset_y == 0
        assert state.image_bytes == b"fake-png-data"

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", return_value="3840,2160,100,200")
    @patch("builtins.open", mock_open(read_data=b"img"))
    @patch("os.unlink")
    def test_capture_full_with_offset(self, _unlink, mock_ps, _temp):
        cap = WSL2ScreenCapture()
        with patch.object(cap, "get_scale_factor", return_value=1.5):
            state = cap.capture_full()

        assert state.width == 3840
        assert state.height == 2160
        assert state.offset_x == 100
        assert state.offset_y == 200
        assert state.scale_factor == 1.5

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("ps fail"))
    def test_capture_full_raises_on_ps_error(self, _ps, _temp):
        cap = WSL2ScreenCapture()
        with pytest.raises(ScreenCaptureError, match="Full screenshot failed"):
            cap.capture_full()

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", return_value="200,100")
    @patch("builtins.open", mock_open(read_data=b"region-data"))
    @patch("os.unlink")
    def test_capture_region(self, _unlink, _ps, _temp):
        cap = WSL2ScreenCapture()
        region = Region(x=10, y=20, width=200, height=100)
        with patch.object(cap, "get_scale_factor", return_value=1.0):
            state = cap.capture_region(region)

        assert state.width == 200
        assert state.height == 100
        assert state.image_bytes == b"region-data"

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("fail"))
    def test_capture_region_raises_on_error(self, _ps, _temp):
        cap = WSL2ScreenCapture()
        region = Region(x=0, y=0, width=100, height=100)
        with pytest.raises(ScreenCaptureError, match="Region screenshot failed"):
            cap.capture_region(region)

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", return_value="2560,1440")
    def test_get_screen_size(self, _ps, _temp):
        cap = WSL2ScreenCapture()
        w, h = cap.get_screen_size()
        assert w == 2560
        assert h == 1440

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("fail"))
    def test_get_screen_size_raises_on_error(self, _ps, _temp):
        cap = WSL2ScreenCapture()
        with pytest.raises(ScreenCaptureError, match="Cannot get screen size"):
            cap.get_screen_size()

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", return_value="1.25")
    def test_get_scale_factor(self, _ps, _temp):
        cap = WSL2ScreenCapture()
        assert cap.get_scale_factor() == 1.25

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("no dpi"))
    def test_get_scale_factor_defaults_on_error(self, _ps, _temp):
        cap = WSL2ScreenCapture()
        assert cap.get_scale_factor() == 1.0


# --- WSL2ActionExecutor ---


class TestWSL2ActionExecutor:
    @patch("computer_use.platform.wsl2._run_ps")
    def test_click_left(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.click(100, 200, button="left")
        script = mock_ps.call_args[0][0]
        assert "MOUSEEVENTF_LEFTDOWN" in script
        assert "MOUSEEVENTF_LEFTUP" in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_click_right(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.click(100, 200, button="right")
        script = mock_ps.call_args[0][0]
        assert "MOUSEEVENTF_RIGHTDOWN" in script
        assert "MOUSEEVENTF_RIGHTUP" in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_click_middle(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.click(100, 200, button="middle")
        script = mock_ps.call_args[0][0]
        assert "MOUSEEVENTF_MIDDLEDOWN" in script
        assert "MOUSEEVENTF_MIDDLEUP" in script

    def test_click_unknown_button_raises(self):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Unknown mouse button"):
            exe.click(100, 200, button="extra")

    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("fail"))
    def test_click_wraps_error(self, _ps):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Click failed"):
            exe.click(50, 50)

    @patch("computer_use.platform.wsl2._run_ps")
    def test_double_click(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.double_click(300, 400)
        script = mock_ps.call_args[0][0]
        # Count actual mouse_event calls (not the const declarations in the class)
        assert script.count("[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN") == 2
        assert script.count("[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP") == 2

    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("err"))
    def test_double_click_wraps_error(self, _ps):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Double-click failed"):
            exe.double_click(10, 20)

    @patch("computer_use.platform.wsl2._run_ps")
    def test_type_text_escapes_special_chars(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.type_text("hello+world{test}")
        script = mock_ps.call_args[0][0]
        # + should become {+}, { should become {{}, } should become {}}
        assert "{+}" in script
        assert "{{}" in script  # escaped {
        assert "{}}" in script  # escaped }

    @patch("computer_use.platform.wsl2._run_ps")
    def test_type_text_plain(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.type_text("abc123")
        script = mock_ps.call_args[0][0]
        assert "abc123" in script

    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("fail"))
    def test_type_text_wraps_error(self, _ps):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Type text failed"):
            exe.type_text("oops")

    @patch("computer_use.platform.wsl2._run_ps")
    def test_key_press_sendkeys_route(self, mock_ps):
        """ctrl+c should go through SendKeys path."""
        exe = WSL2ActionExecutor()
        exe.key_press(["ctrl", "c"])
        script = mock_ps.call_args[0][0]
        assert "SendKeys" in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_key_press_keybd_route_for_win(self, mock_ps):
        """Win key combos should use keybd_event."""
        exe = WSL2ActionExecutor()
        exe.key_press(["win", "d"])
        script = mock_ps.call_args[0][0]
        assert "keybd_event" in script
        assert str(VK_CODES["win"]) in script
        assert str(VK_CODES["d"]) in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_key_press_empty_list_noop(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.key_press([])
        mock_ps.assert_not_called()

    def test_key_press_keybd_unknown_key_raises(self):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Unknown key for keybd_event"):
            exe._key_press_via_keybd(["win", "nonexistent_key"])

    @patch("computer_use.platform.wsl2._run_ps")
    def test_key_press_sendkeys_modifier_only(self, mock_ps):
        """Pressing just a modifier should produce an empty key string."""
        exe = WSL2ActionExecutor()
        exe.key_press(["alt"])
        script = mock_ps.call_args[0][0]
        assert "SendKeys" in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_key_press_sendkeys_multiple_regular(self, mock_ps):
        """Multiple regular keys should be wrapped in parens."""
        exe = WSL2ActionExecutor()
        exe.key_press(["ctrl", "a", "b"])
        script = mock_ps.call_args[0][0]
        # a and b are regular keys, should be grouped: ^(ab)
        assert "(ab)" in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_scroll(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.scroll(500, 600, 3)
        script = mock_ps.call_args[0][0]
        # 3 * 120 = 360
        assert "360" in script
        assert "MOUSEEVENTF_WHEEL" in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_scroll_negative(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.scroll(500, 600, -2)
        script = mock_ps.call_args[0][0]
        assert "-240" in script

    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("fail"))
    def test_scroll_wraps_error(self, _ps):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Scroll failed"):
            exe.scroll(0, 0, 1)

    @patch("computer_use.platform.wsl2._run_ps")
    def test_drag(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.drag(10, 20, 300, 400, duration=0.5)
        script = mock_ps.call_args[0][0]
        assert "MOUSEEVENTF_LEFTDOWN" in script
        assert "MOUSEEVENTF_LEFTUP" in script
        assert "10" in script
        assert "20" in script

    @patch("computer_use.platform.wsl2._run_ps")
    def test_drag_timeout_includes_duration(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.drag(0, 0, 100, 100, duration=2.0)
        # timeout should be duration + 10
        assert mock_ps.call_args[1]["timeout"] == 12.0

    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("fail"))
    def test_drag_wraps_error(self, _ps):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Drag failed"):
            exe.drag(0, 0, 10, 10)

    @patch("computer_use.platform.wsl2._run_ps")
    def test_move_mouse(self, mock_ps):
        exe = WSL2ActionExecutor()
        exe.move_mouse(150, 250)
        script = mock_ps.call_args[0][0]
        assert "150" in script
        assert "250" in script

    @patch("computer_use.platform.wsl2._run_ps", side_effect=RuntimeError("fail"))
    def test_move_mouse_wraps_error(self, _ps):
        exe = WSL2ActionExecutor()
        with pytest.raises(ActionError, match="Mouse move failed"):
            exe.move_mouse(0, 0)


# --- WSL2Backend ---


class TestWSL2Backend:
    @patch("shutil.which", return_value="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    def test_is_available_true_powershell(self, _which):
        backend = WSL2Backend()
        assert backend.is_available() is True

    @patch.object(WSL2Backend, "_probe_bridge", return_value=True)
    @patch("shutil.which", return_value=None)
    def test_is_available_true_bridge_daemon(self, _which, _bridge):
        """Available when bridge daemon is reachable even without powershell on PATH."""
        backend = WSL2Backend()
        assert backend.is_available() is True

    @patch.object(WSL2Backend, "_probe_bridge", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_is_available_false(self, _which, _bridge):
        """Not available when neither powershell nor bridge daemon are reachable."""
        backend = WSL2Backend()
        assert backend.is_available() is False

    @patch.object(WSL2Backend, "_probe_bridge", return_value=False)
    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    def test_get_screen_capture_cached(self, _temp, _bridge):
        """Calling get_screen_capture twice returns the same instance."""
        backend = WSL2Backend()
        cap1 = backend.get_screen_capture()
        cap2 = backend.get_screen_capture()
        assert cap1 is cap2

    @patch.object(WSL2Backend, "_probe_bridge", return_value=False)
    def test_get_action_executor_cached(self, _bridge):
        """Calling get_action_executor twice returns the same instance."""
        backend = WSL2Backend()
        exe1 = backend.get_action_executor()
        exe2 = backend.get_action_executor()
        assert exe1 is exe2


# --- _get_windows_temp_dir ---


class TestGetWindowsTempDir:
    @patch("os.path.isdir")
    def test_first_candidate_found(self, mock_isdir):
        mock_isdir.return_value = True
        with patch.dict("os.environ", {"USER": "testuser"}):
            result = _get_windows_temp_dir()
        assert result == "/mnt/c/Users/testuser/AppData/Local/Temp"

    @patch("os.path.isdir")
    def test_second_candidate_found(self, mock_isdir):
        def isdir_side(path):
            return path == "/mnt/c/Temp"

        mock_isdir.side_effect = isdir_side
        with patch.dict("os.environ", {"USER": "testuser"}):
            result = _get_windows_temp_dir()
        assert result == "/mnt/c/Temp"

    @patch("os.path.isdir", return_value=False)
    @patch("computer_use.platform.wsl2.subprocess.run")
    def test_powershell_fallback(self, mock_run, _isdir):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="C:\\Users\\test\\AppData\\Local\\Temp\n"
        )
        with patch.dict("os.environ", {"USER": "testuser"}):
            result = _get_windows_temp_dir()
        assert result == "/mnt/c/Users/test/AppData/Local/Temp"

    @patch("os.path.isdir", return_value=False)
    @patch("computer_use.platform.wsl2.subprocess.run")
    def test_raises_when_all_fail(self, mock_run, _isdir):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        with patch.dict("os.environ", {"USER": "testuser"}):
            with pytest.raises(ScreenCaptureError, match="Cannot determine Windows temp"):
                _get_windows_temp_dir()


# --- _run_ps ---


class TestRunPs:
    @patch("computer_use.platform.wsl2._persistent_ps_lock", MagicMock())
    @patch("computer_use.platform.wsl2._persistent_ps")
    def test_tries_persistent_first(self, mock_ps_singleton):
        mock_ps_singleton.run.return_value = "ok"
        # Reset the module singleton so _run_ps sees our mock
        with patch("computer_use.platform.wsl2._persistent_ps", mock_ps_singleton):
            result = _run_ps("Get-Date")
        assert result == "ok"
        mock_ps_singleton.run.assert_called_once()

    @patch("computer_use.platform.wsl2._run_ps_subprocess", return_value="fallback ok")
    @patch("computer_use.platform.wsl2._persistent_ps_lock", MagicMock())
    def test_falls_back_to_subprocess_on_error(self, mock_subprocess):
        failing_ps = MagicMock()
        failing_ps.run.side_effect = RuntimeError("persistent failed")
        with patch("computer_use.platform.wsl2._persistent_ps", failing_ps):
            result = _run_ps("Get-Date")
        assert result == "fallback ok"
        mock_subprocess.assert_called_once()


# --- _run_ps_subprocess ---


class TestRunPsSubprocess:
    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2.subprocess.run")
    @patch("builtins.open", mock_open())
    @patch("os.unlink")
    def test_success(self, _unlink, mock_run, _temp):
        mock_run.return_value = MagicMock(returncode=0, stdout="result\n", stderr="")
        result = _run_ps_subprocess("echo hello")
        assert result == "result"

    @patch("computer_use.platform.wsl2._get_windows_temp_dir", return_value="/mnt/c/tmp")
    @patch("computer_use.platform.wsl2.subprocess.run")
    @patch("builtins.open", mock_open())
    @patch("os.unlink")
    def test_nonzero_exit_raises(self, _unlink, mock_run, _temp):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="bad script")
        with pytest.raises(RuntimeError, match="PowerShell error"):
            _run_ps_subprocess("bad")
