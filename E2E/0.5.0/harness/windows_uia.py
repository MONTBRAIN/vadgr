#!/usr/bin/env python3
"""Drive and capture Vadgr Windows surfaces through native UI Automation."""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

# pywinauto initializes display handling while importing. Establish the process
# coordinate space first so a UIA rectangle can be used for native input on a
# scaled monitor without a second DPI conversion.
PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)
except (AttributeError, OSError):
    pass

from comtypes import COMError
from PIL import Image
from pywinauto import Desktop
from pywinauto.uia_defines import IUIA
from pywinauto.uia_defines import NoPatternInterfaceError

PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002
SW_SHOW = 5
SW_RESTORE = 9
BI_RGB = 0
DIB_RGB_COLORS = 0


def enable_per_monitor_dpi_awareness():
    """Keep UIA rectangles and native input coordinates in the same space."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)
    except (AttributeError, OSError):
        pass


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


def native_windows():
    """List Win32 top-level windows, including owned modal dialogs UIA omits."""
    user32 = ctypes.windll.user32
    rows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        title_length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(hwnd, title, title_length + 1)
        class_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_name, len(class_name))
        rows.append({
            "handle": int(hwnd),
            "pid": int(process_id.value),
            "title": title.value,
            "class_name": class_name.value,
            "visible": bool(user32.IsWindowVisible(hwnd)),
            "enabled": bool(user32.IsWindowEnabled(hwnd)),
        })
        return True

    user32.EnumWindows(visit, 0)
    return rows


def select_window(
    handle: int | None, pid: int | None, title_regex: str | None,
    restore: bool, focus: bool,
):
    if handle is not None:
        window = Desktop(backend="uia").window(handle=handle)
        if not window.exists():
            raise SystemExit(f"UIA window handle does not exist: {handle}")
        return window
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


def matching_elements(
    window, name: str, control_type: str | None, automation_id: str | None,
    enabled_only: bool,
):
    if automation_id == "<empty>":
        automation_id = ""
    matches = []
    for element in window.descendants():
        info = element.element_info
        if info.name != name:
            continue
        if control_type is not None and info.control_type.casefold() != control_type.casefold():
            continue
        if automation_id is not None and info.automation_id != automation_id:
            continue
        if enabled_only and not element.is_enabled():
            continue
        matches.append(element)
    return matches


def select_element(
    window, name: str, control_type: str | None, automation_id: str | None,
    enabled_only: bool,
):
    matches = matching_elements(window, name, control_type, automation_id, enabled_only)
    if len(matches) != 1:
        print(json.dumps([element_row(item) for item in matches], indent=2), file=sys.stderr)
        raise SystemExit(f"expected one UIA element named {name!r}, found {len(matches)}")
    return matches[0]


def require_input_ownership(element, window):
    """Refuse to send real input unless this window will receive it.

    A key or mouse event goes to whatever holds focus, never to the element it
    was aimed at. On 2026-10-17 a helper focused a field by name, did not check
    which application held focus, and sent keystrokes into an unrelated
    programmer tool that happened to be in front. So this proves all three
    before any event: the target window is the foreground window, the focused
    element belongs to that window's process, and the focused element is the
    one that was selected.

    A pattern call needs none of this, because it is delivered to the element
    itself and cannot reach another application. Prefer `invoke`.
    """
    user32 = ctypes.windll.user32
    expected = int(window.handle)
    foreground = int(user32.GetForegroundWindow())
    if foreground != expected:
        raise SystemExit(
            f"refusing to send input: the foreground window is {foreground}, "
            f"not the target {expected}. Use the invoke action instead."
        )
    expected_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(expected, ctypes.byref(expected_pid))
    try:
        focused = IUIA().iuia.GetFocusedElement()
    except Exception as error:  # noqa: BLE001 - any failure here must refuse
        raise SystemExit(f"refusing to send input: no focused element ({error})")
    if int(focused.CurrentProcessId) != int(expected_pid.value):
        raise SystemExit(
            "refusing to send input: the focused element belongs to process "
            f"{int(focused.CurrentProcessId)}, not {int(expected_pid.value)}"
        )
    selected = element.element_info
    if focused.CurrentName != selected.name:
        raise SystemExit(
            f"refusing to send input: the focused element is "
            f"{focused.CurrentName!r}, not {selected.name!r}"
        )


def invoke(element, action: str, text: str | None, window=None):
    if action == "invoke":
        element.iface_invoke.Invoke()
    elif action == "click":
        # Some custom-drawn controls advertise Invoke through AccessKit/UIA but
        # do not dispatch the provider action on every supported Windows stack.
        # Keep discovery and targeting semantic, then use the element's bounded
        # native input fallback instead of screen coordinates supplied by a
        # human or image recognition.
        #
        # This is a real mouse event at the element's screen position, so it
        # lands on whatever window is in front of that position.
        require_input_ownership(element, window)
        element.click_input()
    elif action == "press-enter":
        # Exercise the semantic keyboard route used by screen-reader users.
        # This also avoids a provider-specific Invoke action on custom-drawn
        # controls while retaining UIA-based element discovery and focus.
        element.set_focus()
        # set_focus can fail silently on a window that cannot take foreground,
        # and the keystroke would then go to whatever did, so the proof comes
        # after the focus attempt rather than before it.
        require_input_ownership(element, window)
        element.type_keys("{ENTER}")
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


def flat_share(image) -> float:
    """The share of pixels that carry the single most common colour, as seen.

    As seen is the whole point, so a transparent pixel is counted as the
    background a reader would see through it rather than as the colour hiding
    underneath. `PrintWindow` without `PW_RENDERFULLCONTENT` returns this
    window's composited areas with their colour intact and their alpha zeroed:
    measured here, 97.1 percent of such a capture was fully transparent while
    its discarded colour data still looked busy. Judging that on `convert("RGB")`
    called a capture rich that every viewer shows as blank, which is exactly
    backwards for a check that exists to catch a capture nobody can read.

    A capture is refused only when it is entirely one colour, because that is
    certainly unrendered. A mostly flat one is reported rather than refused,
    since it can be a real view of a window that renders in layers.
    """
    total = image.width * image.height
    if total == 0:
        return 1.0
    if image.mode in ("RGBA", "LA") or "transparency" in getattr(image, "info", {}):
        # Over white, because that is what an image viewer and a reader show.
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        pixels = Image.alpha_composite(background, image.convert("RGBA")).convert("RGB")
    else:
        pixels = image.convert("RGB")
    counts = pixels.getcolors(maxcolors=total) or []
    if not counts:
        return 0.0
    return max(count for count, _ in counts) / total


def capture_client(hwnd: int, destination: Path, full_content: bool = False,
                   whole_window: bool = False) -> float:
    """Capture one window's own pixels, with no other window in the image.

    Two corrections over the obvious implementation, both measured on this
    product:

    `PrintWindow` draws the **whole window**, frame included, whatever flag it
    is given. Sizing the bitmap from `GetClientRect` therefore captures the
    client's width and height starting at the frame's top left, which crops the
    content and shifts every element rectangle. The bitmap is sized from
    `GetWindowRect` and the client area is cropped out afterwards.

    Pass `PW_RENDERFULLCONTENT` for every surface this product draws. The
    composited console needs it, and so does the installer bootstrapper, which
    took two wrong explanations before it was measured properly on 2026-10-23.

    Without the flag, that window's composited areas come back with their
    colour intact and their alpha zeroed: 97.1 percent of such a capture was
    fully transparent, so it looks blank to every viewer while its discarded
    colour data still looks busy. With the flag, the same window comes back
    whole and fully opaque, frame, step list, headings, terms text and child
    controls together, once it has finished painting.

    Two earlier versions of this docstring were wrong about this. The first
    said the bootstrapper returns an empty client when the flag is passed, and
    following it produced the partly painted frame that a pass filed as an
    unexplained observation. The second said neither flag carries that window
    whole, which came from capturing it before it had painted. Read
    `flat_share` below rather than either claim.
    """
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)
    except (AttributeError, OSError):
        pass
    gdi32 = ctypes.windll.gdi32
    rectangle = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rectangle)):
        raise ctypes.WinError()
    width = rectangle.right - rectangle.left
    height = rectangle.bottom - rectangle.top
    if width <= 0 or height <= 0:
        raise SystemExit("window has no area to capture")
    window_dc = user32.GetDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        flags = PW_RENDERFULLCONTENT if full_content else 0
        if not user32.PrintWindow(hwnd, memory_dc, flags):
            raise SystemExit(f"PrintWindow failed with flags {flags}")
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
        image = Image.frombuffer("RGBA", (width, height), data, "raw", "BGRA", 0, 1)
        if not whole_window:
            # Map the client area through the window origin, because the bitmap
            # starts at the frame rather than at the client.
            client = wintypes.RECT()
            if not user32.GetClientRect(hwnd, ctypes.byref(client)):
                raise ctypes.WinError()
            origin = wintypes.POINT(0, 0)
            if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
                raise ctypes.WinError()
            left = origin.x - rectangle.left
            top = origin.y - rectangle.top
            image = image.crop((left, top, left + (client.right - client.left),
                                top + (client.bottom - client.top)))
        # A blank capture used to be filed as evidence and then had to be
        # retaken. An image with one colour is never a rendered surface.
        share = flat_share(image)
        if share == 1.0:
            raise SystemExit(
                "the capture is a single flat colour, so the surface did not render; "
                "try the other content flag"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
        return share
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, window_dc)


def main() -> int:
    enable_per_monitor_dpi_awareness()
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("windows")
    subcommands.add_parser("native-windows")
    for name in ("tree", "find", "act", "capture"):
        command = subcommands.add_parser(name)
        command.add_argument("--handle", type=int)
        command.add_argument("--pid", type=int)
        command.add_argument("--title-regex")
        command.add_argument("--restore-window", action="store_true")
        command.add_argument("--focus-window", action="store_true")
        if name in ("find", "act"):
            command.add_argument("--name", required=True)
            command.add_argument("--control-type")
            command.add_argument("--automation-id")
            command.add_argument("--enabled-only", action="store_true")
        if name == "act":
            command.add_argument(
                "--action",
                choices=("invoke", "click", "press-enter", "toggle", "select", "set-value"),
                required=True,
            )
            command.add_argument("--text")
        if name == "capture":
            command.add_argument("--output", type=Path, required=True)
            # The composited egui console renders only with the full-content
            # flag; the Burn bootstrapper renders only without it.
            command.add_argument("--full-content", action="store_true")
            command.add_argument("--whole-window", action="store_true")
    args = parser.parse_args()
    if args.command == "windows":
        print(json.dumps(windows(), indent=2))
        return 0
    if args.command == "native-windows":
        print(json.dumps(native_windows(), indent=2))
        return 0
    window = select_window(
        args.handle, args.pid, args.title_regex,
        args.restore_window or args.focus_window,
        args.focus_window,
    )
    if args.command == "tree":
        print(json.dumps([element_row(item) for item in window.descendants()], indent=2))
    elif args.command == "find":
        print(json.dumps([element_row(item) for item in matching_elements(
            window, args.name, args.control_type, args.automation_id,
            args.enabled_only)], indent=2))
    elif args.command == "act":
        element = select_element(
            window, args.name, args.control_type, args.automation_id,
            args.enabled_only,
        )
        before = element_row(element)
        invoke(element, args.action, args.text, window)
        print(json.dumps({"before": before, "action": args.action}, indent=2))
    elif args.command == "capture":
        share = capture_client(int(window.handle), args.output,
                               args.full_content, args.whole_window)
        print(json.dumps({
            "output": str(args.output),
            "handle": int(window.handle),
            # The share of the image that is one flat colour. A high value on a
            # window that should be busy means the flag carried only one half of
            # it, which is the condition that once got filed as a finished frame.
            "flat_share": round(share, 4),
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
