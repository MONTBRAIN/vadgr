"""Synthetic packet fixtures do not confer publisher approval."""

import stat
import re

import pytest

from scripts import finalize_linux_package_inputs as finalizer
from scripts.tests.test_validate_package_inputs import make_approved_fixture
from scripts.validate_package_inputs import (
    CLOSURES, PackageInputError, canonical_json, parse_json, render_rtf, sha256_bytes,
)


@pytest.fixture
def packet(tmp_path):
    draft, source = tmp_path / "draft", tmp_path / "source"
    inventory, review, payload = make_approved_fixture(
        draft, source, target="x86_64-unknown-linux-gnu",
        payload_manifest=tmp_path / "payload/payload.json")
    review.update(status="draft", closures=dict.fromkeys(CLOSURES, False))
    (draft / "package-input-review.json").write_bytes(canonical_json(review))
    (draft / "REVIEW-PENDING.json").write_bytes(canonical_json({"status": "fixture"}))
    files = {path.relative_to(draft).as_posix(): {
        "bytes": path.stat().st_size, "mode": stat.S_IMODE(path.stat().st_mode),
        "sha256": sha256_bytes(path.read_bytes()),
    } for path in draft.rglob("*") if path.is_file()}
    manifest = {"schema": 1, "status": "awaiting-owner-exact-packet-approval",
                "version": "0.5.0", "target": inventory["target"], "files": files,
                "source_commit": "a" * 40, "components": len(inventory["components"]),
                "terms_sha256": inventory["terms_sha256"],
                "inventory_sha256": files["package-input-inventory.json"]["sha256"],
                "review_sha256": files["package-input-review.json"]["sha256"]}
    manifest_path = tmp_path / "packet-manifest.json"
    manifest_path.write_bytes(canonical_json(manifest))
    return dict(input_root=draft, manifest_path=manifest_path,
                approved_manifest_sha256=sha256_bytes(manifest_path.read_bytes()),
                source_root=source, payload_manifest=payload,
                output_root=tmp_path / "approved", approval_date="2026-09-30")


def test_exact_packet_finalization_preserves_all_reviewed_content(packet):
    before = {p.relative_to(packet["input_root"]): p.read_bytes()
              for p in packet["input_root"].rglob("*") if p.is_file()}
    result = finalizer.finalize_packet(**packet)
    assert result["status"] == "approved"
    assert result["scope"] == "assembled-payload"
    for name, raw in before.items():
        assert (packet["input_root"] / name).read_bytes() == raw
        if str(name) not in ("REVIEW-PENDING.json", "package-input-review.json"):
            assert (packet["output_root"] / name).read_bytes() == raw
    assert not (packet["output_root"] / "REVIEW-PENDING.json").exists()
    receipt = (packet["output_root"] / "owner-approved-packet.json").read_bytes()
    assert packet["approved_manifest_sha256"].encode() in receipt
    assert str(packet["input_root"]).encode() not in receipt


@pytest.mark.parametrize("change", ["manifest", "member", "extra", "link"])
def test_changed_approved_subject_is_rejected_before_output(packet, change):
    root = packet["input_root"]
    if change == "manifest":
        packet["approved_manifest_sha256"] = "0" * 64
    elif change == "member":
        (root / "legal/TERMS.txt").write_bytes(b"changed")
    elif change == "extra":
        (root / "unexpected.txt").write_bytes(b"extra")
    else:
        path = root / "legal/TERMS.txt"
        original = root.parent / "original-terms.txt"
        path.rename(original)
        path.symlink_to(original)
    with pytest.raises((PackageInputError, OSError)):
        finalizer.finalize_packet(**packet)
    assert not packet["output_root"].exists()


def test_changed_approved_member_mode_is_rejected_before_output(packet):
    path = packet["input_root"] / "legal/TERMS.txt"
    original_mode = stat.S_IMODE(path.stat().st_mode)
    try:
        # Read-only changes are observable on Windows as well as POSIX.
        path.chmod(0o444)
        assert stat.S_IMODE(path.stat().st_mode) != original_mode
        with pytest.raises(PackageInputError, match="reviewed member differs"):
            finalizer.finalize_packet(**packet)
        assert not packet["output_root"].exists()
    finally:
        path.chmod(original_mode)


def test_changed_payload_does_not_leave_approved_review(packet):
    packet["payload_manifest"].write_bytes(b"{}\n")
    with pytest.raises(PackageInputError):
        finalizer.finalize_packet(**packet)
    assert (packet["output_root"] / "package-input-review.json").read_bytes() == (
        packet["input_root"] / "package-input-review.json").read_bytes()
    assert not (packet["output_root"] / "owner-approved-packet.json").exists()


def test_existing_output_is_never_overwritten(packet):
    packet["output_root"].mkdir()
    sentinel = packet["output_root"] / "owned.txt"
    sentinel.write_bytes(b"preserve")
    with pytest.raises(PackageInputError):
        finalizer.finalize_packet(**packet)
    assert sentinel.read_bytes() == b"preserve"


def test_missing_rendering_and_inventory_membership_are_mechanical_derivations(packet):
    root = packet["input_root"]
    rtf = root / "legal/TERMS.rtf"
    rtf.unlink()
    review_path = root / "package-input-review.json"
    review = parse_json(review_path.read_bytes())
    del review["files"]["legal/TERMS.rtf"]
    review["files"]["package-input-inventory.json"] = review["inventory_sha256"]
    review_path.write_bytes(canonical_json(review))
    manifest = parse_json(packet["manifest_path"].read_bytes())
    del manifest["files"]["legal/TERMS.rtf"]
    manifest["files"]["package-input-review.json"].update(
        bytes=review_path.stat().st_size, sha256=sha256_bytes(review_path.read_bytes()))
    manifest["review_sha256"] = sha256_bytes(review_path.read_bytes())
    packet["manifest_path"].write_bytes(canonical_json(manifest))
    packet["approved_manifest_sha256"] = sha256_bytes(packet["manifest_path"].read_bytes())
    finalizer.finalize_packet(**packet)
    output = packet["output_root"]
    terms = (root / "legal/TERMS.txt").read_bytes()
    assert (output / "legal/TERMS.txt").read_bytes() == terms
    assert (output / "legal/TERMS.rtf").read_bytes() == render_rtf(terms.decode())
    finalized = parse_json((output / "package-input-review.json").read_bytes())
    assert "package-input-inventory.json" not in finalized["files"]
    assert finalized["files"]["legal/TERMS.rtf"] == sha256_bytes(render_rtf(terms.decode()))
    receipt = parse_json((output / "owner-approved-packet.json").read_bytes())
    assert not receipt["derived_output_separately_owner_reviewed"]
    assert receipt["derived_changes"][0]["path"] == "legal/TERMS.rtf"
    assert not rtf.exists()


@pytest.mark.parametrize("text", ["Terms {accept} \\ café 中文 😀\r\n\tEnd.\n", "Plain terms\n"])
def test_canonical_rendering_preserves_plain_text(text):
    rendered = render_rtf(text).decode("ascii")
    header = r"{\rtf1\ansi\deff0\uc1 "
    assert rendered.startswith(header) and rendered.endswith("}\n")
    body = rendered[len(header):-2]
    tokens = re.findall(r"\\u-?[0-9]+\?|\\par\n|\\tab |\\[\\{}]|[^\\]+", body)
    assert "".join(tokens) == body
    decoded = []
    for token in tokens:
        if token.startswith(r"\u"):
            decoded.append(chr(int(token[2:-1]) % 65536))
        elif token == "\\par\n":
            decoded.append("\n")
        elif token == "\\tab ":
            decoded.append("\t")
        elif token.startswith("\\"):
            decoded.append(token[1:])
        else:
            decoded.append(token)
    assert "".join(decoded).encode("utf-16-le", "surrogatepass").decode("utf-16-le") == text
