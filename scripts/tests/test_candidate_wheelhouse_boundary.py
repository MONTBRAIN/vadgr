"""Trusted downloads finish before feature code can run without credentials."""

from pathlib import Path
import re
import os
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("job", ["build-windows", "build-native"])
def test_trusted_materialization_precedes_token_free_compilation(job):
    workflow = (ROOT / ".github/workflows/candidate.yml").read_text()
    block = workflow.split(f"\n  {job}:\n", 1)[1]
    block = re.split(r"\n  [\w-]+:\n", block, maxsplit=1)[0]
    prepare = block.index("- name: Materialize reviewed wheelhouse with read-only access")
    compile_at = block.index("- name: Build", prepare)
    preparation = block[prepare:compile_at]
    assert "GH_TOKEN: ${{ github.token }}" in preparation
    assert "scripts/cua_wheelhouse.py" in preparation
    assert "cargo " not in preparation
    assert "contents: write" not in block and "id-token: write" not in block
    for step in re.split(r"\n      - ", block[compile_at:]):
        if "scripts/candidate/build-" in step:
            assert "GH_TOKEN: ''" in step
            assert "GITHUB_TOKEN: ''" in step
            assert "wheelhouse" in step


@pytest.mark.parametrize("file", ["build-windows.ps1", "build-native.sh"])
def test_compiler_refuses_credentials_and_never_downloads_wheels(file):
    source = (ROOT / "scripts/candidate" / file).read_text()
    assert "GH_TOKEN" in source and "GITHUB_TOKEN" in source
    assert "--verify" in source
    assert "--out" not in source
    assert "gh api" not in source and "gh attestation" not in source


def test_wix_projects_and_vendor_verification_use_same_reviewed_version():
    for name in ("VadgrMsi", "VadgrBundle"):
        source = (ROOT / f"packaging/windows/{name}.wixproj").read_text()
        assert 'Sdk="WixToolset.Sdk/7.0.0"' in source
        assert "<AcceptEula>wix7</AcceptEula>" in source
    assert "--version 7.0.0" in (ROOT / "scripts/candidate/package-windows.ps1").read_text()
    source = (ROOT / "packaging/windows/verify-wix-payload.ps1").read_text()
    assert "verify /pa /all /tw" in source and "TimeStamperCertificate" in source


@pytest.mark.skipif(os.name != "nt", reason="native PowerShell boundary")
def test_windows_builder_refuses_github_access_before_reading_feature(tmp_path):
    result = subprocess.run([
        "powershell", "-NoProfile", "-NonInteractive", "-File",
        str(ROOT / "scripts/candidate/build-windows.ps1"), "-Architecture", "x64",
        "-SourceDirectory", str(tmp_path / "absent-source"),
        "-OutputDirectory", str(tmp_path / "absent-output"),
        "-WheelhouseDirectory", str(tmp_path / "absent-wheelhouse"),
    ], env={**os.environ, "GH_TOKEN": "synthetic-boundary-marker"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Source build must have no signing or identity credential." in result.stderr
    assert "synthetic-boundary-marker" not in result.stdout + result.stderr
    assert not list(tmp_path.iterdir())


def test_native_matrix_has_exactly_eight_distinct_targets():
    from scripts import distribution_matrix as matrix
    rows = matrix.matrix()
    assert {row["target"] for row in rows} == {
        "windows-x86_64", "windows-aarch64", "macos-x86_64", "macos-aarch64",
        "linux-x86_64", "linux-aarch64", "wsl-x86_64", "wsl-aarch64"}
    for architecture in ("x64", "arm64"):
        assert len(matrix.remaining_builds(architecture)) == 7
