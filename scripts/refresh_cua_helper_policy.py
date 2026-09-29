#!/usr/bin/env python3
"""Rebuild helper signing policies from exact approved replacement records."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.candidate import cua_helpers
from scripts.validate_package_inputs import parse_json, read_owned, require

ARCHITECTURES = ("x86_64", "aarch64")
HOST = "vadgr-cua-host.exe"
RELAY = "relay.exe"


def canonical(value: dict) -> bytes:
    return cua_helpers.canonical(value)


def rebuild(root: Path, architecture: str) -> bytes:
    policy_path = root / "packaging/cua/helper-signing" / f"{architecture}.json"
    review_path = root / "packaging/cua/helper-legal" / f"replacement-{architecture}.json"
    policy_raw = read_owned(policy_path.parent, policy_path.name)
    review_raw = read_owned(review_path.parent, review_path.name)
    policy, review = parse_json(policy_raw), parse_json(review_raw)
    require(policy.get("schema") == 1 and set(policy) == {"schema", "files"},
            "helper policy schema differs")
    require(review.get("schema") == 1 and review.get("status") == "approved"
            and review.get("architecture") == architecture
            and review.get("version") == "0.7.9", "replacement review scope differs")
    members = review.get("members")
    require(isinstance(members, dict) and HOST in members, "replacement members differ")
    expected = {(RELAY if name == HOST else name) for name in members}
    require(set(policy["files"]) == expected, "helper policy membership differs")
    approval = hashlib.sha256(review_raw).hexdigest()
    for source_name, reviewed in members.items():
        name = RELAY if source_name == HOST else source_name
        row = policy["files"][name]
        require(row.get("trust_class") == reviewed.get("trust_class"),
                "helper trust class differs from approved review")
        row["input_sha256"] = reviewed["input_sha256"]
        if row["trust_class"] == "data":
            require(all(row.get(field) is None for field in row if field not in {
                "input_sha256", "trust_class"}), "data helper carries signature policy")
        else:
            require(all(isinstance(row.get(field), str) and row[field] for field in (
                "signer", "signer_policy_sha256", "certificate_sha256",
                "chain_root_sha256", "digest_algorithm", "timestamp_algorithm")),
                "native helper signature policy is incomplete")
            row["legal_approval_sha256"] = approval
    return canonical(policy)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--architecture", choices=ARCHITECTURES, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    expected = rebuild(root, args.architecture)
    policy = root / "packaging/cua/helper-signing" / f"{args.architecture}.json"
    require(args.check != (args.out is not None), "select exactly one output mode")
    if args.check:
        require(read_owned(policy.parent, policy.name) == expected,
                "helper policy differs from approved replacement record")
    else:
        require(not args.out.exists(), "output already exists")
        args.out.write_bytes(expected)
    print(f"Verified {args.architecture} replacement helper policy. No signing was requested.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
