"""CUA helper decisions bind both exact signed-transition revisions."""

import json
from pathlib import Path

from scripts.validate_package_inputs import sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "packaging/cua/helper-legal"
PREDECESSOR = {
    "source": "df7be3d898d57a9f2f6295733e3d76926253e984",
    "run": 36346786722,
    "receipts": {
        "x86_64": "67025e4350428247974c611fcc5a05a4fd7d2bfd65cb707a6f828f159db554c0",
        "aarch64": "87e969fa5d5d1b0e41e43dd8ce08759f4aa0f50aef424ee5cf3a56bbf727fb07",
    },
    "review_date": "2026-09-27",
    "notes": "README.md",
}
# The replacement moved to the Linux accessibility repair at 1e5f3eb. Only the
# browser broker input changed; the decision note records the delegation.
REPLACEMENT = {
    "source": "1e5f3ebf3c3f338657f6522e60f3ad56620c25c6",
    "run": 37546749658,
    "receipts": {
        "x86_64": "f6e6b02336ba5920349aef52dae9950608887b18dae166bd5ffb5c505a131c2c",
        "aarch64": "bfcd90857ec4387edb517daa748af1113a33a86251fdf37aa5990a7d33788ef6",
    },
    "review_date": "2026-10-06",
    "notes": "replacement-1e5f3eb-review.md",
}


def record(name: str) -> dict:
    return json.loads((BASE / name).read_bytes())


def assert_binding(value: dict, architecture: str, expected: dict) -> None:
    assert value["schema"] == 1
    assert value["status"] == "approved"
    assert value["version"] == "0.7.9"
    assert value["architecture"] == architecture
    assert value["source_commit"] == expected["source"]
    assert value["review_date"] == expected["review_date"]
    assert value["review_input"]["repository"] == "MONTBRAIN/vadgr-computer-use"
    assert value["review_input"]["run_id"] == expected["run"]
    assert value["review_input"]["attempt"] == 1
    assert value["review_input"]["receipt_sha256"] == expected["receipts"][architecture]
    assert value["source_offer_required"] is False
    assert value["review_notes_sha256"] == sha256_bytes((BASE / expected["notes"]).read_bytes())
    files = {row["path"]: row for row in value["review_input"]["files"]}
    assert len(files) == len(value["review_input"]["files"])
    manifest = value["input_closure"]["member_manifest"]
    assert files["broker.manifest.json"] == {
        "path": "broker.manifest.json",
        "sha256": manifest["sha256"],
        "size": manifest["size"],
    }


def test_helper_legal_records_cover_both_exact_transition_revisions():
    for architecture in ("x86_64", "aarch64"):
        predecessor = record(f"{architecture}.json")
        replacement = record(f"replacement-{architecture}.json")
        assert_binding(predecessor, architecture, PREDECESSOR)
        assert_binding(replacement, architecture, REPLACEMENT)
        assert set(predecessor["members"]) == set(replacement["members"])
        changed = [
            name for name in predecessor["members"]
            if predecessor["members"][name] != replacement["members"][name]
        ]
        assert changed == ["vadgr-cua-browser-broker.exe"]
