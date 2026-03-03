"""Linux platform backend. Supports X11 (mss/xdotool) and Wayland (Mutter RemoteDesktop/evdev)."""

import io
import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import ForegroundWindow, Region, ScreenState
from computer_use.platform.base import PlatformBackend

logger = logging.getLogger("computer_use.platform.linux")

# Lazy imports so the module loads even without optional deps.
try:
    import mss as mss_import
except ImportError:
    mss_import = None  # type: ignore[assignment]

try:
    import evdev as evdev_import
    from evdev import ecodes
except ImportError:
    evdev_import = None  # type: ignore[assignment]
    ecodes = None  # type: ignore[assignment]

try:
    import dbus as dbus_import
except ImportError:
    dbus_import = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Display session detection
# ---------------------------------------------------------------------------


def _is_wayland() -> bool:
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE") == "wayland"


def _get_scale_factor() -> float:
    raw = os.environ.get("GDK_SCALE", "")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 1.0


# ---------------------------------------------------------------------------
# Screenshot strategies
# ---------------------------------------------------------------------------


class _CliScreenCapture(ScreenCapture):
    """Base for CLI-tool-based screenshot capture (grim, gnome-screenshot, etc.)."""

    def _run_capture(self, args: list[str], output_path: str) -> None:
        raise NotImplementedError

    def _tool_name(self) -> str:
        raise NotImplementedError

    def capture_full(self) -> ScreenState:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name

        try:
            self._run_capture(self._full_args(path), path)
            with open(path, "rb") as f:
                data = f.read()
            w, h = self._read_image_size(data)
            return ScreenState(
                image_bytes=data,
                width=w,
                height=h,
                scale_factor=_get_scale_factor(),
            )
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def capture_region(self, region: Region) -> ScreenState:
        # Capture full screen and crop. Most CLI tools don't support region natively.
        full = self.capture_full()
        from PIL import Image

        img = Image.open(io.BytesIO(full.image_bytes))
        cropped = img.crop((region.x, region.y, region.x + region.width, region.y + region.height))
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return ScreenState(
            image_bytes=buf.getvalue(),
            width=region.width,
            height=region.height,
            scale_factor=full.scale_factor,
        )

    def get_screen_size(self) -> tuple[int, int]:
        state = self.capture_full()
        return (state.width, state.height)

    def get_scale_factor(self) -> float:
        return _get_scale_factor()

    def _full_args(self, output_path: str) -> list[str]:
        raise NotImplementedError

    @staticmethod
    def _read_image_size(data: bytes) -> tuple[int, int]:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        return img.size


class GrimScreenCapture(_CliScreenCapture):
    """Wayland screenshots via grim (wlroots compositors: Sway, Hyprland, etc.)."""

    def _tool_name(self) -> str:
        return "grim"

    def _full_args(self, output_path: str) -> list[str]:
        return ["grim", output_path]

    def _run_capture(self, args: list[str], output_path: str) -> None:
        result = subprocess.run(args, capture_output=True, timeout=10.0)
        if result.returncode != 0:
            raise ScreenCaptureError(f"grim failed: {result.stderr.decode().strip()}")


class GnomeScreenCapture(_CliScreenCapture):
    """Wayland screenshots via gnome-screenshot (GNOME)."""

    def _tool_name(self) -> str:
        return "gnome-screenshot"

    def _full_args(self, output_path: str) -> list[str]:
        return ["gnome-screenshot", "-f", output_path]

    def _run_capture(self, args: list[str], output_path: str) -> None:
        result = subprocess.run(args, capture_output=True, timeout=10.0)
        if result.returncode != 0:
            raise ScreenCaptureError(
                f"gnome-screenshot failed: {result.stderr.decode().strip()}"
            )


class MssScreenCapture(ScreenCapture):
    """X11 screenshots via mss."""

    def __init__(self):
        if mss_import is None:
            raise ScreenCaptureError("mss not installed. Run: pip install mss")
        self._mss = mss_import.mss()

    def capture_full(self) -> ScreenState:
        monitor = self._mss.monitors[1]
        screenshot = self._mss.grab(monitor)
        return ScreenState(
            image_bytes=self._to_png(screenshot),
            width=screenshot.width,
            height=screenshot.height,
            scale_factor=_get_scale_factor(),
        )

    def capture_region(self, region: Region) -> ScreenState:
        monitor = {
            "left": region.x,
            "top": region.y,
            "width": region.width,
            "height": region.height,
        }
        screenshot = self._mss.grab(monitor)
        return ScreenState(
            image_bytes=self._to_png(screenshot),
            width=region.width,
            height=region.height,
            scale_factor=_get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        monitor = self._mss.monitors[1]
        return (monitor["width"], monitor["height"])

    def get_scale_factor(self) -> float:
        return _get_scale_factor()

    @staticmethod
    def _to_png(screenshot) -> bytes:
        from PIL import Image

        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# ---------------------------------------------------------------------------
# Factory: pick the right capture strategy
# ---------------------------------------------------------------------------

_WAYLAND_TOOLS: list[tuple[str, type[_CliScreenCapture]]] = [
    ("grim", GrimScreenCapture),
    ("gnome-screenshot", GnomeScreenCapture),
]


def _create_screen_capture() -> ScreenCapture:
    if not _is_wayland():
        return MssScreenCapture()

    # Binary existing doesn't mean it works (e.g. grim on GNOME).
    # Probe each tool with a real capture attempt.
    for tool, cls in _WAYLAND_TOOLS:
        if not shutil.which(tool):
            continue
        capture = cls()
        try:
            capture.capture_full()
            logger.info("Wayland: using %s for screenshots", tool)
            return capture
        except ScreenCaptureError:
            logger.debug("%s installed but failed, trying next tool", tool)
            continue

    raise ScreenCaptureError(
        "No working Wayland screenshot tool found. Install one of: grim, gnome-screenshot"
    )


# ---------------------------------------------------------------------------
# xdotool key mapping
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Action execution (xdotool -- works on X11 and Wayland via XWayland)
# ---------------------------------------------------------------------------


def _run_xdotool(*args: str) -> str:
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
        raise ActionError("xdotool not installed. Run: sudo apt install xdotool")


class LinuxActionExecutor(ActionExecutor):

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
        button = "4" if amount > 0 else "5"
        for _ in range(abs(amount)):
            _run_xdotool("click", button)

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
        steps = max(int(duration * 60), 10)
        delay_ms = int((duration * 1000) / steps)
        dx = (end_x - start_x) / steps
        dy = (end_y - start_y) / steps
        for i in range(1, steps + 1):
            cx = int(start_x + dx * i)
            cy = int(start_y + dy * i)
            _run_xdotool("mousemove", "--delay", str(delay_ms), str(cx), str(cy))
        _run_xdotool("mouseup", "1")


# ---------------------------------------------------------------------------
# Shared evdev keycodes + Wayland action executor base
# ---------------------------------------------------------------------------

# Hardcoded evdev keycodes (input-event-codes.h). Fallback when python-evdev not installed.
_FALLBACK_EVDEV_KEYCODES: dict[str, int] = {
    "enter": 28, "return": 28, "tab": 15, "escape": 1, "esc": 1,
    "backspace": 14, "delete": 111, "del": 111,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "home": 102, "end": 107, "pageup": 104, "pagedown": 109,
    "space": 57, "ctrl": 29, "control": 29, "alt": 56,
    "shift": 42, "super": 125,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24, "p": 25,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38,
    "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "-": 12, "=": 13, "[": 26, "]": 27, ";": 39, "'": 40,
    ",": 51, ".": 52, "/": 53, "\\": 43, "`": 41,
}

_FALLBACK_BUTTON_CODES: dict[str, int] = {"left": 272, "right": 273, "middle": 274}


def _build_evdev_key_map() -> dict[str, int]:
    """Build key name -> evdev keycode map. Uses ecodes if available, hardcoded fallback."""
    if ecodes is None:
        return dict(_FALLBACK_EVDEV_KEYCODES)
    return {
        "enter": ecodes.KEY_ENTER, "return": ecodes.KEY_ENTER,
        "tab": ecodes.KEY_TAB, "escape": ecodes.KEY_ESC, "esc": ecodes.KEY_ESC,
        "backspace": ecodes.KEY_BACKSPACE, "delete": ecodes.KEY_DELETE, "del": ecodes.KEY_DELETE,
        "up": ecodes.KEY_UP, "down": ecodes.KEY_DOWN,
        "left": ecodes.KEY_LEFT, "right": ecodes.KEY_RIGHT,
        "home": ecodes.KEY_HOME, "end": ecodes.KEY_END,
        "pageup": ecodes.KEY_PAGEUP, "pagedown": ecodes.KEY_PAGEDOWN,
        "space": ecodes.KEY_SPACE, "ctrl": ecodes.KEY_LEFTCTRL, "control": ecodes.KEY_LEFTCTRL,
        "alt": ecodes.KEY_LEFTALT, "shift": ecodes.KEY_LEFTSHIFT, "super": ecodes.KEY_LEFTMETA,
        "f1": ecodes.KEY_F1, "f2": ecodes.KEY_F2, "f3": ecodes.KEY_F3,
        "f4": ecodes.KEY_F4, "f5": ecodes.KEY_F5, "f6": ecodes.KEY_F6,
        "f7": ecodes.KEY_F7, "f8": ecodes.KEY_F8, "f9": ecodes.KEY_F9,
        "f10": ecodes.KEY_F10, "f11": ecodes.KEY_F11, "f12": ecodes.KEY_F12,
        **{chr(c): getattr(ecodes, f"KEY_{chr(c).upper()}") for c in range(ord('a'), ord('z') + 1)},
        **{str(i): getattr(ecodes, f"KEY_{i}") for i in range(10)},
        "-": ecodes.KEY_MINUS, "=": ecodes.KEY_EQUAL,
        "[": ecodes.KEY_LEFTBRACE, "]": ecodes.KEY_RIGHTBRACE,
        ";": ecodes.KEY_SEMICOLON, "'": ecodes.KEY_APOSTROPHE,
        ",": ecodes.KEY_COMMA, ".": ecodes.KEY_DOT, "/": ecodes.KEY_SLASH,
        "\\": ecodes.KEY_BACKSLASH, "`": ecodes.KEY_GRAVE,
    }


def _build_button_map() -> dict[str, int]:
    """Build button name -> evdev button code map."""
    if ecodes is None:
        return dict(_FALLBACK_BUTTON_CODES)
    return {"left": ecodes.BTN_LEFT, "right": ecodes.BTN_RIGHT, "middle": ecodes.BTN_MIDDLE}


class _WaylandActionExecutor(ActionExecutor):
    """Base for Wayland executors. Shared typing and key press logic.

    Subclasses provide _key_event() for their transport (evdev writes, DBus calls, etc.).
    """

    def __init__(self):
        self._key_map = _build_evdev_key_map()
        self._btn_map = _build_button_map()

    def _key_event(self, keycode: int, down: bool) -> None:
        raise NotImplementedError

    def _btn_code(self, button: str) -> int:
        return self._btn_map.get(button, self._btn_map["left"])

    def type_text(self, text: str) -> None:
        if len(text) > 3:
            try:
                subprocess.run(
                    ["wl-copy"], input=text.encode(), timeout=3.0, check=True)
                time.sleep(0.05)
                ctrl = self._key_map.get("ctrl", 29)
                v = self._key_map.get("v", 47)
                self._key_event(ctrl, True)
                self._key_event(v, True)
                time.sleep(0.03)
                self._key_event(v, False)
                self._key_event(ctrl, False)
                time.sleep(0.05)
                return
            except (subprocess.SubprocessError, FileNotFoundError):
                pass

        shift_code = self._key_map.get("shift", 42)
        for ch in text:
            keycode = self._key_map.get(ch.lower())
            if keycode is None:
                continue
            needs_shift = ch.isupper() or ch in '~!@#$%^&*()_+{}|:"<>?'
            if needs_shift:
                self._key_event(shift_code, True)
            self._key_event(keycode, True)
            time.sleep(0.02)
            self._key_event(keycode, False)
            if needs_shift:
                self._key_event(shift_code, False)
            time.sleep(0.02)

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return
        codes = []
        for k in keys:
            code = self._key_map.get(k.lower())
            if code is None:
                logger.warning("Unknown key: %s", k)
                continue
            codes.append(code)
        for code in codes:
            self._key_event(code, True)
        time.sleep(0.03)
        for code in reversed(codes):
            self._key_event(code, False)


# ---------------------------------------------------------------------------
# Evdev action execution (Wayland -- writes directly to kernel input devices)
# ---------------------------------------------------------------------------


def _find_evdev_mouse() -> Optional["evdev_import.InputDevice"]:
    """Find the best mouse/pointer device. Prefers absolute (tablet) devices."""
    if evdev_import is None:
        return None

    best = None
    for path in evdev_import.list_devices():
        try:
            dev = evdev_import.InputDevice(path)
        except (PermissionError, OSError):
            continue

        caps = dev.capabilities()
        has_abs = ecodes.EV_ABS in caps
        has_btn = ecodes.EV_KEY in caps and ecodes.BTN_LEFT in [
            c if isinstance(c, int) else c[0] for c in caps.get(ecodes.EV_KEY, [])
        ]

        if has_abs and has_btn:
            # Absolute device with buttons (VBox tablet, Wacom, etc.) -- best option
            logger.info("evdev mouse: using ABS device %s (%s)", dev.name, path)
            if best is not None:
                best.close()
            return dev

        if best is None and has_btn:
            best = dev
        else:
            dev.close()

    if best:
        logger.info("evdev mouse: using REL device %s (%s)", best.name, best.path)
    return best


def _find_evdev_keyboard() -> Optional["evdev_import.InputDevice"]:
    """Find the keyboard input device."""
    if evdev_import is None:
        return None

    for path in evdev_import.list_devices():
        try:
            dev = evdev_import.InputDevice(path)
        except (PermissionError, OSError):
            continue

        caps = dev.capabilities()
        has_keys = ecodes.EV_KEY in caps
        # A real keyboard has letter keys, not just media buttons
        key_caps = [c if isinstance(c, int) else c[0] for c in caps.get(ecodes.EV_KEY, [])]
        has_letters = ecodes.KEY_A in key_caps and ecodes.KEY_Z in key_caps

        if has_keys and has_letters:
            logger.info("evdev keyboard: %s (%s)", dev.name, path)
            return dev
        dev.close()

    return None


class EvdevActionExecutor(_WaylandActionExecutor):
    """Wayland input via python-evdev. Writes directly to kernel input devices."""

    def __init__(
        self,
        mouse_dev: "evdev_import.InputDevice",
        kbd_dev: "evdev_import.InputDevice",
        screen_w: int = 1366,
        screen_h: int = 853,
    ):
        super().__init__()
        self._mouse = mouse_dev
        self._kbd = kbd_dev
        self._screen_w = screen_w
        self._screen_h = screen_h

        # Check if mouse supports absolute positioning
        caps = mouse_dev.capabilities()
        abs_caps = caps.get(ecodes.EV_ABS, [])
        self._has_abs = any(
            (c[0] if isinstance(c, tuple) else c) == ecodes.ABS_X
            for c in abs_caps
        )

        if self._has_abs:
            # Read the device's coordinate range
            for item in abs_caps:
                code, info = item if isinstance(item, tuple) else (item, None)
                if code == ecodes.ABS_X and info:
                    self._abs_max_x = info.max
                elif code == ecodes.ABS_Y and info:
                    self._abs_max_y = info.max
            if not hasattr(self, "_abs_max_x"):
                self._abs_max_x = 32767
            if not hasattr(self, "_abs_max_y"):
                self._abs_max_y = 32767

    def _move_abs(self, x: int, y: int) -> None:
        """Move cursor using absolute coordinates."""
        ax = int(x * self._abs_max_x / self._screen_w)
        ay = int(y * self._abs_max_y / self._screen_h)
        self._mouse.write(ecodes.EV_ABS, ecodes.ABS_X, ax)
        self._mouse.write(ecodes.EV_ABS, ecodes.ABS_Y, ay)
        self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)

    def _move_rel(self, x: int, y: int) -> None:
        """Move cursor using reset-to-origin + relative movement."""
        # Slam to top-left
        self._mouse.write(ecodes.EV_REL, ecodes.REL_X, -(self._screen_w + 200))
        self._mouse.write(ecodes.EV_REL, ecodes.REL_Y, -(self._screen_h + 200))
        self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
        time.sleep(0.015)
        # Walk to target in chunks
        rx, ry = x, y
        while rx > 0 or ry > 0:
            dx = min(rx, 50)
            dy = min(ry, 50)
            self._mouse.write(ecodes.EV_REL, ecodes.REL_X, dx)
            self._mouse.write(ecodes.EV_REL, ecodes.REL_Y, dy)
            self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
            rx -= dx
            ry -= dy
            time.sleep(0.003)

    def move_mouse(self, x: int, y: int) -> None:
        if self._has_abs:
            self._move_abs(x, y)
        else:
            self._move_rel(x, y)

    def click(self, x: int, y: int, button: str = "left") -> None:
        self.move_mouse(x, y)
        time.sleep(0.05)
        btn = self._btn_code(button)
        self._mouse.write(ecodes.EV_KEY, btn, 1)
        self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
        time.sleep(0.04)
        self._mouse.write(ecodes.EV_KEY, btn, 0)
        self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)

    def double_click(self, x: int, y: int) -> None:
        self.move_mouse(x, y)
        time.sleep(0.05)
        btn = self._btn_code("left")
        for _ in range(2):
            self._mouse.write(ecodes.EV_KEY, btn, 1)
            self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
            time.sleep(0.04)
            self._mouse.write(ecodes.EV_KEY, btn, 0)
            self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
            time.sleep(0.08)

    def _key_event(self, keycode: int, down: bool) -> None:
        self._kbd.write(ecodes.EV_KEY, keycode, 1 if down else 0)
        self._kbd.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)

    def scroll(self, x: int, y: int, amount: int) -> None:
        self.move_mouse(x, y)
        time.sleep(0.05)
        # REL_WHEEL: positive = up, negative = down (matches our API)
        for _ in range(abs(amount)):
            self._mouse.write(ecodes.EV_REL, ecodes.REL_WHEEL, 1 if amount > 0 else -1)
            self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
            time.sleep(0.03)

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        btn = self._btn_code("left")
        self.move_mouse(start_x, start_y)
        time.sleep(0.05)
        self._mouse.write(ecodes.EV_KEY, btn, 1)
        self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)

        steps = max(int(duration * 60), 10)
        delay = duration / steps
        dx = (end_x - start_x) / steps
        dy = (end_y - start_y) / steps

        for i in range(1, steps + 1):
            cx = int(start_x + dx * i)
            cy = int(start_y + dy * i)
            if self._has_abs:
                self._move_abs(cx, cy)
            else:
                # Small relative steps from current position
                self._mouse.write(ecodes.EV_REL, ecodes.REL_X, int(dx))
                self._mouse.write(ecodes.EV_REL, ecodes.REL_Y, int(dy))
                self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
            time.sleep(delay)

        self._mouse.write(ecodes.EV_KEY, btn, 0)
        self._mouse.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)


# ---------------------------------------------------------------------------
# Mutter RemoteDesktop (GNOME Wayland -- proper input injection via DBus)
# ---------------------------------------------------------------------------


def _is_mutter_available() -> bool:
    """Check if Mutter RemoteDesktop DBus interface is available."""
    if dbus_import is None:
        return False
    try:
        bus = dbus_import.SessionBus()
        bus.get_object('org.gnome.Mutter.RemoteDesktop', '/org/gnome/Mutter/RemoteDesktop')
        return True
    except Exception:
        return False


class MutterRemoteDesktopExecutor(_WaylandActionExecutor):
    """GNOME Wayland input via Mutter RemoteDesktop + ScreenCast DBus interfaces."""

    def __init__(self):
        super().__init__()
        self._bus = dbus_import.SessionBus()
        self._session = None
        self._stream_path = None
        self._setup_session()

    def _setup_session(self) -> None:
        """Create RemoteDesktop + ScreenCast sessions for full input control."""
        # RemoteDesktop session
        rd_obj = self._bus.get_object(
            'org.gnome.Mutter.RemoteDesktop', '/org/gnome/Mutter/RemoteDesktop')
        rd_iface = dbus_import.Interface(rd_obj, 'org.gnome.Mutter.RemoteDesktop')
        session_path = rd_iface.CreateSession()

        session_obj = self._bus.get_object('org.gnome.Mutter.RemoteDesktop', session_path)
        self._session = dbus_import.Interface(
            session_obj, 'org.gnome.Mutter.RemoteDesktop.Session')
        session_props = dbus_import.Interface(session_obj, 'org.freedesktop.DBus.Properties')
        session_id = session_props.Get('org.gnome.Mutter.RemoteDesktop.Session', 'SessionId')

        # ScreenCast session (linked to RemoteDesktop for absolute positioning)
        sc_obj = self._bus.get_object(
            'org.gnome.Mutter.ScreenCast', '/org/gnome/Mutter/ScreenCast')
        sc_iface = dbus_import.Interface(sc_obj, 'org.gnome.Mutter.ScreenCast')
        sc_session_path = sc_iface.CreateSession(
            {'remote-desktop-session-id': dbus_import.String(session_id)})
        sc_session_obj = self._bus.get_object('org.gnome.Mutter.ScreenCast', sc_session_path)
        sc_session = dbus_import.Interface(
            sc_session_obj, 'org.gnome.Mutter.ScreenCast.Session')
        self._stream_path = sc_session.RecordMonitor('', {})

        self._session.Start()
        logger.info("Mutter RemoteDesktop session started")

    def _ensure_session(self) -> None:
        """Recreate session if it died."""
        if self._session is None:
            self._setup_session()

    def move_mouse(self, x: int, y: int) -> None:
        self._ensure_session()
        self._session.NotifyPointerMotionAbsolute(
            self._stream_path, dbus_import.Double(float(x)), dbus_import.Double(float(y)))

    def click(self, x: int, y: int, button: str = "left") -> None:
        btn = self._btn_code(button)
        self.move_mouse(x, y)
        time.sleep(0.05)
        self._session.NotifyPointerButton(dbus_import.Int32(btn), dbus_import.Boolean(True))
        time.sleep(0.04)
        self._session.NotifyPointerButton(dbus_import.Int32(btn), dbus_import.Boolean(False))

    def double_click(self, x: int, y: int) -> None:
        btn = self._btn_code("left")
        self.move_mouse(x, y)
        time.sleep(0.05)
        for _ in range(2):
            self._session.NotifyPointerButton(dbus_import.Int32(btn), dbus_import.Boolean(True))
            time.sleep(0.04)
            self._session.NotifyPointerButton(dbus_import.Int32(btn), dbus_import.Boolean(False))
            time.sleep(0.08)

    def _key_event(self, keycode: int, down: bool) -> None:
        self._ensure_session()
        self._session.NotifyKeyboardKeycode(
            dbus_import.UInt32(keycode), dbus_import.Boolean(down))

    def scroll(self, x: int, y: int, amount: int) -> None:
        self.move_mouse(x, y)
        time.sleep(0.05)
        for _ in range(abs(amount)):
            # axis 0 = vertical, positive = scroll up
            self._session.NotifyPointerAxisDiscrete(
                dbus_import.UInt32(0), dbus_import.Int32(1 if amount > 0 else -1))
            time.sleep(0.03)

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        btn = self._btn_code("left")
        self.move_mouse(start_x, start_y)
        time.sleep(0.05)
        self._session.NotifyPointerButton(dbus_import.Int32(btn), dbus_import.Boolean(True))

        steps = max(int(duration * 60), 10)
        delay = duration / steps
        dx = (end_x - start_x) / steps
        dy = (end_y - start_y) / steps
        for i in range(1, steps + 1):
            cx = start_x + dx * i
            cy = start_y + dy * i
            self._session.NotifyPointerMotionAbsolute(
                self._stream_path, dbus_import.Double(cx), dbus_import.Double(cy))
            time.sleep(delay)

        self._session.NotifyPointerButton(dbus_import.Int32(btn), dbus_import.Boolean(False))

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.Stop()
            except Exception:
                pass
            self._session = None
            self._stream_path = None


# ---------------------------------------------------------------------------
# Action executor factory
# ---------------------------------------------------------------------------


def _create_action_executor(screen_w: int = 1366, screen_h: int = 853) -> ActionExecutor:
    """Pick the best action executor for the current session.

    Priority: Mutter RemoteDesktop (GNOME) > evdev (other Wayland) > xdotool (X11).
    """
    if not _is_wayland():
        return LinuxActionExecutor()

    # GNOME Wayland: use Mutter RemoteDesktop DBus interface
    if _is_mutter_available():
        try:
            executor = MutterRemoteDesktopExecutor()
            logger.info("Wayland: using Mutter RemoteDesktop")
            return executor
        except Exception as e:
            logger.warning("Mutter RemoteDesktop failed: %s, trying evdev", e)

    # Other Wayland compositors: try evdev
    if evdev_import is not None:
        mouse = _find_evdev_mouse()
        kbd = _find_evdev_keyboard()
        if mouse is not None and kbd is not None:
            logger.info("Wayland: using evdev")
            return EvdevActionExecutor(mouse, kbd, screen_w, screen_h)
        if mouse:
            mouse.close()
        if kbd:
            kbd.close()

    logger.warning("Wayland: no working input method, falling back to xdotool")
    return LinuxActionExecutor()


# ---------------------------------------------------------------------------
# Foreground window detection
# ---------------------------------------------------------------------------

_FG_WINDOW_TTL = 0.1  # 100ms cache
_fg_window_cache: Optional[tuple[float, Optional[ForegroundWindow]]] = None


def _get_foreground_window_linux() -> Optional[ForegroundWindow]:
    global _fg_window_cache
    now = time.monotonic()
    if _fg_window_cache is not None:
        ts, cached = _fg_window_cache
        if now - ts < _FG_WINDOW_TTL:
            return cached

    result = _query_foreground_window()
    _fg_window_cache = (now, result)
    return result


def _query_foreground_window_wayland() -> Optional[ForegroundWindow]:
    """Get the focused window on Wayland via AT-SPI2 accessibility."""
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError):
        return None

    Atspi.init()
    desktop = Atspi.get_desktop(0)
    best: Optional[ForegroundWindow] = None

    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is None:
            continue
        try:
            for j in range(app.get_child_count()):
                window = app.get_child_at_index(j)
                if window is None:
                    continue
                ss = window.get_state_set()
                if not ss.contains(Atspi.StateType.ACTIVE):
                    continue

                rect = window.get_extents(Atspi.CoordType.SCREEN)
                pid = window.get_process_id()
                app_name = ""
                if pid > 0:
                    try:
                        with open(f"/proc/{pid}/comm") as f:
                            app_name = f.read().strip()
                    except (OSError, IOError):
                        pass
                if not app_name:
                    app_name = app.get_name()

                # Keep updating — last ACTIVE window in the tree is typically
                # the most recently focused one on GNOME.
                best = ForegroundWindow(
                    app_name=app_name,
                    title=window.get_name() or "",
                    x=rect.x, y=rect.y,
                    width=rect.width, height=rect.height,
                    pid=pid,
                )
        except Exception:
            continue

    return best


def _query_foreground_window_xdotool() -> Optional[ForegroundWindow]:
    """Get the focused window on X11 via xdotool."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname",
             "getactivewindow", "getwindowgeometry", "--shell",
             "getactivewindow", "getwindowpid"],
            capture_output=True, text=True, timeout=2.0,
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return None

        title = lines[0]
        geo = {}
        pid = 0
        for line in lines[1:]:
            if "=" in line:
                k, v = line.split("=", 1)
                geo[k.strip()] = v.strip()
            elif line.strip().isdigit():
                pid = int(line.strip())

        x = int(geo.get("X", 0))
        y = int(geo.get("Y", 0))
        width = int(geo.get("WIDTH", 0))
        height = int(geo.get("HEIGHT", 0))

        app_name = ""
        if pid > 0:
            try:
                with open(f"/proc/{pid}/comm") as f:
                    app_name = f.read().strip()
            except (OSError, IOError):
                pass

        return ForegroundWindow(
            app_name=app_name, title=title,
            x=x, y=y, width=width, height=height, pid=pid,
        )
    except Exception:
        return None


def _query_foreground_window() -> Optional[ForegroundWindow]:
    """Get the focused window. Tries Wayland (AT-SPI2) first, then X11 (xdotool)."""
    if _is_wayland():
        result = _query_foreground_window_wayland()
        if result:
            return result
    return _query_foreground_window_xdotool()


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class LinuxBackend(PlatformBackend):

    def __init__(self):
        self._capture: Optional[ScreenCapture] = None
        self._executor: Optional[ActionExecutor] = None

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = _create_screen_capture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            self._executor = _create_action_executor()
        return self._executor

    def is_available(self) -> bool:
        if _is_wayland():
            return _is_mutter_available() or evdev_import is not None
        return shutil.which("xdotool") is not None

    def get_foreground_window(self) -> Optional[ForegroundWindow]:
        return _get_foreground_window_linux()

    def get_accessibility_info(self) -> dict:
        try:
            import pyatspi  # noqa: F401

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
