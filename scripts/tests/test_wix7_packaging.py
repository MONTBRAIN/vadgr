"""Checked-in authoring and ABI must match the reviewed WiX release."""

import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_supported_wix_pin_and_explicit_project_acceptance():
    assert json.loads((ROOT / "packaging/toolchain.json").read_text())["wix"] == "7.0.0"
    for name in ("VadgrMsi", "VadgrBundle"):
        project = ET.parse(ROOT / f"packaging/windows/{name}.wixproj").getroot()
        assert project.attrib["Sdk"] == "WixToolset.Sdk/7.0.0"
        assert project.findtext("PropertyGroup/AcceptEula") == "wix7"
        assert all(row.attrib["Version"] == "7.0.0" for row in project.findall(".//PackageReference"))
    script = (ROOT / "scripts/candidate/package-windows.ps1").read_text()
    assert "--version 7.0.0" in script


def test_wix7_bootstrapper_extension_uses_current_message_and_create_layout():
    # Upstream v7.0.0 BootstrapperApplicationTypes.h starts messages at 65536.
    # BAFunctions.h carries pEngine and pCommand after the version field.
    source = (ROOT / "packaging/windows/ba-functions/src/lib.rs").read_text()
    assert "BA_FUNCTIONS_MESSAGE_ON_DETECT_COMPLETE: u32 = 65_542" in source
    assert "bootstrapper_engine: *mut c_void" in source
    assert "bootstrapper_command: *mut c_void" in source
    assert "BA_FUNCTIONS_API_VERSION" in source
    assert "size_of::<BaFunctionsCreateArgs>()" in source


def test_every_windows_candidate_stage_uses_the_native_architecture():
    workflow = (ROOT / ".github/workflows/candidate.yml").read_text()
    for name in ("build-windows", "sign-windows", "attest"):
        # Parse the job block below its label, rather than a matching global runner.
        start = workflow.index(f"\n  {name}:")
        following = re.search(r"\n  [\w-]+:\n", workflow[start + 1:])
        job = workflow[start:] if following is None else workflow[start:start + 1 + following.start()]
        assert "runs-on: ${{ inputs.architecture == 'x64' && 'windows-2025' || 'windows-11-arm' }}" in job


@pytest.mark.skipif(os.name != "nt" or os.environ.get("VADGR_TEST_WIX_BUILD") != "1",
                    reason="explicit Windows development-only WiX compilation requires the pinned SDK")
def test_compile_real_wix7_authoring_with_synthetic_inputs(tmp_path):
    """Compile, never install. No fixture is approved legal content or a candidate."""
    payload = tmp_path / "payload"
    paths = ["vadgr.exe", "vadgr-app.exe", "install-receipt.json", "README-OFFLINE.txt",
             "package-input-inventory.json", "package-input-review.json",
             "legal/TERMS.txt", "legal/PRIVACY-NOTICE.txt", "legal/SECURITY-AND-PERMISSIONS.txt",
             "legal/THIRD-PARTY-NOTICES.txt", "legal/SUPPORT.txt", "legal/UNINSTALL-AND-DATA.txt",
             "sbom/vadgr-0.5.0.spdx.json", "lib/cua/fixture.txt"]
    for name in paths:
        path = payload / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("DEVELOPMENT FIXTURE ONLY. NOT A RELEASE INPUT.\n", encoding="utf-8")
    terms = tmp_path / "TERMS.rtf"
    terms.write_text(r"{\rtf1 DEVELOPMENT FIXTURE ONLY. NOT APPROVED LEGAL TERMS.}", encoding="ascii")
    output = tmp_path / "output"
    command = ["powershell", "-NoProfile", "-NonInteractive", "-File",
               str(ROOT / "packaging/windows/build.ps1"), "-Architecture", "x64",
               "-Version", "0.5.0", "-PayloadDirectory", str(payload), "-TermsRtf", str(terms),
               "-TermsVersion", "1.0", "-OutputDirectory", str(output), "-DevelopmentUnsigned"]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("Vadgr-0.5.0-windows-x64.msi", "Vadgr-0.5.0-windows-x64-setup.exe"):
        assert (output / name).is_file()
        assert (output / name).stat().st_size > 0
    for kind, name in (("msi", "utilca.dll"), ("bundle", "wixstdba.exe")):
        report = json.loads((output / f"wix-vendor-{kind}.json").read_text(encoding="utf-8-sig"))
        assert report["name"] == name
        assert report["architecture"] == "x64"
        assert report["status"] == "valid"
        assert report["timestamp"] is True
