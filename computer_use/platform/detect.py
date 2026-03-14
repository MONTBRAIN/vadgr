# Copyright 2026 Victor Santiago Montaño Diaz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
        # WSL2 detection: WSL2 IS Linux, but needs Windows-routed backends.
        # Check /proc/version first (works even if env vars are stripped),
        # then fall back to WSL_DISTRO_NAME env var.
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    return Platform.WSL2
        except OSError:
            pass
        if os.environ.get("WSL_DISTRO_NAME"):
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
