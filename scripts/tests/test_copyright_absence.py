"""NONE is an evidence-bound absence statement, never a copyright waiver."""

import io
from pathlib import Path
import tarfile
import zipfile

import pytest

from scripts import copyright_absence as absence
from scripts import validate_package_inputs as package
from scripts.synthesize_windows_legal import MIT_GRANT, MIT_ZERO_GRANT, observed_source_zip


def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as output:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            output.addfile(member, io.BytesIO(raw))
    return stream.getvalue()


@pytest.mark.parametrize("raw, eligible", [
    (b"pub fn demo() {}\n", True),
    (b"Copyright The Authors\n", False),
    (b"copyright Alexander Huszagh.\n", False),
    (b"(C) 2024 Trifecta Tech Foundation\n", False),
    (b"quote_token_with_context!(_s @ a b (c) d e f);\n", True),
    (b"SPDX-FileCopyrightText: Contributors\n", False),
    (b"All rights reserved\n", False),
    (b"Copyright [yyyy] Someone\n", False),
    (b"\0binary", False),
    (b"\xff", False),
    (MIT_GRANT.encode(), True),
    (("MIT License\n" + MIT_GRANT).encode(), True),
    (MIT_ZERO_GRANT.encode(), True),
    (("MIT License\nCopyright Holder\n" + MIT_GRANT).encode(), False),
    (("Copyright Holder\n" + MIT_GRANT).encode(), False),
])
def test_absence_requires_all_members_decoded_and_no_ambiguous_markers(raw, eligible):
    packed = archive({"demo-1/LICENSE": raw})
    assert absence.audit_archive(packed, package.sha256_bytes(packed))["eligible_for_reviewed_NONE"] is eligible


def test_reviewed_binary_requires_exact_complete_byte_coverage(monkeypatch):
    value = b"\0tiny fully inspected record"
    record = {"format": "fixture", "size": len(value), "parts": [(0, len(value), "Every fixture byte")]}
    monkeypatch.setitem(absence.REVIEWED_BINARY_RECORDS, absence.digest(value), record)
    row = absence.inspect_member("record.o", value)
    assert row["status"] == "complete-reviewed-binary-record-no-ownership-statement"
    assert bytes.fromhex(row["reviewed_byte_ranges"][0]["hex"]) == value
    assert absence.inspect_member("record.o", value + b"changed")["status"] == "undecoded-member-needs-review"
    assert absence.inspect_member("record.o", b"\0copyright hidden")["status"] == "undecoded-member-needs-review"
    record["parts"] = [(0, 1, "Header only")]
    with pytest.raises(ValueError, match="incomplete"):
        absence.inspect_member("record.o", value)


def test_reviewed_binary_record_table_is_exact_and_has_no_uninspected_ranges():
    assert len(absence.REVIEWED_BINARY_RECORDS) == 2
    for record in absence.REVIEWED_BINARY_RECORDS.values():
        parts = record["parts"]
        assert parts[0][0] == 0 and parts[-1][1] == record["size"]
        assert all(left[1] == right[0] for left, right in zip(parts, parts[1:]))
        assert all(end > start for start, end, _ in parts)


def test_exact_conda_decoding_observation_is_rechecked_without_optional_decoder(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    source = root / ("packaging/inputs/windows-x86_64/legal/SOURCE-OFFERS/"
        "cargo-sigstore-verify-0.11.0/sigstore-verify-0.11.0.crate")
    with tarfile.open(source, mode="r:gz") as archive:
        raw = archive.extractfile("sigstore-verify-0.11.0/test_data/bundles/signed-package-2.1.0-hb0f4dca_0.conda").read()
    row = absence.inspect_reviewed_conda(raw)
    assert row["status"] == "complete-reviewed-nested-archive-no-ownership-statement"
    assert len(row["files"]) == 9
    assert all(item["status"] == "decoded-no-ownership-markers" for item in row["files"])
    with pytest.raises(ValueError, match="identity differs"):
        absence.inspect_reviewed_conda(raw + b"uninspected trailer")
    assert absence.inspect_member("changed.conda", raw + b"changed")["status"] == "undecoded-member-needs-review"
    original_loads = absence.json.loads
    def changed_observation(value):
        proof = original_loads(value)
        proof["inspection"] = "Unsupported replacement conclusion"
        return proof
    monkeypatch.setattr(absence.json, "loads", changed_observation)
    with pytest.raises(ValueError, match="decoding observation differs"):
        absence.inspect_reviewed_conda(raw)


def test_none_proof_is_recomputed_from_exact_included_archive():
    raw = archive({"demo-1/src/lib.rs": b"pub fn demo() {}\n"})
    digest = package.sha256_bytes(raw)
    proof = absence.audit_archive(raw, digest)
    source = "legal/SOURCE-OFFERS/demo/demo.crate"
    audit = "legal/SOURCE-OFFERS/demo/copyright-absence.json"
    component = {"copyright_text": "NONE", "sha256": digest,
                 "source_offer_files": [{"path": source, "sha256": digest},
                                        {"path": audit, "sha256": package.sha256_bytes(package.canonical_json(proof))}]}
    files = {source: raw, audit: package.canonical_json(proof)}
    package.validate_copyright_absence({"components": [component]}, files)
    with pytest.raises(package.PackageInputError, match="evidence differs"):
        package.validate_copyright_absence({"components": [component]}, {**files, audit: b"{}\n"})
    with pytest.raises(package.PackageInputError, match="source differs"):
        package.validate_copyright_absence({"components": [component]}, {**files, source: raw + b"changed"})


def test_false_positive_regex_negative_does_not_qualify():
    # The old statement detector required (c), a year or the copyright symbol.
    raw = archive({"demo-1/NOTICE": b"Copyright Contributors to Project\n"})
    proof = absence.audit_archive(raw, package.sha256_bytes(raw))
    assert proof["eligible_for_reviewed_NONE"] is False
    assert proof["files"][0]["status"] == "ambiguous-ownership-marker"


def test_reviewed_generic_document_requires_complete_exact_text(monkeypatch):
    text = b"Do not engage in copyright violation or misattribution."
    digest = absence.digest(b" ".join(text.split()))
    monkeypatch.setitem(absence.REVIEWED_DOCUMENTS, digest, "test-reviewed-compliance-document")
    for suffix, eligible in ((b"", True), (b"\nCopyright Actual Owner", False), (b" modified", False)):
        packed = archive({"demo-1/CODE.md": text + suffix})
        proof = absence.audit_archive(packed, absence.digest(packed))
        assert proof["eligible_for_reviewed_NONE"] is eligible
        if eligible:
            assert proof["files"][0]["status"] == "complete-reviewed-document-no-ownership-statement"


def tree_digest(members):
    return package.sha256_bytes(package.canonical_json({name: package.sha256_bytes(raw) for name, raw in members.items()}))


def test_observed_tree_absence_rejects_omitted_members_and_recomputes_exact_zip():
    members = {"LICENSE": MIT_GRANT.encode(), "code.py": b"value = 1\n"}
    raw = observed_source_zip(members)
    expected = tree_digest(members)
    proof = absence.audit_source_tree_zip(raw, expected)
    assert proof["eligible_for_reviewed_NONE"] is True
    assert proof["component_tree_sha256"] == expected
    assert observed_source_zip(dict(reversed(list(members.items())))) == raw
    source, audit = "legal/SOURCE-OFFERS/demo/observed-source.zip", "legal/SOURCE-OFFERS/demo/copyright-absence.json"
    component = {"kind": "runtime", "copyright_text": "NONE", "sha256": expected,
        "source_offer_files": [{"path": source, "sha256": package.sha256_bytes(raw)},
            {"path": audit, "sha256": package.sha256_bytes(package.canonical_json(proof))}]}
    files = {source: raw, audit: package.canonical_json(proof)}
    package.validate_copyright_absence({"components": [component]}, files)
    with pytest.raises(ValueError, match="tree identity differs"):
        absence.audit_source_tree_zip(observed_source_zip({"LICENSE": members["LICENSE"]}), expected)
    with pytest.raises(package.PackageInputError, match="source differs"):
        package.validate_copyright_absence({"components": [component]}, {**files, source: raw + b"changed"})


@pytest.mark.parametrize("value", [b"Copyright Original Owner", b"\0opaque"])
def test_observed_tree_absence_does_not_discard_binary_or_original_claims(value):
    members = {"data": value}
    assert not absence.audit_source_tree_zip(observed_source_zip(members), tree_digest(members))["eligible_for_reviewed_NONE"]


def test_observed_tree_absence_rejects_archive_comment():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("file", b"text")
        archive.comment = b"Copyright Original Owner"
    with pytest.raises(ValueError, match="uninspected"):
        absence.audit_source_tree_zip(output.getvalue(), tree_digest({"file": b"text"}))


def test_observed_tree_absence_rejects_uninspected_trailing_zip_bytes():
    members = {"file": b"text"}
    raw = observed_source_zip(members) + b"Copyright Original Owner"
    with pytest.raises(ValueError, match="uninspected"):
        absence.audit_source_tree_zip(raw, tree_digest(members))
