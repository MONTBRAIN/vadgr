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
HOST_CACHES = {
    "shell-profile/AppData/Local/Microsoft/PowerShell/StartupProfileData-NonInteractive",
    "shell-profile/AppData/Local/Microsoft/Windows/PowerShell/StartupProfileData-NonInteractive",
}


def persistent_path():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        return None


def snapshot(root):
    return [(path.relative_to(root).as_posix(),
             "shell-startup-cache" if path.is_file() and not path.is_symlink()
             and path.relative_to(root).as_posix() in HOST_CACHES
             else hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
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
        shell_profile = root / "shell-profile"
        scratch = root / "temporary"
        profile.mkdir()
        shell_profile.mkdir()
        scratch.mkdir()
        for directory in (profile, shell_profile):
            (directory / "AppData/Local").mkdir(parents=True)
            (directory / "AppData/Roaming").mkdir()
        (profile / "owner-state").write_bytes(b"preserve owner state\n")
        # Normalize Windows environment keys before replacing inherited values.
        environment = {key.upper(): value for key, value in os.environ.items()}
        environment.update(USERPROFILE=str(shell_profile), APPDATA=str(shell_profile / "AppData/Roaming"),
                           LOCALAPPDATA=str(shell_profile / "AppData/Local"), TEMP=str(scratch), TMP=str(scratch),
                           VADGR_PROBE_PROFILE=str(profile), VADGR_PROBE_INSTALLER=str(installer.resolve()))
        # The shell records JIT startup data even after a warmup. Its cached
        # host path stays separate from every owner path visible to the script.
        wrapper = root / "invoke.ps1"
        wrapper.write_text(
            "$env:USERPROFILE = $env:VADGR_PROBE_PROFILE\n"
            "$env:APPDATA = [IO.Path]::Combine($env:USERPROFILE, 'AppData', 'Roaming')\n"
            "$env:LOCALAPPDATA = [IO.Path]::Combine($env:USERPROFILE, 'AppData', 'Local')\n"
            "& $env:VADGR_PROBE_INSTALLER\n"
            "exit $LASTEXITCODE\n", encoding="utf-8", newline="\n")
        warmup = root / "warmup.ps1"
        warmup.write_text("exit 0\n", encoding="utf-8", newline="\n")
        command = [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
        subprocess.run(command + ["-File", str(warmup)], cwd=root, env=environment,
                       capture_output=True, check=True, timeout=30)
        before = snapshot(root)
        path_before = persistent_path()
        result = subprocess.run(command + ["-File", str(wrapper)],
                                cwd=root, env=environment, capture_output=True, text=True, timeout=30)
        if snapshot(root) != before or persistent_path() != path_before:
            raise RuntimeError("Windows source entry point changed owner state")
        if result.returncode != 2 or result.stdout or result.stderr != EXPECTED + "\n":
            raise RuntimeError("Windows source entry point did not return the exact graphical-installer refusal")


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1] / "install.ps1",
           Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    print("Windows graphical-installer refusal passed without owner-state mutation.")
