#!/usr/bin/env python3
"""Create a draft legal bundle from explicit local inputs. This command cannot approve it."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import unicodedata

from validate_package_inputs import (
    CLOSURES, REQUIRED_FILES, PackageInputError, aggregate_files, build_sbom, canonical_json,
    expected_legal_files, parse_json, relative_path, render_rtf, require,
    sha256_bytes, valid_hash, validate_inventory,
)


def _unlinked_path(path: Path) -> Path:
    path = path.absolute()
    for ancestor in (*reversed(path.parents), path):
        metadata = ancestor.lstat()
        require(not stat.S_ISLNK(metadata.st_mode) and not (
            getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ), "unsafe path")
    return path


def _read_regular(path: Path) -> bytes:
    path = _unlinked_path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "unsafe file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
                and (before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino), "unsafe file")
        result = source.read()
        after = os.fstat(source.fileno())
        require((opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns, opened.st_nlink)
                == (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink), "changed input")
    return result


def _new_output_root(path: Path) -> Path:
    path = path.absolute()
    parent = _unlinked_path(path.parent)
    metadata = parent.stat()
    require(stat.S_ISDIR(metadata.st_mode), "unsafe output")
    if hasattr(os, "geteuid"):
        require(metadata.st_uid == os.geteuid(), "unsafe output")
    require(not os.path.lexists(path), "output exists")
    return path


def _check_output_paths(paths: set[str]) -> None:
    normalized = set()
    for name in paths:
        relative_path(name)
        folded = unicodedata.normalize("NFC", name).casefold()
        require(folded not in normalized, "conflicting output paths")
        normalized.add(folded)
    require(not any(unicodedata.normalize("NFC", str(parent)).casefold() in normalized for name in paths
                    for parent in PurePosixPath(name).parents if str(parent) != "."), "conflicting output paths")


def generate_legal_bundle(input_path: Path, output_root: Path) -> dict:
    output_root = _new_output_root(output_root)
    input_path = input_path.absolute()
    document = parse_json(_read_regular(input_path))
    require(set(document) == {"schema", "inventory", "files"}
            and type(document["schema"]) is int and document["schema"] == 1, "invalid schema")
    inventory = document["inventory"]
    validate_inventory(inventory)
    sources = document["files"]
    require(isinstance(sources, dict) and set(sources) == expected_legal_files(inventory), "incomplete files")
    files = {}
    for name, reference in sorted(sources.items()):
        relative_path(name)
        require(isinstance(reference, dict) and set(reference) == {"path", "sha256"}
                and valid_hash(reference["sha256"]), "invalid schema")
        relative = relative_path(reference["path"])
        data = _read_regular(input_path.parent.joinpath(*PurePosixPath(relative).parts))
        require(sha256_bytes(data) == reference["sha256"], "changed input")
        require(bool(data), "empty input")
        if name in REQUIRED_FILES:
            try:
                data.decode("utf-8")
            except UnicodeError:
                raise PackageInputError("invalid public text") from None
        files[name] = data
    require(sha256_bytes(files["legal/TERMS.txt"]) == inventory["terms_sha256"], "changed terms")
    for component in inventory["components"]:
        for field in ("license_files", "notice_files", "source_offer_files"):
            for reference in component[field]:
                require(sha256_bytes(files[reference["path"]]) == reference["sha256"], "changed component text")
    files["legal/TERMS.rtf"] = render_rtf(files["legal/TERMS.txt"].decode("utf-8"))
    files["legal/THIRD-PARTY-NOTICES.txt"] = aggregate_files(inventory, files, "notice_files")
    if any(component["source_offer_files"] for component in inventory["components"]):
        files["legal/SOURCE-OFFER.txt"] = aggregate_files(inventory, files, "source_offer_files")
    files[f"sbom/vadgr-{inventory['version']}.spdx.json"] = canonical_json(build_sbom(inventory))
    inventory_bytes = canonical_json(inventory)
    review = {key: inventory[key] for key in (
        "schema", "version", "target", "terms_version", "terms_sha256", "source_inputs", "payload_manifest_sha256",
    )}
    review.update({
        "status": "draft", "synthetic": False, "inventory_sha256": sha256_bytes(inventory_bytes),
        "files": {name: sha256_bytes(value) for name, value in sorted(files.items())},
        "closures": dict.fromkeys(CLOSURES, False),
    })
    files["package-input-inventory.json"] = inventory_bytes
    files["package-input-review.json"] = canonical_json(review)
    _check_output_paths(set(files))

    # A rejected input never creates a partial bundle. Exclusive creation preserves existing output.
    _new_output_root(output_root)
    output_root.mkdir(mode=0o700)
    for name, value in sorted(files.items()):
        destination = output_root.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            output.write(value)
    return review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = generate_legal_bundle(args.input, args.output)
        sys.stdout.buffer.write(canonical_json(result))
        return 0
    except (PackageInputError, OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        print("Legal bundle generation failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
