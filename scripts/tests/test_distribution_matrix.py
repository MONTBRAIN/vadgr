"""Synthetic release inventories must fail closed before final holding."""

import copy
import hashlib
import json
from pathlib import Path
import struct
import tomllib

import pytest

from scripts import distribution_matrix as gate
from scripts.build_release_manifest import ARTIFACTS


ROOT = Path(__file__).resolve().parents[2]


def test_exact_native_target_matrix():
    expected = {
        "windows-x86_64": ("windows-2025", "x86_64-pc-windows-msvc", "x64", "burn"),
        "windows-aarch64": ("windows-11-arm", "aarch64-pc-windows-msvc", "arm64", "burn"),
        "macos-x86_64": ("macos-15-intel", "x86_64-apple-darwin", "x86_64", "pkg"),
        "macos-aarch64": ("macos-15", "aarch64-apple-darwin", "arm64", "pkg"),
        "linux-x86_64": ("ubuntu-24.04", "x86_64-unknown-linux-gnu", "x86_64", "appimage"),
        "linux-aarch64": ("ubuntu-24.04-arm", "aarch64-unknown-linux-gnu", "aarch64", "appimage"),
        "wsl-x86_64": ("ubuntu-22.04", "x86_64-unknown-linux-gnu", "x86_64", "tar.gz"),
        "wsl-aarch64": ("ubuntu-22.04-arm", "aarch64-unknown-linux-gnu", "aarch64", "tar.gz"),
    }
    assert {row["target"]: tuple(row[key] for key in ("runner", "rust_target", "package_arch", "kind"))
            for row in gate.matrix()} == expected
    assert {row["vehicle"]: (row["target"], row["kind"], row["native_signature"])
            for row in gate.matrix()} == ARTIFACTS
    for selected in ("x64", "arm64"):
        rows = gate.remaining_builds(selected)
        assert len(rows) == 7
        assert len({row["target"] for row in rows}) == 7
        assert "windows-" + {"x64": "x86_64", "arm64": "aarch64"}[selected] not in {r["target"] for r in rows}


@pytest.fixture
def records():
    return [{**row, "name": row["vehicle"], "size": 10, "sha256": "a" * 64,
             "source_sha": "b" * 40, "trusted_sha": "c" * 40,
             "candidate_id": "v0.5.0-rc-1", "run_id": "123", "run_attempt": 1,
             "status": "final-verified", "artifact_id": index + 1,
             "artifact_digest": "sha256:" + "d" * 64}
            for index, row in enumerate(gate.matrix())]


def test_exact_complete_set_is_required(records):
    gate.validate_complete(records)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "rename", "arch", "rust", "runner", "unsigned", "source", "tooling", "run", "attempt", "same-artifact", "digest", "empty", "boolean-size"])
def test_complete_set_refuses_invalid_inventory(records, mutation):
    rows = copy.deepcopy(records)
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = copy.deepcopy(rows[0])
    elif mutation == "extra":
        rows.append(copy.deepcopy(rows[0]))
    else:
        key, value = {
            "rename": ("name", "renamed.exe"), "arch": ("package_arch", "arm64"),
            "rust": ("rust_target", "aarch64-pc-windows-msvc"),
            "runner": ("runner", "windows-latest"), "unsigned": ("status", "unsigned-development"),
            "source": ("source_sha", "e" * 40), "tooling": ("trusted_sha", "f" * 40),
            "run": ("run_id", "124"), "attempt": ("run_attempt", 2),
            "same-artifact": ("artifact_id", 2), "digest": ("artifact_digest", "invalid"),
            "empty": ("size", 0), "boolean-size": ("size", True),
        }[mutation]
        rows[0][key] = value
    with pytest.raises(gate.Refused):
        gate.validate_complete(rows)


def binary(kind, arch):
    data = bytearray(256)
    if kind == "pe":
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3c, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", data, 0x84, {"x86_64": 0x8664, "aarch64": 0xaa64}[arch])
    elif kind == "elf":
        data[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", data, 18, {"x86_64": 62, "aarch64": 183}[arch])
    else:
        struct.pack_into("<II", data, 0, 0xfeedfacf, {"x86_64": 0x1000007, "aarch64": 0x100000c}[arch])
    return bytes(data)


@pytest.mark.parametrize("kind", ["pe", "elf", "macho"])
@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
def test_binary_architecture_is_read_from_bytes(kind, arch):
    assert gate.binary_architecture(binary(kind, arch)) == (kind, arch)


def test_unknown_or_truncated_binary_is_rejected():
    for data in (b"", b"MZ", b"not a binary", binary("pe", "x86_64")[:0x85]):
        with pytest.raises(gate.Refused):
            gate.binary_architecture(data)


def test_macos_universal_dependency_must_contain_the_required_architecture(tmp_path):
    data = bytearray(64)
    struct.pack_into(">II", data, 0, 0xcafebabe, 2)
    struct.pack_into(">I", data, 8, 0x1000007)
    struct.pack_into(">I", data, 28, 0x100000c)
    path = tmp_path / "library.dylib"
    path.write_bytes(data)
    for target in ("macos-x86_64", "macos-aarch64"):
        gate.verify_binary(path, target)
    struct.pack_into(">I", data, 4, 1)
    path.write_bytes(data)
    with pytest.raises(gate.Refused, match="cross-architecture"):
        gate.verify_binary(path, "macos-aarch64")


def test_manifest_refuses_missing_extra_and_renamed_vehicles(tmp_path, records):
    manifest = {"artifacts": []}
    for row in records:
        data = (binary("pe" if row["kind"] == "burn" else "elf", row["target"].split("-", 1)[1])
                if row["kind"] in ("burn", "appimage") else row["name"].encode())
        (tmp_path / row["name"]).write_bytes(data)
        manifest["artifacts"].append({"target": row["target"], "name": row["name"],
            "kind": row["kind"], "native_signature": row["native_signature"],
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    gate.validate_manifest(manifest, tmp_path)
    for mutation in ("missing", "duplicate", "rename"):
        changed = copy.deepcopy(manifest)
        if mutation == "missing":
            changed["artifacts"].pop()
        elif mutation == "duplicate":
            changed["artifacts"].append(changed["artifacts"][0])
        else:
            changed["artifacts"][0]["name"] = "different.exe"
        with pytest.raises(gate.Refused):
            gate.validate_manifest(changed, tmp_path)
    row = manifest["artifacts"][0]
    wrong = binary("pe", "aarch64")
    (tmp_path / row["name"]).write_bytes(wrong)
    row["sha256"] = hashlib.sha256(wrong).hexdigest()
    with pytest.raises(gate.Refused, match="cross-architecture"):
        gate.validate_manifest(manifest, tmp_path)


def test_payload_checks_native_bytes_and_pinned_target(tmp_path):
    pins_path = ROOT / "packaging/cua/pins.toml"
    pins = tomllib.loads(pins_path.read_text())
    target = "x86_64-pc-windows-msvc"
    runtime = tmp_path / "lib/cua"
    runtime.mkdir(parents=True)
    manifest = {"target": target, "cua_version": pins["cua"], "python_version": pins["python"],
                "python_build": pins["python_build"], "python_archive_sha256": pins["targets"][target]["python_sha256"],
                "uv_archive_sha256": pins["targets"][target]["uv_sha256"]}
    (runtime / "payload.json").write_text(json.dumps(manifest))
    (runtime / "python.exe").write_bytes(binary("pe", "x86_64"))
    assert gate.verify_payload(tmp_path, "windows-x86_64", pins_path) == 1
    (runtime / "python.exe").write_bytes(binary("pe", "aarch64"))
    with pytest.raises(gate.Refused, match="cross-architecture"):
        gate.verify_payload(tmp_path, "windows-x86_64", pins_path)
    (runtime / "python.exe").write_bytes(binary("pe", "x86_64"))
    manifest["cua_version"] = "0.0.0"
    (runtime / "payload.json").write_text(json.dumps(manifest))
    with pytest.raises(gate.Refused, match="pin mismatch"):
        gate.verify_payload(tmp_path, "windows-x86_64", pins_path)


def test_workflow_keeps_partial_qualification_distinct_from_complete_distribution():
    workflow = (ROOT / ".github/workflows/candidate.yml").read_text()
    assert "remaining_matrix=$(python scripts/distribution_matrix.py matrix --except-windows" in workflow
    assert "matrix: ${{ fromJSON(needs.preflight.outputs.remaining_matrix) }}" in workflow
    assert "test \"$RUNNER_ARCH\" = '${{ matrix.runner_arch }}'" in workflow
    assert "complete eight-target held candidate is not assembled" in workflow
    publish = (ROOT / ".github/workflows/publish-release.yml").read_text()
    assert "distribution_matrix.py manifest --manifest assets/release-manifest.json --directory assets" in publish
    held = (ROOT / "scripts/candidate/hold-windows.ps1").read_text()
    assert "scope = 'single-target-qualification'; complete_distribution = $false" in held


@pytest.mark.parametrize("platform", ["linux", "wsl", "macos"])
def test_native_builds_use_target_specific_compliance_inputs(platform):
    build = (ROOT / f"packaging/{platform}/build.sh").read_text()
    assert f'inputs="$repo/packaging/inputs/{platform}-$arch"' in build
    assert 'scripts/validate_package_inputs.py" --root "$inputs"' in build
    assert '"$repo/packaging/legal' not in build
    assert '"$repo/packaging/sbom' not in build
