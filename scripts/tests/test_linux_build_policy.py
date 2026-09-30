"""Synthetic ELF policy notes classify bytes, never establish publisher trust."""
import struct
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import check_linux_build_policy as policy


def elf(mode=1, *, architecture="x86_64", descriptor=None, copies=1, owner=b"VADGR\0"):
    desc = descriptor if descriptor is not None else struct.pack("<II", 1, mode)
    note = struct.pack("<III", len(owner), len(desc), 0x56444752)
    note += owner + b"\0" * (-len(owner) % 4) + desc + b"\0" * (-len(desc) % 4)
    notes = note * copies
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIQQQIHHHHHH", ident, 3,
        62 if architecture == "x86_64" else 183, 1, 0, 64, 0, 0, 64, 56, 1, 64, 0, 0)
    segment = struct.pack("<IIQQQQQQ", 4, 4, 120, 0, 0, len(notes), len(notes), 4)
    return header + segment + notes


@pytest.mark.parametrize("architecture", ["x86_64", "aarch64"])
@pytest.mark.parametrize("mode,expected", [(1, "release"), (2, "development")])
def test_exact_binary_bound_modes(architecture, mode, expected):
    assert policy.inspect_binary(elf(mode, architecture=architecture), architecture) == {
        "schema": 1, "mode": expected, "architecture": architecture}


@pytest.mark.parametrize("raw", [b"", b"not ELF", elf(copies=0), elf(copies=2),
    elf(mode=0), elf(mode=3), elf(descriptor=struct.pack("<II", 2, 1)),
    elf(descriptor=b"release"), elf(owner=b"OTHER\0"), elf()[:-1]])
def test_missing_malformed_duplicate_and_unknown_notes_fail(raw):
    with pytest.raises(policy.PolicyError):
        policy.inspect_binary(raw, "x86_64")


def test_architecture_and_segment_bounds_fail():
    with pytest.raises(policy.PolicyError):
        policy.inspect_binary(elf(), "aarch64")
    raw = bytearray(elf())
    struct.pack_into("<Q", raw, 72, 2**63)
    with pytest.raises(policy.PolicyError):
        policy.inspect_binary(bytes(raw), "x86_64")


def test_development_rejected_as_release_without_sidecar(tmp_path):
    binary = tmp_path / "vadgr"
    binary.write_bytes(elf(2))
    with pytest.raises(policy.PolicyError, match="mode differs"):
        policy.verify(binary, "release", "x86_64")
    assert policy.verify(binary, "development", "x86_64")["mode"] == "development"


def test_sidecar_cannot_turn_release_bytes_into_development(tmp_path):
    binary = tmp_path / "vadgr"
    binary.write_bytes(elf())
    (tmp_path / "vadgr.development.json").write_text('{"development":true}')
    with pytest.raises(policy.PolicyError, match="mode differs"):
        policy.verify(binary, "development", "x86_64")


def test_cargo_hardlinked_regular_binary_keeps_exact_policy_checks(tmp_path):
    binary = tmp_path / "vadgr"
    binary.write_bytes(elf())
    dependency_binary = tmp_path / "vadgr-dependency"
    os.link(binary, dependency_binary)
    assert binary.stat().st_nlink == 2
    assert policy.verify(binary, "release", "x86_64")["mode"] == "release"
    assert policy.verify(dependency_binary, "release", "x86_64")["mode"] == "release"
    with pytest.raises(policy.PolicyError, match="mode differs"):
        policy.verify(binary, "development", "x86_64")
    with pytest.raises(policy.PolicyError, match="identity differs"):
        policy.verify(binary, "release", "aarch64")
    with pytest.raises(policy.PolicyError, match="unsafe or oversized"):
        policy.verify_appimage(binary, "release", "x86_64", tmp_path / "missing-pins.json")


@pytest.mark.skipif(os.name == "nt", reason="native POSIX link and FIFO semantics")
def test_binary_policy_still_refuses_symlinks_and_special_files(tmp_path):
    binary = tmp_path / "vadgr"
    binary.write_bytes(elf())
    linked = tmp_path / "symlink"
    linked.symlink_to(binary.name)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    for unsafe in (linked, fifo):
        with pytest.raises(policy.PolicyError, match="unsafe or oversized"):
            policy.verify(unsafe, "release", "x86_64")


def runtime():
    names = b"\0.shstrtab\0.digest_md5\0"
    raw = bytearray(elf())
    strings = len(raw)
    raw.extend(names)
    digest = len(raw)
    raw.extend(bytes(16))
    table = len(raw)
    raw.extend(bytes(64))
    raw.extend(struct.pack("<IIQQQQIIQQ", 1, 3, 0, 0, strings, len(names), 0, 0, 1, 0))
    raw.extend(struct.pack("<IIQQQQIIQQ", 11, 1, 0, 0, digest, 16, 0, 0, 1, 0))
    struct.pack_into("<Q", raw, 40, table)
    struct.pack_into("<HH", raw, 60, 3, 1)
    return bytes(raw), digest


@pytest.mark.parametrize("mode,expected", [(1, "release"), (2, "development")])
def test_appimage_checks_exact_embedded_executable_and_normalized_runtime(tmp_path, monkeypatch, mode, expected):
    prefix, slot = runtime()
    altered = bytearray(prefix)
    altered[slot:slot + 16] = bytes(range(16))
    image = tmp_path / "installer.AppImage"
    image.write_bytes(altered + b"hsqs" + elf(mode))
    pins = tmp_path / "runtime.json"
    pins.write_text(json.dumps({"targets": {"x86_64": {
        "size": len(prefix), "sha256": hashlib.sha256(prefix).hexdigest()}}}))
    calls = []
    def extract(subject, offset):
        calls.append((subject, offset))
        return subject.read_bytes()[offset + 4:]
    monkeypatch.setattr(policy, "extract_executable", extract)
    # A detached executable has no influence on the vehicle's classification.
    (tmp_path / "vadgr").write_bytes(elf(3 - mode))
    assert policy.verify_appimage(image, expected, "x86_64", pins)["mode"] == expected
    assert calls == [(image, len(prefix))]
    with pytest.raises(policy.PolicyError, match="mode differs"):
        policy.verify_appimage(image, "development" if mode == 1 else "release", "x86_64", pins)
    altered[slot - 1] ^= 1
    image.write_bytes(altered + b"hsqs" + elf(mode))
    with pytest.raises(policy.PolicyError):
        policy.verify_appimage(image, expected, "x86_64", pins)


def test_runtime_requires_one_exact_digest_slot():
    prefix, slot = runtime()
    assert policy.normalized_runtime(prefix, "x86_64") == prefix
    malformed = bytearray(prefix)
    malformed[slot - 12] ^= 1
    with pytest.raises(policy.PolicyError):
        policy.normalized_runtime(malformed, "x86_64")


@pytest.mark.skipif(os.name == "nt", reason="Linux decoder pipe selector")
@pytest.mark.parametrize("size,code,passes", [(8, 0, True), (17, 0, False), (8, 1, False)])
def test_decoder_checks_output_limit_and_exit_status(tmp_path, monkeypatch, size, code, passes):
    original = subprocess.Popen
    image = tmp_path / "never-executed.AppImage"
    monkeypatch.setattr(policy, "MAX_BINARY", 16)
    def decoder(command, **kwargs):
        assert command == ["unsquashfs", "-o", "100", "-cat", str(image), "usr/bin/vadgr"]
        return original([sys.executable, "-c",
                         f"import sys; sys.stdout.buffer.write(b'x' * {size}); sys.exit({code})"], **kwargs)
    monkeypatch.setattr(policy.subprocess, "Popen", decoder)
    if passes:
        assert policy.extract_executable(image, 100) == b"x" * size
    else:
        with pytest.raises(policy.PolicyError):
            policy.extract_executable(image, 100)


def test_final_producers_classify_exact_vehicle_before_execution():
    root = Path(__file__).resolve().parents[2]
    candidate = (root / "scripts/candidate/build-native.sh").read_text()
    native = candidate.split('  linux)\n', 1)[1].split('  wsl)\n', 1)[0]
    assert native.index('check_linux_build_policy.py" --appimage "$vehicle"') < native.index('--appimage-extract')
    assert '--runtime-pins "$trusted/packaging/linux/runtime.json"' in native
    assert '--expect release --architecture "$arch"' in native
    publication = (root / ".github/workflows/publish-release.yml").read_text()
    native = publication.split('\n  verify-linux-wsl:', 1)[1].split('\n  publish:', 1)[0]
    assert native.index('check_linux_build_policy.py --appimage "$image" --expect release') < native.index('chmod 0755 "$image"')
    assert 'squashfs-tools' in native
