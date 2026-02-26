"""WSL2 platform backend using PowerShell bridge to control Windows desktop."""

import logging
import os
import shutil
import subprocess
import tempfile

from computer_use.core.actions import ActionExecutor
from computer_use.core.errors import ActionError, ScreenCaptureError
from computer_use.core.screenshot import ScreenCapture
from computer_use.core.types import Region, ScreenState
from computer_use.platform.base import PlatformBackend

logger = logging.getLogger("computer_use.platform.wsl2")

POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


# --- Path conversion utilities ---


def wsl_to_win_path(wsl_path: str) -> str:
    """Convert /mnt/c/Users/... to C:\\Users\\..."""
    if wsl_path.startswith("/mnt/"):
        drive = wsl_path[5]
        rest = wsl_path[6:].replace("/", "\\")
        return f"{drive.upper()}:{rest}"
    return wsl_path


def win_to_wsl_path(win_path: str) -> str:
    """Convert C:\\Users\\... to /mnt/c/Users/..."""
    if len(win_path) >= 2 and win_path[1] == ":":
        drive = win_path[0].lower()
        rest = win_path[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return win_path


def _get_windows_temp_dir() -> str:
    """Get a Windows temp directory accessible from WSL2."""
    user = os.environ.get("USER", "")
    candidates = [
        f"/mnt/c/Users/{user}/AppData/Local/Temp",
        "/mnt/c/Temp",
        "/mnt/c/Windows/Temp",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    # Fallback: ask PowerShell
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-Command", "$env:TEMP"],
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    if result.returncode == 0 and result.stdout.strip():
        return win_to_wsl_path(result.stdout.strip())
    raise ScreenCaptureError("Cannot determine Windows temp directory from WSL2")


def _run_ps(script: str, timeout: float = 15.0) -> str:
    """Run a PowerShell script from WSL2 and return stdout."""
    win_temp = _get_windows_temp_dir()
    script_path = os.path.join(win_temp, "cue_temp.ps1")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    try:
        win_script_path = wsl_to_win_path(script_path)
        result = subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                win_script_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"PowerShell error (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout.strip()
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


# --- Screenshot capture ---

CAPTURE_FULL_SCRIPT = """
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap($vs.Width, $vs.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($vs.Location, [System.Drawing.Point]::Empty, $vs.Size)
$bitmap.Save("{output_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "$($vs.Width),$($vs.Height),$($vs.X),$($vs.Y)"
"""

CAPTURE_REGION_SCRIPT = """
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bitmap = New-Object System.Drawing.Bitmap({width}, {height})
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$src = New-Object System.Drawing.Point({x}, {y})
$dst = [System.Drawing.Point]::Empty
$size = New-Object System.Drawing.Size({width}, {height})
$graphics.CopyFromScreen($src, $dst, $size)
$bitmap.Save("{output_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "{width},{height}"
"""

SCREEN_SIZE_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
$vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
Write-Output "$($vs.Width),$($vs.Height)"
"""

SCALE_FACTOR_SCRIPT = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class DpiHelper {
    [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr hwnd);
    [DllImport("gdi32.dll")] public static extern int GetDeviceCaps(IntPtr hdc, int index);
    [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
    public static float GetScale() {
        IntPtr hdc = GetDC(IntPtr.Zero);
        int dpi = GetDeviceCaps(hdc, 88);
        ReleaseDC(IntPtr.Zero, hdc);
        return dpi / 96.0f;
    }
}
'@
Write-Output ([DpiHelper]::GetScale())
"""


class WSL2ScreenCapture(ScreenCapture):
    """Screenshot capture via PowerShell on WSL2."""

    def __init__(self):
        self._win_temp = _get_windows_temp_dir()

    def capture_full(self) -> ScreenState:
        output_wsl = os.path.join(self._win_temp, "cue_screenshot.png")
        output_win = wsl_to_win_path(output_wsl)
        script = CAPTURE_FULL_SCRIPT.format(output_path=output_win)

        try:
            result = _run_ps(script)
        except Exception as e:
            raise ScreenCaptureError(f"Full screenshot failed: {e}") from e

        try:
            with open(output_wsl, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            raise ScreenCaptureError(f"Cannot read screenshot file: {e}") from e
        finally:
            try:
                os.unlink(output_wsl)
            except OSError:
                pass

        parts = result.split(",")
        width = int(parts[0])
        height = int(parts[1])
        offset_x = int(parts[2]) if len(parts) > 2 else 0
        offset_y = int(parts[3]) if len(parts) > 3 else 0

        return ScreenState(
            image_bytes=image_bytes,
            width=width,
            height=height,
            scale_factor=self.get_scale_factor(),
            offset_x=offset_x,
            offset_y=offset_y,
        )

    def capture_region(self, region: Region) -> ScreenState:
        output_wsl = os.path.join(self._win_temp, "cue_screenshot_region.png")
        output_win = wsl_to_win_path(output_wsl)
        script = CAPTURE_REGION_SCRIPT.format(
            x=region.x,
            y=region.y,
            width=region.width,
            height=region.height,
            output_path=output_win,
        )

        try:
            _run_ps(script)
        except Exception as e:
            raise ScreenCaptureError(f"Region screenshot failed: {e}") from e

        try:
            with open(output_wsl, "rb") as f:
                image_bytes = f.read()
        except OSError as e:
            raise ScreenCaptureError(f"Cannot read screenshot file: {e}") from e
        finally:
            try:
                os.unlink(output_wsl)
            except OSError:
                pass

        return ScreenState(
            image_bytes=image_bytes,
            width=region.width,
            height=region.height,
            scale_factor=self.get_scale_factor(),
        )

    def get_screen_size(self) -> tuple[int, int]:
        try:
            result = _run_ps(SCREEN_SIZE_SCRIPT)
            parts = result.split(",")
            return (int(parts[0]), int(parts[1]))
        except Exception as e:
            raise ScreenCaptureError(f"Cannot get screen size: {e}") from e

    def get_scale_factor(self) -> float:
        try:
            result = _run_ps(SCALE_FACTOR_SCRIPT)
            return float(result)
        except Exception:
            return 1.0


# --- Action execution ---

MOUSE_MOVE_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})
"""

MOUSE_EVENT_SCRIPT = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class MouseInput {{
    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, int dx, int dy, int dwData, IntPtr dwExtraInfo);

    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
    public const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
    public const uint MOUSEEVENTF_RIGHTUP = 0x0010;
    public const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020;
    public const uint MOUSEEVENTF_MIDDLEUP = 0x0040;
    public const uint MOUSEEVENTF_WHEEL = 0x0800;
}}
'@
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})
Start-Sleep -Milliseconds 50
{mouse_actions}
"""

SENDKEYS_SCRIPT = """
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("{text}")
"""

# Virtual key codes for keybd_event (used for keys SendKeys can't handle, like Win)
VK_CODES = {
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46,
    "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52,
    "s": 0x53, "t": 0x54, "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "ctrl": 0xA2, "control": 0xA2, "alt": 0xA4, "shift": 0xA0,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

KEYBD_EVENT_SCRIPT = """
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class KeyInput {{
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, IntPtr dwExtraInfo);
    public const uint KEYEVENTF_KEYUP = 0x0002;
}}
'@
{key_actions}
"""

# Mapping from key names to SendKeys format
SENDKEYS_MAP = {
    "enter": "{ENTER}",
    "return": "{ENTER}",
    "tab": "{TAB}",
    "escape": "{ESC}",
    "esc": "{ESC}",
    "backspace": "{BS}",
    "delete": "{DEL}",
    "del": "{DEL}",
    "up": "{UP}",
    "down": "{DOWN}",
    "left": "{LEFT}",
    "right": "{RIGHT}",
    "home": "{HOME}",
    "end": "{END}",
    "pageup": "{PGUP}",
    "pagedown": "{PGDN}",
    "f1": "{F1}",
    "f2": "{F2}",
    "f3": "{F3}",
    "f4": "{F4}",
    "f5": "{F5}",
    "f6": "{F6}",
    "f7": "{F7}",
    "f8": "{F8}",
    "f9": "{F9}",
    "f10": "{F10}",
    "f11": "{F11}",
    "f12": "{F12}",
    "space": " ",
}

# Modifier key prefixes for SendKeys
MODIFIER_MAP = {
    "ctrl": "^",
    "control": "^",
    "alt": "%",
    "shift": "+",
}


class WSL2ActionExecutor(ActionExecutor):
    """Action execution via PowerShell on WSL2."""

    def move_mouse(self, x: int, y: int) -> None:
        script = MOUSE_MOVE_SCRIPT.format(x=x, y=y)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Mouse move failed: {e}") from e

    def click(self, x: int, y: int, button: str = "left") -> None:
        if button == "left":
            actions = (
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)"
            )
        elif button == "right":
            actions = (
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_RIGHTUP, 0, 0, 0, [IntPtr]::Zero)"
            )
        elif button == "middle":
            actions = (
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
                "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_MIDDLEUP, 0, 0, 0, [IntPtr]::Zero)"
            )
        else:
            raise ActionError(f"Unknown mouse button: {button}")

        script = MOUSE_EVENT_SCRIPT.format(x=x, y=y, mouse_actions=actions)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Click failed at ({x}, {y}): {e}") from e

    def double_click(self, x: int, y: int) -> None:
        actions = (
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)\n"
            "Start-Sleep -Milliseconds 50\n"
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)\n"
            "[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)"
        )
        script = MOUSE_EVENT_SCRIPT.format(x=x, y=y, mouse_actions=actions)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Double-click failed at ({x}, {y}): {e}") from e

    def type_text(self, text: str) -> None:
        # Escape special SendKeys characters: +, ^, %, ~, (, ), {, }, [, ]
        escaped = ""
        for ch in text:
            if ch in ("+", "^", "%", "~", "(", ")", "{", "}", "[", "]"):
                escaped += "{" + ch + "}"
            else:
                escaped += ch
        script = SENDKEYS_SCRIPT.format(text=escaped)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Type text failed: {e}") from e

    def key_press(self, keys: list[str]) -> None:
        if not keys:
            return

        # Check if any key requires keybd_event (e.g., Win key)
        needs_keybd = any(k.lower() in ("win", "lwin", "rwin") for k in keys)

        if needs_keybd:
            self._key_press_via_keybd(keys)
        else:
            self._key_press_via_sendkeys(keys)

    def _key_press_via_sendkeys(self, keys: list[str]) -> None:
        modifiers = []
        regular_keys = []
        for key in keys:
            lower = key.lower()
            if lower in MODIFIER_MAP:
                modifiers.append(MODIFIER_MAP[lower])
            elif lower in SENDKEYS_MAP:
                regular_keys.append(SENDKEYS_MAP[lower])
            else:
                regular_keys.append(key)

        prefix = "".join(modifiers)
        if len(regular_keys) > 1:
            keys_str = "(" + "".join(regular_keys) + ")"
        elif regular_keys:
            keys_str = regular_keys[0]
        else:
            keys_str = ""

        sendkeys_str = prefix + keys_str
        script = SENDKEYS_SCRIPT.format(text=sendkeys_str)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Key press failed for {keys}: {e}") from e

    def _key_press_via_keybd(self, keys: list[str]) -> None:
        actions = []
        vk_codes_used = []
        for key in keys:
            lower = key.lower()
            vk = VK_CODES.get(lower)
            if vk is None:
                raise ActionError(f"Unknown key for keybd_event: {key}")
            vk_codes_used.append(vk)
            actions.append(f"[KeyInput]::keybd_event({vk}, 0, 0, [IntPtr]::Zero)")

        actions.append("Start-Sleep -Milliseconds 50")

        for vk in reversed(vk_codes_used):
            actions.append(f"[KeyInput]::keybd_event({vk}, 0, [KeyInput]::KEYEVENTF_KEYUP, [IntPtr]::Zero)")

        script = KEYBD_EVENT_SCRIPT.format(key_actions="\n".join(actions))
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Key press failed for {keys}: {e}") from e

    def scroll(self, x: int, y: int, amount: int) -> None:
        # WHEEL_DELTA is 120 per notch
        wheel_amount = amount * 120
        actions = f"[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_WHEEL, 0, 0, {wheel_amount}, [IntPtr]::Zero)"
        script = MOUSE_EVENT_SCRIPT.format(x=x, y=y, mouse_actions=actions)
        try:
            _run_ps(script)
        except Exception as e:
            raise ActionError(f"Scroll failed at ({x}, {y}): {e}") from e

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 0.5,
    ) -> None:
        # Compute intermediate steps for smooth drag
        steps = max(int(duration * 60), 10)  # ~60 fps
        dx = (end_x - start_x) / steps
        dy = (end_y - start_y) / steps
        sleep_ms = int((duration * 1000) / steps)

        move_lines = []
        for i in range(steps + 1):
            cx = int(start_x + dx * i)
            cy = int(start_y + dy * i)
            move_lines.append(
                f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({cx}, {cy})"
            )
            if i < steps:
                move_lines.append(f"Start-Sleep -Milliseconds {sleep_ms}")

        script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class MouseInput {{
    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, int dx, int dy, int dwData, IntPtr dwExtraInfo);
    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
}}
'@
[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({start_x}, {start_y})
Start-Sleep -Milliseconds 50
[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [IntPtr]::Zero)
{chr(10).join(move_lines)}
[MouseInput]::mouse_event([MouseInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [IntPtr]::Zero)
"""
        try:
            _run_ps(script, timeout=duration + 10.0)
        except Exception as e:
            raise ActionError(
                f"Drag failed from ({start_x},{start_y}) to ({end_x},{end_y}): {e}"
            ) from e


# --- Backend ---


class WSL2Backend(PlatformBackend):
    """WSL2 platform backend. Routes all operations through PowerShell."""

    def __init__(self):
        self._capture = None
        self._executor = None

    def get_screen_capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = WSL2ScreenCapture()
        return self._capture

    def get_action_executor(self) -> ActionExecutor:
        if self._executor is None:
            self._executor = WSL2ActionExecutor()
        return self._executor

    def is_available(self) -> bool:
        return shutil.which("powershell.exe") is not None

    def get_accessibility_info(self) -> dict:
        return {
            "available": shutil.which("powershell.exe") is not None,
            "api_name": "UI Automation (via PowerShell)",
            "notes": "Uses Windows UI Automation API through PowerShell subprocess bridge",
        }
