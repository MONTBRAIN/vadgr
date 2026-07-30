"""The desktop channel -- a native dialog / toast, branched across the four OSes.

``notify`` raises a toast (``low``/``normal``) or a modal (``high``); ``request``
raises a dialog with the choice buttons and returns the pressed button. The
native command is selected by OS -- ``osascript`` (macOS), ``notify-send`` /
``zenity`` (Linux, incl. WSL to the Linux desktop), PowerShell (Windows) -- and
run through an injectable ``runner`` so tests assert the selection without a GUI.
"""

from __future__ import annotations

import platform
import subprocess
from typing import Callable

from engine.channels.base import Delivery, HumanPrompt

_YES = {"approve", "approved", "yes", "y", "ok", "allow"}
_REVISE = {"revise", "edit", "change"}


def _default_runner(argv: list[str]) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return proc.stdout


class DesktopChannel:
    name = "desktop"

    def __init__(
        self,
        *,
        os_name: str | None = None,
        runner: Callable[[list[str]], str] = _default_runner,
    ):
        self._os = os_name or platform.system()
        self._run = runner

    async def notify(self, message: str, *, importance: str = "normal") -> Delivery:
        modal = importance == "high"
        argv = self._notify_argv(message, modal=modal)
        if argv:
            self._run(argv)
        return Delivery(delivered=[self.name])

    async def request(self, prompt: HumanPrompt) -> dict:
        argv = self._request_argv(prompt)
        raw = self._run(argv) if argv else ""
        return self._interpret(prompt, raw)

    # -- per-OS command construction ----------------------------------------

    def _notify_argv(self, message: str, *, modal: bool) -> list[str]:
        if self._os == "Darwin":
            script = (
                f'display dialog "{message}" buttons {{"OK"}}'
                if modal
                else f'display notification "{message}" with title "vadgr"'
            )
            return ["osascript", "-e", script]
        if self._os == "Windows":
            verb = "MessageBox" if modal else "Notify"
            return [
                "powershell", "-NoProfile", "-Command",
                f"[void][System.Windows.Forms.MessageBox]::Show('{message}')"
                if modal
                else f"Write-Output '{verb}: {message}'",
            ]
        # Linux / WSL desktop.
        if modal:
            return ["zenity", "--info", f"--text={message}"]
        return ["notify-send", "vadgr", message]

    def _request_argv(self, prompt: HumanPrompt) -> list[str]:
        text = prompt.text
        if self._os == "Darwin":
            buttons = self._buttons(prompt)
            btn = ", ".join(f'"{b}"' for b in buttons)
            return [
                "osascript", "-e",
                f'button returned of (display dialog "{text}" buttons {{{btn}}})',
            ]
        if self._os == "Windows":
            return [
                "powershell", "-NoProfile", "-Command",
                f"$r = [System.Windows.Forms.MessageBox]::Show('{text}',"
                "'vadgr','YesNo'); Write-Output $r",
            ]
        # Linux / WSL.
        return ["zenity", "--question", f"--text={text}"]

    def _buttons(self, prompt: HumanPrompt) -> list[str]:
        if prompt.kind == "plan":
            return ["approve", "revise", "reject"]
        if prompt.kind == "question" and prompt.options:
            return list(prompt.options)
        return ["approve", "reject"]

    def _interpret(self, prompt: HumanPrompt, raw: str) -> dict:
        answer = (raw or "").strip()
        low = answer.lower()
        if prompt.kind == "approval":
            # zenity --question exits 0 (empty stdout) on Yes; treat explicit
            # affirmatives and an empty (OK/Yes) reply as approve.
            choice = "approve" if (low in _YES or answer == "") else "reject"
            return {"choice": choice, "text": answer, "timed_out": False}
        if prompt.kind == "plan":
            if low in _YES:
                choice = "approve"
            elif low in _REVISE:
                choice = "revise"
            else:
                choice = "reject"
            return {"choice": choice, "text": answer, "timed_out": False}
        return {"choice": answer, "text": answer, "timed_out": False}
