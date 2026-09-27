"""Unsigned profile assembly cannot claim an authorized runtime."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from unittest.mock import patch

import pytest

from scripts import check_cua_ci_readiness as readiness
from scripts.validate_package_inputs import PackageInputError


def write_json(path, value):
    raw = json.dumps(value).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def runtime(tmp_path, profile):
    root = tmp_path / "install"
    cua = root / "lib/cua"
    cua.mkdir(parents=True)
    binding = {"target": readiness.profiles.target_for(profile), "requirements_sha256": "1" * 64,
               "wheel_manifest_sha256": "2" * 64, "release_profile": profile,
               "cua_profile_manifest_sha256": "3" * 64}
    (cua / "runtime").write_bytes(b"synthetic runtime")
    digest = write_json(cua / "installed-inventory.json", {
        "schema": 1, "target": binding["target"], "files": {
            "runtime": {"size": 17, "sha256": hashlib.sha256(b"synthetic runtime").hexdigest()}}})
    payload = {"schema": 3, **binding, "installed_inventory_sha256": digest,
               "cua_version": "0.7.9"}
    write_json(cua / "payload.json", payload)
    return root, cua, binding, payload


def test_unsigned_profile_checks_inventory_and_requires_unavailable_runtime(tmp_path):
    root, cua, binding, _ = runtime(tmp_path, "macos-aarch64")
    with patch.object(readiness.profiles, "reviewed", return_value=(binding, {}, {"cua_version": "0.7.9"})):
        assert readiness.expected_ready(root, tmp_path, tmp_path, "macos-aarch64") is False
        (cua / "runtime").write_bytes(b"changed runtime")
        with pytest.raises(PackageInputError, match="bytes differ"):
            readiness.expected_ready(root, tmp_path, tmp_path, "macos-aarch64")


@pytest.mark.parametrize("profile", ["linux-x86_64", "linux-aarch64", "wsl-x86_64", "wsl-aarch64"])
def test_linux_runtime_case_distinct_files_preserve_the_unsigned_boundary(tmp_path, profile):
    root, cua, binding, payload = runtime(tmp_path, profile)
    names = ("python/share/terminfo/2/2621A", "python/share/terminfo/2/2621a")
    inventory = json.loads((cua / "installed-inventory.json").read_bytes())
    for name, data in zip(names, (b"uppercase terminal", b"lowercase terminal")):
        path = cua / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        inventory["files"][name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if (cua / names[0]).read_bytes() != b"uppercase terminal":
        pytest.skip("fixture requires a case-sensitive filesystem")
    payload["installed_inventory_sha256"] = write_json(cua / "installed-inventory.json", inventory)
    write_json(cua / "payload.json", payload)
    with patch.object(readiness.profiles, "reviewed", return_value=(binding, {}, {"cua_version": "0.7.9"})):
        assert readiness.expected_ready(root, tmp_path, tmp_path, profile) is False
        for name in names:
            path = cua / name
            before = path.read_bytes()
            path.write_bytes(b"changed")
            with pytest.raises(PackageInputError, match="bytes differ"):
                readiness.expected_ready(root, tmp_path, tmp_path, profile)
            path.write_bytes(before)


@pytest.mark.parametrize("field,value", [("release_profile", "macos-x86_64"),
                                       ("cua_version", "0.7.8"), ("schema", 2)])
def test_profile_readiness_refuses_wrong_payload(tmp_path, field, value):
    root, cua, binding, payload = runtime(tmp_path, "macos-aarch64")
    write_json(cua / "payload.json", {**payload, field: value})
    with patch.object(readiness.profiles, "reviewed", return_value=(binding, {}, {"cua_version": "0.7.9"})):
        with pytest.raises(PackageInputError):
            readiness.expected_ready(root, tmp_path, tmp_path, "macos-aarch64")


@pytest.mark.parametrize("name", ["cua-runtime-authorization.json", "cua-runtime-authorization.sigstore.json"])
def test_unsigned_probe_cannot_accept_installed_authorization(tmp_path, name):
    root, _, binding, _ = runtime(tmp_path, "macos-aarch64")
    (root / name).write_bytes(b"unexpected")
    with patch.object(readiness.profiles, "reviewed", return_value=(binding, {}, {"cua_version": "0.7.9"})):
        with pytest.raises(PackageInputError, match="unsigned"):
            readiness.expected_ready(root, tmp_path, tmp_path, "macos-aarch64")


@pytest.mark.parametrize("schema", [1, 2])
def test_non_profile_payload_keeps_required_availability(tmp_path, schema):
    write_json(tmp_path / "lib/cua/payload.json", {"schema": schema, "cua_version": "0.7.8"})
    assert readiness.expected_ready(tmp_path, tmp_path, tmp_path, None) is True


def test_profile_cannot_silently_fall_back_to_non_profile_expectation(tmp_path):
    root, _, _, _ = runtime(tmp_path, "macos-aarch64")
    with pytest.raises(PackageInputError, match="profile"):
        readiness.expected_ready(root, tmp_path, tmp_path, None)


def test_every_ci_probe_uses_verified_readiness_for_health_and_settings():
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
    assert "python scripts/check_cua_ci_readiness.py" in workflow
    assert workflow.count('--argjson ready "$CUA_CLEAN_EXPECTED_READY"') == 4
    assert workflow.count('.modules == {"computer_use": $ready}') == 2
    assert workflow.count('"venv_ready": $ready') == 2
    assert '$health.modules.computer_use -ne $expectedReady' in workflow
    assert '$computerUse.venv_ready -ne $expectedReady' in workflow


@pytest.mark.parametrize("ready", [True, False])
@pytest.mark.parametrize("actual", [True, False, None])
def test_windows_workflow_rejects_wrong_readiness_on_both_surfaces(ready, actual):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is required to execute the Windows assertions")
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
    health_check = re.search(r"(?s)          \$moduleKeys = .*?\n          }", workflow)[0]
    settings_check = re.search(r"(?s)          \$computerUseKeys = .*?\n          }", workflow)[0]
    document = json.dumps({"health": {"modules": {"computer_use": actual}},
                           "settings": {"enabled": True, "platform": "native", "venv_ready": actual}})
    script = ("$ErrorActionPreference = 'Stop'\n"
              f"$document = '{document}' | ConvertFrom-Json\n"
              f"$expectedReady = ${str(ready).lower()}\n"
              "$health = $document.health\n$computerUse = $document.settings\n"
              # Evaluate independently so a failed health check cannot hide a
              # settings check that would accept the wrong readiness.
              f"try {{ {health_check} ; 'health:pass' }} catch {{ 'health:fail' }}\n"
              f"try {{ {settings_check} ; 'settings:pass' }} catch {{ 'settings:fail' }}\n")
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    expected = "pass" if actual is ready else "fail"
    assert result.stdout.splitlines() == [f"health:{expected}", f"settings:{expected}"]


@pytest.mark.parametrize("ready", [True, False])
@pytest.mark.parametrize("actual", [True, False, None])
def test_unix_workflow_rejects_wrong_readiness_on_both_surfaces(ready, actual):
    jq = shutil.which("jq")
    if not jq:
        pytest.skip("jq is required to execute the Unix assertions")
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
    expressions = re.findall(r"--argjson ready \"\$CUA_CLEAN_EXPECTED_READY\" (?:\\\n\s*)?'(.*?)'",
                             workflow, re.DOTALL)
    assert len(expressions) == 4
    for expression in expressions:
        if ".status" in expression:
            body = {"status": "healthy", "version": "0.5.0",
                    "platform": "macos" if '"macos"' in expression else "linux",
                    "modules": {"computer_use": actual},
                    "transport": {"loopback": {"name": "loopback", "available": True,
                                               "advertise_host": None, "bind_host": "127.0.0.1"}}}
        else:
            body = {"enabled": True, "platform": "native", "venv_ready": actual}
        result = subprocess.run([jq, "-e", "--arg", "version", "0.5.0", "--argjson", "ready",
                                 str(ready).lower(), expression], input=json.dumps(body),
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == (0 if actual is ready else 1), result.stderr
