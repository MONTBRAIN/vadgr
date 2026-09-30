"""Synthetic consistency fixtures only. These records are never legal approval."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_package_inputs as package

REPO = Path(__file__).resolve().parents[2]
VERSION = "0.5.0"
TARGET = "aarch64-apple-darwin"


@pytest.mark.parametrize("architecture", ["x86_64", "aarch64"])
def test_linux_profile_legal_review_binds_embedded_appimage_runtime(architecture):
    profile = f"linux-{architecture}"
    names = package.profile_source_inputs(profile)
    assert "packaging/linux/runtime.json" in names
    assert package.profile_from_inputs(names, f"{architecture}-unknown-linux-gnu") == profile
    assert package.profile_from_inputs(names - {"packaging/linux/runtime.json"},
                                       f"{architecture}-unknown-linux-gnu") is None


@pytest.mark.parametrize("system", ["windows", "macos", "wsl"])
def test_non_appimage_profiles_do_not_bind_linux_runtime(system):
    assert "packaging/linux/runtime.json" not in package.profile_source_inputs(f"{system}-x86_64")


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
        if name == "packaging/toolchain.json":
            path.write_bytes(b'{"schema":1,"fixture":true}\n')
        else:
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


def test_reviewed_text_input_accepts_only_exact_windows_line_endings():
    raw = b"first\nsecond\n"
    expected = package.sha256_bytes(raw)
    assert package.source_input_matches("Cargo.lock", raw.replace(b"\n", b"\r\n"), expected)
    assert package.source_input_matches("packaging/cua/pins.toml", raw.replace(b"\n", b"\r\n"), expected)
    assert not package.source_input_matches("payload.zip", raw.replace(b"\n", b"\r\n"), expected)
    assert not package.source_input_matches("Cargo.lock", b"first\rsecond\r\n", expected)
    assert not package.source_input_matches("Cargo.lock", b"changed\r\n", expected)


def test_canonical_text_sha256_is_checkout_independent():
    lf = b"first\nsecond\n"
    assert package.canonical_text_sha256(lf) == package.canonical_text_sha256(
        lf.replace(b"\n", b"\r\n"))
    with pytest.raises(package.PackageInputError, match="text line endings differ"):
        package.canonical_text_sha256(b"first\rsecond\n")


def test_none_without_exact_source_and_absence_audit_is_rejected(bundle):
    _, _, inventory, _, _ = bundle
    inventory["components"][0]["copyright_text"] = "NONE"
    with pytest.raises(package.PackageInputError, match="copyright absence evidence required"):
        package.validate_inventory(inventory)


def test_custom_grant_requires_exact_extracted_text(bundle):
    _, _, inventory, _, _ = bundle
    component = inventory["components"][0]
    raw = b"Exact custom conditions."
    digest = package.sha256_bytes(raw)
    identifier = "LicenseRef-Conditions-" + digest
    entry = component["license_files"][0]
    entry.update(sha256=digest, license_ids=[identifier])
    component.update(license_declared=identifier, license_concluded=identifier)
    package.validate_inventory(inventory)
    with pytest.raises(package.PackageInputError, match="custom license text required"):
        package.build_sbom(inventory)
    with pytest.raises(package.PackageInputError, match="custom license text identity differs"):
        package.build_sbom(inventory, {entry["path"]: raw + b"changed"})
    sbom = package.build_sbom(inventory, {entry["path"]: raw})
    assert sbom["hasExtractedLicensingInfos"][0]["extractedText"] == raw.decode()
    entry["sha256"] = "a" * 64
    with pytest.raises(package.PackageInputError, match="custom license text identity differs"):
        package.validate_inventory(inventory)


def test_evidence_bound_none_still_requires_approved_review(bundle):
    import io
    import tarfile

    from scripts.copyright_absence import audit_archive
    root, _, inventory, review, _ = bundle
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        member = tarfile.TarInfo("synthetic-1/src/lib.rs")
        raw = b"pub fn synthetic_fixture() {}\n"
        member.size = len(raw)
        archive.addfile(member, io.BytesIO(raw))
    raw = stream.getvalue()
    digest = package.sha256_bytes(raw)
    archive_name = "legal/SOURCE-OFFERS/synthetic-cargo/source.crate"
    audit_name = "legal/SOURCE-OFFERS/synthetic-cargo/copyright-absence.json"
    files = {archive_name: raw, audit_name: package.canonical_json(audit_archive(raw, digest))}
    component = inventory["components"][0]
    component.update(copyright_text="NONE", sha256=digest, source_offer_required=True,
                     source_offer_files=[{"path": name, "sha256": package.sha256_bytes(data)} for name, data in files.items()])
    files["legal/SOURCE-OFFER.txt"] = package.aggregate_files(inventory, files, "source_offer_files")
    files[f"sbom/vadgr-{VERSION}.spdx.json"] = package.canonical_json(package.build_sbom(inventory))
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
        review["files"][name] = package.sha256_bytes(data)
    rebind(bundle)
    assert validate(bundle, source_only=True)["scope"] == "source-inputs"
    review["status"] = "draft"
    rebind(bundle)
    with pytest.raises(package.PackageInputError, match="approval required"):
        validate(bundle, source_only=True)


def rebind(bundle):
    root, _, inventory, review, _ = bundle
    write_json(root / "package-input-inventory.json", inventory)
    review["inventory_sha256"] = package.sha256_bytes(package.canonical_json(inventory))
    write_json(root / "package-input-review.json", review)


def test_schema_two_legal_source_inputs_bind_target_lock_and_native_manifest(bundle):
    root, source, inventory, review, _ = bundle
    target_lock = f"packaging/cua/locks/{TARGET}.lock"
    manifest = "packaging/cua/native-wheel-manifest.json"
    for name, content in ((target_lock, b"synthetic==1 --hash=sha256:" + b"a" * 64 + b"\n"),
                          (manifest, b'{"schema":1,"synthetic":true}\n')):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    inventory["source_inputs"].pop("packaging/cua/requirements.lock")
    inventory["source_inputs"].update({name: package.sha256_bytes((source / name).read_bytes())
                                      for name in (target_lock, manifest)})
    review["source_inputs"] = deepcopy(inventory["source_inputs"])
    sbom_name = f"sbom/vadgr-{VERSION}.spdx.json"
    sbom = package.canonical_json(package.build_sbom(inventory))
    (root / sbom_name).write_bytes(sbom)
    review["files"][sbom_name] = package.sha256_bytes(sbom)
    rebind(bundle)
    assert validate(bundle, source_only=True)["scope"] == "source-inputs"
    runtime = root / "lib/cua"
    member = runtime / "runtime.txt"
    member.write_bytes(b"synthetic payload")
    installed = {"schema": 1, "target": TARGET, "files": {"runtime.txt": {
        "size": member.stat().st_size, "sha256": package.sha256_bytes(member.read_bytes())}}}
    write_json(runtime / "installed-inventory.json", installed)
    payload = json.loads((runtime / "payload.json").read_bytes())
    payload.update(schema=2, requirements_sha256=inventory["source_inputs"][target_lock],
                   wheel_manifest_sha256=inventory["source_inputs"][manifest],
                   installed_inventory_sha256=package.sha256_bytes(package.canonical_json(installed)))
    write_json(runtime / "payload.json", payload)
    inventory["payload_manifest_sha256"] = package.sha256_bytes(package.canonical_json(payload))
    review["payload_manifest_sha256"] = inventory["payload_manifest_sha256"]
    sbom = package.canonical_json(package.build_sbom(inventory))
    (root / sbom_name).write_bytes(sbom)
    review["files"][sbom_name] = package.sha256_bytes(sbom)
    rebind(bundle)
    validate(bundle)
    member.write_bytes(b"changed payload")
    with pytest.raises(package.PackageInputError):
        validate(bundle)
    (source / target_lock).write_bytes(b"changed")
    with pytest.raises(package.PackageInputError, match="source input mismatch"):
        validate(bundle, source_only=True)


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
            try:
                path.symlink_to(root / "legal/TERMS.txt")
            except OSError as error:
                if getattr(error, "winerror", None) != 1314:
                    raise
                pytest.skip("Windows symlink creation requires a privilege absent on this host")
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
    result = subprocess.run([sys.executable, str(REPO / "scripts/validate_package_inputs.py"), "--root", str(root), "--source-root", str(source), "--version", VERSION, "--target", TARGET], capture_output=True, text=True, check=False)
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
    root, _, _, _, _payload = bundle
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(root / "lib", target_is_directory=True)
    except OSError as error:
        if getattr(error, "winerror", None) != 1314:
            raise
        pytest.skip("Windows symlink creation requires a privilege absent on this host")
    with pytest.raises(package.PackageInputError):
        validate(bundle, payload_manifest=linked / "cua/payload.json")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction boundary")
def test_explicit_payload_rejects_junction_ancestor(bundle, tmp_path):
    import _winapi

    root, _, _, _, _ = bundle
    linked = tmp_path / "linked"
    _winapi.CreateJunction(str(root / "lib"), str(linked))
    assert linked.is_junction()
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


def test_unknown_declared_license_is_preserved_when_conclusion_is_resolved(bundle):
    bundle[2]["components"][0]["license_declared"] = "NOASSERTION"
    package.validate_inventory(bundle[2])
    assert package.build_sbom(bundle[2])["packages"][0]["licenseDeclared"] == "NOASSERTION"


def test_unknown_copyright_is_preserved_when_distribution_duties_are_resolved(bundle):
    bundle[2]["components"][0]["copyright_text"] = "NOASSERTION"
    package.validate_inventory(bundle[2])
    assert package.build_sbom(bundle[2])["packages"][0]["copyrightText"] == "NOASSERTION"


def test_exact_source_archive_may_be_shared_by_multiple_components(bundle):
    inventory = bundle[2]
    first = inventory["components"][0]
    first["source_offer_required"] = True
    first["source_offer_files"] = [{"path": "legal/SOURCE-OFFERS/shared/source.tar.gz", "sha256": "1" * 64}]
    second = deepcopy(first)
    second["id"] = "shared-source-peer"
    second["sha256"] = "2" * 64
    for field in ("license_files", "notice_files"):
        for entry in second[field]:
            entry["path"] = entry["path"].replace("synthetic-cargo", "shared-source-peer")
    inventory["components"].append(second)
    inventory["coverage"][first["kind"]]["component_ids"].append(second["id"])
    package.validate_inventory(inventory)


def test_shared_source_archive_must_keep_identical_bytes(bundle):
    inventory = bundle[2]
    first = inventory["components"][0]
    first["source_offer_required"] = True
    first["source_offer_files"] = [{"path": "legal/SOURCE-OFFERS/shared/source.tar.gz", "sha256": "1" * 64}]
    second = deepcopy(first)
    second["id"] = "changed-source-peer"
    second["sha256"] = "2" * 64
    for field in ("license_files", "notice_files"):
        for entry in second[field]:
            entry["path"] = entry["path"].replace("synthetic-cargo", "changed-source-peer")
    second["source_offer_files"][0]["sha256"] = "3" * 64
    inventory["components"].append(second)
    inventory["coverage"][first["kind"]]["component_ids"].append(second["id"])
    with pytest.raises(package.PackageInputError):
        package.validate_inventory(inventory)


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
