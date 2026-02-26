"""Linux/X11 platform backend using mss for screenshots and xdotool for input."""

import io
import logging
import shutil
import subprocess
from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import Region, ScreenState
from computer_use.platform.base import PlatformBackend

logger = logging.getLogger("computer_use.platform.linux")


class LinuxScreenCapture(ScreenCapture):
    """Screenshot capture using mss (X11/Wayland via XShm)."""

    def __init__(self):
        try:
            import mss

            self._mss = mss.mss()
        except ImportError:
            raise ScreenCaptureError(
                "mss library not installed. Run: pip install mss"
            )

    def capture_full(self) -> ScreenState:
        monitor = self._mss.monitors[1]  # Primary monitor
        screenshot = self._mss.grab(monitor)
        image_bytes = self._to_png(screenshot)
        return ScreenState(
            image_bytes=image_bytes,
            width=screenshot.width,
            height=screenshot.height,
            scale_factor=self.get_scale_factor(),
        )

    def capture_region(self, region: Region) -> ScreenState:
        monitor = {
            "left": region.x,
            "top": region.y,
            "width": region.width,
            "height": region.height,
        }
        screenshot = self._mss.grab(monitor)
        image_bytes = self._to_png(screenshot)
        return ScreenState(
            image_bytes=image_bytes,
            width=region.width,
            height=region.height,
            scale_factor=self.get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        monitor = self._mss.monitors[1]
        return (monitor["width"], monitor["height"])

    def get_scale_factor(self) -> float:
        # Try to read from GDK_SCALE or Xrandr
        import os

        scale = os.environ.get("GDK_SCALE")
        if scale:
            try:
                return float(scale)
            except ValueError:
                pass
        return 1.0

    def _to_png(self, screenshot) -> bytes:
        """Convert mss screenshot to PNG bytes."""
        from PIL import Image

        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# xdotool key name mapping
XDOTOOL_KEY_MAP = {
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "space": "space",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12",
}


def _run_xdotool(*args: str) -> str:
    """Run an xdotool command and return stdout."""
    try:
        result = subprocess.run(
            ["xdotool", *args],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if result.returncode != 0:
            raise ActionError(f"xdotool error: {result.stderr.strip()}")
        return result.stdout.strip()
    except FileNotFoundError:
        raise ActionError(
            "xdotool not installed. Run: sudo apt install xdotool"
        )


class LinuxActionExecutor(ActionExecutor):
    """Action execution using xdotool on Linux/X11."""

    def move_mouse(self, x: int, y: int) -> None:
        _run_xdotool("mousemove", str(x), str(y))

    def click(self, x: int, y: int, button: str = "left") -> None:
        button_num = {"left": "1", "middle": "2", "right": "3"}.get(button, "1")
        _run_xdotool("mousemove", str(x), str(y))
        _run_xdotool("click", button_num)

    def double_click(self, x: int, y: int) -> None:
        _run_xdotool("mousemove", str(x), str(y))
        _run_xdotool("click", "--repeat", "2", "--delay", "50", "1")

    def type_text(self, text: str) -> None:
        _run_xdotool("type", "--clearmodifiers", text)

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return
        mapped = [XDOTOOL_KEY_MAP.get(k.lower(), k) for k in keys]
        combo = "+".join(mapped)
        _run_xdotool("key", "--clearmodifiers", combo)

    def scroll(self, x: int, y: int, amount: int) -> None:
        _run_xdotool("mousemove", str(x), str(y))
        if amount > 0:
            for _ in range(abs(amount)):
                _run_xdotool("click", "4")  # scroll up
        else:
            for _ in range(abs(amount)):
                _run_xdotool("click", "5")  # scroll down

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        _run_xdotool("mousemove", str(start_x), str(start_y))
        _run_xdotool("mousedown", "1")
        # Move in steps
        steps = max(int(duration * 60), 10)
        delay_ms = int((duration * 1000) / steps)
        dx = (end_x - start_x) / steps
        dy = (end_y - start_y) / steps
        for i in range(1, steps + 1):
            cx = int(start_x + dx * i)
            cy = int(start_y + dy * i)
            _run_xdotool("mousemove", "--delay", str(delay_ms), str(cx), str(cy))
        _run_xdotool("mouseup", "1")


class LinuxBackend(PlatformBackend):
    """Linux/X11 platform backend."""

    def __init__(self):
        self._capture = None
        self._executor = None

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = LinuxScreenCapture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            self._executor = LinuxActionExecutor()
        return self._executor

    def is_available(self) -> bool:
        return shutil.which("xdotool") is not None

    def get_accessibility_info(self) -> dict:
        try:
            import pyatspi

            return {
                "available": True,
                "api_name": "AT-SPI2",
                "notes": "pyatspi library available",
            }
        except ImportError:
            return {
                "available": False,
                "api_name": "AT-SPI2",
                "notes": "pyatspi not installed. Run: pip install pyatspi",
            }
