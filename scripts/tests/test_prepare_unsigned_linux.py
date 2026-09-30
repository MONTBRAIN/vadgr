"""Preparation binds exact source and payload bytes without granting approval."""

import os
from pathlib import Path
import subprocess

import pytest

from scripts import prepare_unsigned_linux as preparation
from scripts.validate_package_inputs import PackageInputError


def test_exact_clean_committed_source(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = tmp_path / "source.txt"
    source.write_text("original\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
    head = subprocess.check_output(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True).strip()
    assert preparation.source_identity(tmp_path, head)["source_commit"] == head
    with pytest.raises(PackageInputError, match="source commit differs"):
        preparation.source_identity(tmp_path, "0" * 40)
    source.write_text("changed\n")
    with pytest.raises(PackageInputError, match="source must be clean"):
        preparation.source_identity(tmp_path, head)


@pytest.mark.parametrize("system,machine,release", [
    ("Windows", "x86_64", "10"), ("Linux", "aarch64", "6.8"),
    ("Linux", "x86_64", "6.8-microsoft-standard-WSL2"),
])
def test_wrong_native_host_refused(monkeypatch, system, machine, release):
    monkeypatch.setattr(preparation.platform, "system", lambda: system)
    monkeypatch.setattr(preparation.platform, "machine", lambda: machine)
    monkeypatch.setattr(preparation.platform, "release", lambda: release)
    with pytest.raises(PackageInputError):
        preparation.native_target("x86_64")


@pytest.mark.skipif(os.name == "nt", reason="POSIX payload mode and symlink semantics")
def test_inventory_binds_bytes_modes_and_relative_links(tmp_path):
    content = tmp_path / "python"
    content.write_bytes(b"runtime")
    content.chmod(0o755)
    (tmp_path / "python3").symlink_to("python")
    original = preparation.inventory(tmp_path)
    assert original[0]["size"] == 7
    assert original[0]["mode"] == 0o755
    assert original[1]["target"] == "python"
    content.write_bytes(b"changed")
    assert preparation.inventory(tmp_path) != original
    content.chmod(0o644)
    assert preparation.inventory(tmp_path)[0]["mode"] == 0o644


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_inventory_refuses_external_links(tmp_path):
    (tmp_path / "escape").symlink_to(tmp_path.parent)
    with pytest.raises(PackageInputError, match="link escapes"):
        preparation.inventory(tmp_path)


@pytest.mark.parametrize("key", preparation.CREDENTIALS)
def test_compilation_refuses_credentials(monkeypatch, key):
    monkeypatch.setenv(key, "synthetic-fixture")
    with pytest.raises(PackageInputError, match="compilation must have no"):
        preparation.build_environment("linux-x86_64")


def test_build_uses_final_rust_pin_and_ignores_inherited_target_directory(monkeypatch):
    for key in preparation.CREDENTIALS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARGO_TARGET_DIR", "/unrelated-build")
    monkeypatch.setenv("RUSTUP_TOOLCHAIN", "stable")
    environment = preparation.build_environment("linux-x86_64")
    assert environment["RUSTUP_TOOLCHAIN"] == "1.97.1"
    assert environment["CARGO_TARGET_DIR"] == str(preparation.ROOT / "target")
    assert environment["VADGR_RELEASE_PROFILE"] == "linux-x86_64"


def test_tampered_preparation_refused_before_packaging(tmp_path, monkeypatch):
    source = {"source_commit": "a" * 40, "source_tree": "b" * 40}
    monkeypatch.setattr(preparation, "source_identity", lambda *args: source)
    monkeypatch.setattr(preparation, "native_target", lambda *args:
                        ("linux-x86_64", "x86_64-unknown-linux-gnu"))
    monkeypatch.setattr(preparation, "build_environment", lambda *args: {})
    binary = tmp_path / "vadgr"
    binary.write_bytes(b"original")
    preparation.write_new(tmp_path / "preparation.json", {
        "schema": 1, "development": True, "publishable": False,
        "legal_approval": False, "signing": "disabled", "attestation": "absent",
        "platform": "linux", "architecture": "x86_64", "release_profile": "linux-x86_64",
        **source, "files": preparation.inventory(tmp_path),
    })
    binary.write_bytes(b"replaced")
    with pytest.raises(PackageInputError, match="prepared bytes changed"):
        preparation.package(tmp_path, tmp_path / "absent-tool", "x86_64", "a" * 40)


def test_receipt_is_canonical_and_never_overwrites(tmp_path):
    path = tmp_path / "receipt.json"
    preparation.write_new(path, {"z": 2, "a": 1})
    assert path.read_bytes() == b'{\n  "a": 1,\n  "z": 2\n}\n'
    with pytest.raises(FileExistsError):
        preparation.write_new(path, {"changed": True})


@pytest.mark.skipif(os.name == "nt", reason="native POSIX shell packaging path")
def test_linux_builder_uses_same_external_payload_for_validation_and_packaging(tmp_path):
    """Exercise the shell builder up to its first validator without compiling."""
    root = tmp_path / "source"
    script = root / "packaging/linux/build.sh"
    script.parent.mkdir(parents=True)
    original = Path(__file__).resolve().parents[2] / "packaging/linux/build.sh"
    script.write_bytes(original.read_bytes())
    payload = tmp_path / "prepared-payload"
    payload.mkdir()
    # A deliberately failing validator prints only the arguments this fixture supplies.
    validator = root / "scripts/validate_package_inputs.py"
    validator.parent.mkdir()
    validator.write_text("import sys\nprint('\\n'.join(sys.argv[1:]))\nsys.exit(17)\n")
    env = dict(os.environ, APPIMAGETOOL="/bin/true", VADGR_PACKAGE_PAYLOAD_ROOT=str(payload))
    result = subprocess.run(["sh", str(script), "0.5.0", "x86_64"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 17
    assert str(payload / "lib/cua/payload.json") in result.stdout
    assert "pinned private CUA payload is missing" not in result.stderr
