"""Windows bridge daemon: persistent TCP server for fast desktop automation.

Runs natively on Windows. Communicates with WSL2 via TCP localhost.
Uses mss for screenshots, ctypes for Win32 SendInput.

Usage:
    python daemon.py [--port 19542]
    python daemon.py --help
"""

# ── DPI awareness MUST be set before ANY Win32 API call or mss import ──
# This ensures all coordinate APIs use physical pixels consistently,
# whether connected via physical display or Remote Desktop.
import ctypes
import ctypes.wintypes
import sys

def _set_dpi_awareness():
    """Set per-monitor DPI awareness v2. Must run before any Win32 usage."""
    if sys.platform != "win32":
        return
    try:
        # Preferred: Windows 10 1703+ (per-monitor v2)
        u32 = ctypes.windll.user32
        u32.SetProcessDpiAwarenessContext.restype = ctypes.wintypes.BOOL
        u32.SetProcessDpiAwarenessContext.argtypes = [ctypes.wintypes.HANDLE]
        if u32.SetProcessDpiAwarenessContext(ctypes.wintypes.HANDLE(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        # Fallback: Windows 8.1+ (per-monitor v1)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    try:
        # Last resort: Vista+ (system DPI aware)
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

_set_dpi_awareness()
# ── Now safe to use Win32 APIs and import mss ──

import argparse
import base64
import io
import json
import logging
import math
import random
import socket
import struct
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bridge.daemon")

# Win32 constants
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
MOUSEEVENTF_VIRTUALDESK = 0x4000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

HEADER_SIZE = 4
DEFAULT_PORT = 19542
CLIENT_TIMEOUT = 30  # seconds; stale connections are closed after this idle time

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
    "super": 0x5B, "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46,
    "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52,
    "s": 0x53, "t": 0x54, "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
}

# Win32 API handles
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


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


def _send_key_event(vk, down=True):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = 0
    inp.union.ki.dwFlags = 0 if down else KEYEVENTF_KEYUP
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = None
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _log_dpi_diagnostics():
    """Log DPI and coordinate space info at startup for debugging."""
    try:
        ctx = user32.GetThreadDpiAwarenessContext()
        awareness = user32.GetAwarenessFromDpiAwarenessContext(ctx)
        names = {0: "UNAWARE", 1: "SYSTEM_AWARE", 2: "PER_MONITOR_AWARE"}
        logger.info("DPI awareness: %s (%d)", names.get(awareness, "UNKNOWN"), awareness)
    except Exception:
        logger.info("DPI awareness: could not query (older Windows)")

    cx = user32.GetSystemMetrics(SM_CXSCREEN)
    cy = user32.GetSystemMetrics(SM_CYSCREEN)
    logger.info("Primary screen: %dx%d", cx, cy)

    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    logger.info("Virtual screen: origin=(%d,%d) size=%dx%d", vx, vy, vw, vh)

    try:
        dpi = user32.GetDpiForSystem()
        logger.info("System DPI: %d (scale=%.1fx)", dpi, dpi / 96.0)
    except AttributeError:
        try:
            hdc = user32.GetDC(0)
            dpi = gdi32.GetDeviceCaps(hdc, 88)
            user32.ReleaseDC(0, hdc)
            logger.info("DPI (GetDeviceCaps): %d (scale=%.1fx)", dpi, dpi / 96.0)
        except Exception:
            pass


# Adaptation functions for muscle memory (used when hit_count > 0).
# These live alongside daemon.py on Windows, or in core/ on WSL/Linux.
try:
    from spatial_cache import adapted_fitts_duration, muscle_memory_windmouse_params
    _HAS_ADAPT = True
except ImportError:
    _HAS_ADAPT = False


class ScreenCapturer:
    """Fast screenshot capture using mss. Thread-safe via per-thread instances."""

    def __init__(self):
        self._local = threading.local()

    def _get_sct(self):
        """Return a per-thread mss instance (GDI contexts are thread-affine)."""
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss
            sct = mss.mss()
            self._local.sct = sct
        return sct

    def capture_full(self, quality=85):
        sct = self._get_sct()
        monitor = sct.monitors[1]  # primary monitor
        img = sct.grab(monitor)
        jpeg_bytes = self._to_jpeg(img, quality)
        return {
            "width": img.width,
            "height": img.height,
            "offset_x": monitor["left"],
            "offset_y": monitor["top"],
            "scale_factor": self._get_scale_factor(),
            "image_b64": base64.b64encode(jpeg_bytes).decode("ascii"),
        }

    def capture_region(self, x, y, width, height, quality=85):
        sct = self._get_sct()
        region = {"left": x, "top": y, "width": width, "height": height}
        img = sct.grab(region)
        jpeg_bytes = self._to_jpeg(img, quality)
        return {
            "width": img.width,
            "height": img.height,
            "image_b64": base64.b64encode(jpeg_bytes).decode("ascii"),
        }

    def screen_size(self):
        # Query fresh each time -- RDP can change resolution mid-session
        sct = self._get_sct()
        m = sct.monitors[1]
        return {"width": m["width"], "height": m["height"]}

    def scale_factor(self):
        return {"factor": self._get_scale_factor()}

    def _get_scale_factor(self):
        try:
            dpi = user32.GetDpiForSystem()
            return dpi / 96.0
        except AttributeError:
            pass
        try:
            hmon = user32.MonitorFromPoint(ctypes.wintypes.POINT(0, 0), 1)
            dpi_x = ctypes.c_uint()
            dpi_y = ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(
                hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            )
            return dpi_x.value / 96.0
        except (AttributeError, OSError):
            pass
        try:
            hdc = user32.GetDC(0)
            dpi = gdi32.GetDeviceCaps(hdc, 88)
            user32.ReleaseDC(0, hdc)
            return dpi / 96.0
        except Exception:
            return 1.0

    def _to_jpeg(self, mss_img, quality):
        from PIL import Image
        img = Image.frombytes("RGB", (mss_img.width, mss_img.height), mss_img.rgb)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()


# ── Natural mouse movement (WindMouse + Fitts's Law) ──
# Pure math, zero dependencies beyond stdlib math/random.
# Tune these constants to adjust movement feel:

_SQRT3 = math.sqrt(3)
_SQRT5 = math.sqrt(5)

# WindMouse path shape
WIND_GRAVITY = 9.0       # pull toward target (higher = straighter path)
WIND_STRENGTH = 3.0      # random curvature (higher = more wobbly)
WIND_MAX_VEL = 20.0      # max step size in pixels per tick
WIND_HOMING_DIST = 12.0  # distance (px) where homing phase kicks in
WIND_VEL_SCALE = 6.0     # velocity scales as dist / this (lower = faster)

# Fitts's Law timing (seconds)
FITTS_A = 0.05           # base reaction time
FITTS_A_JITTER = 0.01    # gaussian noise on a
FITTS_B = 0.11           # log-distance coefficient
FITTS_B_JITTER = 0.015   # gaussian noise on b
FITTS_MIN_DURATION = 0.07  # floor duration

# Click pauses (seconds)
PRE_CLICK_BASE = 0.03    # min pause before clicking
PRE_CLICK_RAND = 0.05    # random extra pause (uniform)
PRE_DRAG_BASE = 0.03     # min pause before drag press
PRE_DRAG_RAND = 0.04     # random extra drag pause

# Drag trajectory (gentler than free movement)
DRAG_GRAVITY = 7.0
DRAG_WIND = 2.0
DRAG_MAX_VEL = 12.0


def _windmouse_path(start_x, start_y, end_x, end_y, gravity=WIND_GRAVITY,
                    wind=WIND_STRENGTH, max_vel=WIND_MAX_VEL,
                    homing_dist=WIND_HOMING_DIST):
    """Generate a human-like mouse path using the WindMouse algorithm.

    Models the cursor as a particle with two forces:
    - Gravity: constant pull toward target (ballistic aim)
    - Wind: random perturbation that evolves smoothly (natural curvature)

    Returns list of (x, y) integer pixel coordinates.
    """
    dist = math.hypot(end_x - start_x, end_y - start_y)
    if dist < 2:
        return [(end_x, end_y)]

    # Scale parameters to distance so short moves aren't over-animated
    w = min(wind, dist / 50.0)
    m = min(max_vel, dist / WIND_VEL_SCALE)
    m = max(m, 3.0)

    points = []
    sx, sy = float(start_x), float(start_y)
    cx, cy = start_x, start_y
    vx = vy = wx = wy = 0.0
    cur_max = m

    while True:
        d = math.hypot(end_x - sx, end_y - sy)
        if d < 1:
            break

        w_mag = min(w, d)

        if d >= homing_dist:
            # Ballistic phase: active wind perturbation
            wx = wx / _SQRT3 + (random.random() * 2 - 1) * w_mag / _SQRT5
            wy = wy / _SQRT3 + (random.random() * 2 - 1) * w_mag / _SQRT5
        else:
            # Homing phase: wind decays, speed drops
            wx /= _SQRT3
            wy /= _SQRT3
            if cur_max < 3:
                cur_max = random.random() * 3 + 3
            else:
                cur_max /= _SQRT5

        vx += wx + gravity * (end_x - sx) / d
        vy += wy + gravity * (end_y - sy) / d

        v_mag = math.hypot(vx, vy)
        if v_mag > cur_max:
            v_clip = cur_max / 2 + random.random() * cur_max / 2
            vx = (vx / v_mag) * v_clip
            vy = (vy / v_mag) * v_clip

        sx += vx
        sy += vy
        mx, my = int(round(sx)), int(round(sy))

        if mx != cx or my != cy:
            points.append((mx, my))
            cx, cy = mx, my

    # Ensure we land exactly on target
    if not points or points[-1] != (end_x, end_y):
        points.append((end_x, end_y))

    return points


def _fitts_duration(distance, target_width=40):
    """Movement duration in seconds based on Fitts's Law with human jitter."""
    if distance < 1:
        return 0.0
    a = FITTS_A + random.gauss(0, FITTS_A_JITTER)
    b = FITTS_B + random.gauss(0, FITTS_B_JITTER)
    return max(FITTS_MIN_DURATION, a + b * math.log2(distance / target_width + 1))


def _ease_out_quad(t):
    """Easing function: fast start, decelerating to stop. t in [0, 1]."""
    return t * (2 - t)


def _generate_delays(num_points, total_duration):
    """Generate per-step sleep durations using easeOutQuad timing.

    Early steps are short (fast movement), later steps are longer (deceleration).
    """
    if num_points <= 1:
        return [total_duration]

    timestamps = []
    for i in range(num_points):
        t = i / (num_points - 1)
        timestamps.append(_ease_out_quad(t) * total_duration)

    delays = []
    for i in range(1, len(timestamps)):
        delays.append(max(0.001, timestamps[i] - timestamps[i - 1]))
    return delays


class InputSender:
    """Mouse and keyboard input via Win32 SendInput with proper DPI handling.

    Uses MOUSEEVENTF_ABSOLUTE for all mouse positioning -- atomic move+click,
    no race conditions, correct coordinate generation for all apps.
    Queries virtual screen metrics fresh each call to adapt to RDP changes.

    Natural movement uses WindMouse path generation + Fitts's Law timing.
    """

    def _get_virtual_screen(self):
        """Get current virtual screen bounds. Fresh each call for RDP."""
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return vx, vy, vw, vh

    def _normalize(self, x, y):
        """Convert physical pixel coords to 0-65535 normalized virtual desktop coords."""
        vx, vy, vw, vh = self._get_virtual_screen()
        abs_x = int((x - vx) * 65535 / max(vw - 1, 1))
        abs_y = int((y - vy) * 65535 / max(vh - 1, 1))
        return abs_x, abs_y

    def _make_move_input(self, abs_x, abs_y):
        """Create an INPUT struct for absolute mouse move."""
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = abs_x
        inp.union.mi.dy = abs_y
        inp.union.mi.dwFlags = (
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        )
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = None
        return inp

    def _make_button_input(self, flags, data=0):
        """Create an INPUT struct for a mouse button event."""
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dwFlags = flags
        inp.union.mi.mouseData = data
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = None
        return inp

    def _button_flags(self, button):
        if button == "right":
            return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        if button == "middle":
            return MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    @staticmethod
    def _get_cursor_pos():
        """Get current cursor position in physical pixels."""
        point = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def smooth_move(self, end_x, end_y, target_width=40, hit_count=0):
        """Move mouse to (end_x, end_y) with human-like WindMouse motion.

        When hit_count > 1, adapts path and timing via muscle memory:
        straighter paths, faster movement.
        """
        start_x, start_y = self._get_cursor_pos()
        distance = math.hypot(end_x - start_x, end_y - start_y)

        if distance < 2:
            return

        # Adapt WindMouse params based on muscle memory
        path_kwargs = {}
        if _HAS_ADAPT and hit_count > 1:
            path_kwargs = muscle_memory_windmouse_params(hit_count)
        path = _windmouse_path(start_x, start_y, end_x, end_y, **path_kwargs)

        duration = _fitts_duration(distance, target_width)
        if _HAS_ADAPT and hit_count > 1:
            duration = adapted_fitts_duration(duration, hit_count)
        delays = _generate_delays(len(path), duration)

        for i, (px, py) in enumerate(path):
            abs_x, abs_y = self._normalize(px, py)
            inp = self._make_move_input(abs_x, abs_y)
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            if i < len(delays):
                time.sleep(delays[i])

    def _instant_move(self, x, y):
        """Teleport cursor to (x, y) instantly (old behavior)."""
        abs_x, abs_y = self._normalize(x, y)
        inp = self._make_move_input(abs_x, abs_y)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def move_mouse(self, x, y, natural=True, hit_count=0):
        if natural:
            self.smooth_move(x, y, hit_count=hit_count)
        else:
            self._instant_move(x, y)

    def click(self, x, y, button="left", natural=True, hit_count=0):
        down_flag, up_flag = self._button_flags(button)

        if natural:
            # Approach target with smooth movement
            self.smooth_move(x, y, hit_count=hit_count)
            time.sleep(PRE_CLICK_BASE + random.random() * PRE_CLICK_RAND)
            # Slight click offset (humans don't hit pixel-perfect center)
            offset_x = x + int(random.gauss(0, 2))
            offset_y = y + int(random.gauss(0, 2))
            abs_x, abs_y = self._normalize(offset_x, offset_y)
        else:
            abs_x, abs_y = self._normalize(x, y)

        # Atomic click: move + down + up
        inputs = (INPUT * 3)()
        inputs[0] = self._make_move_input(abs_x, abs_y)
        inputs[1] = self._make_button_input(down_flag)
        inputs[2] = self._make_button_input(up_flag)
        sent = user32.SendInput(3, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        if sent != 3:
            logger.warning("SendInput click returned %d (expected 3)", sent)

    def double_click(self, x, y, natural=True, hit_count=0):
        if natural:
            self.smooth_move(x, y, hit_count=hit_count)
            time.sleep(PRE_CLICK_BASE + random.random() * PRE_CLICK_RAND)
            offset_x = x + int(random.gauss(0, 2))
            offset_y = y + int(random.gauss(0, 2))
            abs_x, abs_y = self._normalize(offset_x, offset_y)
        else:
            abs_x, abs_y = self._normalize(x, y)

        # Atomic: move + down + up + down + up
        inputs = (INPUT * 5)()
        inputs[0] = self._make_move_input(abs_x, abs_y)
        inputs[1] = self._make_button_input(MOUSEEVENTF_LEFTDOWN)
        inputs[2] = self._make_button_input(MOUSEEVENTF_LEFTUP)
        # Inter-click delay for double-click (80-150ms like a human)
        time.sleep(0.08 + random.random() * 0.07)
        inputs[3] = self._make_button_input(MOUSEEVENTF_LEFTDOWN)
        inputs[4] = self._make_button_input(MOUSEEVENTF_LEFTUP)
        sent = user32.SendInput(5, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        if sent != 5:
            logger.warning("SendInput double_click returned %d (expected 5)", sent)

    def type_text(self, text):
        """Type text via clipboard paste (Ctrl+V).

        This is the most reliable method across all applications, keyboard
        layouts, and RDP sessions. Sets clipboard content then pastes.
        Falls back to per-character KEYEVENTF_UNICODE for very short text.
        """
        if len(text) <= 3:
            # Very short text: direct key injection avoids clipboard side effects
            self._type_unicode(text)
            return

        # Set clipboard and paste
        self._set_clipboard(text)
        time.sleep(0.05)  # let clipboard settle
        # Ctrl+V paste
        _send_key_event(0x11, down=True)   # Ctrl down
        _send_key_event(0x56, down=True)   # V down
        _send_key_event(0x56, down=False)  # V up
        _send_key_event(0x11, down=False)  # Ctrl up
        time.sleep(0.05)  # let target app process the paste

    def _type_unicode(self, text):
        """Type short text using KEYEVENTF_UNICODE one char at a time."""
        for char in text:
            if char in ("\n", "\r"):
                _send_key_event(0x0D, down=True)
                _send_key_event(0x0D, down=False)
            else:
                code = ord(char)
                inputs = (INPUT * 2)()
                inputs[0].type = INPUT_KEYBOARD
                inputs[0].union.ki.wVk = 0
                inputs[0].union.ki.wScan = code
                inputs[0].union.ki.dwFlags = KEYEVENTF_UNICODE
                inputs[0].union.ki.time = 0
                inputs[0].union.ki.dwExtraInfo = None
                inputs[1].type = INPUT_KEYBOARD
                inputs[1].union.ki.wVk = 0
                inputs[1].union.ki.wScan = code
                inputs[1].union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                inputs[1].union.ki.time = 0
                inputs[1].union.ki.dwExtraInfo = None
                user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
            time.sleep(0.01)

    @staticmethod
    def _set_clipboard(text):
        """Set Windows clipboard text using Win32 API.

        Must declare correct 64-bit return types for GlobalAlloc/GlobalLock,
        otherwise ctypes truncates the pointer to 32 bits -> access violation.
        """
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        kernel32 = ctypes.windll.kernel32

        # Declare proper 64-bit pointer return types (critical on x64)
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

        data = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_mem:
            raise OSError("GlobalAlloc failed")
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            raise OSError("GlobalLock failed")
        ctypes.memmove(p_mem, data, len(data))
        kernel32.GlobalUnlock(h_mem)

        if not user32.OpenClipboard(0):
            raise OSError("OpenClipboard failed")
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, ctypes.c_void_p(h_mem))
        user32.CloseClipboard()

    def key_press(self, keys):
        vk_codes = []
        for key in keys:
            lower = key.lower()
            if lower in VK_MAP:
                vk_codes.append(VK_MAP[lower])
            elif len(key) == 1:
                vk = user32.VkKeyScanW(ord(key))
                if vk != -1:
                    vk_codes.append(vk & 0xFF)
            else:
                logger.warning("Unknown key: %s", key)

        for vk in vk_codes:
            _send_key_event(vk, down=True)
        time.sleep(0.02)
        for vk in reversed(vk_codes):
            _send_key_event(vk, down=False)

    def scroll(self, x, y, amount):
        abs_x, abs_y = self._normalize(x, y)

        # Atomic: move + scroll
        inputs = (INPUT * 2)()
        inputs[0] = self._make_move_input(abs_x, abs_y)
        inputs[1] = self._make_button_input(MOUSEEVENTF_WHEEL, data=amount * 120)
        sent = user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        if sent != 2:
            logger.warning("SendInput scroll returned %d (expected 2)", sent)

    def drag(self, start_x, start_y, end_x, end_y, duration=0.5,
             natural=True):
        if natural:
            # Move to start position naturally
            self.smooth_move(start_x, start_y)
            time.sleep(PRE_DRAG_BASE + random.random() * PRE_DRAG_RAND)

        abs_sx, abs_sy = self._normalize(start_x, start_y)

        # Press down at start
        inputs = (INPUT * 2)()
        inputs[0] = self._make_move_input(abs_sx, abs_sy)
        inputs[1] = self._make_button_input(MOUSEEVENTF_LEFTDOWN)
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))

        if natural:
            # Use WindMouse path for the drag trajectory
            path = _windmouse_path(start_x, start_y, end_x, end_y,
                                   gravity=DRAG_GRAVITY, wind=DRAG_WIND,
                                   max_vel=DRAG_MAX_VEL)
            delays = _generate_delays(len(path), duration)
            for i, (px, py) in enumerate(path):
                self._instant_move(px, py)
                if i < len(delays):
                    time.sleep(delays[i])
        else:
            # Linear interpolation fallback
            steps = max(int(duration * 60), 10)
            sleep_time = duration / steps
            for i in range(1, steps + 1):
                t = i / steps
                cx = int(start_x + (end_x - start_x) * t)
                cy = int(start_y + (end_y - start_y) * t)
                self._instant_move(cx, cy)
                time.sleep(sleep_time)

        # Release
        inp = self._make_button_input(MOUSEEVENTF_LEFTUP)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class BridgeDaemon:
    """TCP server that dispatches JSON requests to ScreenCapturer and InputSender."""

    def __init__(self, port):
        self._port = port
        self._capturer = ScreenCapturer()
        self._input = InputSender()
        self._dispatch_lock = threading.Lock()
        self._handlers = {
            "ping": self._handle_ping,
            "screenshot_full": self._handle_screenshot_full,
            "screenshot_region": self._handle_screenshot_region,
            "screen_size": self._handle_screen_size,
            "scale_factor": self._handle_scale_factor,
            "move_mouse": self._handle_move_mouse,
            "click": self._handle_click,
            "double_click": self._handle_double_click,
            "type_text": self._handle_type_text,
            "key_press": self._handle_key_press,
            "scroll": self._handle_scroll,
            "drag": self._handle_drag,
            "foreground_window": self._handle_foreground_window,
        }

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self._port))
        server.listen(4)
        logger.info("Bridge daemon listening on 0.0.0.0:%d", self._port)

        while True:
            client, addr = server.accept()
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.settimeout(CLIENT_TIMEOUT)
            logger.info("Client connected from %s", addr)
            t = threading.Thread(
                target=self._serve_client, args=(client, addr), daemon=True
            )
            t.start()

    def _serve_client(self, client, addr):
        try:
            self._handle_client(client)
        except socket.timeout:
            logger.info("Client %s timed out after %ds idle", addr, CLIENT_TIMEOUT)
        except Exception as e:
            logger.warning("Client %s disconnected: %s", addr, e)
        finally:
            client.close()

    def _handle_client(self, sock):
        while True:
            header = self._recv_exact(sock, HEADER_SIZE)
            if not header:
                break
            length = struct.unpack("!I", header)[0]
            payload = self._recv_exact(sock, length)
            if not payload:
                break

            request = json.loads(payload)
            response = self._dispatch(request)
            self._send_response(sock, response)

    def _dispatch(self, request):
        req_id = request.get("id", "")
        method = request.get("method", "")
        params = request.get("params", {})

        handler = self._handlers.get(method)
        if handler is None:
            return {"id": req_id, "ok": False, "error": f"Unknown method: {method}"}

        with self._dispatch_lock:
            try:
                result = handler(params)
                return {"id": req_id, "ok": True, "result": result}
            except Exception as e:
                logger.error("Error in %s: %s", method, e)
                return {"id": req_id, "ok": False, "error": str(e)}

    def _send_response(self, sock, response):
        payload = json.dumps(response, separators=(",", ":")).encode("utf-8")
        sock.sendall(struct.pack("!I", len(payload)) + payload)

    def _recv_exact(self, sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _handle_ping(self, params):
        return {"pong": True}

    def _handle_screenshot_full(self, params):
        quality = params.get("quality", 85)
        return self._capturer.capture_full(quality)

    def _handle_screenshot_region(self, params):
        return self._capturer.capture_region(
            params["x"], params["y"],
            params["width"], params["height"],
            params.get("quality", 85),
        )

    def _handle_screen_size(self, params):
        return self._capturer.screen_size()

    def _handle_scale_factor(self, params):
        return self._capturer.scale_factor()

    def _handle_move_mouse(self, params):
        self._input.move_mouse(params["x"], params["y"],
                               natural=params.get("natural", True),
                               hit_count=params.get("hit_count", 0))
        return {}

    def _handle_click(self, params):
        self._input.click(params["x"], params["y"],
                          button=params.get("button", "left"),
                          natural=params.get("natural", True),
                          hit_count=params.get("hit_count", 0))
        return {}

    def _handle_double_click(self, params):
        self._input.double_click(params["x"], params["y"],
                                 natural=params.get("natural", True),
                                 hit_count=params.get("hit_count", 0))
        return {}

    def _handle_type_text(self, params):
        self._input.type_text(params["text"])
        return {}

    def _handle_key_press(self, params):
        self._input.key_press(params["keys"])
        return {}

    def _handle_scroll(self, params):
        self._input.scroll(params["x"], params["y"], params["amount"])
        return {}

    def _handle_drag(self, params):
        self._input.drag(
            params["start_x"], params["start_y"],
            params["end_x"], params["end_y"],
            params.get("duration", 0.5),
            natural=params.get("natural", True),
        )
        return {}

    def _handle_foreground_window(self, params):
        """Return foreground window info via Win32 APIs."""
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {"error": "no foreground window"}

            # Window rect
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

            # Window title
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value

            # Process name via PID
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            app_name = ""
            try:
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
                )
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

            return {
                "app_name": app_name,
                "title": title,
                "x": rect.left,
                "y": rect.top,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
                "pid": pid.value,
            }
        except Exception as e:
            return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Vadgr Bridge Daemon")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    if sys.platform != "win32":
        logger.error("This daemon must run on Windows, not %s", sys.platform)
        sys.exit(1)

    _log_dpi_diagnostics()

    # Set 1ms timer resolution for smooth mouse movement
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
        logger.info("Timer resolution set to 1ms")
    except Exception:
        logger.warning("Could not set 1ms timer resolution")

    daemon = BridgeDaemon(args.port)
    try:
        daemon.run()
    except KeyboardInterrupt:
        logger.info("Shutting down")
    finally:
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass


if __name__ == "__main__":
    main()
