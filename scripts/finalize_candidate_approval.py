#!/usr/bin/env python3
"""Bind the exact reviewed Windows package inputs for protected authorization."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_package_inputs import parse_json, read_owned, require

TARGETS = {"x64": "x86_64", "arm64": "aarch64"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target(root: Path, architecture: str) -> dict:
    package = root / "packaging/inputs" / ("windows-" + architecture)
    review = parse_json(read_owned(package, "package-input-review.json"))
    require(review.get("status") == "approved" and review.get("version") == "0.5.0"
            and review.get("terms_version") == "1.0"
            and review.get("target") == architecture + "-pc-windows-msvc"
            and isinstance(review.get("files"), dict), "package review scope differs")
    legal = {}
    selected = [name for name in review["files"]
                if name == "README-OFFLINE.txt" or name.startswith("legal/")]
    require("legal/TERMS.rtf" in selected and "README-OFFLINE.txt" in selected,
            "required legal files are absent")
    for name in sorted(selected):
        raw = read_owned(package, name)
        require(digest(raw) == review["files"][name], "reviewed legal file differs")
        legal["payload/" + name] = digest(raw)
    legal["TERMS.rtf"] = legal["payload/legal/TERMS.rtf"]
    helper_root = root / "packaging/cua/helper-signing"
    for suffix in (".json", "-outer.json", "-outer-review.json", "-predecessors.json"):
        name = architecture + suffix
        legal["packaging/cua/helper-signing/" + name] = digest(read_owned(helper_root, name))
    sbom = read_owned(package, "sbom/vadgr-0.5.0.spdx.json")
    inventory = read_owned(package, "package-input-inventory.json")
    require(digest(sbom) == review["files"]["sbom/vadgr-0.5.0.spdx.json"]
            and digest(inventory) == review["inventory_sha256"],
            "reviewed SBOM or inventory differs")
    return {
        "generator_sha256": digest(read_owned(root / "scripts", "generate_legal_bundle.py")),
        "inventory_sha256": digest(inventory),
        "legal_hashes": legal,
        "sbom_sha256": digest(sbom),
    }


def build(root: Path) -> bytes:
    value = {"schema": 1, "terms_version": "1.0", "version": "0.5.0",
             "targets": {name: target(root, architecture)
                         for name, architecture in TARGETS.items()}}
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = build(args.root.resolve())
    if args.check:
        require(read_owned(args.out.parent, args.out.name) == expected,
                "candidate approval record differs")
    else:
        require(not args.out.exists(), "candidate approval record already exists")
        with args.out.open("xb") as stream:
            stream.write(expected)
    print("Verified exact Windows candidate inputs. No protected operation was authorized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
