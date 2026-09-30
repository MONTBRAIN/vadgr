"""Preparation binds exact source and payload bytes without granting approval."""

import os
from pathlib import Path
import subprocess
import sys
import tarfile
import textwrap

import pytest

from scripts import prepare_unsigned_linux as preparation
from scripts.validate_package_inputs import PackageInputError

IDENTITY = {"source_commit": "a" * 40, "source_tree": "b" * 40}


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


@pytest.mark.parametrize("names", [
    ("legal/LICENSES/uniseg-asset-sphinx/LICENSE",
     "legal/LICENSES/uniseg-asset-sphinx-jquery-compat/LICENSE"),
    ("site-packages/annotated_types/test_cases.py",
     "site-packages/annotated_types-0.8.0.dist-info/INSTALLER"),
    ("site-packages/cryptography/hazmat/bindings/_rust/x509.pyi",
     "site-packages/cryptography/hazmat/bindings/_rust.abi3.so"),
])
def test_inventory_orders_complete_posix_paths_for_native_verifier(tmp_path, names):
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"inventory fixture\n")
    # Path component ordering differs at a directory prefix followed by '-' or '.'.
    assert [path.as_posix() for path in sorted(map(Path, names))] != sorted(names)
    rows = preparation.inventory(tmp_path)
    assert [row["path"] for row in rows] == sorted(names)
    assert all(left["path"] < right["path"] for left, right in zip(rows, rows[1:]))


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_inventory_refuses_external_links(tmp_path):
    (tmp_path / "escape").symlink_to(tmp_path.parent)
    with pytest.raises(PackageInputError, match="link escapes"):
        preparation.inventory(tmp_path)


@pytest.mark.parametrize("key", preparation.CREDENTIALS)
def test_compilation_refuses_credentials(monkeypatch, key):
    monkeypatch.setenv(key, "synthetic-fixture")
    with pytest.raises(PackageInputError, match="compilation must have no"):
        preparation.build_environment("linux-x86_64", IDENTITY)


def test_build_uses_final_rust_pin_and_ignores_inherited_target_directory(monkeypatch):
    for key in preparation.CREDENTIALS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARGO_TARGET_DIR", "/unrelated-build")
    monkeypatch.setenv("RUSTUP_TOOLCHAIN", "stable")
    monkeypatch.setenv("CARGO_ENCODED_RUSTFLAGS", "--cfg=unrelated")
    environment = preparation.build_environment("linux-x86_64", IDENTITY)
    assert environment["RUSTUP_TOOLCHAIN"] == "1.97.1"
    assert environment["CARGO_TARGET_DIR"] == str(preparation.ROOT / "target")
    assert environment["VADGR_RELEASE_PROFILE"] == "linux-x86_64"
    assert environment["VADGR_QUALIFICATION_SOURCE_COMMIT"] == IDENTITY["source_commit"]
    assert environment["VADGR_QUALIFICATION_SOURCE_TREE"] == IDENTITY["source_tree"]
    assert "CARGO_ENCODED_RUSTFLAGS" not in environment


@pytest.mark.parametrize("identity", [{}, {"source_commit": "a" * 40},
    {"source_commit": "A" * 40, "source_tree": "b" * 40},
    {"source_commit": "a" * 40, "source_tree": "b" * 39}])
def test_compilation_refuses_missing_or_malformed_source_bindings(monkeypatch, identity):
    for key in preparation.CREDENTIALS:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(PackageInputError, match="source"):
        preparation.build_environment("linux-x86_64", identity)


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
    env = dict(os.environ, APPIMAGETOOL=sys.executable, VADGR_PACKAGE_PAYLOAD_ROOT=str(payload))
    result = subprocess.run(["sh", str(script), "0.5.0", "x86_64"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 17
    assert str(payload / "lib/cua/payload.json") in result.stdout
    assert "pinned private CUA payload is missing" not in result.stderr


@pytest.mark.skipif(os.name == "nt", reason="native POSIX shell packaging path")
@pytest.mark.parametrize("mode,feature", [(None, "native-gui"), ("development", "linux-unsigned-qualification")])
def test_linux_builder_selects_exact_explicit_feature(tmp_path, mode, feature):
    root = tmp_path / "source"
    script = root / "packaging/linux/build.sh"
    script.parent.mkdir(parents=True)
    script.write_bytes((Path(__file__).resolve().parents[2] / "packaging/linux/build.sh").read_bytes())
    scripts = root / "scripts"
    scripts.mkdir()
    for name in ("validate_package_inputs.py", "verify_appimage_runtime.py"):
        (scripts / name).write_text("pass\n")
    payload = root / "payload"
    payload.mkdir()
    tools = root / "tools"
    tools.mkdir()
    cargo = tools / "cargo"
    cargo.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 19\n')
    cargo.chmod(0o755)
    environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"],
        APPIMAGETOOL=sys.executable, APPIMAGE_RUNTIME="fixture-runtime", VADGR_PACKAGE_PAYLOAD_ROOT=str(payload))
    command = ["sh", str(script), "0.5.0", "x86_64"] + ([mode] if mode else [])
    result = subprocess.run(command, env=environment, text=True, capture_output=True)
    assert result.returncode == 19
    assert result.stdout.splitlines() == ["build", "--locked", "--release", "--features", feature,
                                        "--target", "x86_64-unknown-linux-gnu", "--bin", "vadgr"]


def test_workflow_retains_preparation_after_refused_package_without_hiding_failure():
    workflow = (preparation.ROOT / ".github/workflows/unsigned-linux-preparation.yml").read_text()
    retain = workflow.split("- name: Retain exact development observations", 1)[1]
    assert "always() && steps.preparation.outcome == 'success'" in retain
    assert "PACKAGE_OUTCOME: ${{ steps.package.outcome }}" in retain
    assert 'if test "$PACKAGE_OUTCOME" = success; then' in retain
    assert "always() && steps.retain.outcome == 'success'" in retain
    assert "continue-on-error" not in workflow
    assert "|| true" not in workflow


def test_preparation_compiles_only_the_development_feature(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, "source_identity", lambda *args: IDENTITY)
    monkeypatch.setattr(preparation, "native_target", lambda *args: ("linux-x86_64", "x86_64-unknown-linux-gnu"))
    monkeypatch.setattr(preparation, "build_environment", lambda *args: {})
    monkeypatch.setattr(preparation.cua_wheelhouse, "verify_materialized", lambda *args: None)
    calls = []
    def stop_at_compile(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(19, command)
    monkeypatch.setattr(preparation.subprocess, "run", stop_at_compile)
    with pytest.raises(subprocess.CalledProcessError):
        preparation.prepare(tmp_path / "new", tmp_path / "wheelhouse", "x86_64", "a" * 40)
    assert calls == [["cargo", "build", "--locked", "--release", "--features",
        "linux-unsigned-qualification", "--target", "x86_64-unknown-linux-gnu", "--bin", "vadgr"]]


@pytest.mark.skipif(os.name == "nt", reason="native POSIX retention script")
def test_failed_package_retains_only_complete_preparation(tmp_path):
    workflow = (preparation.ROOT / ".github/workflows/unsigned-linux-preparation.yml").read_text()
    retain = workflow.split("- name: Retain exact development observations", 1)[1].split("- uses: actions/upload-artifact", 1)[0]
    script = textwrap.dedent(retain.split("run: |\n", 1)[1]).rstrip()
    prepared = tmp_path / "linux-prepared"
    prepared.mkdir()
    (prepared / "preparation.json").write_text("fixture receipt")
    (prepared / "vadgr").write_bytes(b"fixture executable")
    package = tmp_path / "target/package"
    package.mkdir(parents=True)
    (package / "Vadgr-0.5.0-linux-x86_64-installer.AppImage").write_bytes(b"partial unqualified output")
    result = subprocess.run(["bash", "-c", script], cwd=tmp_path,
        env=dict(os.environ, RUNNER_TEMP=str(tmp_path), PACKAGE_OUTCOME="failure"), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "Preparation only: package step outcome=failure" in result.stdout
    retained = tmp_path / "linux-retained"
    assert {path.name for path in retained.iterdir()} == {"preparation.tar.gz", "preparation.json"}
    with tarfile.open(retained / "preparation.tar.gz") as archive:
        assert {row.name for row in archive if row.isfile()} == {"./vadgr", "./preparation.json"}
