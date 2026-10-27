#!/usr/bin/env python3
"""Import hash-bound source evidence without granting package approval."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from validate_package_inputs import PackageInputError, canonical_json, relative_path

REPORTS = {
    "nested_wheels": ("nested-wheel-evidence.json", "nested-wheels"),
    "native_sources": ("native-source-evidence.json", "native-sources"),
    "python": ("python-evidence.json", ""),
    "grants": ("grant-evidence.json", ""),
}
TARGETS = ("windows-x86_64", "windows-aarch64")
OUTSTANDING = [
    "Map source/build catalogues to the exact installed target payload; catalogues can include unlinked optional dependencies.",
    "Resolve workspace source identities, nested assets and native components, license choices, copyright notices and redistribution duties.",
    "Deliver required corresponding source and notices; source acquisition alone does not satisfy recipient delivery.",
    "Bind the reviewed inventory to actual target wheel and payload manifest hashes before any package approval.",
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_file(root, name):
    try:
        relative_path(name)
    except PackageInputError as error:
        raise ValueError("unsafe evidence path") from error
    root = root.resolve()
    path = root / name
    if not path.resolve().is_relative_to(root):
        raise ValueError("unsafe evidence path")
    if any(parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction())
           for parent in (path, *path.parents) if parent != root and parent.is_relative_to(root)):
        raise ValueError("linked evidence path")
    return path


def read_verified(root, record):
    expected = record.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("invalid evidence digest")
    data = safe_file(root, record["path"]).read_bytes()
    if digest(data) != expected:
        raise ValueError("evidence digest mismatch")
    return data


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def validate_unreviewed(packet):
    if packet.get("status") != "incomplete" or packet.get("review_status") != "unreviewed":
        raise ValueError("source supplement must remain unreviewed")
    for value in walk(packet):
        if ("license_concluded" in value and value["license_concluded"] is not None
                or "review_status" in value and value["review_status"] != "unreviewed"
                or "status" in value and value["status"] not in {"incomplete", "unreviewed"}
                or any(key in value for key in ("closures", "approved", "approval"))):
            raise ValueError("source supplement must remain unreviewed")


def validate_origins(repo, value):
    for entry in walk(value):
        if "sbom" in entry:
            if entry.get("target") not in TARGETS or not entry["sbom"].startswith(
                    f"packaging/legal-review/{entry['target']}/sources/"):
                raise ValueError("invalid SBOM origin")
            read_verified(repo, {"path": entry["sbom"], "sha256": entry["sbom_sha256"]})
        if "origins" in entry and "name" in entry:
            for origin in entry["origins"]:
                document = json.loads(read_verified(repo, {
                    "path": origin["sbom"], "sha256": origin["sbom_sha256"]}))
                matches = [item for item in document.get("components", [])
                           if item.get("name") == entry["name"] and item.get("version") == entry["version"]]
                if (len(matches) != 1 or matches[0].get("licenses") != entry["license_declared"]
                        or {item["content"] for item in matches[0].get("hashes", []) if item["alg"] == "SHA-256"}
                        != {entry["sha256"]}):
                    raise ValueError("SBOM component mismatch")
        if "origin" in entry and "component" in entry:
            origin = entry["origin"]
            document = json.loads(read_verified(repo, {
                "path": origin["sbom"], "sha256": origin["sbom_sha256"]}))
            if entry["component"] not in document.get("components", []):
                raise ValueError("SBOM component mismatch")


def add_file(files, name, data):
    relative_path(name)
    portable = unicodedata.normalize("NFC", name).casefold()
    if any(unicodedata.normalize("NFC", key).casefold() == portable for key in files):
        raise ValueError("evidence path collision")
    files[name] = data
    return {"path": name, "sha256": digest(data)}


def verify_component_archives(source, group, components):
    for item in components:
        if group == "nested_wheels":
            name = f"{item['name']}-{item['version']}.crate"
        else:
            suffix = ".tar.xz" if item["download_location"].endswith(".tar.xz") else ".tar.gz"
            name = item["name"] + suffix
        read_verified(source, {"path": "archives/" + name, "sha256": item["sha256"]})


def import_packet(source, repo, output):
    if output.exists():
        raise ValueError("output must not exist")
    files, groups = {}, {}
    for group, (report, prefix) in REPORTS.items():
        raw = safe_file(source, report).read_bytes()
        value = json.loads(raw)
        add_file(files, "sources/reports/" + report, raw)
        if group in {"nested_wheels", "native_sources"}:
            verify_component_archives(source, group, value[
                "registry_components" if group == "nested_wheels" else "components"])
        if group == "python":
            for artifact in value["artifacts"]:
                arch = artifact["architecture"]
                if arch not in {"x64", "arm64"}:
                    raise ValueError("invalid Python architecture")
                read_verified(source, {"path": f"python-{arch}-full.tar.zst", "sha256": artifact["sha256"]})
                triple = "x86_64" if arch == "x64" else "aarch64"
                artifact["download_location"] = (
                    "https://github.com/astral-sh/python-build-standalone/releases/download/20260825/"
                    f"cpython-3.12.14%2B20260825-{triple}-pc-windows-msvc-pgo-full.tar.zst")
                artifact["scope"] = "full build source evidence, not the install-only payload"
        for entry in walk(value):
            if "path" not in entry or "sha256" not in entry:
                continue
            original = entry["path"]
            data = read_verified(source / prefix, entry)
            copied = add_file(files, f"sources/{group}/{original}", data)
            entry.update(copied)
        groups[group] = value
    # The exact manifest was parsed as data during acquisition, never executed.
    manifest = safe_file(source, "upstream-download-manifest.json").read_bytes()
    add_file(files, "sources/reports/upstream-download-manifest.json", manifest)
    collections = []
    for target in TARGETS:
        name = f"packaging/legal-review/{target}/collection.json"
        collections.append({"path": name, "sha256": digest(safe_file(repo, name).read_bytes())})
    packet = {"schema": 1, "status": "incomplete", "review_status": "unreviewed",
              "source_collections": collections, "groups": groups,
              "files": [{"path": name, "sha256": digest(data)} for name, data in sorted(files.items())],
              "outstanding_review": OUTSTANDING}
    validate_unreviewed(packet)
    validate_origins(repo, packet)
    output.mkdir(parents=True)
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    (output / "collection.json").write_bytes(canonical_json(packet))
    verify_packet(output, repo)
    return packet


def verify_packet(root, repo):
    packet = json.loads(safe_file(root, "collection.json").read_bytes())
    if packet.get("schema") != 1 or not packet.get("outstanding_review"):
        raise ValueError("invalid source supplement")
    validate_unreviewed(packet)
    files = {}
    for item in packet["files"]:
        if not item["path"].startswith("sources/"):
            raise ValueError("invalid evidence path")
        add_file(files, item["path"], read_verified(root, item))
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != set(files) | {"collection.json"}:
        raise ValueError("unexpected or missing evidence file")
    for entry in walk(packet["groups"]):
        if "path" in entry and "sha256" in entry:
            if entry["path"] not in files or digest(files[entry["path"]]) != entry["sha256"]:
                raise ValueError("unbound evidence file")
    for item in packet["source_collections"]:
        read_verified(repo, item)
    validate_origins(repo, packet)
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        packet = verify_packet(args.output, args.source_root)
    else:
        if args.source is None:
            parser.error("--source is required for import")
        packet = import_packet(args.source, args.source_root, args.output)
    print(f"Source supplement: {len(packet['files'])} exact files; status incomplete, review unreviewed")


if __name__ == "__main__":
    main()
