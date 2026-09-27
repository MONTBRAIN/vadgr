"""Source observations separate dependency scope, ownership evidence and approval."""

import io
import json
import tarfile

import pytest

from scripts import inspect_legal_crate_sources as crates
from scripts import windows_legal_source_evidence as evidence
from scripts.validate_package_inputs import PackageInputError, sha256_bytes
from scripts.synthesize_windows_legal import Packet


@pytest.mark.parametrize("expression, expected", [
    ("cfg(windows)", True), ("cfg(unix)", False),
    ('cfg(all(windows, target_arch = "x86_64"))', True),
    ('cfg(all(windows, target_arch = "aarch64"))', False),
    ('cfg(any(unix, feature = "optional"))', None),
    ('cfg(not(target_os = "windows"))', False),
    ("aarch64-pc-windows-msvc", False),
])
def test_target_scope_preserves_unknown_features(expression, expected):
    assert evidence.cfg_matches(expression, "x86_64") is expected


def test_nested_macros_and_build_edges_are_not_runtime_dependencies():
    nodes = [{"name": name, "version": "1", "bom-ref": name} for name in ("root", "normal", "build", "macro", "unix")]
    sbom = {"metadata": {"component": nodes[0]}, "components": nodes[1:],
            "dependencies": [{"ref": "root", "dependsOn": ["normal", "build", "macro", "unix"]}]}
    manifests = {("root", "1"): {"dependencies": {"normal": "1", "macro": "1"},
                  "build-dependencies": {"build": "1"}, "target": {"cfg(unix)": {"dependencies": {"unix": "1"}}}},
                 ("macro", "1"): {"lib": {"proc-macro": True}}}
    result, missing = evidence.nested_graph(sbom, manifests, "x86_64")
    assert result["normal"] == ["target-link-relevant"]
    assert result["build"] == result["macro"] == ["build-or-generated-code"]
    assert "unix" not in result
    assert missing == []


def test_missing_parent_source_is_explicit_not_normal():
    sbom = {"metadata": {"component": {"name": "root", "version": "1", "bom-ref": "root"}},
            "components": [{"name": "child", "version": "1", "bom-ref": "child"}],
            "dependencies": [{"ref": "root", "dependsOn": ["child"]}]}
    result, missing = evidence.nested_graph(sbom, {}, "x86_64")
    assert result["child"] == ["source-edge-unresolved"]
    assert missing == ["root"]


@pytest.mark.parametrize("include_source", [True, False])
def test_parent_nested_catalogue_closes_only_with_every_source_edge(include_source):
    packet = Packet()
    packet.evidence = [{"id": "wheel-example"}]
    packet.pending = [{"id": "wheel-example", "items": ["target-specific-nested-SBOM-scope", "legal-review"]}]
    sbom = {"metadata": {"component": {"name": "root", "version": "1", "bom-ref": "root"}},
            "components": [{"name": "child", "version": "1", "bom-ref": "child", "purl": "pkg:cargo/child@1"}],
            "dependencies": [{"ref": "root", "dependsOn": ["child"]}]}
    packet.files["nested-sboms/wheel-example/catalogue.json"] = json.dumps(sbom).encode()
    observations = {"root": {"manifests": {"root/Cargo.toml": {
        "package": {"name": "root", "version": "1"}, "dependencies": {"child": "1"}}}}} if include_source else {}
    evidence.classify_nested(packet, observations, [], "x86_64")
    assert ("target-specific-nested-SBOM-scope" not in packet.pending[0]["items"]) is include_source
    assert "legal-review" in packet.pending[0]["items"]


def archive(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as stream:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            stream.addfile(member, io.BytesIO(raw))
    return output.getvalue()


def test_original_copyright_not_inferred_from_authors():
    raw = archive({"demo-1/Cargo.toml": b'[package]\nname="demo"\nversion="1"\nauthors=["Example"]\n',
                   "demo-1/LICENSE": b"Copyright [yyyy] [name of copyright owner]\n"})
    component = {"name": "demo", "version": "1", "sha256": sha256_bytes(raw),
                 "download_location": "https://example.org/demo"}
    result = crates.inspect_archive(raw, component)
    assert result["copyright_observation"] == "no-statement-detected"
    assert result["files_scanned"] == 2
    with pytest.raises(PackageInputError, match="hash differs"):
        crates.inspect_archive(raw, {**component, "sha256": "0" * 64})


def test_original_statement_records_source_line_and_hash():
    raw = archive({"demo-1/src/lib.rs": b"// Copyright 2026 Original Holder\n"})
    component = {"name": "demo", "version": "1", "sha256": sha256_bytes(raw),
                 "download_location": "https://example.org/demo"}
    claim = crates.inspect_archive(raw, component)["original_statements"][0]
    assert claim["path"] == "demo-1/src/lib.rs"
    assert claim["statements"] == [{"line": 1, "text": "// Copyright 2026 Original Holder"}]


def test_source_archive_traversal_is_rejected():
    raw = archive({"../escape": b"data"})
    with pytest.raises(PackageInputError, match="unsafe path"):
        crates.inspect_archive(raw, {"sha256": sha256_bytes(raw)})


def test_native_mapping_refuses_non_pe():
    with pytest.raises(PackageInputError, match="not PE"):
        evidence.pe_imports(b"not native", "x64")
