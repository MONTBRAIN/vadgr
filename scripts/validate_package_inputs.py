#!/usr/bin/env python3
"""Check approved package bytes. Approval identity comes from trusted source review,
not from a JSON boolean. This command never creates an approval record.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tomllib
import unicodedata
from urllib.parse import urlsplit


SOURCE_INPUTS = ("Cargo.lock", "packaging/cua/pins.toml", "packaging/cua/requirements.lock", "packaging/toolchain.json")
CLOSURES = ("publisher", "market_rights", "apache_compatibility", "product_data", "third_party_duties")
KINDS = {"cargo", "wheel", "runtime", "asset", "framework"}
REQUIRED_FILES = {
    "legal/TERMS.txt", "legal/LICENSE.txt", "legal/NOTICE.txt",
    "legal/PRIVACY-NOTICE.txt", "legal/SECURITY-AND-PERMISSIONS.txt",
    "legal/SUPPORT.txt", "legal/UNINSTALL-AND-DATA.txt", "README-OFFLINE.txt",
}
INVENTORY_KEYS = {"schema", "created", "version", "target", "terms_version", "terms_sha256", "source_inputs", "payload_manifest_sha256", "coverage", "components"}
REVIEW_KEYS = (INVENTORY_KEYS - {"coverage", "components", "created"}) | {"status", "synthetic", "inventory_sha256", "files", "closures"}
COMPONENT_KEYS = {"id", "name", "version", "kind", "sha256", "download_location", "copyright_text", "license_declared", "license_concluded", "license_files", "notice_required", "notice_files", "source_offer_required", "source_offer_files"}
TARGETS = {f"{arch}-{suffix}" for arch in ("aarch64", "x86_64") for suffix in ("apple-darwin", "unknown-linux-gnu", "pc-windows-msvc")}
# A new identifier needs an explicit supported-terms change, not a guessed license.
LICENSE_IDS = set("""Apache-2.0 MIT BSD-2-Clause BSD-3-Clause BSD-4-Clause ISC Zlib
BSL-1.0 CC0-1.0 Unlicense MPL-2.0 OFL-1.1 Ubuntu-font-1.0
Unicode-3.0 Unicode-DFS-2016 Unicode-DFS-2015 Python-2.0 PSF-2.0
BlueOak-1.0.0 0BSD BSD-3-Clause-Clear BSD-3-Clause-Open-MPI BSD-3-Clause-LBNL
BSD-2-Clause-Views BSD-2-Clause-Patent BSD-3-Clause-Attribution
MIT-0 MIT-CMU MIT-open-group OpenSSL RHeCos-1.1
Apache-1.1 Artistic-2.0 CC-BY-3.0 CC-BY-4.0 CC-BY-SA-4.0
LGPL-2.1-only LGPL-2.1-or-later LGPL-3.0-only LGPL-3.0-or-later
GPL-2.0-only GPL-2.0-or-later GPL-3.0-only GPL-3.0-or-later
AGPL-3.0-only AGPL-3.0-or-later bzip2-1.0.6 libpng-2.0 Libpng
FTL IJG TCL X11 W3C HPND curl NCSA libtiff PostgreSQL""".split())
EXCEPTION_IDS = {"LLVM-exception", "GCC-exception-3.1", "Classpath-exception-2.0", "Autoconf-exception-3.0", "Bison-exception-2.2"}


class PackageInputError(Exception):
    """A fixed error category safe for build output."""


def require(condition: bool, category: str) -> None:
    if not condition:
        raise PackageInputError(category)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def valid_hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def relative_path(value: object) -> str:
    require(isinstance(value, str) and bool(value) and "\\" not in value and ":" not in value, "unsafe path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and all(part not in {".", ".."} for part in path.parts), "unsafe path")
    require(all(ord(char) >= 32 and ord(char) != 127 for char in value), "unsafe path")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {prefix + suffix for prefix in ("COM", "LPT") for suffix in "123456789¹²³"}
    require(not any(char in value for char in '<>"|?*'), "unsafe path")
    require(all(not part.endswith((".", " ")) and part.split(".", 1)[0].upper() not in reserved for part in path.parts), "unsafe path")
    return value


def read_owned(root: Path, relative: str) -> bytes:
    relative_path(relative)
    require(root.is_dir() and not root.is_symlink(), "unsafe path")
    for ancestor in (root.absolute(), *root.absolute().parents):
        require(not ancestor.is_symlink() and not getattr(ancestor, "is_junction", lambda: False)(), "unsafe path")
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "unsafe path")
    try:
        metadata = path.lstat()
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, "unsafe file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            require(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1
                    and (metadata.st_dev, metadata.st_ino) == (opened.st_dev, opened.st_ino), "unsafe file")
            result = source.read()
            after = os.fstat(source.fileno())
            require((opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns, opened.st_nlink)
                    == (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink), "changed input")
            return result
    except OSError:
        raise PackageInputError("missing input") from None


def parse_json(value: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, item in items:
            require(key not in result, "invalid schema")
            result[key] = item
        return result
    try:
        result = json.loads(value, object_pairs_hook=pairs)
        require(isinstance(result, dict), "invalid schema")
        return result
    except (ValueError, UnicodeError):
        raise PackageInputError("invalid schema") from None


def validate_conclusion(value: object) -> None:
    require(isinstance(value, str) and 0 < len(value) <= 1024, "unresolved license")
    tokens = re.findall(r"[A-Za-z0-9.-]+|[()]", value)
    require("".join(tokens) == re.sub(r"\s", "", value), "unresolved license")
    position = 0

    def term():
        nonlocal position
        require(position < len(tokens), "unresolved license")
        if tokens[position] == "(":
            position += 1
            expression()
            require(position < len(tokens) and tokens[position] == ")", "unresolved license")
            position += 1
        else:
            require(tokens[position] in LICENSE_IDS, "unresolved license")
            position += 1
            if position < len(tokens) and tokens[position] == "WITH":
                position += 1
                require(position < len(tokens) and tokens[position] in EXCEPTION_IDS, "unresolved license")
                position += 1

    def expression():
        nonlocal position
        term()
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            term()

    expression()
    require(position == len(tokens), "unresolved license")


def validate_inventory(inventory: dict) -> None:
    require(isinstance(inventory, dict) and set(inventory) == INVENTORY_KEYS, "invalid inventory")
    require(type(inventory["schema"]) is int and inventory["schema"] == 1, "invalid inventory")
    require(isinstance(inventory["created"], str), "invalid inventory")
    try:
        require(datetime.strptime(inventory["created"], "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") == inventory["created"], "invalid inventory")
    except ValueError:
        raise PackageInputError("invalid inventory") from None
    require(isinstance(inventory["version"], str) and re.fullmatch(r"\d+\.\d+\.\d+", inventory["version"]), "invalid inventory")
    require(isinstance(inventory["target"], str) and inventory["target"] in TARGETS, "invalid inventory")
    require(isinstance(inventory["terms_version"], str) and re.fullmatch(r"\d+(?:\.\d+)+", inventory["terms_version"]), "invalid inventory")
    require(valid_hash(inventory["terms_sha256"]) and valid_hash(inventory["payload_manifest_sha256"]), "invalid inventory")
    require(isinstance(inventory["source_inputs"], dict) and set(inventory["source_inputs"]) == set(SOURCE_INPUTS)
            and all(valid_hash(value) for value in inventory["source_inputs"].values()), "invalid inventory")
    coverage = inventory["coverage"]
    require(isinstance(coverage, dict) and set(coverage) == KINDS, "incomplete coverage")
    components = inventory["components"]
    require(isinstance(components, list) and bool(components), "incomplete coverage")
    identifiers = set()
    file_paths = set()
    for component in components:
        require(isinstance(component, dict) and set(component) == COMPONENT_KEYS, "invalid component")
        identifier = component["id"]
        require(isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", identifier)
                and identifier not in identifiers and identifier != "DOCUMENT", "invalid component")
        identifiers.add(identifier)
        require(isinstance(component["kind"], str) and component["kind"] in KINDS and valid_hash(component["sha256"]), "invalid component")
        for field in ("name", "version", "license_declared"):
            require(isinstance(component[field], str) and bool(component[field].strip())
                    and not any(ord(char) < 32 for char in component[field]), "invalid component")
        validate_conclusion(component["license_concluded"])
        validate_conclusion(re.sub(r"\bOR\b", "AND", component["license_declared"]))
        location = component["download_location"]
        require(isinstance(location, str), "invalid component")
        parsed = urlsplit(location)
        require(parsed.scheme == "https" and parsed.hostname and "." in parsed.hostname
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment,
                "unresolved provenance")
        copyright_text = component["copyright_text"]
        require(isinstance(copyright_text, str) and bool(copyright_text.strip())
                and "NOASSERTION" not in copyright_text and copyright_text != "NONE", "unresolved copyright")
        covered_licenses = set()
        for field in ("notice_required", "source_offer_required"):
            require(type(component[field]) is bool, "invalid component")
        for field, prefix in (("license_files", "legal/LICENSES/"), ("notice_files", "legal/NOTICES/"), ("source_offer_files", "legal/SOURCE-OFFERS/")):
            files = component[field]
            require(isinstance(files, list), "incomplete coverage")
            if field == "license_files" or component[field.replace("_files", "_required")]:
                require(bool(files), "incomplete coverage")
            for entry in files:
                keys = {"path", "sha256", "license_ids"} if field == "license_files" else {"path", "sha256"}
                require(isinstance(entry, dict) and set(entry) == keys and valid_hash(entry["sha256"]), "invalid component")
                if field == "license_files":
                    ids = entry["license_ids"]
                    require(isinstance(ids, list) and bool(ids) and all(isinstance(item, str) and item in LICENSE_IDS | EXCEPTION_IDS for item in ids)
                            and len(set(ids)) == len(ids), "incomplete license coverage")
                    covered_licenses.update(ids)
                name = relative_path(entry["path"])
                portable_name = unicodedata.normalize("NFC", name).casefold()
                require(name.startswith(prefix) and portable_name not in file_paths, "incomplete coverage")
                file_paths.add(portable_name)
        concluded_atoms = set(re.findall(r"[A-Za-z0-9.-]+", component["license_concluded"])) - {"AND", "WITH"}
        require(covered_licenses == concluded_atoms, "incomplete license coverage")
    for kind, entry in coverage.items():
        require(isinstance(entry, dict) and set(entry) == {"status", "component_ids"}
                and entry["status"] == "complete" and isinstance(entry["component_ids"], list), "incomplete coverage")
        expected = {component["id"] for component in components if component["kind"] == kind}
        require(all(isinstance(value, str) for value in entry["component_ids"])
                and len(entry["component_ids"]) == len(expected) and set(entry["component_ids"]) == expected, "incomplete coverage")
        if kind in {"cargo", "wheel", "runtime"}:
            require(bool(expected), "incomplete coverage")


def expected_legal_files(inventory: dict) -> set[str]:
    return REQUIRED_FILES | {entry["path"] for component in inventory["components"]
                             for field in ("license_files", "notice_files", "source_offer_files") for entry in component[field]}


def render_rtf(text: str) -> bytes:
    result = [r"{\rtf1\ansi\deff0\uc1 "]
    for char in text:
        if char in "\\{}":
            result.append("\\" + char)
        elif char == "\n":
            result.append("\\par\n")
        elif char == "\r":
            result.append("\\u13?")
        elif char == "\t":
            result.append("\\tab ")
        elif 32 <= ord(char) < 127:
            result.append(char)
        else:
            encoded = char.encode("utf-16-le")
            for offset in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[offset:offset + 2], "little", signed=True)
                result.append(f"\\u{unit}?")
    return ("".join(result) + "}\n").encode("ascii")


def build_sbom(inventory: dict) -> dict:
    packages = [{"SPDXID": "SPDXRef-" + item["id"], "name": item["name"], "versionInfo": item["version"],
                 "downloadLocation": item["download_location"], "filesAnalyzed": False,
                 "checksums": [{"algorithm": "SHA256", "checksumValue": item["sha256"]}],
                 "licenseConcluded": item["license_concluded"], "licenseDeclared": item["license_declared"],
                 "copyrightText": item["copyright_text"]} for item in sorted(inventory["components"], key=lambda item: item["id"])]
    return {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": "vadgr-" + inventory["version"] + "-" + inventory["target"],
            "documentNamespace": "https://spdx.org/spdxdocs/vadgr-" + sha256_bytes(canonical_json(inventory)),
            "creationInfo": {"created": inventory["created"], "creators": ["Tool: vadgr-package-inputs"]},
            "packages": packages, "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES",
                                                      "relatedSpdxElement": item["SPDXID"]} for item in packages]}


def aggregate_files(inventory: dict, files: dict[str, bytes], field: str) -> bytes:
    result = []
    for component in sorted(inventory["components"], key=lambda item: item["id"]):
        for entry in sorted(component[field], key=lambda item: item["path"]):
            result.extend([component["name"].encode("utf-8") + b"\n", files[entry["path"]], b"\n"])
    return b"".join(result) or b"No additional third-party NOTICE files are required by the component inventory.\n"


def validate_package_inputs(root: Path, source_root: Path, version: str, target: str, *,
                            payload_manifest: Path | None = None, source_only: bool = False) -> dict:
    try:
        return _validate_package_inputs(root, source_root, version, target, payload_manifest, source_only)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise PackageInputError("invalid package inputs") from None


def _validate_package_inputs(root, source_root, version, target, payload_manifest, source_only):
    require(type(source_only) is bool and target in TARGETS, "invalid target")
    require(not (source_only and payload_manifest is not None), "ambiguous validation scope")
    inventory_bytes = read_owned(root, "package-input-inventory.json")
    inventory = parse_json(inventory_bytes)
    validate_inventory(inventory)
    review = parse_json(read_owned(root, "package-input-review.json"))
    require(set(review) == REVIEW_KEYS and type(review["schema"]) is int and review["schema"] == 1, "invalid review")
    require(review["status"] == "approved" and review["synthetic"] is False, "approval required")
    require(isinstance(review["closures"], dict) and set(review["closures"]) == set(CLOSURES)
            and all(value is True for value in review["closures"].values()), "review incomplete")
    require(inventory["version"] == version and inventory["target"] == target, "identity mismatch")
    for field in REVIEW_KEYS & INVENTORY_KEYS:
        require(review[field] == inventory[field], "review identity mismatch")
    require(review["inventory_sha256"] == sha256_bytes(inventory_bytes), "inventory mismatch")
    source_bytes = {name: read_owned(source_root, name) for name in SOURCE_INPUTS}
    require({name: sha256_bytes(data) for name, data in source_bytes.items()} == inventory["source_inputs"], "source input mismatch")
    source_version = tomllib.loads(read_owned(source_root, "Cargo.toml").decode("utf-8"))["package"]["version"]
    require(source_version == version, "source version mismatch")
    pins = tomllib.loads(source_bytes["packaging/cua/pins.toml"].decode("utf-8"))
    target_pins = pins["targets"][target]
    expected_payload = {"schema": 1, "cua_version": pins["cua"], "python_version": pins["python"],
                        "python_build": pins["python_build"], "target": target,
                        "requirements_sha256": inventory["source_inputs"]["packaging/cua/requirements.lock"],
                        "python_archive_sha256": target_pins["python_sha256"], "uv_archive_sha256": target_pins["uv_sha256"]}
    if not source_only:
        if payload_manifest is None:
            payload_bytes = read_owned(root, "lib/cua/payload.json")
        else:
            payload_bytes = read_owned(payload_manifest.parent, payload_manifest.name)
        require(sha256_bytes(payload_bytes) == inventory["payload_manifest_sha256"], "payload identity mismatch")
        actual_payload = parse_json(payload_bytes)
        require(type(actual_payload.get("schema")) is int and actual_payload == expected_payload, "payload pins mismatch")
    generated = {"legal/TERMS.rtf", "legal/THIRD-PARTY-NOTICES.txt", f"sbom/vadgr-{version}.spdx.json"}
    if any(component["source_offer_files"] for component in inventory["components"]):
        generated.add("legal/SOURCE-OFFER.txt")
    expected_files = expected_legal_files(inventory) | generated
    hashes = review["files"]
    require(isinstance(hashes, dict) and set(hashes) == expected_files
            and all(valid_hash(value) for value in hashes.values()), "file inventory mismatch")
    actual_files = {"README-OFFLINE.txt"}
    for directory in ("legal", "sbom"):
        parent = root / directory
        require(parent.is_dir() and not parent.is_symlink(), "unsafe path")
        for path in parent.rglob("*"):
            require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "unsafe path")
            if not path.is_dir():
                actual_files.add(path.relative_to(root).as_posix())
    require(actual_files == expected_files, "file inventory mismatch")
    files = {name: read_owned(root, name) for name in expected_files}
    require(all(sha256_bytes(data) == hashes[name] for name, data in files.items()), "file hash mismatch")
    for name in REQUIRED_FILES:
        text = files[name].decode("utf-8")
        require(bool(text.strip()) and "\x00" not in text, "invalid disclosure")
    require(sha256_bytes(files["legal/TERMS.txt"]) == inventory["terms_sha256"], "terms mismatch")
    require(files["legal/TERMS.rtf"] == render_rtf(files["legal/TERMS.txt"].decode("utf-8")), "terms rendering mismatch")
    for component in inventory["components"]:
        for field in ("license_files", "notice_files", "source_offer_files"):
            for entry in component[field]:
                require(bool(files[entry["path"]].strip()) and sha256_bytes(files[entry["path"]]) == entry["sha256"], "component text mismatch")
    require(files["legal/THIRD-PARTY-NOTICES.txt"] == aggregate_files(inventory, files, "notice_files"), "notice mismatch")
    if "legal/SOURCE-OFFER.txt" in generated:
        require(files["legal/SOURCE-OFFER.txt"] == aggregate_files(inventory, files, "source_offer_files"), "source offer mismatch")
    require(files[f"sbom/vadgr-{version}.spdx.json"] == canonical_json(build_sbom(inventory)), "SBOM mismatch")
    return {"schema": 1, "status": "approved", "scope": "source-inputs" if source_only else "assembled-payload",
            "version": version, "target": target, "terms_version": inventory["terms_version"],
            "terms_sha256": inventory["terms_sha256"], "payload_manifest_sha256": inventory["payload_manifest_sha256"],
            "inventory_sha256": review["inventory_sha256"], "component_count": len(inventory["components"]),
            "file_count": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--payload-manifest", type=Path)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_package_inputs(args.root, args.source_root, args.version, args.target,
                                         payload_manifest=args.payload_manifest, source_only=args.source_only)
        require(result.get("scope") == ("source-inputs" if args.source_only else "assembled-payload"), "validation scope mismatch")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PackageInputError, OSError, ValueError, TypeError, KeyError, UnicodeError):
        print("Package inputs failed validation.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
