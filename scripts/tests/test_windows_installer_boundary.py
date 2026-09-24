"""The retired source entry point refuses without changing owner state."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_windows_installer_boundary import EXPECTED, verify


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows probe")


def test_real_windows_entry_point_refuses_without_mutation(tmp_path):
    verify(ROOT / "install.ps1", tmp_path)


@pytest.mark.parametrize("prefix,suffix", [
    ('New-Item -ItemType Directory "$env:USERPROFILE/unexpected" | Out-Null\n', ''),
    ('Set-Content "$env:USERPROFILE/owner-state" changed\n', ''),
    ('New-Item -ItemType Directory "$env:TEMP/unexpected" | Out-Null\n', ''),
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
