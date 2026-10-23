"""Unsigned assembly observations are not candidate or signature approvals."""
import hashlib
import json
from pathlib import Path


def test_recorded_078_payload_remains_refused_and_hash_bound():
    root = Path(__file__).resolve().parents[2] / "packaging/legal-review/windows-x86_64/assembly-0.7.8"
    record = json.loads((root / "observation.json").read_bytes())
    assert record["status"] == "not-candidate-ready"
    assert record["legal_review_status"] == "draft"
    assert record["signed"] is False
    for name, key in (("payload.json", "payload_manifest_sha256"),
                      ("installed-inventory.json", "installed_inventory_sha256")):
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == record[key]
    inventory = json.loads((root / "installed-inventory.json").read_bytes())
    assert len(inventory["files"]) == record["payload_file_count"]
    assert sum(row["size"] for row in inventory["files"].values()) == record["payload_bytes"]
    for name in inventory["files"]:
        assert not name.endswith((".pdb", ".pyc", ".pyo"))
        assert not {"test", "tests", "__pycache__", "idle_test"}.intersection(name.split("/"))
    for archive in record["nested_archives"]:
        assert inventory["files"][archive["path"]]["sha256"] == archive["sha256"]
    members = [member for archive in record["nested_archives"] for member in archive["pe_members"]]
    assert len(members) == 23
    assert sum(not member["embedded_certificate_present"] for member in members) == 21
