"""The retired source entry point refuses without changing owner state."""

from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_windows_installer_boundary as boundary
from check_windows_installer_boundary import EXPECTED, verify


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows probe")


@pytest.mark.parametrize("shell", ["powershell", "pwsh"])
def test_real_windows_entry_point_refuses_without_mutation(tmp_path, shell):
    executable = shutil.which(shell)
    if executable is None:
        pytest.skip(f"{shell} is not available")
    with patch.object(boundary.shutil, "which", return_value=executable):
        verify(ROOT / "install.ps1", tmp_path)


def test_shell_warmup_uses_a_distinct_noop_file_before_the_installer(tmp_path):
    execute = boundary.subprocess.run
    invocations = []

    def record(arguments, **kwargs):
        invocations.append(arguments)
        if len(invocations) == 1:
            assert "-File" in arguments
            warmup = Path(arguments[-1])
            assert warmup != ROOT / "install.ps1"
            assert warmup.read_text(encoding="utf-8") == "exit 0\n"
        return execute(arguments, **kwargs)

    with patch.object(boundary.subprocess, "run", side_effect=record):
        verify(ROOT / "install.ps1", tmp_path)
    assert len(invocations) == 2
    assert invocations[0][:-1] == invocations[1][:-1]


@pytest.mark.parametrize("prefix,suffix", [
    ('New-Item -ItemType Directory "$env:USERPROFILE/unexpected" | Out-Null\n', ''),
    ('Set-Content "$env:USERPROFILE/owner-state" changed\n', ''),
    ('New-Item -ItemType Directory "$env:TEMP/unexpected" | Out-Null\n', ''),
    ('New-Item -ItemType Directory "$env:LOCALAPPDATA/Microsoft/PowerShell" -Force | Out-Null\n'
     'Set-Content "$env:LOCALAPPDATA/Microsoft/PowerShell/StartupProfileData-NonInteractive" changed\n', ''),
    ('Write-Output "unexpected output"\n', ''),
    ('', 'exit 0\n'),
])
def test_probe_rejects_mutation_or_a_false_refusal(tmp_path, prefix, suffix):
    script = tmp_path / "fixture.ps1"
    script.write_text(prefix + f"[Console]::Error.WriteLine('{EXPECTED}')\n"
                      + (suffix or "exit 2\n"), encoding="utf-8")
    with pytest.raises(RuntimeError):
        verify(script, tmp_path)


def test_probe_rejects_an_unrelated_error(tmp_path):
    script = tmp_path / "fixture.ps1"
    script.write_text("[Console]::Error.WriteLine('unrelated failure')\nexit 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        verify(script, tmp_path)


@pytest.mark.parametrize("cache", sorted(boundary.HOST_CACHES))
def test_only_exact_shell_startup_cache_paths_are_outside_the_mutation_oracle(tmp_path, cache):
    known = tmp_path / cache
    known.parent.mkdir(parents=True)
    known.write_bytes(b"shell cache")
    before = boundary.snapshot(tmp_path)
    known.write_bytes(b"changed shell cache")
    assert boundary.snapshot(tmp_path) == before
    (known.parent / "unknown-cache").write_bytes(b"unknown")
    assert boundary.snapshot(tmp_path) != before


@pytest.mark.parametrize("cache", sorted(boundary.HOST_CACHES))
def test_shell_cache_removal_is_not_hidden(tmp_path, cache):
    known = tmp_path / cache
    known.parent.mkdir(parents=True)
    known.write_bytes(b"shell cache")
    before = boundary.snapshot(tmp_path)
    known.unlink()
    assert boundary.snapshot(tmp_path) != before
