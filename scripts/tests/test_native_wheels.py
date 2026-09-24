"""Untrusted wheel outputs cannot become approved dependency inputs."""

import copy
import hashlib
import io
import json
from pathlib import Path
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
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(member, bytes(body))
        archive.writestr("cryptography-50.0.1.dist-info/METADATA", "Name: cryptography\nVersion: 50.0.1\n")
        archive.writestr("cryptography-50.0.1.dist-info/WHEEL", "Wheel-Version: 1.0\nTag: cp312-cp312-win_arm64\n")
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
    path = tmp_path / "cryptography-50.0.1-cp312-cp312-win_arm64.whl"
    path.write_bytes(wheel_bytes())
    record = gate.inspect_wheel(path, "windows-aarch64")
    assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["native_members"] == ["cryptography/hazmat/bindings/_rust.pyd"]


@pytest.mark.parametrize("name", ["../escape.pyd", "/absolute.pyd", "CON.pyd", "a\\bad.pyd"])
def test_unsafe_wheel_members_are_rejected(tmp_path, name):
    path = tmp_path / "cryptography-50.0.1-cp312-cp312-win_arm64.whl"
    path.write_bytes(wheel_bytes(member=name))
    with pytest.raises(gate.Refused):
        gate.inspect_wheel(path, "windows-aarch64")


def test_native_wheel_cannot_claim_another_target(tmp_path):
    path = tmp_path / "cryptography-50.0.1-cp312-cp312-win_arm64.whl"
    path.write_bytes(wheel_bytes())
    with pytest.raises(gate.Refused):
        gate.inspect_wheel(path, "macos-x86_64")


def test_json_duplicate_fields_are_rejected(tmp_path):
    path = tmp_path / "record.json"
    path.write_text('{"schema": 1, "schema": 2}')
    with pytest.raises(gate.Refused):
        gate.read_json(path)


def test_workflow_keeps_builds_without_credentials():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/native-wheels.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    for name in ("build-windows", "build-macos"):
        job = workflow["jobs"][name]
        assert job.get("permissions", {}) == {"contents": "read"}
        assert "environment" not in job
        assert "continue-on-error" not in job
    attest = workflow["jobs"]["validate-and-attest"]
    assert attest["permissions"]["id-token"] == "write"
    assert set(attest["needs"]) == {"build-windows", "build-macos"}
    assert "environment" not in attest


def test_native_recipe_keeps_build_resolution_offline():
    from scripts import build_native_wheels as build
    command = build.wheel_command(Path("uv"), Path("python"), Path("source"), Path("out"))
    assert "--offline" in command and "--no-build-isolation" in command
    assert "--no-sources" in command
