#!/usr/bin/env python3
"""Build the deterministic public release manifest from final artifact bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib


ARTIFACTS = {
    "Vadgr-0.5.0-windows-x64-setup.exe": ("windows-x86_64", "burn", "authenticode"),
    "Vadgr-0.5.0-windows-arm64-setup.exe": ("windows-aarch64", "burn", "authenticode"),
    "Vadgr-0.5.0-macos-x86_64.pkg": ("macos-x86_64", "pkg", "developer-id-notarized"),
    "Vadgr-0.5.0-macos-arm64.pkg": ("macos-aarch64", "pkg", "developer-id-notarized"),
    "Vadgr-0.5.0-linux-x86_64-installer.AppImage": ("linux-x86_64", "appimage", "keyless-manifest"),
    "Vadgr-0.5.0-linux-aarch64-installer.AppImage": ("linux-aarch64", "appimage", "keyless-manifest"),
    "Vadgr-0.5.0-wsl-x86_64.tar.gz": ("wsl-x86_64", "tar.gz", "keyless-manifest"),
    "Vadgr-0.5.0-wsl-aarch64.tar.gz": ("wsl-aarch64", "tar.gz", "keyless-manifest"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path, prefix: str) -> dict[str, str]:
    if not root.is_dir() or root.is_symlink():
        raise SystemExit(f"missing or unsafe {prefix} directory")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SystemExit(f"symlink in {prefix} inventory: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SystemExit(f"special file in {prefix} inventory: {path}")
        relative = path.relative_to(root)
        if any(part in (".", "..") or "\\" in part for part in relative.parts):
            raise SystemExit(f"unsafe {prefix} inventory path: {path}")
        result[f"{prefix}/{relative.as_posix()}"] = sha256(path)
    if not result:
        raise SystemExit(f"empty {prefix} inventory")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--terms-version", required=True)
    parser.add_argument("--terms", type=Path, required=True)
    parser.add_argument("--legal-root", type=Path, required=True)
    parser.add_argument("--sbom-root", type=Path, required=True)
    parser.add_argument("--pins", type=Path, default=Path("packaging/cua/pins.toml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise SystemExit("source commit must be a lowercase full SHA")
    pins = tomllib.loads(args.pins.read_text(encoding="utf-8"))
    rows = []
    for name, (target, kind, signature) in ARTIFACTS.items():
        matches = list(args.artifacts.rglob(name))
        if len(matches) != 1:
            raise SystemExit(f"expected exactly one {name}, found {len(matches)}")
        path = matches[0]
        rows.append(
            {
                "name": name,
                "target": target,
                "kind": kind,
                "size": path.stat().st_size,
                "sha256": sha256(path),
                "native_signature": signature,
            }
        )
    legal_hashes = inventory(args.legal_root, "legal")
    if legal_hashes.get("legal/TERMS.txt") != sha256(args.terms):
        raise SystemExit("the terms checksum must match legal/TERMS.txt")
    manifest = {
        "schema": 1,
        "product": "vadgr",
        "version": "0.5.0",
        "release_sequence": 500,
        "tag": "v0.5.0",
        "source_commit": args.source_commit,
        "terms_version": args.terms_version,
        "terms_sha256": sha256(args.terms),
        "cua_version": pins["cua"],
        "python_version": pins["python"],
        "legal_hashes": legal_hashes,
        "sbom_hashes": inventory(args.sbom_root, "sbom"),
        "artifacts": rows,
    }
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
