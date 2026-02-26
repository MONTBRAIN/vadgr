"""macOS platform backend using screencapture and osascript/cliclick."""

import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import Region, ScreenState
from computer_use.platform.base import PlatformBackend

logger = logging.getLogger("computer_use.platform.macos")


class MacOSScreenCapture(ScreenCapture):
    """Screenshot capture using macOS screencapture command."""

    def capture_full(self) -> ScreenState:
        if sys.platform != "darwin":
            raise ScreenCaptureError("MacOSScreenCapture requires macOS")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        try:
            result = subprocess.run(
                ["screencapture", "-x", "-t", "png", tmp_path],
                capture_output=True,
                timeout=10.0,
            )
            if result.returncode != 0:
                raise ScreenCaptureError(
                    f"screencapture failed: {result.stderr.decode()}"
                )

            with open(tmp_path, "rb") as f:
                image_bytes = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        return ScreenState(
            image_bytes=image_bytes,
            width=width,
            height=height,
            scale_factor=self.get_scale_factor(),
        )

    def capture_region(self, region: Region) -> ScreenState:
        if sys.platform != "darwin":
            raise ScreenCaptureError("MacOSScreenCapture requires macOS")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name

        # screencapture -R x,y,w,h for region capture
        rect = f"{region.x},{region.y},{region.width},{region.height}"
        try:
            result = subprocess.run(
                ["screencapture", "-x", "-R", rect, "-t", "png", tmp_path],
                capture_output=True,
                timeout=10.0,
            )
            if result.returncode != 0:
                raise ScreenCaptureError(
                    f"screencapture region failed: {result.stderr.decode()}"
                )

            with open(tmp_path, "rb") as f:
                image_bytes = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return ScreenState(
            image_bytes=image_bytes,
            width=region.width,
            height=region.height,
            scale_factor=self.get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        if sys.platform != "darwin":
            raise ScreenCaptureError("MacOSScreenCapture requires macOS")

        # Use system_profiler to get display resolution
        try:
            result = subprocess.run(
                [
                    "python3", "-c",
                    "from AppKit import NSScreen; s = NSScreen.mainScreen().frame(); "
                    "print(f'{int(s.size.width)},{int(s.size.height)}')",
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                return (int(parts[0]), int(parts[1]))
        except Exception:
            pass

        # Fallback: take a screenshot and check dimensions
        screen = self.capture_full()
        return (screen.width, screen.height)

    def get_scale_factor(self) -> float:
        if sys.platform != "darwin":
            return 1.0
        try:
            result = subprocess.run(
                [
                    "python3", "-c",
                    "from AppKit import NSScreen; "
                    "print(NSScreen.mainScreen().backingScaleFactor())",
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return 2.0  # Default Retina


# AppleScript key code mapping
APPLESCRIPT_KEY_MAP = {
    "enter": 36, "return": 36, "tab": 48,
    "escape": 53, "esc": 53, "backspace": 51,
    "delete": 117, "del": 117,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "home": 115, "end": 119,
    "pageup": 116, "pagedown": 121,
    "space": 49,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}

MODIFIER_APPLESCRIPT = {
    "ctrl": "control down",
    "control": "control down",
    "alt": "option down",
    "option": "option down",
    "shift": "shift down",
    "super": "command down",
    "cmd": "command down",
    "command": "command down",
}


def _run_applescript(script: str) -> str:
    """Run an AppleScript and return stdout."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if result.returncode != 0:
            raise ActionError(f"AppleScript error: {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError:
        raise ActionError("osascript not found. Are you on macOS?")


class MacOSActionExecutor(ActionExecutor):
    """Action execution using AppleScript and cliclick on macOS."""

    def __init__(self):
        self._has_cliclick = shutil.which("cliclick") is not None

    def move_mouse(self, x: int, y: int) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"m:{x},{y}"],
                capture_output=True,
                timeout=5.0,
            )
        else:
            _run_applescript(
                f'tell application "System Events" to '
                f"set position of mouse to {{{x}, {y}}}"
            )

    def click(self, x: int, y: int, button: str = "left") -> None:
        if self._has_cliclick:
            cmd = {"left": "c", "right": "rc", "middle": "mc"}.get(button, "c")
            subprocess.run(
                ["cliclick", f"{cmd}:{x},{y}"],
                capture_output=True,
                timeout=5.0,
            )
        else:
            # AppleScript click
            _run_applescript(
                f'tell application "System Events" to click at {{{x}, {y}}}'
            )

    def double_click(self, x: int, y: int) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"dc:{x},{y}"],
                capture_output=True,
                timeout=5.0,
            )
        else:
            _run_applescript(
                f'tell application "System Events" to double click at {{{x}, {y}}}'
            )

    def type_text(self, text: str) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"t:{text}"],
                capture_output=True,
                timeout=10.0,
            )
        else:
            # Escape for AppleScript
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            _run_applescript(
                f'tell application "System Events" to keystroke "{escaped}"'
            )

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return

        # Separate modifiers from regular keys
        modifiers = []
        regular = []
        for key in keys:
            lower = key.lower()
            if lower in MODIFIER_APPLESCRIPT:
                modifiers.append(MODIFIER_APPLESCRIPT[lower])
            elif lower in APPLESCRIPT_KEY_MAP:
                regular.append(APPLESCRIPT_KEY_MAP[lower])
            elif len(key) == 1:
                regular.append(key)

        modifier_str = ", ".join(modifiers) if modifiers else ""

        if regular and isinstance(regular[0], int):
            # Key code
            using = f" using {{{modifier_str}}}" if modifier_str else ""
            _run_applescript(
                f'tell application "System Events" to key code {regular[0]}{using}'
            )
        elif regular and isinstance(regular[0], str):
            using = f" using {{{modifier_str}}}" if modifier_str else ""
            _run_applescript(
                f'tell application "System Events" to keystroke "{regular[0]}"{using}'
            )

    def scroll(self, x: int, y: int, amount: int) -> None:
        self.move_mouse(x, y)
        time.sleep(0.05)
        # Use cliclick or AppleScript for scrolling
        if self._has_cliclick:
            # cliclick doesn't support scroll, use AppleScript
            pass
        _run_applescript(
            f'tell application "System Events" to scroll area 1 by {amount}'
        )

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        if self._has_cliclick:
            subprocess.run(
                ["cliclick", f"dd:{start_x},{start_y}", f"du:{end_x},{end_y}"],
                capture_output=True,
                timeout=duration + 5.0,
            )
        else:
            _run_applescript(
                f'tell application "System Events" to click at {{{start_x}, {start_y}}}'
            )
            time.sleep(0.1)
            # AppleScript doesn't natively support drag, would need CGEvent


class MacOSBackend(PlatformBackend):
    """macOS platform backend."""

    def __init__(self):
        self._capture = None
        self._executor = None

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = MacOSScreenCapture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            self._executor = MacOSActionExecutor()
        return self._executor

    def is_available(self) -> bool:
        return sys.platform == "darwin"

    def get_accessibility_info(self) -> dict:
        try:
            import AppKit

            return {
                "available": True,
                "api_name": "macOS Accessibility API",
                "notes": "pyobjc available. Ensure accessibility permissions are granted in System Preferences.",
            }
        except ImportError:
            return {
                "available": False,
                "api_name": "macOS Accessibility API",
                "notes": "pyobjc not installed. Run: pip install pyobjc-framework-ApplicationServices",
            }
