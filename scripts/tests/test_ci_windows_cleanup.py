"""The real Windows cleanup retries transient locks, not failed product checks."""

import base64
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def cleanup_script():
    text = WORKFLOW.read_text()
    step = text.split("- name: What it imports, and the user's steps with the toolchain out of reach\n", 1)[1]
    return textwrap.dedent(step.split("          # Stop it and leave nothing behind.\n", 1)[1].split("          exit 0", 1)[0])


def test_cleanup_is_owned_bounded_and_after_product_oracles():
    text = WORKFLOW.read_text()
    code = cleanup_script()
    assert text.index('throw "the CLI exited') < text.index("$cleanupRoot =")
    assert "[IO.Path]::GetDirectoryName($cleanupRoot) -ne $temporaryRoot" in code
    assert "[guid]::TryParse" in code and "ReparsePoint" in code
    assert "Stop-Process -InputObject $daemon" in code
    assert code.index("WaitForExit(10000)") < code.index("Remove-Item")
    assert "ElapsedMilliseconds -ge 10000" in code
    assert "Remove-Item -LiteralPath $cleanupRoot" in code
    assert "Get-Process" not in code and "SilentlyContinue" not in code


def ps_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_cleanup(tmp_path, *, old=False, outside=False, timeout=False):
    executable = shutil.which("pwsh") or shutil.which("powershell")
    assert executable, "Native Windows cleanup requires PowerShell"
    # The fixture owns both its child and its file lock. The timer releases only
    # that lock; no product process or owner file is inspected or changed.
    setup = r'''
$ErrorActionPreference = 'Stop'
$env:RUNNER_TEMP = TEMPORARY
$root = Join-Path $env:RUNNER_TEMP ([guid]::NewGuid())
New-Item -ItemType Directory -Path $root | Out-Null
Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Threading;
public static class FixtureLock {
    public static FileStream Stream;
    public static Timer Timer;
    public static void Hold(string path) {
        Stream = new FileStream(path, FileMode.Create, FileAccess.ReadWrite, FileShare.None);
        Timer = new Timer(_ => Stream.Dispose(), null, LOCK_DELAY, Timeout.Infinite);
    }
}
'@
$daemon = Start-Process -FilePath EXECUTABLE -ArgumentList '-NoProfile -NonInteractive -Command "Start-Sleep -Seconds 30"' -WindowStyle Hidden -PassThru
[FixtureLock]::Hold((Join-Path $root 'vadgr.db'))
try {
'''.replace("TEMPORARY", ps_literal(tmp_path)).replace("EXECUTABLE", ps_literal(executable))
    setup = setup.replace("LOCK_DELAY", "Timeout.Infinite" if old else "1200")
    if outside:
        setup += "$env:RUNNER_TEMP = Join-Path $env:RUNNER_TEMP 'not-the-parent'\n"
    if timeout:
        setup += "$realDaemon = $daemon\n$daemon = [pscustomobject]@{HasExited=$true}\n"
        setup += "$daemon | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value { param($ms) return $false }\n"
    code = "Stop-Process -Id $daemon.Id -Force\nRemove-Item -LiteralPath $root -Recurse -Force\n" if old else cleanup_script()
    finish = r'''
  if (Test-Path -LiteralPath $root) { throw 'Test directory remains.' }
  if (-not $daemon.HasExited) { throw 'Test daemon remains.' }
  Write-Output 'Owned cleanup completed.'
} finally {
  [FixtureLock]::Stream.Dispose()
  [FixtureLock]::Timer.Dispose()
  if ($realDaemon) { $daemon = $realDaemon }
  if (-not $daemon.HasExited) { $daemon.Kill(); $daemon.WaitForExit(10000) | Out-Null }
}
'''
    encoded = base64.b64encode((setup + code + finish).encode("utf-16-le")).decode()
    return subprocess.run([executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                          capture_output=True, text=True, timeout=45,
                          creationflags=subprocess.CREATE_NO_WINDOW)


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows file sharing and process handles")
def test_native_transient_database_lock_fails_old_cleanup_but_passes_bounded_cleanup(tmp_path):
    previous = run_cleanup(tmp_path, old=True)
    assert previous.returncode != 0, previous.stdout
    assert "vadgr.db" in previous.stderr
    current = run_cleanup(tmp_path)
    assert current.returncode == 0, current.stdout + current.stderr
    assert "Owned cleanup completed." in current.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows process handles")
@pytest.mark.parametrize("case", ["outside", "timeout"])
def test_native_cleanup_refuses_unsafe_root_or_unconfirmed_exit(tmp_path, case):
    result = run_cleanup(tmp_path, **{case: True})
    assert result.returncode != 0
    expected = "outside the owned temporary directory" if case == "outside" else "did not exit before cleanup"
    assert expected in result.stderr
    assert "Owned cleanup completed." not in result.stdout
