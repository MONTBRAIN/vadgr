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


def test_filled_bracketed_copyright_is_distinct_from_template():
    assert crates.statements("Copyright [2025] [N0, INC]") == [
        {"line": 1, "text": "Copyright [2025] [N0, INC]"}]
    assert crates.statements("Copyright [yyyy] [name of copyright owner]") == []
    assert crates.statements("Copyright [2025] [name of copyright owner]") == []


@pytest.mark.parametrize("changed", ["none", "vcs", "manifest", "grant"])
def test_external_grant_binds_application_revision_and_full_text(tmp_path, monkeypatch, changed):
    grant = b"exact complete external grant"
    monkeypatch.setitem(evidence.EXTERNAL_CRATE_GRANTS, "demo",
        ("1", "a" * 40, "https://example.org/demo", "grant.txt", sha256_bytes(grant), "https://example.org/grant"))
    (tmp_path / "grant.txt").write_bytes(grant + (b"changed" if changed == "grant" else b""))
    raw = archive({"demo-1/Cargo.toml": (
        '[package]\nname="demo"\nversion="1"\nrepository="https://example.org/demo"\nlicense="'
        + ("MIT" if changed == "manifest" else "Apache-2.0 OR MIT") + '"\n').encode(),
        "demo-1/.cargo_vcs_info.json": json.dumps({"git": {"sha1": ("b" if changed == "vcs" else "a") * 40},
            "path_in_vcs": "demo"}).encode()})
    row = {"name": "demo", "version": "1", "sha256": sha256_bytes(raw)}
    if changed == "none":
        notice, proof = evidence.crate_external_grant(row, raw, tmp_path)
        assert notice == ("grant.txt", grant)
        assert proof["archive_sha256"] == row["sha256"]
        assert len(proof["source_files"]) == 2
    else:
        with pytest.raises(PackageInputError, match="differs"):
            evidence.crate_external_grant(row, raw, tmp_path)


def test_source_archive_traversal_is_rejected():
    raw = archive({"../escape": b"data"})
    with pytest.raises(PackageInputError, match="unsafe path"):
        crates.inspect_archive(raw, {"sha256": sha256_bytes(raw)})


def test_native_mapping_refuses_non_pe():
    with pytest.raises(PackageInputError, match="not PE"):
        evidence.pe_imports(b"not native", "x64")


def test_accesskit_scope_requires_explicit_source_notice_and_exact_archive():
    raw = archive({"accesskit-1/src/lib.rs": b"// Derived from Chromium's accessibility abstraction.\n// found in the LICENSE.chromium file.\n"})
    row = {"name": "accesskit", "version": "1", "sha256": sha256_bytes(raw)}
    grants = {"MIT", "Apache-2.0", "BSD-3-Clause"}
    result = evidence.crate_grant_scope(row, raw, "Apache-2.0", grants)
    assert result["expression"] == "Apache-2.0 AND BSD-3-Clause"
    assert result["source_files"][0]["path"] == "accesskit-1/src/lib.rs"
    assert result["status"] == "source-scope-proposal-not-package-approval"
    assert evidence.crate_grant_scope(row, raw, "Apache-2.0", grants | {"Unknown"}) is None
    with pytest.raises(PackageInputError, match="archive identity differs"):
        evidence.crate_grant_scope(row, raw + b"changed", "Apache-2.0", grants)


@pytest.mark.parametrize("extra, resolved", [(b"", True), (b"* [src/runtime.rs](src/runtime.rs) extra grant", False)])
def test_crossbeam_test_scope_never_discards_a_new_runtime_reference(extra, resolved):
    readme = (b"#### Third party software\n* [examples/matching.rs](examples/matching.rs)\n"
              b"* [tests/mpsc.rs](tests/mpsc.rs)\n* [tests/golang.rs](tests/golang.rs)\n"
              b"Copies of third party licenses can be found\n" + extra)
    raw = archive({"crossbeam-channel-1/README.md": readme, "crossbeam-channel-1/LICENSE-THIRD-PARTY": b"retained catalogue"})
    result = evidence.crate_grant_scope({"name": "crossbeam-channel", "version": "1", "sha256": sha256_bytes(raw)},
        raw, "Apache-2.0", {"Apache-2.0", "MIT", "BSD-3-Clause"})
    assert (result is not None) is resolved


def test_font_crate_scope_requires_all_embedded_grants():
    raw = archive({"epaint_default_fonts-1/fonts/Hack-Regular.txt":
        b"Source Foundry Authors and licensed under the MIT License\n"
        b"Bitstream Vera Sans Mono Copyright 2003 Bitstream Inc. and licensed under the Bitstream Vera License"})
    row = {"name": "epaint_default_fonts", "version": "1", "sha256": sha256_bytes(raw)}
    grants = {"Apache-2.0", "MIT", "Bitstream-Vera", "OFL-1.1", "Ubuntu-font-1.0"}
    assert "Bitstream-Vera" in evidence.crate_grant_scope(row, raw, "Apache-2.0", grants)["expression"]
    assert evidence.crate_grant_scope(row, raw, "Apache-2.0", grants - {"Bitstream-Vera"}) is None
    assert evidence.crate_grant_scope(row, raw, "Apache-2.0", grants | {"Unknown"}) is None


@pytest.mark.parametrize("features, resolved", [(None, False), (["bundled"], True), (["bundled-sqlcipher"], False)])
def test_sqlcipher_scope_requires_observed_features(features, resolved):
    raw = archive({"libsqlite3-sys-1/build.rs":
        b'if cfg!(any(feature = "sqlcipher", feature = "bundled-sqlcipher")) { "sqlcipher" } else { "sqlite3" }',
        "libsqlite3-sys-1/sqlcipher/LICENSE": b"retained original SQLCipher grant"})
    row = {"name": "libsqlite3-sys", "version": "1", "sha256": sha256_bytes(raw)}
    assert (evidence.crate_grant_scope(row, raw, "MIT", {"MIT", "BSD-3-Clause"}, features) is not None) is resolved


@pytest.mark.parametrize("name, extra_bsd", [("lexical-parse-integer", False), ("lexical-parse-float", True)])
def test_lexical_scope_does_not_assign_write_algorithms_to_parse_crates(name, extra_bsd):
    text = (b"## `write-floats, not(compact)`\nlexical-write-float/src/algorithm.rs Apache2 With LLVM Exceptions\n"
        b"## `write-floats, compact`\n## `write-floats, radix`\nlexical-write-float/src/radix.rs\n"
        b"## `parse-floats, compact`\nlexical-parse-float/src/bellerophon.rs\n# License Terms\n")
    raw = archive({name + "-1/LICENSE.md": text})
    row = {"name": name, "version": "1", "sha256": sha256_bytes(raw)}
    grants = {"Apache-2.0", "MIT", "BSD-3-Clause", "BSL-1.0", "LLVM-exception"}
    result = evidence.crate_grant_scope(row, raw, "Apache-2.0", grants)
    assert ("BSD-3-Clause" in result["expression"]) is extra_bsd
    assert "BSL-1.0" not in result["expression"]
    assert evidence.crate_grant_scope(row, raw, "Apache-2.0", grants | {"Unknown"}) is None


def test_apache_application_notice_requires_complete_separately_pinned_grant(tmp_path, monkeypatch):
    grant = b"complete pinned text"
    spec = evidence.EXTERNAL_CRATE_GRANTS["cms"]
    monkeypatch.setitem(evidence.EXTERNAL_CRATE_GRANTS, "cms", (*spec[:4], sha256_bytes(grant), spec[-1]))
    (tmp_path / spec[3]).write_bytes(grant)
    application = [("LICENSE", b'Licensed under the Apache License, Version 2.0 (the "License");\n'
        b'http://www.apache.org/licenses/LICENSE-2.0')]
    notice, proof = evidence.complete_apache_reference(application, tmp_path)
    assert notice[1] == grant
    assert proof["application_files"][0]["sha256"] == sha256_bytes(application[0][1])
    assert evidence.complete_apache_reference([("LICENSE", b"Apache")], tmp_path) is None
    (tmp_path / spec[3]).write_bytes(b"truncated")
    with pytest.raises(PackageInputError, match="text differs"):
        evidence.complete_apache_reference(application, tmp_path)


def test_explicit_source_copyright_string_is_retained_without_inventing_author_claims():
    line = '__copyright__ = "Copyright Kenneth Reitz"'
    assert crates.statements(line) == [{"line": 1, "text": line}]
    assert crates.statements('__author__ = "Kenneth Reitz"') == []
