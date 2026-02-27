"""Windows bridge daemon: persistent TCP server for fast desktop automation.

Runs natively on Windows. Communicates with WSL2 via TCP localhost.
Uses mss for screenshots, ctypes for Win32 SendInput.

Usage:
    python daemon.py [--port 19542]
    python daemon.py --help
"""

import argparse
import base64
import ctypes
import ctypes.wintypes
import io
import json
import logging
import socket
import struct
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("bridge.daemon")

# Win32 constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
LOGPIXELSX = 88

HEADER_SIZE = 4
DEFAULT_PORT = 19542

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

# Win32 structures
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


def _send_mouse_input(flags, dx=0, dy=0, data=0):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi.dx = dx
    inp.union.mi.dy = dy
    inp.union.mi.mouseData = data
    inp.union.mi.dwFlags = flags
    inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = None
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _send_key_event(vk, down=True):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.union.ki.wVk = vk
    inp.union.ki.wScan = 0
    inp.union.ki.dwFlags = 0 if down else KEYEVENTF_KEYUP
    inp.union.ki.time = 0
    inp.union.ki.dwExtraInfo = None
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class ScreenCapturer:
    """Fast screenshot capture using mss."""

    def __init__(self):
        import mss
        self._sct = mss.mss()

    def capture_full(self, quality=85):
        monitor = self._sct.monitors[1]  # primary monitor
        img = self._sct.grab(monitor)
        jpeg_bytes = self._to_jpeg(img, quality)
        offset_x = monitor["left"]
        offset_y = monitor["top"]
        return {
            "width": img.width,
            "height": img.height,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "scale_factor": self._get_scale_factor(),
            "image_b64": base64.b64encode(jpeg_bytes).decode("ascii"),
        }

    def capture_region(self, x, y, width, height, quality=85):
        region = {"left": x, "top": y, "width": width, "height": height}
        img = self._sct.grab(region)
        jpeg_bytes = self._to_jpeg(img, quality)
        return {
            "width": img.width,
            "height": img.height,
            "image_b64": base64.b64encode(jpeg_bytes).decode("ascii"),
        }

    def screen_size(self):
        m = self._sct.monitors[1]
        return {"width": m["width"], "height": m["height"]}

    def scale_factor(self):
        return {"factor": self._get_scale_factor()}

    def _get_scale_factor(self):
        try:
            hdc = user32.GetDC(0)
            dpi = gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
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


class InputSender:
    """Mouse and keyboard input via Win32 SendInput."""

    def move_mouse(self, x, y):
        user32.SetCursorPos(x, y)

    def click(self, x, y, button="left"):
        self.move_mouse(x, y)
        time.sleep(0.02)
        if button == "left":
            _send_mouse_input(MOUSEEVENTF_LEFTDOWN)
            _send_mouse_input(MOUSEEVENTF_LEFTUP)
        elif button == "right":
            _send_mouse_input(MOUSEEVENTF_RIGHTDOWN)
            _send_mouse_input(MOUSEEVENTF_RIGHTUP)
        elif button == "middle":
            _send_mouse_input(MOUSEEVENTF_MIDDLEDOWN)
            _send_mouse_input(MOUSEEVENTF_MIDDLEUP)

    def double_click(self, x, y):
        self.move_mouse(x, y)
        time.sleep(0.02)
        _send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        _send_mouse_input(MOUSEEVENTF_LEFTUP)
        time.sleep(0.05)
        _send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        _send_mouse_input(MOUSEEVENTF_LEFTUP)

    def type_text(self, text):
        for char in text:
            vk = user32.VkKeyScanW(ord(char))
            if vk == -1:
                hwnd = user32.GetForegroundWindow()
                user32.SendMessageW(hwnd, 0x0102, ord(char), 0)
            else:
                key_code = vk & 0xFF
                modifiers = (vk >> 8) & 0xFF
                if modifiers & 1:
                    _send_key_event(0x10, down=True)
                _send_key_event(key_code, down=True)
                _send_key_event(key_code, down=False)
                if modifiers & 1:
                    _send_key_event(0x10, down=False)
                time.sleep(0.01)

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
        self.move_mouse(x, y)
        time.sleep(0.02)
        _send_mouse_input(MOUSEEVENTF_WHEEL, data=amount * 120)

    def drag(self, start_x, start_y, end_x, end_y, duration=0.5):
        self.move_mouse(start_x, start_y)
        time.sleep(0.02)
        _send_mouse_input(MOUSEEVENTF_LEFTDOWN)

        steps = max(int(duration * 60), 10)
        sleep_time = duration / steps
        for i in range(1, steps + 1):
            t = i / steps
            cx = int(start_x + (end_x - start_x) * t)
            cy = int(start_y + (end_y - start_y) * t)
            self.move_mouse(cx, cy)
            time.sleep(sleep_time)

        _send_mouse_input(MOUSEEVENTF_LEFTUP)


class BridgeDaemon:
    """TCP server that dispatches JSON requests to ScreenCapturer and InputSender."""

    def __init__(self, port):
        self._port = port
        self._capturer = ScreenCapturer()
        self._input = InputSender()
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
        }

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self._port))
        server.listen(1)
        logger.info("Bridge daemon listening on 0.0.0.0:%d", self._port)

        while True:
            client, addr = server.accept()
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            logger.info("Client connected from %s", addr)
            try:
                self._handle_client(client)
            except Exception as e:
                logger.warning("Client disconnected: %s", e)
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
        self._input.move_mouse(params["x"], params["y"])
        return {}

    def _handle_click(self, params):
        self._input.click(params["x"], params["y"], params.get("button", "left"))
        return {}

    def _handle_double_click(self, params):
        self._input.double_click(params["x"], params["y"])
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
        )
        return {}


def main():
    parser = argparse.ArgumentParser(description="Agent Forge Bridge Daemon")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    if sys.platform != "win32":
        logger.error("This daemon must run on Windows, not %s", sys.platform)
        sys.exit(1)

    daemon = BridgeDaemon(args.port)
    try:
        daemon.run()
    except KeyboardInterrupt:
        logger.info("Shutting down")


if __name__ == "__main__":
    main()
