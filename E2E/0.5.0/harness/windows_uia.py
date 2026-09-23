#!/usr/bin/env python3
"""Drive and capture Vadgr Windows surfaces through native UI Automation."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import sys
import time

from PIL import Image
from pywinauto import Desktop
from pywinauto.uia_defines import NoPatternInterfaceError
from comtypes import COMError


PW_CLIENTONLY = 0x00000001
SW_SHOW = 5
SW_RESTORE = 9
BI_RGB = 0
DIB_RGB_COLORS = 0
PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def restore_win32_window(pid: int | None, pattern: re.Pattern[str] | None, focus: bool):
    user32 = ctypes.windll.user32
    matches = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if pid is not None and process_id.value != pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if pattern is not None and not pattern.search(title.value):
            return True
        if title.value:
            matches.append((int(hwnd), title.value))
        return True

    user32.EnumWindows(visit, 0)
    if len(matches) != 1:
        raise SystemExit(f"expected one Win32 window to restore, found {len(matches)}: {matches}")
    hwnd, _ = matches[0]
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.ShowWindow(hwnd, SW_RESTORE)
    if focus:
        user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    return Desktop(backend="uia").window(handle=hwnd)


def windows():
    rows = []
    for window in Desktop(backend="uia").windows():
        try:
            rows.append({
                "handle": int(window.handle),
                "pid": int(window.process_id()),
                "title": window.window_text(),
                "control_type": window.element_info.control_type,
                "visible": bool(window.is_visible()),
                "enabled": bool(window.is_enabled()),
            })
        except (RuntimeError, TypeError, COMError):
            continue
    return rows


def select_window(pid: int | None, title_regex: str | None, restore: bool, focus: bool):
    pattern = re.compile(title_regex, re.IGNORECASE) if title_regex else None
    matches = []
    for window in Desktop(backend="uia").windows():
        try:
            if pid is not None and int(window.process_id()) != pid:
                continue
            if pattern is not None and not pattern.search(window.window_text()):
                continue
            matches.append(window)
        except (RuntimeError, TypeError, COMError):
            continue
    if not matches and restore:
        return restore_win32_window(pid, pattern, focus)
    if len(matches) != 1:
        summary = [{"handle": int(item.handle), "pid": int(item.process_id()),
                    "title": item.window_text()} for item in matches]
        raise SystemExit(f"expected one UIA window, found {len(matches)}: {summary}")
    window = matches[0]
    if restore:
        ctypes.windll.user32.ShowWindow(int(window.handle), SW_SHOW)
        ctypes.windll.user32.ShowWindow(int(window.handle), SW_RESTORE)
        if focus:
            ctypes.windll.user32.SetForegroundWindow(int(window.handle))
        time.sleep(0.8)
        window = Desktop(backend="uia").window(handle=int(window.handle))
    elif not window.is_visible():
        raise SystemExit("matched UIA window is not visible; pass --restore-window")
    return window


def element_row(element):
    info = element.element_info
    rectangle = info.rectangle
    row = {
        "name": info.name,
        "control_type": info.control_type,
        "automation_id": info.automation_id,
        "enabled": bool(element.is_enabled()),
        "visible": bool(element.is_visible()),
        "rectangle": [rectangle.left, rectangle.top, rectangle.right, rectangle.bottom],
    }
    try:
        row["toggle_state"] = int(element.iface_toggle.CurrentToggleState)
    except (AttributeError, TypeError, ValueError, COMError, NoPatternInterfaceError):
        pass
    return row


def matching_elements(window, name: str, control_type: str | None, enabled_only: bool):
    matches = []
    for element in window.descendants():
        info = element.element_info
        if info.name != name:
            continue
        if control_type is not None and info.control_type.casefold() != control_type.casefold():
            continue
        if enabled_only and not element.is_enabled():
            continue
        matches.append(element)
    return matches


def select_element(window, name: str, control_type: str | None, enabled_only: bool):
    matches = matching_elements(window, name, control_type, enabled_only)
    if len(matches) != 1:
        print(json.dumps([element_row(item) for item in matches], indent=2), file=sys.stderr)
        raise SystemExit(f"expected one UIA element named {name!r}, found {len(matches)}")
    return matches[0]


def invoke(element, action: str, text: str | None):
    if action == "invoke":
        element.iface_invoke.Invoke()
    elif action == "toggle":
        element.iface_toggle.Toggle()
    elif action == "select":
        element.iface_selection_item.Select()
    elif action == "set-value":
        if text is None:
            raise SystemExit("set-value requires --text")
        element.iface_value.SetValue(text)
    else:
        raise SystemExit(f"unsupported action: {action}")


def capture_client(hwnd: int, destination: Path):
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)
    except (AttributeError, OSError):
        pass
    gdi32 = ctypes.windll.gdi32
    rectangle = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rectangle)):
        raise ctypes.WinError()
    width = rectangle.right - rectangle.left
    height = rectangle.bottom - rectangle.top
    if width <= 0 or height <= 0:
        raise SystemExit("window has no client area")
    window_dc = user32.GetDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, PW_CLIENTONLY):
            raise SystemExit("PrintWindow(PW_CLIENTONLY) failed")
        class BitmapInfoHeader(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD), ("width", wintypes.LONG),
                ("height", wintypes.LONG), ("planes", wintypes.WORD),
                ("bit_count", wintypes.WORD), ("compression", wintypes.DWORD),
                ("size_image", wintypes.DWORD), ("x_pixels", wintypes.LONG),
                ("y_pixels", wintypes.LONG), ("colors_used", wintypes.DWORD),
                ("colors_important", wintypes.DWORD),
            ]
        header = BitmapInfoHeader()
        header.size = ctypes.sizeof(BitmapInfoHeader)
        header.width = width
        header.height = -height
        header.planes = 1
        header.bit_count = 32
        header.compression = BI_RGB
        data = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(memory_dc, bitmap, 0, height, data,
                               ctypes.byref(header), DIB_RGB_COLORS):
            raise ctypes.WinError()
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.frombuffer("RGBA", (width, height), data, "raw", "BGRA", 0, 1).save(destination)
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("windows")
    for name in ("tree", "find", "act", "capture"):
        command = subcommands.add_parser(name)
        command.add_argument("--pid", type=int)
        command.add_argument("--title-regex")
        command.add_argument("--restore-window", action="store_true")
        command.add_argument("--focus-window", action="store_true")
        if name in ("find", "act"):
            command.add_argument("--name", required=True)
            command.add_argument("--control-type")
            command.add_argument("--enabled-only", action="store_true")
        if name == "act":
            command.add_argument("--action", choices=("invoke", "toggle", "select", "set-value"), required=True)
            command.add_argument("--text")
        if name == "capture":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "windows":
        print(json.dumps(windows(), indent=2))
        return 0
    window = select_window(
        args.pid, args.title_regex, args.restore_window or args.focus_window,
        args.focus_window,
    )
    if args.command == "tree":
        print(json.dumps([element_row(item) for item in window.descendants()], indent=2))
    elif args.command == "find":
        print(json.dumps([element_row(item) for item in matching_elements(
            window, args.name, args.control_type, args.enabled_only)], indent=2))
    elif args.command == "act":
        element = select_element(window, args.name, args.control_type, args.enabled_only)
        before = element_row(element)
        invoke(element, args.action, args.text)
        print(json.dumps({"before": before, "action": args.action}, indent=2))
    elif args.command == "capture":
        capture_client(int(window.handle), args.output)
        print(json.dumps({"output": str(args.output), "handle": int(window.handle)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
