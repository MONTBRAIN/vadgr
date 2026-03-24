"""Tests for api.utils.platform cross-platform utilities.

TDD: these tests are written BEFORE the implementation.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.utils.platform import (
    kill_process_tree,
    new_session_kwargs,
    python_command,
    remove_path_entry,
    resolve_command,
    venv_bin_dir,
    venv_pip,
    venv_python,
)


# ---------------------------------------------------------------------------
# python_command
# ---------------------------------------------------------------------------

class TestPythonCommand:
    def test_returns_string(self):
        result = python_command()
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("api.utils.platform.sys")
    def test_returns_python_on_windows(self, mock_sys):
        mock_sys.platform = "win32"
        assert python_command() == "python"

    @patch("api.utils.platform.sys")
    def test_returns_python3_on_linux(self, mock_sys):
        mock_sys.platform = "linux"
        assert python_command() == "python3"

    @patch("api.utils.platform.sys")
    def test_returns_python3_on_darwin(self, mock_sys):
        mock_sys.platform = "darwin"
        assert python_command() == "python3"


# ---------------------------------------------------------------------------
# venv_bin_dir
# ---------------------------------------------------------------------------

class TestVenvBinDir:
    @patch("api.utils.platform.sys")
    def test_returns_scripts_on_windows(self, mock_sys):
        mock_sys.platform = "win32"
        result = venv_bin_dir("/some/.venv")
        assert result == Path("/some/.venv") / "Scripts"

    @patch("api.utils.platform.sys")
    def test_returns_bin_on_linux(self, mock_sys):
        mock_sys.platform = "linux"
        result = venv_bin_dir("/some/.venv")
        assert result == Path("/some/.venv") / "bin"

    @patch("api.utils.platform.sys")
    def test_returns_bin_on_darwin(self, mock_sys):
        mock_sys.platform = "darwin"
        result = venv_bin_dir("/some/.venv")
        assert result == Path("/some/.venv") / "bin"

    def test_accepts_path_object(self):
        result = venv_bin_dir(Path("/some/.venv"))
        assert isinstance(result, Path)

    def test_accepts_string(self):
        result = venv_bin_dir("/some/.venv")
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# venv_pip
# ---------------------------------------------------------------------------

class TestVenvPip:
    @patch("api.utils.platform.sys")
    def test_pip_inside_scripts_on_windows(self, mock_sys):
        mock_sys.platform = "win32"
        result = venv_pip("/my/.venv")
        assert result == Path("/my/.venv") / "Scripts" / "pip"

    @patch("api.utils.platform.sys")
    def test_pip_inside_bin_on_linux(self, mock_sys):
        mock_sys.platform = "linux"
        result = venv_pip("/my/.venv")
        assert result == Path("/my/.venv") / "bin" / "pip"

    def test_returns_path_object(self):
        assert isinstance(venv_pip("/v"), Path)


# ---------------------------------------------------------------------------
# venv_python
# ---------------------------------------------------------------------------

class TestVenvPython:
    @patch("api.utils.platform.sys")
    def test_python_inside_scripts_on_windows(self, mock_sys):
        mock_sys.platform = "win32"
        result = venv_python("/my/.venv")
        assert result == Path("/my/.venv") / "Scripts" / "python"

    @patch("api.utils.platform.sys")
    def test_python_inside_bin_on_linux(self, mock_sys):
        mock_sys.platform = "linux"
        result = venv_python("/my/.venv")
        assert result == Path("/my/.venv") / "bin" / "python"

    def test_returns_path_object(self):
        assert isinstance(venv_python("/v"), Path)


# ---------------------------------------------------------------------------
# remove_path_entry
# ---------------------------------------------------------------------------

class TestRemovePathEntry:
    def test_removes_exact_match(self):
        path_str = os.pathsep.join(["/usr/bin", "/home/user/.venv/bin", "/usr/local/bin"])
        result = remove_path_entry(path_str, "/home/user/.venv/bin")
        entries = result.split(os.pathsep)
        assert "/home/user/.venv/bin" not in entries
        assert "/usr/bin" in entries
        assert "/usr/local/bin" in entries

    def test_no_match_returns_unchanged(self):
        path_str = os.pathsep.join(["/usr/bin", "/usr/local/bin"])
        result = remove_path_entry(path_str, "/nonexistent")
        assert result == path_str

    def test_empty_path_string(self):
        result = remove_path_entry("", "/foo")
        assert result == ""

    def test_removes_multiple_occurrences(self):
        path_str = os.pathsep.join(["/a", "/b", "/a", "/c"])
        result = remove_path_entry(path_str, "/a")
        entries = result.split(os.pathsep)
        assert "/a" not in entries
        assert "/b" in entries
        assert "/c" in entries

    @patch("api.utils.platform.os")
    @patch("api.utils.platform.sys")
    def test_case_insensitive_on_windows(self, mock_sys, mock_os):
        mock_sys.platform = "win32"
        mock_os.pathsep = ";"
        path_str = "C:\\Users\\Foo\\bin;C:\\Python39;C:\\Windows"
        result = remove_path_entry(path_str, "c:\\users\\foo\\bin")
        assert "C:\\Users\\Foo\\bin" not in result.split(";")
        assert "C:\\Python39" in result.split(";")

    @patch("api.utils.platform.os")
    @patch("api.utils.platform.sys")
    def test_case_sensitive_on_linux(self, mock_sys, mock_os):
        mock_sys.platform = "linux"
        mock_os.pathsep = ":"
        path_str = "/Foo/bin:/foo/bin:/usr/bin"
        result = remove_path_entry(path_str, "/Foo/bin")
        entries = result.split(":")
        assert "/Foo/bin" not in entries
        # /foo/bin is different on Linux (case-sensitive)
        assert "/foo/bin" in entries

    def test_accepts_path_object_as_entry(self):
        # Use OS-native paths so the test works on both platforms
        a, b, c = "aaa", "bbb", "ccc"
        path_str = os.pathsep.join([a, b, c])
        result = remove_path_entry(path_str, Path(b))
        entries = result.split(os.pathsep)
        assert b not in entries
        assert a in entries
        assert c in entries


# ---------------------------------------------------------------------------
# new_session_kwargs
# ---------------------------------------------------------------------------

class TestNewSessionKwargs:
    @patch("api.utils.platform.sys")
    def test_linux_returns_start_new_session(self, mock_sys):
        mock_sys.platform = "linux"
        result = new_session_kwargs()
        assert result == {"start_new_session": True}

    @patch("api.utils.platform.sys")
    def test_darwin_returns_start_new_session(self, mock_sys):
        mock_sys.platform = "darwin"
        result = new_session_kwargs()
        assert result == {"start_new_session": True}

    @patch("api.utils.platform.subprocess")
    @patch("api.utils.platform.sys")
    def test_windows_returns_creation_flags(self, mock_sys, mock_subprocess):
        mock_sys.platform = "win32"
        mock_subprocess.CREATE_NEW_PROCESS_GROUP = 0x00000200
        result = new_session_kwargs()
        assert "creationflags" in result
        assert result["creationflags"] == 0x00000200

    def test_returns_dict(self):
        result = new_session_kwargs()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# kill_process_tree
# ---------------------------------------------------------------------------

class TestKillProcessTree:
    @pytest.mark.asyncio
    @patch("api.utils.platform.sys")
    async def test_linux_calls_killpg(self, mock_sys):
        mock_sys.platform = "linux"
        proc = AsyncMock()
        proc.pid = 12345
        proc.returncode = None
        proc.wait = AsyncMock()

        with patch("api.utils.platform.os") as mock_os:
            mock_os.getpgid.return_value = 12345
            # SIGKILL = 9 on all Unix systems; use constant since Windows
            # doesn't have signal.SIGKILL
            _SIGKILL = 9
            with patch("api.utils.platform.signal") as mock_signal:
                mock_signal.SIGKILL = _SIGKILL
                await kill_process_tree(proc)
                mock_os.killpg.assert_called_once_with(12345, _SIGKILL)

    @pytest.mark.asyncio
    @patch("api.utils.platform.sys")
    async def test_windows_calls_taskkill(self, mock_sys):
        mock_sys.platform = "win32"
        proc = AsyncMock()
        proc.pid = 9999
        proc.returncode = None
        proc.wait = AsyncMock()

        with patch("api.utils.platform.subprocess") as mock_sub:
            await kill_process_tree(proc)
            mock_sub.run.assert_called_once()
            call_args = mock_sub.run.call_args[0][0]
            assert "taskkill" in call_args
            assert "/F" in call_args
            assert "/T" in call_args
            assert "/PID" in call_args
            assert "9999" in call_args

    @pytest.mark.asyncio
    @patch("api.utils.platform.sys")
    async def test_falls_back_to_proc_kill_on_error(self, mock_sys):
        mock_sys.platform = "linux"
        proc = AsyncMock()
        proc.pid = 12345
        proc.returncode = None
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with patch("api.utils.platform.os") as mock_os:
            mock_os.killpg.side_effect = OSError("no such process")
            mock_os.getpgid.return_value = 12345
            with patch("api.utils.platform.signal"):
                await kill_process_tree(proc)
                proc.kill.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.utils.platform.sys")
    async def test_windows_falls_back_to_proc_kill_on_taskkill_error(self, mock_sys):
        mock_sys.platform = "win32"
        proc = AsyncMock()
        proc.pid = 9999
        proc.returncode = None
        proc.wait = AsyncMock()
        proc.kill = MagicMock()

        with patch("api.utils.platform.subprocess") as mock_sub:
            mock_sub.run.side_effect = OSError("taskkill failed")
            await kill_process_tree(proc)
            proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_waits_for_process_after_kill(self):
        proc = AsyncMock()
        proc.pid = 1
        proc.returncode = None
        proc.wait = AsyncMock()

        with patch("api.utils.platform.os", create=True) as mock_os, \
             patch("api.utils.platform.signal", create=True):
            mock_os.killpg.side_effect = OSError()
            mock_os.getpgid.return_value = 1
            await kill_process_tree(proc)
            proc.wait.assert_awaited_once()


# ---------------------------------------------------------------------------
# resolve_command
# ---------------------------------------------------------------------------

class TestResolveCommand:
    @patch("api.utils.platform.shutil")
    def test_returns_resolved_path_when_found(self, mock_shutil):
        mock_shutil.which.return_value = "/usr/bin/codex"
        result = resolve_command("codex")
        assert result == "/usr/bin/codex"
        mock_shutil.which.assert_called_once_with("codex")

    @patch("api.utils.platform.shutil")
    def test_returns_original_when_not_found(self, mock_shutil):
        mock_shutil.which.return_value = None
        result = resolve_command("nonexistent")
        assert result == "nonexistent"

    @patch("api.utils.platform.shutil")
    def test_resolves_cmd_extension_on_windows(self, mock_shutil):
        mock_shutil.which.return_value = "C:\\Users\\user\\AppData\\Roaming\\npm\\codex.CMD"
        result = resolve_command("codex")
        assert result == "C:\\Users\\user\\AppData\\Roaming\\npm\\codex.CMD"

    @patch("api.utils.platform.shutil")
    def test_resolves_exe_on_windows(self, mock_shutil):
        mock_shutil.which.return_value = "C:\\Users\\user\\.local\\bin\\claude.EXE"
        result = resolve_command("claude")
        assert result == "C:\\Users\\user\\.local\\bin\\claude.EXE"

    @patch("api.utils.platform.shutil")
    def test_works_on_linux(self, mock_shutil):
        mock_shutil.which.return_value = "/usr/local/bin/claude"
        result = resolve_command("claude")
        assert result == "/usr/local/bin/claude"

    @patch("api.utils.platform.shutil")
    def test_does_not_resolve_absolute_paths(self, mock_shutil):
        """Absolute paths should be returned as-is without calling which."""
        result = resolve_command("/usr/bin/python3")
        mock_shutil.which.assert_not_called()
        assert result == "/usr/bin/python3"

    @patch("api.utils.platform.shutil")
    def test_does_not_resolve_windows_absolute_paths(self, mock_shutil):
        result = resolve_command("C:\\Python312\\python.exe")
        mock_shutil.which.assert_not_called()
        assert result == "C:\\Python312\\python.exe"
