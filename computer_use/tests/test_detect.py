"""Tests for platform detection."""

import os
import sys
from unittest.mock import mock_open, patch

import pytest

from computer_use.core.types import Platform
from computer_use.platform.detect import detect_platform


class TestDetectPlatform:
    def test_wsl2_with_env_and_proc(self):
        """WSL2 detection: WSL_DISTRO_NAME env + microsoft in /proc/version."""
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            patch("sys.platform", "linux"),
            patch(
                "builtins.open",
                mock_open(read_data="Linux version 5.15 microsoft-standard-WSL2"),
            ),
        ):
            assert detect_platform() == Platform.WSL2

    def test_wsl2_with_env_only(self):
        """WSL2 detection: WSL_DISTRO_NAME set, /proc/version unreadable."""
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            patch("sys.platform", "linux"),
            patch("builtins.open", side_effect=OSError("No such file")),
        ):
            assert detect_platform() == Platform.WSL2

    def test_wsl2_proc_version_only(self):
        """WSL2 detection: no WSL_DISTRO_NAME but /proc/version has microsoft."""
        env = os.environ.copy()
        env.pop("WSL_DISTRO_NAME", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("sys.platform", "linux"),
            patch(
                "builtins.open",
                mock_open(read_data="Linux version 5.15 microsoft-standard-WSL2"),
            ),
        ):
            assert detect_platform() == Platform.WSL2

    def test_native_linux(self):
        """Native Linux: no WSL_DISTRO_NAME, /proc/version without microsoft."""
        env = os.environ.copy()
        env.pop("WSL_DISTRO_NAME", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("sys.platform", "linux"),
            patch(
                "builtins.open",
                mock_open(read_data="Linux version 6.1.0-generic"),
            ),
        ):
            assert detect_platform() == Platform.LINUX

    def test_macos(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.platform", "darwin"),
        ):
            assert detect_platform() == Platform.MACOS

    def test_windows(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.platform", "win32"),
        ):
            assert detect_platform() == Platform.WINDOWS

    def test_unsupported(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.platform", "freebsd"),
        ):
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                detect_platform()
