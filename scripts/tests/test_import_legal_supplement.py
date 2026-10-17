"""Supplement import must preserve bytes without creating legal approval."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import import_legal_supplement as supplement


def test_verified_source_is_verbatim_and_cannot_escape(tmp_path):
    content = b"Original copyright\r\nOriginal terms  \r\n"
    (tmp_path / "LICENSE").write_bytes(content)
    record = {"path": "LICENSE", "sha256": hashlib.sha256(content).hexdigest()}
    assert supplement.read_verified(tmp_path, record) == content
    for bad in ("../LICENSE", "C:/LICENSE", "dir/../LICENSE"):
        with pytest.raises(ValueError):
            supplement.read_verified(tmp_path, dict(record, path=bad))
    (tmp_path / "LICENSE").write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest"):
        supplement.read_verified(tmp_path, record)


def sample_packet():
    return {"schema": 1, "status": "incomplete", "review_status": "unreviewed",
            "source_collections": [], "groups": {"nested_wheels": {"status": "unreviewed",
                "registry_components": [{"license_concluded": None, "review_status": "unreviewed"}]}},
            "files": [], "outstanding_review": ["Final payload mapping remains unresolved."]}


@pytest.mark.parametrize("edit", [
    lambda value: value.update(status="approved"),
    lambda value: value.update(review_status="approved"),
    lambda value: value["groups"]["nested_wheels"]["registry_components"][0].update(license_concluded="MIT"),
    lambda value: value["groups"]["nested_wheels"].update(closures={"third_party_duties": True}),
])
def test_supplement_cannot_claim_approval(edit):
    packet = sample_packet()
    edit(packet)
    with pytest.raises(ValueError, match="unreviewed"):
        supplement.validate_unreviewed(packet)


def test_target_origin_digest_is_bound_to_existing_sbom(tmp_path):
    path = tmp_path / "packaging/legal-review/windows-x86_64/sources/wheel/example.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{}")
    origin = {"target": "windows-x86_64", "sbom": path.relative_to(tmp_path).as_posix(),
              "sbom_sha256": hashlib.sha256(b"{}").hexdigest()}
    supplement.validate_origins(tmp_path, {"origins": [origin]})
    changed = copy.deepcopy(origin)
    changed["sbom_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        supplement.validate_origins(tmp_path, {"origins": [changed]})


def test_registry_claim_must_match_the_original_sbom(tmp_path):
    path = tmp_path / "packaging/legal-review/windows-x86_64/sources/wheel/example.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"components": [{"name": "example", "version": "1.0",
        "hashes": [{"alg": "SHA-256", "content": "a" * 64}], "licenses": [{"expression": "MIT"}]}]}))
    origin = {"target": "windows-x86_64", "sbom": path.relative_to(tmp_path).as_posix(),
              "sbom_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    claim = {"name": "example", "version": "1.0", "sha256": "b" * 64,
             "license_declared": [{"expression": "MIT"}], "origins": [origin]}
    with pytest.raises(ValueError, match="SBOM component"):
        supplement.validate_origins(tmp_path, claim)


def test_evidence_copy_detects_portable_path_collision(tmp_path):
    files = {}
    supplement.add_file(files, "sources/LICENSE", b"original")
    with pytest.raises(ValueError, match="collision"):
        supplement.add_file(files, "sources/license", b"different")


def test_archive_mismatch_blocks_import_before_output(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "archives").mkdir()
    (source / "archives/example-1.0.crate").write_bytes(b"changed")
    entry = {"name": "example", "version": "1.0", "sha256": "0" * 64,
             "source_files": [], "license_concluded": None, "review_status": "unreviewed"}
    with pytest.raises(ValueError, match="digest"):
        supplement.verify_component_archives(source, "nested_wheels", [entry])


def test_tracked_supplement_has_exact_files_and_unresolved_status():
    repo = Path(__file__).resolve().parents[2]
    root = repo / "packaging/legal-review/supplement"
    packet = supplement.verify_packet(root, repo)
    assert packet["status"] == "incomplete"
    assert len(packet["groups"]["nested_wheels"]["registry_components"]) == 143
    assert len(packet["groups"]["native_sources"]["components"]) == 14
    assert len(packet["groups"]["python"]["artifacts"]) == 2
