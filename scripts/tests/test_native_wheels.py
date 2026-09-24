"""Untrusted wheel outputs cannot become approved dependency inputs."""

import copy
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile

import pytest

from scripts import validate_native_wheels as gate


ROOT = Path(__file__).resolve().parents[2]


def descriptor():
    return gate.read_json(ROOT / "packaging/cua/native-wheels-input.json")


def wheel_bytes(target="windows-aarch64", member="cryptography/hazmat/bindings/_rust.pyd"):
    body = bytearray(512)
    body[:2] = b"MZ"
    struct.pack_into("<I", body, 0x3c, 0x80)
    body[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", body, 0x84, 0xAA64)
    struct.pack_into("<H", body, 0x94, 240)
    struct.pack_into("<H", body, 0x98, 0x20B)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(member, bytes(body))
        archive.writestr("cryptography-50.0.1.dist-info/METADATA", "Name: cryptography\nVersion: 50.0.1\n")
        archive.writestr("cryptography-50.0.1.dist-info/WHEEL", "Wheel-Version: 1.0\nTag: cp311-abi3-win_arm64\n")
    return output.getvalue()


def test_reviewed_descriptor_covers_exact_native_targets():
    data = descriptor()
    gate.validate_descriptor(data)
    assert set(data["targets"]) == {"windows-aarch64", "macos-x86_64"}
    for target in data["targets"].values():
        names = [row["name"] for row in target["python_dependencies"]]
        assert len(names) == len(set(names))
        assert "cryptography_vectors" in names


@pytest.mark.parametrize("mutation", ["source", "version", "target", "hash", "http", "filename", "duplicate", "rust"])
def test_descriptor_refuses_ambiguous_or_unreviewed_inputs(mutation):
    data = copy.deepcopy(descriptor())
    row = data["targets"]["windows-aarch64"]["python_dependencies"][0]
    if mutation == "source":
        data["cryptography"]["sha256"] = "0" * 64
    elif mutation == "version":
        data["cryptography"]["version"] = "46.0.3"
    elif mutation == "target":
        data["targets"]["linux-x86_64"] = data["targets"]["windows-aarch64"]
    elif mutation == "hash":
        row["sha256"] = "invalid"
    elif mutation == "http":
        row["url"] = row["url"].replace("https:", "http:")
    elif mutation == "filename":
        row["filename"] = "../outside.whl"
    elif mutation == "duplicate":
        data["targets"]["windows-aarch64"]["python_dependencies"].append(row)
    else:
        data["rust"]["version"] = "stable"
    with pytest.raises(gate.Refused):
        gate.validate_descriptor(data)


def test_wheel_identity_and_native_header_are_independently_read(tmp_path):
    path = tmp_path / "cryptography-50.0.1-cp311-abi3-win_arm64.whl"
    path.write_bytes(wheel_bytes())
    record = gate.inspect_wheel(path, "windows-aarch64")
    assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["native_members"] == ["cryptography/hazmat/bindings/_rust.pyd"]


@pytest.mark.parametrize("name", ["../escape.pyd", "/absolute.pyd", "CON.pyd", "a\\bad.pyd"])
def test_unsafe_wheel_members_are_rejected(tmp_path, name):
    path = tmp_path / "cryptography-50.0.1-cp311-abi3-win_arm64.whl"
    path.write_bytes(wheel_bytes(member=name))
    with pytest.raises(gate.Refused):
        gate.inspect_wheel(path, "windows-aarch64")


def test_native_wheel_cannot_claim_another_target(tmp_path):
    path = tmp_path / "cryptography-50.0.1-cp311-abi3-win_arm64.whl"
    path.write_bytes(wheel_bytes())
    with pytest.raises(gate.Refused):
        gate.inspect_wheel(path, "macos-x86_64")


def test_json_duplicate_fields_are_rejected(tmp_path):
    path = tmp_path / "record.json"
    path.write_text('{"schema": 1, "schema": 2}')
    with pytest.raises(gate.Refused):
        gate.read_json(path)


def test_workflow_keeps_builds_without_credentials():
    workflow = (ROOT / ".github/workflows/native-wheels.yml").read_text()
    assert "\npermissions:\n  contents: read\n\njobs:" in workflow
    assert "secrets." not in workflow and "continue-on-error" not in workflow
    for name in ("build-windows", "build-macos"):
        job = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  [a-z-]+:|\Z)", workflow).group(1)
        assert re.search(r"(?m)^    permissions:\n      contents: read\n    steps:", job)
        assert "write" not in job and "environment:" not in job
    attest = workflow.split("\n  validate-and-attest:\n", 1)[1]
    assert "\n      id-token: write\n" in attest
    assert attest.startswith("    needs: [build-windows, build-macos]\n")
    assert "environment:" not in attest


def test_native_recipe_keeps_build_resolution_offline():
    from scripts import build_native_wheels as build
    command = build.wheel_command(Path("uv"), Path("python"), Path("source"), Path("out"))
    assert "--offline" in command and "--no-build-isolation" in command
    assert "--no-sources" in command
    assert "--config-settings=build-args=--features=pyo3/abi3-py311" in command


def test_windows_compiler_environment_normalizes_case(monkeypatch):
    from scripts import build_native_wheels as build
    monkeypatch.setattr(build.platform, "system", lambda: "Windows")
    monkeypatch.setenv("ProgramFiles(x86)", "C:/Programs")
    monkeypatch.setenv("PATH", "original")
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    replies = iter([json.dumps([{"installationVersion": "reviewed", "installationPath": "C:/VS"}]),
                    "Path=C:/native-compiler\nVCToolsInstallDir=C:/VS/tools\nVSCMD_ARG_TGT_ARCH=arm64"])
    monkeypatch.setattr(build, "run", lambda *args, **kwargs: next(replies))
    environment, report = build.compiler_environment({}, {"visual_studio": "reviewed", "sdk": "pinned"})
    assert environment["PATH"] == "C:/native-compiler" and "Path" not in environment
    assert report["msvc_tools"] == "C:/VS/tools"


@pytest.mark.parametrize("kind", ["skipped", "failure", "error"])
def test_upstream_report_cannot_substitute_skips_or_failures_for_passes(kind):
    body = f'<testcase><{kind} message="reason"/></testcase>' * 1000
    with pytest.raises(gate.Refused):
        gate.test_counts(f"<testsuite>{body}</testsuite>".encode())


def test_upstream_report_retains_explained_skips():
    body = '<testcase/>' * 1000 + '<testcase><skipped message="platform"/></testcase>'
    counts = gate.test_counts(f"<testsuite>{body}</testsuite>".encode())
    assert counts == {"total": 1001, "passed": 1000, "skipped": 1, "skip_reasons": ["platform"]}


def test_pe_delayed_imports_cannot_hide_external_crypto():
    with zipfile.ZipFile(io.BytesIO(wheel_bytes())) as archive:
        body = bytearray(archive.read("cryptography/hazmat/bindings/_rust.pyd"))
    struct.pack_into("<I", body, 0x98 + 216, 0x1000)
    with pytest.raises(gate.Refused, match="delayed imports"):
        gate.native_imports(body, "windows-aarch64")


def test_macos_deployment_floor_is_preserved():
    body = bytearray(64)
    struct.pack_into("<IIIIIIII", body, 0, 0xfeedfacf, 0x1000007, 3, 6, 1, 24, 0, 0)
    struct.pack_into("<IIIIII", body, 32, 0x32, 24, 1, 13 << 16, 15 << 16, 0)
    assert gate.native_imports(body, "macos-x86_64") == []
    struct.pack_into("<I", body, 44, 14 << 16)
    with pytest.raises(gate.Refused, match="deployment floor"):
        gate.native_imports(body, "macos-x86_64")


def test_recipe_hash_survives_native_checkout_line_endings(tmp_path):
    recipe = tmp_path / "recipe.py"
    recipe.write_bytes(b"line one\r\nline two\r\n")
    assert gate.recipe_digest(recipe) == gate.digest(b"line one\nline two\n")


@pytest.mark.parametrize("mutation", [None, "source", "recipe", "compiler", "inventory", "cargo", "tests"])
def test_reports_bind_tools_sources_inventory_and_test_results(mutation):
    data = descriptor()
    configuration = data["targets"]["windows-aarch64"]
    image_version, image = next(iter(configuration["images"].items()))
    counts = {"passed": 1000, "skipped": 0, "total": 1000, "skip_reasons": []}
    wheel_hash = "a" * 64
    lock = "".join(f'{row["name"]}=={row["version"]} --hash=sha256:{row["sha256"]}\n'
                   for row in configuration["python_dependencies"])
    report = {"schema": 1, "tests": counts.copy(), "image_version": image_version,
              "wheel_sha256": wheel_hash, "python": ["3.12.14", "ARM64"],
              "rust": "rustc 1.97.1 (fixture)", "openssl": "OpenSSL 4.0.2 fixture",
              "compiler": {"sdk": image["sdk"], "visual_studio": image["visual_studio"], "msvc_tools": "pinned"},
              "build_lock_sha256": gate.digest(lock.encode()),
              "recipe_sha256": gate.recipe_digest(ROOT / "scripts/build_native_wheels.py"),
              "sources": {name: {"url": row["url"], "sha256": row["sha256"]}
                          for name, row in {"cryptography": data["cryptography"], "openssl": data["openssl"],
                                            "python": configuration["python"], "uv": configuration["uv"]}.items()}}
    sbom = {"schema": 1, "kind": "build-input-inventory", "target": "windows-aarch64", "static_openssl": True,
            "cryptography": data["cryptography"], "openssl": data["openssl"],
            "python_build_tools": configuration["python_dependencies"], "wheel_sha256": wheel_hash,
            "cargo_lock_sha256": "b" * 64,
            "cargo_packages": [{"name": "fixture", "version": "1", "source": "upstream-source"}]}
    if mutation == "source":
        report["sources"]["openssl"]["sha256"] = "c" * 64
    elif mutation == "recipe":
        report["recipe_sha256"] = "c" * 64
    elif mutation == "compiler":
        report["compiler"]["sdk"] = "unreviewed"
    elif mutation == "inventory":
        sbom["static_openssl"] = False
    elif mutation == "cargo":
        sbom["cargo_packages"][0]["source"] = "git+https://example.invalid/moving"
    elif mutation == "tests":
        report["tests"]["passed"] = 1
    if mutation:
        with pytest.raises(gate.Refused):
            gate.validate_reports(report, sbom, data, "windows-aarch64", counts, wheel_hash)
    else:
        gate.validate_reports(report, sbom, data, "windows-aarch64", counts, wheel_hash)
