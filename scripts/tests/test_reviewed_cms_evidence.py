"""Exact CMS decoding narrows evidence gaps without blessing encrypted content."""

import io
import tarfile
from pathlib import Path

import pytest

from scripts import copyright_absence as absence
from scripts import reviewed_cms_evidence as cms


@pytest.fixture
def source():
    root = Path(__file__).resolve().parents[2]
    raw = (root / "scripts/tests/fixtures/cms-0.2.3.crate").read_bytes()
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        files = {row.name: archive.extractfile(row).read() for row in archive if row.isfile()}
    return raw, files


@pytest.mark.parametrize("name", cms.REVIEWED)
def test_exact_cms_records_cover_every_byte_and_keep_ciphertext_unresolved(source, name):
    _, files = source
    raw = files[cms.PREFIX + "examples/" + name]
    plaintext = files[cms.PREFIX + "examples/data.txt"]
    result = cms.inspect_cms(name, raw, plaintext, absence.MARKERS)
    fields = result["reviewed_byte_ranges"]
    assert bytes.fromhex("".join(row["hex"] for row in fields)) == raw
    assert all(left["end_exclusive"] == right["offset"] for left, right in zip(fields, fields[1:]))
    if name == "encrypted_data.bin":
        assert result["status"] == "undecoded-member-needs-review"
        assert result["unresolved_encrypted_content"]["size"] == 448
        assert result["source_plaintext"]["binding"] == "not-established"
        assert "plaintext_verified" not in result
    else:
        assert result["plaintext_verified"] is True
        assert result["source_plaintext"]["binding"] == "exact-decoded-equality"
    for changed in (raw[:-1], raw + b"uninspected", raw[:-1] + bytes([raw[-1] ^ 1])):
        with pytest.raises(ValueError, match="identity differs"):
            cms.inspect_cms(name, changed, plaintext, absence.MARKERS)
    with pytest.raises(ValueError, match="identity differs"):
        cms.inspect_cms(name, raw, plaintext + b"Copyright Owner", absence.MARKERS)


def test_cms_partial_decoding_cannot_approve_whole_archive_absence(source):
    raw, _ = source
    proof = absence.audit_archive(raw, absence.digest(raw))
    assert proof["eligible_for_reviewed_NONE"] is False
    complete = [row for row in proof["files"] if row.get("plaintext_verified")]
    assert len(complete) == 2
    encrypted = next(row for row in proof["files"] if row["path"].endswith("/encrypted_data.bin"))
    assert encrypted["status"] == "undecoded-member-needs-review"
    assert encrypted["unresolved_encrypted_content"]["offset"] == 76


def test_cms_source_binding_rejects_replaced_test_context(source):
    raw, retained = source
    rows = absence.audit_archive(raw, absence.digest(raw))["files"]
    retained[cms.PREFIX + "encrypted_data.rs"] += b"changed source context"
    with pytest.raises(ValueError, match="context differs"):
        cms.inspect_cms_fixtures(rows, retained, absence.MARKERS)


@pytest.mark.parametrize("name", cms.KEYS)
def test_exact_mathematical_key_fields_have_no_uninspected_attribute_or_trailer(source, name):
    _, files = source
    raw = files[cms.PREFIX + "examples/" + name]
    result = cms.inspect_key(name, raw)
    assert result["status"] == "complete-reviewed-binary-record-no-ownership-statement"
    assert bytes.fromhex("".join(row["hex"] for row in result["reviewed_byte_ranges"])) == raw
    for changed in (raw[:-1], raw + b"Copyright Original Owner", bytes([raw[0] ^ 1]) + raw[1:]):
        with pytest.raises(ValueError, match="identity differs"):
            cms.inspect_key(name, changed)


def test_misnamed_ec_fixture_is_a_fully_decoded_certificate_not_an_owner_statement(source):
    _, files = source
    raw = files[cms.PREFIX + "examples/ec384-ee-key.der"]
    row = absence.inspect_member("ec384-ee-key.der", raw)
    assert row["status"] == "complete-reviewed-binary-record-no-ownership-statement"
    parts = row["reviewed_byte_ranges"]
    assert bytes.fromhex("".join(item["hex"] for item in parts)) == raw
    assert any("ECDSA signature" in item["interpretation"] for item in parts)
    assert any(item.get("decoded_text") == "Red Hound" for item in parts)
    assert "not copyright declarations" in row["meaning"]
    assert absence.inspect_member("changed.der", raw + b"uninspected")["status"] == "undecoded-member-needs-review"


@pytest.mark.parametrize("name", ["GoodCACert.crt", "ValidCertificatePathTest1EE.crt", "rsa_cert.der", "sceptest_csr.der"])
def test_exact_certificate_and_request_fields_are_complete_not_identity_to_owner_inferences(source, name):
    _, files = source
    raw = files[cms.PREFIX + "examples/" + name]
    row = absence.inspect_member(name, raw)
    assert row["status"] == "complete-reviewed-binary-record-no-ownership-statement"
    parts = row["reviewed_byte_ranges"]
    assert bytes.fromhex("".join(item["hex"] for item in parts)) == raw
    assert any("decoded_text" in item for item in parts)
    assert all(left["end_exclusive"] == right["offset"] for left, right in zip(parts, parts[1:]))
    assert "not copyright declarations" in row["meaning"]
