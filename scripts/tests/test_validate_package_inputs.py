"""Synthetic consistency fixtures only. These records are never legal approval."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_package_inputs as package  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
VERSION = "0.5.0"
TARGET = "aarch64-apple-darwin"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(package.canonical_json(value))


def make_approved_fixture(root: Path, source_root: Path, *, version=VERSION, target=TARGET,
                          payload_manifest: Path | None = None):
    """Write synthetic package data into caller-owned temporary test directories.

    The false synthetic flag exercises the production schema, not real approval.
    This test helper replaces source fixture locks; never call it on a checkout.
    """
    assert source_root.resolve() != REPO.resolve()
    for name in package.SOURCE_INPUTS:
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((REPO / name).read_bytes())
    (source_root / "Cargo.toml").write_text(f'[package]\nname="synthetic-vadgr"\nversion="{version}"\n', encoding="utf-8")
    pins = tomllib.loads((source_root / "packaging/cua/pins.toml").read_text())
    hashes = {name: package.sha256_bytes((source_root / name).read_bytes()) for name in package.SOURCE_INPUTS}
    payload = {"schema": 1, "cua_version": pins["cua"], "python_version": pins["python"],
               "python_build": pins["python_build"], "requirements_sha256": hashes["packaging/cua/requirements.lock"],
               "python_archive_sha256": pins["targets"][target]["python_sha256"],
               "uv_archive_sha256": pins["targets"][target]["uv_sha256"], "target": target}
    payload_path = payload_manifest or root / "lib/cua/payload.json"
    write_json(payload_path, payload)
    files = {name: f"Synthetic fixture only: {name}\n".encode() for name in package.REQUIRED_FILES}
    components = []
    for kind in ("cargo", "wheel", "runtime"):
        name = f"synthetic-{kind}"
        path = f"legal/LICENSES/{name}.txt"
        files[path] = b"Synthetic test license bytes. Not a redistribution license.\n"
        components.append({"id": name, "name": name, "version": "1.0.0", "kind": kind,
                           "sha256": "b" * 64, "download_location": "https://example.org/synthetic-test.tar.gz",
                           "copyright_text": "Copyright synthetic test fixture",
                           "license_declared": "MIT", "license_concluded": "MIT",
                           "license_files": [{"path": path, "sha256": package.sha256_bytes(files[path]), "license_ids": ["MIT"]}],
                           "notice_required": False, "notice_files": [], "source_offer_required": False, "source_offer_files": []})
    inventory = {"schema": 1, "created": "2026-01-01T00:00:00Z", "version": version, "target": target,
                 "terms_version": "1.0", "terms_sha256": package.sha256_bytes(files["legal/TERMS.txt"]),
                 "source_inputs": hashes, "payload_manifest_sha256": package.sha256_bytes(payload_path.read_bytes()),
                 "components": components, "coverage": {kind: {"status": "complete", "component_ids": [item["id"] for item in components if item["kind"] == kind]} for kind in package.KINDS}}
    files["legal/TERMS.rtf"] = package.render_rtf(files["legal/TERMS.txt"].decode())
    files["legal/THIRD-PARTY-NOTICES.txt"] = package.aggregate_files(inventory, files, "notice_files")
    files[f"sbom/vadgr-{version}.spdx.json"] = package.canonical_json(package.build_sbom(inventory))
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    write_json(root / "package-input-inventory.json", inventory)
    review = {key: deepcopy(inventory[key]) for key in package.REVIEW_KEYS & package.INVENTORY_KEYS}
    review.update(status="approved", synthetic=False, inventory_sha256=package.sha256_bytes(package.canonical_json(inventory)),
                  files={name: package.sha256_bytes(data) for name, data in files.items()},
                  closures={name: True for name in package.CLOSURES})
    write_json(root / "package-input-review.json", review)
    return inventory, review, payload_path


@pytest.fixture
def bundle(tmp_path):
    root, source = tmp_path / "inputs", tmp_path / "source"
    inventory, review, payload = make_approved_fixture(root, source)
    return root, source, inventory, review, payload


def validate(bundle, **kwargs):
    root, source, *_ = bundle
    return package.validate_package_inputs(root, source, VERSION, TARGET, **kwargs)


def rebind(bundle):
    root, _, inventory, review, _ = bundle
    write_json(root / "package-input-inventory.json", inventory)
    review["inventory_sha256"] = package.sha256_bytes(package.canonical_json(inventory))
    write_json(root / "package-input-review.json", review)


@pytest.mark.parametrize("field,value", [("status", "draft"), ("synthetic", True), ("schema", 2), ("version", "9.9.9"), ("target", "x86_64-apple-darwin"), ("terms_version", "2.0"), ("terms_sha256", "0" * 64), ("inventory_sha256", "0" * 64)])
def test_refuses_unapproved_or_unbound_review(bundle, field, value):
    root, _, _, review, _ = bundle
    review[field] = value
    write_json(root / "package-input-review.json", review)
    with pytest.raises(package.PackageInputError):
        validate(bundle)


@pytest.mark.parametrize("closure", package.CLOSURES)
def test_each_legal_review_question_must_be_closed(bundle, closure):
    root, _, _, review, _ = bundle
    review["closures"][closure] = False
    write_json(root / "package-input-review.json", review)
    with pytest.raises(package.PackageInputError):
        validate(bundle)


@pytest.mark.parametrize("change", ["changed", "extra", "missing", "symlink", "hardlink", "escape", "lock", "payload", "sbom", "rtf", "coverage", "conclusion", "compound", "notice", "source_offer", "provenance", "copyright", "created"])
def test_refuses_package_input_mutations(bundle, change):
    root, source, inventory, review, payload = bundle
    if change == "changed":
        (root / "legal/TERMS.txt").write_bytes(b"Changed")
    elif change == "extra":
        (root / "legal/extra.txt").write_bytes(b"Extra")
    elif change == "missing":
        (root / "legal/SUPPORT.txt").unlink()
    elif change in {"symlink", "hardlink"}:
        path = root / "legal/SUPPORT.txt"
        path.unlink()
        if change == "symlink":
            path.symlink_to(root / "legal/TERMS.txt")
        else:
            path.hardlink_to(root / "legal/TERMS.txt")
    elif change == "escape":
        review["files"]["../secret.txt"] = "0" * 64
    elif change == "lock":
        (source / "Cargo.lock").write_bytes(b"changed lock")
    elif change == "payload":
        payload.write_bytes(b"{}")
    elif change in {"sbom", "rtf"}:
        name = f"sbom/vadgr-{VERSION}.spdx.json" if change == "sbom" else "legal/TERMS.rtf"
        (root / name).write_bytes(b"{}")
        review["files"][name] = package.sha256_bytes(b"{}")
    elif change == "coverage":
        inventory["components"].pop()
    elif change == "conclusion":
        inventory["components"][0]["license_concluded"] = "NOASSERTION"
    elif change == "compound":
        inventory["components"][0]["license_concluded"] = "MIT AND OFL-1.1"
    elif change == "notice":
        inventory["components"][0]["notice_required"] = True
    elif change == "source_offer":
        inventory["components"][0]["source_offer_required"] = True
    elif change == "provenance":
        inventory["components"][0]["download_location"] = "NOASSERTION"
    elif change == "copyright":
        inventory["components"][0]["copyright_text"] = "NOASSERTION"
    elif change == "created":
        inventory["created"] = "unknown"
    rebind(bundle)
    with pytest.raises(package.PackageInputError):
        validate(bundle)


def test_approved_fixture_checks_actual_payload_and_source_only_is_explicit(bundle):
    assert validate(bundle)["scope"] == "assembled-payload"
    bundle[-1].unlink()
    assert validate(bundle, source_only=True)["scope"] == "source-inputs"
    with pytest.raises(package.PackageInputError):
        validate(bundle)


def test_cli_failure_has_no_untrusted_input_in_output(bundle):
    root, source, *_ = bundle
    (root / "package-input-review.json").write_text('{"private-marker":"credential-shaped-content"}', encoding="utf-8")
    result = subprocess.run([sys.executable, str(REPO / "scripts/validate_package_inputs.py"), "--root", str(root), "--source-root", str(source), "--version", VERSION, "--target", TARGET], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Package inputs failed validation.\n"


@pytest.mark.parametrize("field", ["target", "kind"])
def test_inventory_malformed_membership_values_have_safe_errors(bundle, field):
    inventory = bundle[2]
    if field == "target":
        inventory["target"] = []
    else:
        inventory["components"][0]["kind"] = {}
    with pytest.raises(package.PackageInputError):
        package.validate_inventory(inventory)


def test_explicit_payload_rejects_symlinked_ancestor(bundle, tmp_path):
    root, _, _, _, payload = bundle
    linked = tmp_path / "linked"
    linked.symlink_to(root / "lib", target_is_directory=True)
    with pytest.raises(package.PackageInputError):
        validate(bundle, payload_manifest=linked / "cua/payload.json")


@pytest.mark.parametrize("conclusion,covered", [("Apache-2.0 WITH LLVM-exception", ["Apache-2.0"]), ("MIT AND OFL-1.1", ["MIT"])])
def test_every_concluded_license_and_exception_needs_mapped_bytes(bundle, conclusion, covered):
    inventory = bundle[2]
    component = inventory["components"][0]
    component["license_concluded"] = conclusion
    component["license_files"][0]["license_ids"] = covered
    with pytest.raises(package.PackageInputError):
        package.validate_inventory(inventory)


@pytest.mark.parametrize("identifier", ["SSLeay", "UFL-1.0"])
def test_non_spdx_aliases_cannot_be_concluded_licenses(identifier):
    with pytest.raises(package.PackageInputError):
        package.validate_conclusion(identifier)


def test_unknown_declared_license_cannot_enter_the_sbom(bundle):
    bundle[2]["components"][0]["license_declared"] = "NOASSERTION"
    with pytest.raises(package.PackageInputError):
        package.validate_inventory(bundle[2])


@pytest.mark.parametrize("name", ["CON.txt", "NUL.txt", "aux", "com1.bin", "LPT9", "COM¹", "file.", "file ", "dir./file.txt", "file?.txt", "file*.txt"])
def test_portable_paths_reject_device_names_and_aliases(name):
    with pytest.raises(package.PackageInputError):
        package.relative_path("legal/LICENSES/" + name)


@pytest.mark.parametrize("alias", ["CAFÉ.txt", "cafe\u0301.txt"])
def test_approved_inventory_rejects_portable_filename_collisions(bundle, alias):
    inventory = bundle[2]
    first = inventory["components"][0]["license_files"][0]
    first["path"] = "legal/LICENSES/café.txt"
    second = deepcopy(first)
    second["path"] = "legal/LICENSES/" + alias
    inventory["components"][0]["license_files"].append(second)
    with pytest.raises(package.PackageInputError):
        package.validate_inventory(inventory)
