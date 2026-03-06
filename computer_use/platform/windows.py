"""Windows native platform backend using ctypes for direct Win32 API access."""

import ctypes
import ctypes.wintypes
import io
import logging
import random
import struct
import sys
import time
from typing import Optional

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.smooth_move import (
    CursorTracker,
    DRAG_GRAVITY,
    DRAG_MAX_VEL,
    DRAG_WIND,
    PRE_CLICK_BASE,
    PRE_CLICK_RAND,
    PRE_DRAG_BASE,
    PRE_DRAG_RAND,
    generate_delays,
    smooth_move,
    windmouse_path,
)
from computer_use.core.types import ForegroundWindow, Region, ScreenState
from computer_use.platform.base import PlatformBackend

logger = logging.getLogger("computer_use.platform.windows")

# Only load win32 types on Windows
_dpi_awareness_set = False
if sys.platform == "win32":
    # Enable per-monitor DPI awareness so coordinates match physical pixels
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        _dpi_awareness_set = True
    except Exception:
        pass  # Already set or shcore unavailable

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32

    # Input event constants
    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_ABSOLUTE = 0x8000
    KEYEVENTF_KEYUP = 0x0002

    # Virtual key codes
    VK_MAP = {
        "enter": 0x0D, "return": 0x0D, "tab": 0x09,
        "escape": 0x1B, "esc": 0x1B, "backspace": 0x08,
        "delete": 0x2E, "del": 0x2E,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "home": 0x24, "end": 0x23,
        "pageup": 0x21, "pagedown": 0x22,
        "space": 0x20,
        "ctrl": 0x11, "control": 0x11,
        "alt": 0x12, "shift": 0x10,
        "super": 0x5B, "win": 0x5B,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
        "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
        "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    }

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.wintypes.LONG),
            ("dy", ctypes.wintypes.LONG),
            ("mouseData", ctypes.wintypes.DWORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.wintypes.WORD),
            ("wScan", ctypes.wintypes.WORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.wintypes.DWORD), ("union", INPUT_UNION)]


class WindowsScreenCapture(ScreenCapture):
    """Screenshot capture using Win32 GDI API."""

    def capture_full(self) -> ScreenState:
        if sys.platform != "win32":
            raise ScreenCaptureError("WindowsScreenCapture requires Windows")

        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        gdi32.SelectObject(hdc_mem, hbmp)
        gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, 0x00CC0020)

        image_bytes = self._bitmap_to_png(hbmp, width, height)

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        return ScreenState(
            image_bytes=image_bytes,
            width=width,
            height=height,
            scale_factor=self.get_scale_factor(),
        )

    def capture_region(self, region: Region) -> ScreenState:
        if sys.platform != "win32":
            raise ScreenCaptureError("WindowsScreenCapture requires Windows")

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, region.width, region.height)
        gdi32.SelectObject(hdc_mem, hbmp)
        gdi32.BitBlt(
            hdc_mem, 0, 0, region.width, region.height,
            hdc_screen, region.x, region.y, 0x00CC0020,
        )

        image_bytes = self._bitmap_to_png(hbmp, region.width, region.height)

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        return ScreenState(
            image_bytes=image_bytes,
            width=region.width,
            height=region.height,
            scale_factor=self.get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        if sys.platform != "win32":
            raise ScreenCaptureError("WindowsScreenCapture requires Windows")
        return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))

    def get_scale_factor(self) -> float:
        if sys.platform != "win32":
            return 1.0
        try:
            hdc = user32.GetDC(0)
            dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            user32.ReleaseDC(0, hdc)
            return dpi / 96.0
        except Exception:
            return 1.0

    def _bitmap_to_png(self, hbmp, width: int, height: int) -> bytes:
        """Convert a Windows HBITMAP to PNG bytes using Pillow."""
        from PIL import Image

        # Get bitmap bits
        bmi = struct.pack(
            "IiiHHIIIIII",
            40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0,
        )
        buf = ctypes.create_string_buffer(width * height * 4)
        hdc = user32.GetDC(0)
        gdi32.GetDIBits(hdc, hbmp, 0, height, buf, bmi, 0)
        user32.ReleaseDC(0, hdc)

        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
        output = io.BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()


class WindowsActionExecutor(ActionExecutor):
    """Action execution using Win32 SendInput API with smooth mouse movement."""

    def __init__(self):
        self._tracker = CursorTracker()

    def _send_mouse_input(self, flags: int, dx: int = 0, dy: int = 0, data: int = 0):
        if sys.platform != "win32":
            raise ActionError("WindowsActionExecutor requires Windows")
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = dx
        inp.union.mi.dy = dy
        inp.union.mi.mouseData = data
        inp.union.mi.dwFlags = flags
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = None
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _raw_move(self, x: int, y: int) -> None:
        """Low-level SetCursorPos. Used as the primitive for smooth_move."""
        user32.SetCursorPos(x, y)
        self._tracker.update(x, y)

    def move_mouse(self, x: int, y: int, hit_count: int = 0) -> None:
        if sys.platform != "win32":
            raise ActionError("WindowsActionExecutor requires Windows")
        smooth_move(x, y, self._tracker.get_pos, self._raw_move, hit_count=hit_count)

    def click(self, x: int, y: int, button: str = "left", hit_count: int = 0) -> None:
        self.move_mouse(x, y, hit_count=hit_count)
        time.sleep(PRE_CLICK_BASE + random.random() * PRE_CLICK_RAND)
        if button == "left":
            self._send_mouse_input(MOUSEEVENTF_LEFTDOWN)
            self._send_mouse_input(MOUSEEVENTF_LEFTUP)
        elif button == "right":
            self._send_mouse_input(MOUSEEVENTF_RIGHTDOWN)
            self._send_mouse_input(MOUSEEVENTF_RIGHTUP)
        elif button == "middle":
            self._send_mouse_input(MOUSEEVENTF_MIDDLEDOWN)
            self._send_mouse_input(MOUSEEVENTF_MIDDLEUP)

    def double_click(self, x: int, y: int, hit_count: int = 0) -> None:
        self.move_mouse(x, y, hit_count=hit_count)
        time.sleep(PRE_CLICK_BASE + random.random() * PRE_CLICK_RAND)
        self._send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        self._send_mouse_input(MOUSEEVENTF_LEFTUP)
        time.sleep(0.05)
        self._send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        self._send_mouse_input(MOUSEEVENTF_LEFTUP)

    def type_text(self, text: str) -> None:
        if sys.platform != "win32":
            raise ActionError("WindowsActionExecutor requires Windows")
        for char in text:
            vk = ctypes.windll.user32.VkKeyScanW(ord(char))
            if vk == -1:
                self._send_unicode_char(char)
            else:
                key_code = vk & 0xFF
                modifiers = (vk >> 8) & 0xFF
                if modifiers & 1:  # Shift
                    self._send_key_event(0x10, down=True)
                self._send_key_event(key_code, down=True)
                self._send_key_event(key_code, down=False)
                if modifiers & 1:
                    self._send_key_event(0x10, down=False)
                time.sleep(0.02)

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return
        vk_codes = []
        for key in keys:
            lower = key.lower()
            if lower in VK_MAP:
                vk_codes.append(VK_MAP[lower])
            elif len(key) == 1:
                vk = ctypes.windll.user32.VkKeyScanW(ord(key))
                vk_codes.append(vk & 0xFF)
            else:
                logger.warning("Unknown key: %s", key)
                continue

        for vk in vk_codes:
            self._send_key_event(vk, down=True)
        for vk in reversed(vk_codes):
            self._send_key_event(vk, down=False)

    def scroll(self, x: int, y: int, amount: int) -> None:
        self._raw_move(x, y)
        time.sleep(0.05)
        self._send_mouse_input(MOUSEEVENTF_WHEEL, data=amount * 120)

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
        hit_count: int = 0,
    ) -> None:
        self.move_mouse(start_x, start_y, hit_count=hit_count)
        time.sleep(PRE_DRAG_BASE + random.random() * PRE_DRAG_RAND)
        self._send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        path = windmouse_path(
            start_x, start_y, end_x, end_y,
            gravity=DRAG_GRAVITY, wind=DRAG_WIND, max_vel=DRAG_MAX_VEL,
        )
        delays = generate_delays(len(path), duration)
        for i, (px, py) in enumerate(path):
            self._raw_move(px, py)
            if i < len(delays):
                time.sleep(delays[i])
        self._send_mouse_input(MOUSEEVENTF_LEFTUP)

    def _send_key_event(self, vk: int, down: bool = True):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.wScan = 0
        inp.union.ki.dwFlags = 0 if down else KEYEVENTF_KEYUP
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = None
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _send_unicode_char(self, char: str):
        hwnd = user32.GetForegroundWindow()
        user32.SendMessageW(hwnd, 0x0102, ord(char), 0)  # WM_CHAR


class WindowsBackend(PlatformBackend):
    """Windows native platform backend."""

    def __init__(self):
        self._capture = None
        self._executor = None

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = WindowsScreenCapture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            self._executor = WindowsActionExecutor()
        return self._executor

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def get_foreground_window(self) -> Optional[ForegroundWindow]:
        if sys.platform != "win32":
            return None
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value

            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            app_name = ""
            try:
                handle = kernel32.OpenProcess(0x1000, False, pid.value)
                if handle:
                    try:
                        name_buf = ctypes.create_unicode_buffer(512)
                        size = ctypes.wintypes.DWORD(512)
                        kernel32.QueryFullProcessImageNameW(
                            handle, 0, name_buf, ctypes.byref(size)
                        )
                        full_path = name_buf.value
                        if full_path:
                            app_name = full_path.rsplit("\\", 1)[-1]
                    finally:
                        kernel32.CloseHandle(handle)
            except Exception:
                pass

            return ForegroundWindow(
                app_name=app_name,
                title=title,
                x=rect.left,
                y=rect.top,
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
                pid=pid.value,
            )
        except Exception:
            return None

    def get_accessibility_info(self) -> dict:
        return {
            "available": sys.platform == "win32",
            "api_name": "UI Automation",
            "notes": "Native Windows UI Automation via ctypes",
        }
