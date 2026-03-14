"""Tests for platform detection and backend factory."""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from computer_use.core.types import Platform
from computer_use.platform.detect import detect_platform, get_backend


class TestDetectPlatform:
    def test_wsl2_detected_via_env_and_proc_version(self):
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            patch("sys.platform", "linux"),
            patch(
                "builtins.open",
                mock_open(read_data="Linux 5.15.90.1-microsoft-standard-WSL2"),
            ),
        ):
            assert detect_platform() == Platform.WSL2

    def test_wsl2_detected_when_proc_version_unreadable(self):
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            patch("sys.platform", "linux"),
            patch("builtins.open", side_effect=OSError),
        ):
            assert detect_platform() == Platform.WSL2

    def test_wsl2_detected_via_proc_version_without_env(self):
        """WSL2 detected via /proc/version even without WSL_DISTRO_NAME."""
        env = os.environ.copy()
        env.pop("WSL_DISTRO_NAME", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("sys.platform", "linux"),
            patch(
                "builtins.open",
                mock_open(read_data="Linux 5.15.90.1-microsoft-standard-WSL2"),
            ),
        ):
            assert detect_platform() == Platform.WSL2

    def test_plain_linux_without_wsl_env(self):
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

    def test_macos_detected(self):
        with patch("sys.platform", "darwin"):
            assert detect_platform() == Platform.MACOS

    def test_windows_detected(self):
        with patch("sys.platform", "win32"):
            assert detect_platform() == Platform.WINDOWS

    def test_unsupported_platform_raises_runtime_error(self):
        with patch("sys.platform", "aix"):
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                detect_platform()

    def test_wsl2_proc_version_without_microsoft_still_trusts_env(self):
        with (
            patch.dict(os.environ, {"WSL_DISTRO_NAME": "Debian"}),
            patch("sys.platform", "linux"),
            patch(
                "builtins.open",
                mock_open(read_data="Linux version 5.15 generic"),
            ),
        ):
            result = detect_platform()
            assert result == Platform.WSL2


class TestGetBackend:
    def test_wsl2_returns_wsl2_backend(self):
        mock_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {"computer_use.platform.wsl2": MagicMock(WSL2Backend=mock_cls)},
        ):
            backend = get_backend(Platform.WSL2)
            mock_cls.assert_called_once()
            assert backend is mock_cls.return_value

    def test_windows_returns_windows_backend(self):
        mock_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {"computer_use.platform.windows": MagicMock(WindowsBackend=mock_cls)},
        ):
            backend = get_backend(Platform.WINDOWS)
            mock_cls.assert_called_once()
            assert backend is mock_cls.return_value

    def test_macos_returns_macos_backend(self):
        mock_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {"computer_use.platform.macos": MagicMock(MacOSBackend=mock_cls)},
        ):
            backend = get_backend(Platform.MACOS)
            mock_cls.assert_called_once()
            assert backend is mock_cls.return_value

    def test_linux_returns_linux_backend(self):
        mock_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {"computer_use.platform.linux": MagicMock(LinuxBackend=mock_cls)},
        ):
            backend = get_backend(Platform.LINUX)
            mock_cls.assert_called_once()
            assert backend is mock_cls.return_value

    def test_none_platform_triggers_detection(self):
        mock_cls = MagicMock()
        with (
            patch(
                "computer_use.platform.detect.detect_platform",
                return_value=Platform.LINUX,
            ),
            patch.dict(
                "sys.modules",
                {"computer_use.platform.linux": MagicMock(LinuxBackend=mock_cls)},
            ),
        ):
            backend = get_backend(None)
            mock_cls.assert_called_once()
            assert backend is mock_cls.return_value

    def test_default_arg_is_none(self):
        mock_cls = MagicMock()
        with (
            patch(
                "computer_use.platform.detect.detect_platform",
                return_value=Platform.MACOS,
            ),
            patch.dict(
                "sys.modules",
                {"computer_use.platform.macos": MagicMock(MacOSBackend=mock_cls)},
            ),
        ):
            backend = get_backend()
            mock_cls.assert_called_once()
            assert backend is mock_cls.return_value
