"""Platform detection logic."""

import os
import sys

from computer_use.core.types import Platform


def detect_platform() -> Platform:
    """Detect the current platform, including WSL2.

    Detection order:
    1. Check for WSL2 (Linux kernel with Microsoft string + WSL_DISTRO_NAME)
    2. Check sys.platform for native OS
    """
    if sys.platform == "linux":
        # WSL2 detection: WSL2 IS Linux, but needs Windows-routed backends
        wsl_distro = os.environ.get("WSL_DISTRO_NAME")
        if wsl_distro:
            try:
                with open("/proc/version", "r") as f:
                    if "microsoft" in f.read().lower():
                        return Platform.WSL2
            except OSError:
                pass
            # Trust WSL_DISTRO_NAME even without /proc/version
            return Platform.WSL2
        return Platform.LINUX

    if sys.platform == "darwin":
        return Platform.MACOS

    if sys.platform == "win32":
        return Platform.WINDOWS

    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def get_backend(platform: Platform = None):
    """Factory: return the correct PlatformBackend for the detected OS."""
    if platform is None:
        platform = detect_platform()

    match platform:
        case Platform.WSL2:
            from computer_use.platform.wsl2 import WSL2Backend

            return WSL2Backend()
        case Platform.WINDOWS:
            from computer_use.platform.windows import WindowsBackend

            return WindowsBackend()
        case Platform.MACOS:
            from computer_use.platform.macos import MacOSBackend

            return MacOSBackend()
        case Platform.LINUX:
            from computer_use.platform.linux import LinuxBackend

            return LinuxBackend()
