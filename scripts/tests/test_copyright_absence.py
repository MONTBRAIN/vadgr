"""NONE is an evidence-bound absence statement, never a copyright waiver."""

import io
import tarfile

import pytest

from scripts import copyright_absence as absence
from scripts import validate_package_inputs as package
from scripts.synthesize_windows_legal import MIT_GRANT, MIT_ZERO_GRANT


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
