"""Draft generation uses explicit synthetic files in a fresh temporary directory."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "generate_legal_bundle.py"
REQUIRED = {
    "legal/TERMS.txt", "legal/LICENSE.txt", "legal/NOTICE.txt",
    "legal/PRIVACY-NOTICE.txt", "legal/SECURITY-AND-PERMISSIONS.txt",
    "legal/SUPPORT.txt", "legal/UNINSTALL-AND-DATA.txt", "README-OFFLINE.txt",
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def generator(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("generate_legal_bundle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path.resolve()
    contents = {name: ("Synthetic public text for " + name + "\r\n").encode() for name in REQUIRED}
    contents["legal/TERMS.txt"] = "Terms {accept} \\ café 中文 😀\r\n\tEnd.\n".encode()
    components = []
    for kind in ("cargo", "wheel", "runtime"):
        refs = {}
        for field, directory in (("license_files", "LICENSES"), ("notice_files", "NOTICES"),
                                 ("source_offer_files", "SOURCE-OFFERS")):
            name = f"legal/{directory}/{kind}.txt"
            contents[name] = f"Synthetic {kind} {directory}\r\nCopyright fixture\n".encode()
            refs[field] = [{"path": name, "sha256": digest(contents[name])}]
            if field == "license_files":
                refs[field][0]["license_ids"] = ["MIT"]
        components.append({
            "id": kind, "name": "synthetic-" + kind, "version": "1.2.3", "kind": kind,
            "sha256": digest(kind.encode()), "license_declared": "MIT", "license_concluded": "MIT",
            "download_location": "https://example.com/" + kind, "copyright_text": "Copyright synthetic fixture",
            "notice_required": True, "source_offer_required": True, **refs,
        })
    inventory = {
        "schema": 1, "version": "0.5.0", "target": "aarch64-apple-darwin", "terms_version": "1.0",
        "created": "2026-01-01T00:00:00Z",
        "terms_sha256": digest(contents["legal/TERMS.txt"]),
        "source_inputs": {name: digest(name.encode()) for name in (
            "Cargo.lock", "packaging/cua/pins.toml", "packaging/cua/requirements.lock", "packaging/toolchain.json")},
        "payload_manifest_sha256": digest(b"synthetic manifest"),
        "coverage": {kind: {"status": "complete", "component_ids": [kind] if kind in {"cargo", "wheel", "runtime"} else []}
                     for kind in ("cargo", "wheel", "runtime", "asset", "framework")},
        "components": components,
    }
    files = {}
    for index, (name, data) in enumerate(sorted(contents.items())):
        source = root / "sources" / f"public-{index}.txt"
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(data)
        files[name] = {"path": source.relative_to(root).as_posix(), "sha256": digest(data)}
    document = {"schema": 1, "inventory": inventory, "files": files}
    path = root / "input.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, document, contents


def save(inputs):
    path, document, _ = inputs
    path.write_text(json.dumps(document), encoding="utf-8")


def output_files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_generates_deterministic_verbatim_draft(generator, inputs):
    path, document, contents = inputs
    first, second = path.parent / "first", path.parent / "second"
    review = generator.generate_legal_bundle(path, first)
    generator.generate_legal_bundle(path, second)
    files = output_files(first)
    assert files == output_files(second)
    assert all(files[name] == value for name, value in contents.items())
    assert review == json.loads(files["package-input-review.json"])
    assert review["status"] == "draft" and review["synthetic"] is False
    assert review["closures"] == dict.fromkeys(("publisher", "market_rights", "apache_compatibility", "product_data", "third_party_duties"), False)
    assert review["inventory_sha256"] == digest(files["package-input-inventory.json"])
    assert json.loads(files["package-input-inventory.json"]) == document["inventory"]
    assert review["files"] == {name: digest(data) for name, data in files.items() if not name.startswith("package-input-")}
    assert str(path.parent).encode() not in b"".join(files.values())
    sbom = json.loads(files["sbom/vadgr-0.5.0.spdx.json"])
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert {item["SPDXID"] for item in sbom["packages"]} == {"SPDXRef-cargo", "SPDXRef-wheel", "SPDXRef-runtime"}
    for directory, aggregate in (("NOTICES", "THIRD-PARTY-NOTICES.txt"), ("SOURCE-OFFERS", "SOURCE-OFFER.txt")):
        for name, data in contents.items():
            if name.startswith(f"legal/{directory}/"):
                assert data in files["legal/" + aggregate]


def test_terms_rtf_escapes_unicode_and_control_syntax(generator, inputs):
    path, _, contents = inputs
    output = path.parent / "result"
    generator.generate_legal_bundle(path, output)
    assert (output / "legal/TERMS.txt").read_bytes() == contents["legal/TERMS.txt"]
    rtf = (output / "legal/TERMS.rtf").read_bytes()
    assert rtf.startswith(b"{\\rtf1") and rtf.endswith(b"}\n")
    assert b"\\{accept\\}" in rtf and b"\\\\" in rtf
    assert b"\\u233?" in rtf and b"\\u20013?\\u25991?" in rtf
    assert b"\\u-10179?\\u-8704?" in rtf
    assert b"\\par\n" in rtf and b"\\tab " in rtf


@pytest.mark.parametrize("mutation", ["file_hash", "terms_hash", "license_hash", "missing", "extra", "unresolved", "coverage", "schema", "approval"])
def test_rejects_invalid_inputs_before_writing(generator, inputs, mutation):
    path, document, _ = inputs
    if mutation == "file_hash":
        document["files"]["legal/NOTICE.txt"]["sha256"] = "0" * 64
    elif mutation == "terms_hash":
        document["inventory"]["terms_sha256"] = "0" * 64
    elif mutation == "license_hash":
        document["inventory"]["components"][0]["license_files"][0]["sha256"] = "0" * 64
    elif mutation == "missing":
        del document["files"]["legal/PRIVACY-NOTICE.txt"]
    elif mutation == "extra":
        document["files"]["legal/extra.txt"] = document["files"]["legal/NOTICE.txt"]
    elif mutation == "unresolved":
        document["inventory"]["components"][0]["license_concluded"] = "MIT OR Apache-2.0"
    elif mutation == "coverage":
        document["inventory"]["coverage"]["wheel"]["component_ids"] = []
    elif mutation == "schema":
        document["schema"] = True
    else:
        document["status"] = "approved"
    save(inputs)
    output = path.parent / "result"
    with pytest.raises((generator.PackageInputError, OSError)):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


@pytest.mark.parametrize("relative", ["../escape.txt", "/absolute.txt", "sources/../escape.txt", "sources//text.txt", "C:secret.txt", "sources\\text.txt"])
def test_rejects_unsafe_source_reference(generator, inputs, relative):
    path, document, _ = inputs
    document["files"]["legal/NOTICE.txt"]["path"] = relative
    save(inputs)
    output = path.parent / "result"
    with pytest.raises((generator.PackageInputError, OSError)):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["symlink", "directory_link", "hardlink", "directory", "input_link"])
def test_rejects_linked_and_nonregular_inputs(generator, inputs, kind):
    path, document, _ = inputs
    source = path.parent / document["files"]["legal/NOTICE.txt"]["path"]
    if kind == "hardlink":
        os.link(source, source.with_suffix(".linked"))
    elif kind == "directory":
        source.unlink()
        source.mkdir()
    else:
        target = source if kind == "symlink" else source.parent if kind == "directory_link" else path
        link = path.parent / "link"
        try:
            link.symlink_to(target, target_is_directory=kind == "directory_link")
        except OSError:
            pytest.skip("symbolic links are not available")
        if kind == "input_link":
            path = link
        else:
            document["files"]["legal/NOTICE.txt"]["path"] = "link" if kind == "symlink" else "link/" + source.name
            save(inputs)
    output = path.parent / "result"
    with pytest.raises((generator.PackageInputError, OSError)):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["directory", "file", "dangling_link", "parent_link"])
def test_never_overwrites_existing_output_or_follows_parent_link(generator, inputs, kind):
    path, _, _ = inputs
    output = path.parent / "result"
    sentinel = b"Existing owner bytes"
    if kind == "directory":
        output.mkdir()
        (output / "sentinel").write_bytes(sentinel)
    elif kind == "file":
        output.write_bytes(sentinel)
    else:
        try:
            output.symlink_to(path.parent if kind == "parent_link" else path.parent / "absent", target_is_directory=True)
        except OSError:
            pytest.skip("symbolic links are not available")
        if kind == "parent_link":
            output = output / "new"
    with pytest.raises((generator.PackageInputError, OSError)):
        generator.generate_legal_bundle(path, output)
    if kind == "directory":
        assert (output / "sentinel").read_bytes() == sentinel
    elif kind == "file":
        assert output.read_bytes() == sentinel
    elif kind == "parent_link":
        assert not (path.parent / "new").exists()
    else:
        assert output.is_symlink()


def test_cli_reports_draft_and_fixed_errors(inputs):
    path, document, _ = inputs
    output = path.parent / "result"
    result = subprocess.run([sys.executable, str(SCRIPT), "--input", str(path), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "draft"
    document["files"]["legal/NOTICE.txt"]["path"] = "../private-marker"
    save(inputs)
    result = subprocess.run([sys.executable, str(SCRIPT), "--input", str(path), "--output", str(path.parent / "bad")], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == "" and result.stderr == "Legal bundle generation failed.\n"
    assert "private-marker" not in result.stderr


def test_optional_obligations_remain_explicit_without_invented_source_offer(generator, inputs):
    path, document, _ = inputs
    for component in document["inventory"]["components"]:
        for field in ("notice_files", "source_offer_files"):
            for reference in component[field]:
                del document["files"][reference["path"]]
            component[field] = []
        component["notice_required"] = component["source_offer_required"] = False
    save(inputs)
    output = path.parent / "result"
    generator.generate_legal_bundle(path, output)
    assert not (output / "legal/SOURCE-OFFER.txt").exists()
    assert (output / "legal/THIRD-PARTY-NOTICES.txt").read_bytes() == b"No additional third-party NOTICE files are required by the component inventory.\n"


def test_rejects_output_file_directory_collision_before_writing(generator, inputs):
    path, document, _ = inputs
    reference = document["inventory"]["components"][1]["license_files"][0]
    old_name = reference["path"]
    reference["path"] = "legal/LICENSES/cargo.txt/wheel.txt"
    document["files"][reference["path"]] = document["files"].pop(old_name)
    save(inputs)
    output = path.parent / "result"
    with pytest.raises(generator.PackageInputError):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="requires POSIX ownership")
def test_rejects_output_parent_owned_by_another_user(generator, inputs, monkeypatch):
    path, _, _ = inputs
    monkeypatch.setattr(generator.os, "geteuid", lambda: -1)
    output = path.parent / "result"
    with pytest.raises(generator.PackageInputError):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


def test_duplicate_json_keys_fail_before_writing(generator, inputs):
    path, _, _ = inputs
    path.write_bytes(b'{"schema": 1, "schema": 1}')
    output = path.parent / "result"
    with pytest.raises(generator.PackageInputError):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


@pytest.mark.parametrize("field", ["license_files", "notice_files", "source_offer_files"])
def test_preserves_non_utf8_component_bytes(generator, inputs, field):
    path, document, _ = inputs
    reference = document["inventory"]["components"][0][field][0]
    source = document["files"][reference["path"]]
    data = b"Synthetic component text\r\nCopyright \xa9 fixture\n"
    (path.parent / source["path"]).write_bytes(data)
    source["sha256"] = reference["sha256"] = digest(data)
    save(inputs)
    output = path.parent / "result"
    review = generator.generate_legal_bundle(path, output)
    assert (output / reference["path"]).read_bytes() == data
    assert review["files"][reference["path"]] == digest(data)
    if field != "license_files":
        aggregate = "THIRD-PARTY-NOTICES.txt" if field == "notice_files" else "SOURCE-OFFER.txt"
        assert data in (output / "legal" / aggregate).read_bytes()


def test_rejects_empty_component_bytes(generator, inputs):
    path, document, _ = inputs
    reference = document["inventory"]["components"][0]["license_files"][0]
    source = document["files"][reference["path"]]
    (path.parent / source["path"]).write_bytes(b"")
    source["sha256"] = reference["sha256"] = digest(b"")
    save(inputs)
    output = path.parent / "result"
    with pytest.raises(generator.PackageInputError):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_required_public_text_must_remain_utf8(generator, inputs, name):
    path, document, _ = inputs
    source = document["files"][name]
    data = b"Invalid public text \xa9"
    (path.parent / source["path"]).write_bytes(data)
    source["sha256"] = digest(data)
    if name == "legal/TERMS.txt":
        document["inventory"]["terms_sha256"] = digest(data)
    save(inputs)
    output = path.parent / "result"
    with pytest.raises(generator.PackageInputError):
        generator.generate_legal_bundle(path, output)
    assert not output.exists()


@pytest.mark.parametrize("paths", [
    {"legal/LICENSES/caf\u00e9.txt", "legal/LICENSES/cafe\u0301.txt"},
    {"legal/LICENSES/caf\u00e9", "legal/LICENSES/cafe\u0301/LICENSE.txt"},
])
def test_rejects_unicode_normalization_output_collisions(generator, paths):
    with pytest.raises(generator.PackageInputError):
        generator._check_output_paths(paths)
