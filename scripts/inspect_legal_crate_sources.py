#!/usr/bin/env python3
"""Inspect pinned crate archives as data for original copyright and build scope.

No source is executed. Author metadata is not converted into a copyright claim.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import re
import sys
import tarfile
import tomllib
import zipfile
from urllib.request import urlopen

if __package__:
    from scripts.validate_package_inputs import canonical_json, parse_json, read_owned, relative_path, require, sha256_bytes
else:
    from validate_package_inputs import canonical_json, parse_json, read_owned, relative_path, require, sha256_bytes


def statements(text):
    """Keep original statement lines, excluding license instructions and examples."""
    lines = []
    for number, line in enumerate(text.splitlines(), 1):
        match = re.search(r"(?:copyright\s*(?:\(c\)|©|[12][0-9]{3})|©\s*[12][0-9]{3})", line, re.I)
        match = match or re.search(
            r"^\s*(?://|#|\*)?\s*(?i:copyright)(?:\s*:\s*|\s+)(?!(?i:and\b|owner\b|license\b|notice\b|holders?\b|law\b)|\[|<)[A-Z0-9]",
            line)
        match = match or re.search(r"^\s*(?://|#|\*)?\s*\([cC]\)\s*[12][0-9]{3}\b", line)
        match = match or re.search(r"Copyrights in this project are retained by their contributors", line)
        match = match or re.search(r"SPDX-FileCopyrightText:\s*(?!(?:NONE|NOASSERTION)\s*$)\S", line)
        match = match or re.search(r"^\s*Copyright \[[12][0-9]{3}\] \[(?!name\b)[A-Za-z0-9][^\]]+\]\s*$", line)
        match = match or re.search(r"^\s*__copyright__\s*=\s*['\"]Copyright [A-Z][A-Za-z .'-]+['\"]\s*$", line)
        if match and not any(token in line.lower() for token in (
                "[yyyy]", "<year>", "[year]", "yyyy", "your name", "example copyright", "copyright (c) <")):
            lines.append({"line": number, "text": line.strip()})
    return lines


def inspect_archive(raw, component):
    require(sha256_bytes(raw) == component["sha256"], "crate archive hash differs")
    files = []
    notices = []
    claims = []
    manifests = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        seen = set()
        total = 0
        for member in archive.getmembers():
            relative_path(member.name.rstrip("/"))
            require(member.name.casefold() not in seen, "crate paths alias")
            seen.add(member.name.casefold())
            require(member.isdir() or member.isfile(), "crate has a link or special member")
            if not member.isfile():
                continue
            require(member.size <= 32 * 1024 * 1024, "crate member is oversized")
            total += member.size
            require(total <= 512 * 1024 * 1024 and len(files) < 100000, "crate expansion limit exceeded")
            data = archive.extractfile(member).read()
            record = {"path": member.name, "size": len(data), "sha256": sha256_bytes(data)}
            files.append(record)
            if Path(member.name).name in ("Cargo.toml", "Cargo.toml.orig"):
                try:
                    manifests[member.name] = tomllib.loads(data.decode("utf-8"))
                except (UnicodeError, tomllib.TOMLDecodeError):
                    pass
            try:
                text = data.decode("utf-8")
            except UnicodeError:
                continue
            if "\x00" in text:
                continue
            found = statements(text)
            if found:
                claims.append({**record, "statements": found})
            base = Path(member.name).name.lower()
            if any(token in base for token in ("license", "copying", "notice", "copyright", "authors")):
                notices.append({**record, "text": text})
    return {"schema": 1, "name": component["name"], "version": component["version"],
            "archive_sha256": component["sha256"], "download_location": component["download_location"],
            "archive_files_sha256": sha256_bytes(canonical_json(sorted(files, key=lambda row: row["path"]))),
            "files_scanned": len(files), "original_statements": claims, "supplied_notices": notices,
            "manifests": manifests,
            "copyright_observation": "original-statements-found" if claims else "no-statement-detected",
            "limitation": "No detected statement is not a public-domain declaration. Authors are not copyright assertions; unrelated test/example notices may have separate scope."}


def acquire(component, cache, cargo_cache):
    filename = component["name"] + "-" + component["version"] + ".crate"
    target = cache / filename
    if target.exists():
        raw = read_owned(cache, filename)
    else:
        candidates = sorted(cargo_cache.glob("*/" + filename)) if cargo_cache else []
        if candidates:
            raw = read_owned(candidates[0].parent, candidates[0].name)
        else:
            require(component["download_location"] == f"https://static.crates.io/crates/{component['name']}/{filename}",
                    "crate acquisition URL differs")
            with urlopen(component["download_location"], timeout=60) as response:
                raw = response.read(32 * 1024 * 1024 + 1)
            require(len(raw) <= 32 * 1024 * 1024, "crate archive is oversized")
        require(sha256_bytes(raw) == component["sha256"], "crate acquisition hash differs")
        with target.open("xb") as stream:
            stream.write(raw)
    return inspect_archive(raw, component)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--cargo-cache", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, action="append", default=[],
                        help="Also acquire exact crates pinned by SBOMs in each observed wheelhouse")
    args = parser.parse_args()
    require(not args.output.exists() and args.output.parent.is_dir(), "output is not new")
    require(args.cache.is_dir(), "cache is absent")
    rows = {}
    for architecture in ("x86_64", "aarch64"):
        inventory = parse_json(read_owned(args.source_root, f"packaging/inputs/windows-{architecture}/package-input-inventory.json"))
        for row in inventory["components"]:
            if row["download_location"].startswith("https://static.crates.io/crates/") and row["kind"] == "cargo":
                key = (row["name"], row["version"])
                require(key not in rows or rows[key]["sha256"] == row["sha256"], "crate identities conflict")
                rows[key] = row
    for wheelhouse in args.wheelhouse:
        manifest = parse_json(read_owned(wheelhouse, "wheelhouse.json"))
        for wheel in manifest["wheels"]:
            raw = read_owned(wheelhouse, wheel["filename"])
            require(len(raw) == wheel["size"] and sha256_bytes(raw) == wheel["sha256"], "observed wheel identity differs")
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for name in archive.namelist():
                    if not name.endswith(".json") or not ("sbom" in name.lower() or "cyclonedx" in name.lower()):
                        continue
                    require(archive.getinfo(name).file_size <= 16 * 1024 * 1024, "nested SBOM is oversized")
                    for component in parse_json(archive.read(name)).get("components", []):
                        if not component.get("purl", "").startswith("pkg:cargo/") or not component.get("bom-ref", "").startswith("registry+"):
                            continue
                        hashes = {item["content"] for item in component.get("hashes", []) if item.get("alg") == "SHA-256"}
                        require(len(hashes) == 1, "nested registry component hash is missing")
                        name, version = component["name"], component["version"]
                        row = {"name": name, "version": version, "sha256": next(iter(hashes)),
                               "download_location": f"https://static.crates.io/crates/{name}/{name}-{version}.crate"}
                        key = (name, version)
                        require(key not in rows or rows[key]["sha256"] == row["sha256"], "observed nested crate identities conflict")
                        rows[key] = row
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda row: acquire(row, args.cache, args.cargo_cache), [rows[key] for key in sorted(rows)]))
    output = {"schema": 1, "status": "source-observations-not-approval", "archives": results}
    with args.output.open("xb") as stream:
        stream.write(canonical_json(output))
    print(f"Inspected {len(results)} exact crate archives; statements found in {sum(bool(row['original_statements']) for row in results)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
