#!/usr/bin/env python3
"""Apply an explicit owner decision to an unchanged, hash-bound Linux packet.

The caller supplies the independently approved manifest digest. This command
checks its exact subject; it cannot authenticate or create the owner's decision.
It grants no signing, publication or protected candidate authorization.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import stat
import sys

if __package__:
    from scripts.validate_package_inputs import (
        CLOSURES, PackageInputError, canonical_json, parse_json, read_owned,
        relative_path, render_rtf, require, sha256_bytes, valid_hash, validate_package_inputs,
    )
else:
    from validate_package_inputs import (
        CLOSURES, PackageInputError, canonical_json, parse_json, read_owned,
        relative_path, render_rtf, require, sha256_bytes, valid_hash, validate_package_inputs,
    )


def finalize_packet(*, input_root: Path, manifest_path: Path,
                    approved_manifest_sha256: str, source_root: Path,
                    payload_manifest: Path, output_root: Path,
                    approval_date: str) -> dict:
    require(valid_hash(approved_manifest_sha256), "approved manifest digest required")
    require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", approval_date) is not None,
            "approval date required")
    require(not output_root.exists() and not output_root.is_symlink()
            and output_root.parent.is_dir(), "new output directory required")
    for root in (input_root, output_root.parent):
        for ancestor in (root, *root.parents):
            require(not ancestor.is_symlink(), "unsafe packet path")
    manifest_raw = read_owned(manifest_path.parent, manifest_path.name)
    require(sha256_bytes(manifest_raw) == approved_manifest_sha256,
            "approved manifest differs")
    manifest = parse_json(manifest_raw)
    require(manifest["schema"] == 1
            and manifest["status"] == "awaiting-owner-exact-packet-approval"
            and manifest["version"] == "0.5.0"
            and manifest["target"] in ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu"),
            "reviewed Linux identity differs")
    members = manifest["files"]
    require(isinstance(members, dict) and members, "reviewed members required")
    observed = set()
    for path in input_root.rglob("*"):
        metadata = path.lstat()
        require(stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode),
                "unsafe packet member")
        if stat.S_ISREG(metadata.st_mode):
            observed.add(path.relative_to(input_root).as_posix())
    require(observed == set(members), "reviewed member set differs")
    files = {}
    for name, record in members.items():
        relative_path(name)
        raw = read_owned(input_root, name)
        require(set(record) == {"bytes", "mode", "sha256"}
                and len(raw) == record["bytes"]
                and sha256_bytes(raw) == record["sha256"]
                and stat.S_IMODE((input_root / name).stat().st_mode) == record["mode"],
                "reviewed member differs")
        files[name] = raw
    inventory = parse_json(files["package-input-inventory.json"])
    draft_raw = files["package-input-review.json"]
    review = parse_json(draft_raw)
    require(review["status"] == "draft" and review["synthetic"] is False
            and review["closures"] == dict.fromkeys(CLOSURES, False), "draft review differs")
    require(set(files) == set(review["files"]) | {
        "package-input-inventory.json", "package-input-review.json", "REVIEW-PENDING.json"},
        "unexpected packet metadata")
    require(manifest["inventory_sha256"] == sha256_bytes(files["package-input-inventory.json"])
            and manifest["review_sha256"] == sha256_bytes(draft_raw)
            and manifest["terms_sha256"] == inventory["terms_sha256"]
            and manifest["target"] == inventory["target"]
            and manifest["components"] == len(inventory["components"]), "manifest binding differs")
    derived = []
    rtf = "legal/TERMS.rtf"
    rendered = render_rtf(files["legal/TERMS.txt"].decode("utf-8"))
    if rtf not in files:
        files[rtf] = rendered
        review["files"][rtf] = sha256_bytes(rendered)
        derived.append({"path": rtf, "operation": "add", "sha256": sha256_bytes(rendered),
                        "reason": "Canonical rendering of the unchanged approved terms."})
    else:
        require(files[rtf] == rendered, "reviewed terms rendering differs")
    inventory_name = "package-input-inventory.json"
    if inventory_name in review["files"]:
        require(review["files"][inventory_name] == manifest["inventory_sha256"],
                "reviewed inventory digest differs")
        del review["files"][inventory_name]
    review.update(status="approved", closures=dict.fromkeys(CLOSURES, True))
    approved_raw = canonical_json(review)
    derived.extend([
        {"path": "package-input-review.json", "operation": "replace",
         "before_sha256": manifest["review_sha256"], "sha256": sha256_bytes(approved_raw),
         "reason": "Apply owner approval and canonical legal-file membership; inventory is bound separately."},
        {"path": "REVIEW-PENDING.json", "operation": "omit",
         "before_sha256": members["REVIEW-PENDING.json"]["sha256"],
         "reason": "Preserve the original pending record only in the unchanged approved draft."},
    ])
    output_root.mkdir(mode=0o700)
    for name, raw in sorted(files.items()):
        if name == "REVIEW-PENDING.json":
            continue
        destination = output_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(approved_raw if name == "package-input-review.json" else raw)
        destination.chmod(members[name]["mode"] if name in members else 0o644)
    try:
        result = validate_package_inputs(output_root, source_root, "0.5.0", inventory["target"],
                                         payload_manifest=payload_manifest)
    except Exception:
        # A failed derived copy stays available for diagnosis, but remains a draft.
        (output_root / "package-input-review.json").write_bytes(draft_raw)
        raise
    receipt = {
        "schema": 1, "status": "owner-approved-exact-packet", "approval_date": approval_date,
        "approved_manifest_sha256": approved_manifest_sha256,
        "authority": "Explicit publisher-owner approval of the exact packet.",
        "source_commit": manifest["source_commit"], "target": inventory["target"],
        "inventory_sha256": manifest["inventory_sha256"],
        "draft_review_sha256": manifest["review_sha256"],
        "approved_review_sha256": sha256_bytes(approved_raw),
        "unchanged_terms_inventory_licenses_notices_and_sources": True,
        "derived_changes": derived,
        "derived_output_separately_owner_reviewed": False, "signing_authorized": False,
        "candidate_authorized": False, "publishable": False,
    }
    with (output_root / "owner-approved-packet.json").open("xb") as stream:
        stream.write(canonical_json(receipt))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("input-root", "manifest-path", "source-root", "payload-manifest", "output-root"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--approved-manifest-sha256", required=True)
    parser.add_argument("--approval-date", required=True)
    try:
        result = finalize_packet(**vars(parser.parse_args()))
        print(canonical_json(result).decode(), end="")
        return 0
    except (PackageInputError, OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        print(f"Linux packet finalization failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
