"""Draft synthesis must preserve provenance and cannot approve unresolved inputs."""

import io
import zipfile

import pytest

from scripts import synthesize_windows_legal as synthesis
from scripts.validate_package_inputs import PackageInputError


def metadata():
    packages = [{"id": name, "targets": [{"kind": ["proc-macro" if name == "macro" else "lib"]}]}
                for name in ("root", "normal", "build", "dev", "macro", "shared")]
    def edge(name, kind=None):
        return {"pkg": name, "dep_kinds": [{"kind": kind}]}
    nodes = [{"id": "root", "deps": [edge("normal"), edge("build", "build"), edge("dev", "dev"), edge("macro")]},
             {"id": "normal", "deps": [edge("shared")]}, {"id": "build", "deps": [edge("shared")]},
             {"id": "dev", "deps": [edge("shared")]}, {"id": "macro", "deps": []},
             {"id": "shared", "deps": []}]
    return {"packages": packages, "resolve": {"root": "root", "nodes": nodes}}


def test_cargo_contexts_are_not_promoted_to_linkage():
    result = synthesis.cargo_scopes(metadata())
    assert result["normal"] == ["target-normal"]
    assert result["macro"] == ["build-or-generated-code"]
    assert result["dev"] == ["development"]
    assert result["shared"] == ["build-or-generated-code", "development", "target-normal"]


@pytest.mark.parametrize("declared, expected", [
    ("MIT OR Apache-2.0", "Apache-2.0"), ("MIT/Apache-2.0", "Apache-2.0"),
    ("MIT AND BSD-3-Clause", "MIT AND BSD-3-Clause"),
    ("Apache-2.0 WITH LLVM-exception", "Apache-2.0 WITH LLVM-exception"),
    ("(MIT OR Apache-2.0) AND Unicode-3.0", "(Apache-2.0) AND Unicode-3.0"),
    ([{"expression": "MIT OR Apache-2.0"}], "Apache-2.0"),
    ("unidentified grant", None),
])
def test_license_selection_never_discards_conjunction_or_exception(declared, expected):
    assert synthesis.license_choice(declared) == expected


def test_copyright_does_not_promote_authors_or_template():
    sources = [("notice", b"Author: Someone\nCopyright [yyyy] [name of copyright owner]\nCopyright (c) 2020 Actual holder\n")]
    assert synthesis.copyright_lines(sources) == "Copyright (c) 2020 Actual holder"


def test_license_filename_is_not_a_grant():
    assert synthesis.license_atoms(b"LICENSE-APACHE; see another file") == set()


def test_truncated_mit_never_closes_review_or_source_duty():
    fragment = b'Copyright (c) 2026 Holder\nPermission is hereby granted, free of charge\nTHE SOFTWARE IS PROVIDED AS IS\n'
    packet = synthesis.Packet()
    packet.component(identifier="fragment", name="fragment", version="1", kind="cargo", digest="a" * 64,
                     location="https://example.org/source", declared="MIT", sources=[("LICENSE", fragment)],
                     scope="test", pending=["license-choice-and-original-copyright", "notice-and-source-duty"])
    assert synthesis.license_atoms(fragment) == set()
    assert packet.components[0]["license_concluded"] == "NOASSERTION"
    assert packet.components[0]["source_offer_required"] is None
    assert len(packet.pending[0]["items"]) == 2
    assert synthesis.license_atoms(synthesis.MIT_GRANT.encode()) == {"MIT"}


@pytest.mark.parametrize("declared, expected", [
    ("MIT OR Apache-2.0", "MIT OR Apache-2.0"),
    ([{"expression": "Apache-2.0 OR BSD-3-Clause"}], "Apache-2.0 OR BSD-3-Clause"),
    ("GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3", None),
    ("AGPL-3.0-only", "AGPL-3.0-only"),
])
def test_declared_expression_is_not_a_concluded_choice(declared, expected):
    assert synthesis.declared_expression(declared) == expected


def test_mutated_observation_is_rejected_before_using_claims(tmp_path):
    (tmp_path / "preparation-observation.json").write_bytes(
        b'{"architecture":"x64","target":"aarch64-pc-windows-msvc","source":{"source_sha":"0000000000000000000000000000000000000000","run_id":1}}')
    with pytest.raises(PackageInputError, match="retained observation identity differs"):
        synthesis.verify_observation(tmp_path, tmp_path, "x64")


def test_choice_uses_an_available_explicit_alternative():
    assert synthesis.license_choice("MIT OR Apache-2.0", {"MIT"}) == "MIT"
    assert synthesis.license_choice("Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT") == "Apache-2.0"


def test_unreviewed_component_stays_unresolved():
    packet = synthesis.Packet()
    packet.component(identifier="example", name="example", version="1", kind="wheel", digest="a" * 64,
                     location="https://example.org/exact.whl", declared="MIT", sources=[("LICENSE", b"missing grant")],
                     scope="installed-wheel", pending=["legal-review"])
    row = packet.components[0]
    assert row["license_concluded"] == "NOASSERTION"
    assert row["copyright_text"] == "NOASSERTION"
    assert row["source_offer_required"] is None
    assert packet.pending == [{"id": "example", "items": ["legal-review"]}]


def test_emit_is_deterministic_and_refuses_overwrite(tmp_path):
    output = tmp_path / "packet"
    files = {"legal/original.txt": b"Original\r\n", "review.json": b"{}\n"}
    synthesis.emit(files, output, False)
    synthesis.emit(files, output, True)
    with pytest.raises(PackageInputError, match="already exists"):
        synthesis.emit(files, output, False)
    (output / "review.json").write_bytes(b"changed")
    with pytest.raises(PackageInputError, match="bytes differ"):
        synthesis.emit(files, output, True)


@pytest.mark.parametrize("name", ["../outside", "a:stream", "CON", "safe/../outside"])
def test_output_paths_are_bounded(name):
    with pytest.raises(PackageInputError):
        synthesis.Packet().put(name, b"data")


def test_wheel_case_alias_is_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("LICENSE", b"one")
        archive.writestr("license", b"two")
    with pytest.raises(PackageInputError, match="alias"):
        synthesis.wheel_metadata(buffer.getvalue())


def test_wheel_metadata_and_notice_preserve_original_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("demo-1.dist-info/METADATA", b"Name: demo\nVersion: 1\nLicense-Expression: MIT\n\n")
        archive.writestr("demo-1.dist-info/licenses/LICENSE", b"Original\r\n")
    message, declared, notices, sboms = synthesis.wheel_metadata(buffer.getvalue())
    assert message["Name"] == "demo"
    assert declared == "MIT"
    assert notices == [("demo-1.dist-info/licenses/LICENSE", b"Original\r\n")]
    assert sboms == []
