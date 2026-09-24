#!/usr/bin/env python3
"""Run the Windows source-entry refusal in disposable owner state."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


EXPECTED = ("Windows uses the graphical Vadgr installer. Download the Windows installer "
            "from https://github.com/MONTBRAIN/vadgr/releases.")


def persistent_path():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        return None


def snapshot(root):
    return [(str(path.relative_to(root)),
             hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
            for path in sorted(root.rglob("*"))]


def verify(installer: Path, temporary: Path):
    if sys.platform != "win32":
        raise RuntimeError("This probe requires native Windows")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise RuntimeError("PowerShell is required")
    with tempfile.TemporaryDirectory(prefix="vadgr-windows-refusal-", dir=temporary) as directory:
        root = Path(directory)
        profile = root / "profile"
        scratch = root / "temporary"
        profile.mkdir()
        scratch.mkdir()
        (profile / "AppData/Local").mkdir(parents=True)
        (profile / "AppData/Roaming").mkdir()
        (profile / "owner-state").write_bytes(b"preserve owner state\n")
        # Normalize Windows environment keys before replacing inherited values.
        environment = {key.upper(): value for key, value in os.environ.items()}
        environment.update(USERPROFILE=str(profile), APPDATA=str(profile / "AppData/Roaming"),
                           LOCALAPPDATA=str(profile / "AppData/Local"), TEMP=str(scratch), TMP=str(scratch))
        # Windows PowerShell creates its own startup cache even with no profile.
        # Initialize that host state before the installer mutation boundary.
        command = [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
        subprocess.run(command + ["-Command", "exit 0"], cwd=root, env=environment,
                       capture_output=True, check=True, timeout=30)
        before = snapshot(root)
        path_before = persistent_path()
        result = subprocess.run(command + ["-File", str(installer.resolve())],
                                cwd=root, env=environment, capture_output=True, text=True, timeout=30)
        if snapshot(root) != before or persistent_path() != path_before:
            raise RuntimeError("Windows source entry point changed owner state")
        if result.returncode != 2 or result.stdout or result.stderr != EXPECTED + "\n":
            raise RuntimeError("Windows source entry point did not return the exact graphical-installer refusal")


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1] / "install.ps1",
           Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    print("Windows graphical-installer refusal passed without owner-state mutation.")
