"""Draft synthesis must preserve provenance and cannot approve unresolved inputs."""

import io
import json
from pathlib import Path
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


@pytest.mark.parametrize("explicit_scope", [True, False])
def test_python_composite_preserves_upstream_declaration_and_requires_explicit_scope(explicit_scope):
    root = Path(__file__).resolve().parents[2] / "packaging/inputs/windows-x86_64"
    inventory = json.loads((root / "package-input-inventory.json").read_bytes())
    row = next(row for row in inventory["components"] if row["id"] == "wheel-typing-extensions-4.16.0")
    raw = (root / row["notice_files"][0]["path"]).read_bytes()
    if not explicit_scope:
        raw = raw.replace(b"ZERO-CLAUSE BSD LICENSE FOR CODE IN THE PYTHON DOCUMENTATION", b"Unmapped additional grant")
    packet = synthesis.Packet()
    packet.component(identifier="python-example", name="example", version="1", kind="runtime",
        digest="a" * 64, location="https://example.org", declared="PSF-2.0", sources=[("LICENSE", raw)],
        scope="test", pending=[])
    assert packet.components[0]["license_declared"] == "PSF-2.0"
    assert packet.evidence[0]["original_license_declaration"] == "PSF-2.0"
    assert (packet.components[0]["license_concluded"] == "Python-2.0 AND 0BSD") is explicit_scope
    assert ("additional-retained-grant-scope" not in packet.pending[0]["items"]) is explicit_scope


def test_cdla_recognition_requires_the_complete_retained_grant():
    root = Path(__file__).resolve().parents[2] / "packaging/inputs/windows-x86_64"
    raw = (root / "legal/NOTICES/cargo-webpki-roots-1.0.9/000-000-LICENSE").read_bytes()
    assert synthesis.license_atoms(raw) == {"CDLA-Permissive-2.0"}
    assert not synthesis.license_atoms(raw[:100])
    assert "CDLA-Permissive-2.0" not in synthesis.license_atoms(raw + b"Additional condition")


def test_pywin32_composite_refuses_unmapped_lgpl_scope():
    root = Path(__file__).resolve().parents[2] / "packaging/inputs/windows-x86_64/legal/NOTICES/wheel-pywin32-312"
    sources = [("adodbapi/license.txt", (root / "000-license.txt").read_bytes()),
        ("win32/License.txt", (root / "001-License.txt").read_bytes()),
        ("pythonwin/Scintilla-License.txt", (root / "002-Scintilla-License.txt").read_bytes()),
        ("pythonwin/pywin/idle/LICENSE.txt", (root / "003-LICENSE.txt").read_bytes()),
        ("win32comext/mapi/MAPIStubLibrary-License.txt", (root / "014-MAPIStubLibrary-License.txt").read_bytes()),
        ("win32comext/mapi/NOTICE.md", (root / "015-NOTICE.md").read_bytes())]
    assert synthesis.pywin32_grant_scope(sources) == "BSD-3-Clause AND HPND AND MIT AND Python-2.0 AND LGPL-2.1-or-later"
    with pytest.raises(PackageInputError, match="LGPL scope"):
        synthesis.pywin32_grant_scope([*sources, ("another-library/LICENSE", sources[0][1])])


def test_lowercase_and_symbol_original_copyright_is_retained():
    assert synthesis.copyright_lines([("source", b"copyright Alexander Huszagh.\n(C) 2024 Trifecta Tech Foundation\n")]) == (
        "(C) 2024 Trifecta Tech Foundation\ncopyright Alexander Huszagh.")


def test_mit_zero_requires_complete_grant_without_mit_notice_condition():
    assert synthesis.license_atoms(synthesis.MIT_ZERO_GRANT.encode()) == {"MIT-0"}
    assert not synthesis.license_atoms(b"MIT No Attribution\nPermission is hereby granted")


def test_sqlite_disclaimer_is_not_an_invented_copyright_holder():
    raw = synthesis.SQLITE_BLESSING.encode()
    assert synthesis.license_atoms(raw) == {"blessing"}
    assert synthesis.copyright_lines([("license.terms", raw)]) == "The author disclaims copyright to this source code."
    assert not synthesis.license_atoms(raw.split(b"May you find")[0])


def test_tcl_copyright_statement_preserves_named_parties():
    raw = b"This software is copyrighted by the Regents of Example University,\nOther Corporation and other parties. The following terms apply to all files."
    assert synthesis.copyright_lines([("license.terms", raw)]) == (
        "This software is copyrighted by the Regents of Example University, Other Corporation and other parties.")


def test_bsd_third_condition_without_article_is_not_downgraded():
    text = '''Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
Redistributions of source code must retain the above copyright notice,
this list of conditions and the following disclaimer.
Redistributions in binary form must reproduce the above copyright notice,
this list of conditions and the following disclaimer in the documentation
and/or other materials provided with the distribution.
Neither name of Holder nor the names of contributors may be used to endorse
or promote products derived from this software without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.'''
    assert synthesis.license_atoms(text.encode()) == {"BSD-3-Clause"}
    assert not synthesis.license_atoms(text.split("THIS SOFTWARE")[0].encode())


def test_custom_grant_is_digest_bound_and_cannot_remove_source_review():
    raw = b"Exact unusual redistribution conditions, Copyright 2026 Holder."
    digest = synthesis.sha256_bytes(raw)
    identifier = "LicenseRef-Exact-" + digest
    packet = synthesis.Packet()
    packet.component(identifier="custom", name="custom", version="1", kind="runtime", digest="a" * 64,
        location="https://example.org/source", declared=identifier, sources=[("conditions", raw)],
        scope="test", pending=["notice-and-source-duty"], custom_grants={identifier: digest})
    assert packet.components[0]["license_concluded"] == identifier
    assert packet.components[0]["source_offer_required"] is None
    assert packet.pending[0]["items"] == ["notice-and-source-duty"]
    with pytest.raises(PackageInputError, match="custom source grant differs"):
        synthesis.Packet().component(identifier="bad", name="bad", version="1", kind="runtime", digest="a" * 64,
            location="https://example.org/source", declared=identifier, sources=[("conditions", raw + b"changed")],
            scope="test", pending=[], custom_grants={identifier: digest})


def test_observed_source_claims_retain_hash_and_do_not_approve():
    packet = synthesis.Packet()
    packet.component(identifier="source", name="source", version="1", kind="wheel", digest="a" * 64,
        location="https://example.org/source", declared="MIT", sources=[("LICENSE", synthesis.MIT_GRANT.encode())],
        scope="test", pending=["license-choice-and-original-copyright", "separate-scope-review"])
    claims = [{"path": "source.py", "sha256": "b" * 64,
               "statements": [{"line": 1, "text": "Copyright 2026 Original Holder"}]}]
    synthesis.add_original_claims(packet, "source", claims)
    assert packet.components[0]["copyright_text"] == "Copyright 2026 Original Holder"
    assert packet.pending[0]["items"] == ["separate-scope-review"]
    assert packet.evidence[0]["original_source_statement_count"] == 1
    assert b'"' + b'b' * 64 + b'"' in packet.files["legal/NOTICES/source/observed-source-copyright.json"]


def test_observed_wheel_catalogue_adds_missing_exact_crate_and_refuses_conflict():
    packet = synthesis.Packet()
    component = {"name": "example", "version": "2", "purl": "pkg:cargo/example@2",
                 "bom-ref": "registry+https://github.com/rust-lang/crates.io-index#example@2",
                 "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
                 "licenses": [{"expression": "MIT OR Apache-2.0"}]}
    packet.files["nested-sboms/wheel-example/catalogue.json"] = json.dumps({"components": [component]}).encode()
    synthesis.add_observed_nested_crates(packet)
    assert packet.components[0]["version"] == "2"
    assert packet.components[0]["sha256"] == "a" * 64
    assert packet.components[0]["license_declared"] == "MIT OR Apache-2.0"
    assert packet.components[0]["license_concluded"] == "NOASSERTION"
    synthesis.add_observed_nested_crates(packet)
    assert len(packet.components) == 1
    component["hashes"][0]["content"] = "b" * 64
    packet.files["nested-sboms/wheel-example/catalogue.json"] = json.dumps({"components": [component]}).encode()
    with pytest.raises(PackageInputError, match="nested crate identity conflicts"):
        synthesis.add_observed_nested_crates(packet)


def test_adodbapi_source_delivery_is_deterministic_and_separate(monkeypatch):
    monkeypatch.setattr(synthesis, "license_atoms", lambda raw: {"LGPL-2.1-or-later"} if raw == b"full grant" else set())
    stream = io.BytesIO()
    members = {"adodbapi/license.txt": b"full grant", "adodbapi/setup.py": b"setup",
               "adodbapi/adodbapi.py": b'Copyright (C) 2002 Holder\nversion 2.1 or any later version\n__version__ = "2.6.2.0"\n',
               "unrelated.dll": b"not source"}
    with zipfile.ZipFile(stream, "w") as wheel:
        for name, raw in members.items():
            wheel.writestr(name, raw)
    first, second = synthesis.Packet(), synthesis.Packet()
    for packet in (first, second):
        synthesis.add_adodbapi(packet, stream.getvalue(), "wheel-pywin32-312", "https://example.org/wheel")
    assert first.files == second.files
    assert first.components[0]["version"] == "2.6.2.0"
    assert first.components[0]["source_offer_required"] is True
    assert first.pending[0]["items"] == ["LGPL-source-delivery-review"]
    assert "unrelated.dll" not in first.evidence[0]["members"]
    assert not any(name.endswith(".py") for name in first.files)
    assert first.files["legal/NOTICES/wheel-pywin32-312-adodbapi/001-adodbapi.py.txt"] == members["adodbapi/adodbapi.py"]


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
