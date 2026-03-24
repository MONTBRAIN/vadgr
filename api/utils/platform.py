"""Cross-platform utilities for Agent Forge.

Provides OS-aware helpers for subprocess management, virtualenv path
resolution, and PATH manipulation.  All functions use ``sys.platform``
checks so adding a new platform (e.g. macOS) is a single ``elif`` branch.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import Union


# ---------------------------------------------------------------------------
# Python command resolution
# ---------------------------------------------------------------------------

def python_command() -> str:
    """Return the Python interpreter command for the current platform.

    Windows installs as ``python``; Linux/macOS as ``python3``.
    """
    if sys.platform == "win32":
        return "python"
    return "python3"


# ---------------------------------------------------------------------------
# Virtualenv path resolution
# ---------------------------------------------------------------------------

def venv_bin_dir(venv_path: Union[str, Path]) -> Path:
    """Return the directory containing executables inside a virtualenv.

    Windows: ``<venv>/Scripts``
    Linux/macOS: ``<venv>/bin``
    """
    venv_path = Path(venv_path)
    if sys.platform == "win32":
        return venv_path / "Scripts"
    return venv_path / "bin"


def venv_pip(venv_path: Union[str, Path]) -> Path:
    """Return the full path to ``pip`` inside a virtualenv."""
    return venv_bin_dir(venv_path) / "pip"


def venv_python(venv_path: Union[str, Path]) -> Path:
    """Return the full path to ``python`` inside a virtualenv."""
    return venv_bin_dir(venv_path) / "python"


# ---------------------------------------------------------------------------
# PATH manipulation
# ---------------------------------------------------------------------------

def remove_path_entry(path_string: str, entry: Union[str, Path]) -> str:
    """Remove all occurrences of *entry* from a ``PATH``-style string.

    Uses ``os.pathsep`` for splitting/joining.  On Windows the comparison
    is case-insensitive; on other platforms it is exact.
    """
    if not path_string:
        return path_string

    entry_str = str(entry)
    case_insensitive = sys.platform == "win32"

    if case_insensitive:
        entry_lower = entry_str.lower()
        parts = [
            p for p in path_string.split(os.pathsep)
            if p.lower() != entry_lower
        ]
    else:
        parts = [
            p for p in path_string.split(os.pathsep)
            if p != entry_str
        ]

    return os.pathsep.join(parts)


# ---------------------------------------------------------------------------
# Command resolution
# ---------------------------------------------------------------------------

def resolve_command(cmd: str) -> str:
    """Resolve a command name to its full executable path.

    On Windows, ``asyncio.create_subprocess_exec`` does not consult
    ``PATHEXT`` so bare names like ``codex`` fail when the real binary
    is ``codex.CMD`` (npm shim).  ``shutil.which`` handles this correctly
    on every platform — native ``.exe``, npm ``.cmd``, and Unix binaries.

    Absolute paths are returned unchanged.
    """
    if os.path.isabs(cmd) or PureWindowsPath(cmd).is_absolute():
        return cmd
    resolved = shutil.which(cmd)
    return resolved if resolved else cmd


# ---------------------------------------------------------------------------
# Subprocess process management
# ---------------------------------------------------------------------------

def new_session_kwargs() -> dict:
    """Return keyword arguments to isolate a subprocess in its own session.

    On Windows: ``creationflags=CREATE_NEW_PROCESS_GROUP``
    On Linux/macOS: ``start_new_session=True``
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Kill a subprocess and its children, then wait for it to exit.

    On Linux/macOS: sends ``SIGKILL`` to the process group.
    On Windows: uses ``taskkill /F /T`` to kill the process tree.
    Falls back to ``proc.kill()`` on any error.
    """
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass

    await proc.wait()
