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
}
REPLACEMENT = {
    "source": "e4496d006b0965c0b55710af608723344154ed46",
    "run": 36347342928,
    "receipts": {
        "x86_64": "222723fc5b9118db46206a953f1fe6de4cecbe4ec4fa6546a01845f442f6dac5",
        "aarch64": "6964b41b158be42ee8374e828fae003a33c9345acc3f6cb629ec94bc9718e5a8",
    },
}


def record(name: str) -> dict:
    return json.loads((BASE / name).read_bytes())


def assert_binding(value: dict, architecture: str, expected: dict) -> None:
    assert value["schema"] == 1
    assert value["status"] == "approved"
    assert value["version"] == "0.7.9"
    assert value["architecture"] == architecture
    assert value["source_commit"] == expected["source"]
    assert value["review_date"] == "2026-09-27"
    assert value["review_input"]["repository"] == "MONTBRAIN/vadgr-computer-use"
    assert value["review_input"]["run_id"] == expected["run"]
    assert value["review_input"]["attempt"] == 1
    assert value["review_input"]["receipt_sha256"] == expected["receipts"][architecture]
    assert value["source_offer_required"] is False
    assert value["review_notes_sha256"] == sha256_bytes((BASE / "README.md").read_bytes())
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
