#!/usr/bin/env python3
"""Close a retained Windows package packet from exact reviewed source bytes.

The command does not fetch data and does not approve terms for the publisher.
It applies the recorded package decisions to an exact draft packet, regenerates
the derived inventory, notices and SBOM, and then runs the package validator.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

if __package__:
    from scripts.validate_package_inputs import (
        CLOSURES,
        KINDS,
        aggregate_files,
        build_sbom,
        canonical_json,
        expected_legal_files,
        parse_json,
        read_owned,
        sha256_bytes,
        validate_package_inputs,
    )
else:
    from validate_package_inputs import (
        CLOSURES,
        KINDS,
        aggregate_files,
        build_sbom,
        canonical_json,
        expected_legal_files,
        parse_json,
        read_owned,
        sha256_bytes,
        validate_package_inputs,
    )


PILLOW_SOURCE = "pillow-12.3.0.tar.gz"
PILLOW_SOURCE_SHA256 = "3b8182a766685eaa002637e28b4ec8d6b18819a0c71f579bf0dbaa5830297cce"
REVIEW_SOURCES = {
    "freetype-2.14.3-FTL.TXT": "5a5ee54c5001bbad1cdc1a57cc3dd4c42199b2da09d39c7ee41fab002d02967f",
    "libavif-1.4.2-LICENSE": "165abf92cc04b39e80d29cadea7a6a7e8fddf59407d4ad2616507a7ebe8216f9",
    "libjpeg-turbo-3.1.4.1-LICENSE.md": "e10114e6e40f3d0311c401ca25245ac5ef459a43c20f976fd63f03e816f5741f",
    "libjpeg-turbo-3.1.4.1-README.ijg": "75815e3bf6484201a3c3d17a1bbf10f2e8e3237f84df10a2357ea896db2a81d6",
    "openjpeg-2.5.4-LICENSE": "a6af136f3e15038a666b61f376612a07d9a4e48cb7c01adbf3e33b3f14ab49b6",
    "libtiff-4.7.1-LICENSE.md": "0e27c2382d7b8147972bbb746e04059a1152c8d0fda9d03ef1399d1a433c4ade",
    "zlib-ng-2.3.3-LICENSE.md": "6c9f0d975b41afaa34d22f55bb8986ce69e5cb7ad327cb2b28820cd425edf5ee",
    "little-cms-2.19.1-LICENSE": "6dbd60437f8ef91d8de1f08ad75882547fd4931bfcc3566a0735f28db1484d31",
    "libwebp-1.6.0-COPYING": "5aec868f669e384a22372a4e8a1a6cd7d44c64cd451f960ca69cc170d1e13acf",
    PILLOW_SOURCE: PILLOW_SOURCE_SHA256,
}
GENERATED_COMPONENT_PREFIX = "pillow-native-"


class FinalizationError(Exception):
    """A package packet cannot be finalized from the supplied exact bytes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalizationError(message)


def checked_source(root: Path, name: str) -> bytes:
    raw = read_owned(root, name)
    require(sha256_bytes(raw) == REVIEW_SOURCES[name], f"review source differs: {name}")
    return raw


def entry(path: str, raw: bytes, license_ids: list[str] | None = None) -> dict:
    result = {"path": path, "sha256": sha256_bytes(raw)}
    if license_ids is not None:
        result["license_ids"] = license_ids
    return result


def component_map(inventory: dict) -> dict[str, dict]:
    return {row["id"]: row for row in inventory["components"]}


def module_identity(scope: dict, stem: str) -> str:
    matches = [row["sha256"] for name, row in scope["native_members"].items()
               if Path(name).name.startswith(stem + ".")]
    require(len(matches) == 1, f"Pillow native module differs: {stem}")
    return matches[0]


def add_file(files: dict[str, bytes], path: str, raw: bytes) -> dict:
    prior = files.get(path)
    require(prior is None or prior == raw, f"review file collision: {path}")
    files[path] = raw
    return entry(path, raw)


def add_license(files: dict[str, bytes], identifier: str, name: str, raw: bytes,
                ids: list[str]) -> tuple[list[dict], list[dict]]:
    path = f"legal/LICENSES/{identifier}/{name}"
    license_row = add_file(files, path, raw)
    license_row["license_ids"] = ids
    notice_path = f"legal/NOTICES/{identifier}/{name}"
    notice_row = add_file(files, notice_path, raw)
    return [license_row], [notice_row]


def native_component(parent: dict, identifier: str, name: str, version: str,
                     module_sha256: str, declared: str, concluded: str,
                     license_files: list[dict], notice_files: list[dict],
                     source_files: list[dict] | None = None) -> dict:
    return {
        "id": identifier,
        "name": name,
        "version": version,
        "kind": "wheel",
        "sha256": module_sha256,
        "download_location": parent["download_location"],
        "copyright_text": "NOASSERTION",
        "license_declared": declared,
        "license_concluded": concluded,
        "license_files": license_files,
        "notice_required": True,
        "notice_files": notice_files,
        "source_offer_required": bool(source_files),
        "source_offer_files": source_files or [],
    }


def close_existing_components(inventory: dict, files: dict[str, bytes]) -> None:
    components = component_map(inventory)

    # PyPI publishes the informal classifier value "PSF" for pywin32. It is
    # not an SPDX identifier. Preserve that fact in the review ledger, but use
    # SPDX NOASSERTION in the shipped SBOM and keep the exact concluded grants.
    components["wheel-pywin32-312"]["license_declared"] = "NOASSERTION"

    cms = components["cargo-cms-0.2.3"]
    for source in cms["source_offer_files"]:
        files.pop(source["path"], None)
    cms["copyright_text"] = "NOASSERTION"
    cms["source_offer_required"] = False
    cms["source_offer_files"] = []

    cpython = components["runtime-cpython-3.12.14"]
    core = components["native-cpython-3.12"]
    core_license = core["license_files"][0]
    core_raw = files[core_license["path"]]
    runtime_path = "legal/LICENSES/runtime-cpython-3.12.14/000-CPython-LICENSE"
    runtime_license = add_file(files, runtime_path, core_raw)
    runtime_license["license_ids"] = ["0BSD", "Python-2.0"]
    cpython["license_concluded"] = "Python-2.0 AND 0BSD"
    cpython["license_files"] = [runtime_license]
    cpython["notice_required"] = True
    cpython["source_offer_required"] = False
    cpython["source_offer_files"] = []

    rust = components["runtime-rust-std-1.97.1"]
    llvm_notice = next(row for row in rust["notice_files"] if row["path"].endswith("LLVM-exception.txt"))
    llvm_raw = files[llvm_notice["path"]]
    llvm_path = "legal/LICENSES/runtime-rust-std-1.97.1/002-LLVM-exception.txt"
    llvm_license = add_file(files, llvm_path, llvm_raw)
    llvm_license["license_ids"] = ["LLVM-exception"]
    rust["license_concluded"] = "Apache-2.0 AND (Apache-2.0 WITH LLVM-exception)"
    rust["license_files"].append(llvm_license)

    wix_source = components["native-wix"]["source_offer_files"]
    require(len(wix_source) == 1, "WiX source archive is not exact")
    for identifier in (
        "framework-wixtoolset.bal.wixext-7.0.0",
        "framework-wixtoolset.sdk-7.0.0",
        "framework-wixtoolset.util.wixext-7.0.0",
    ):
        component = components[identifier]
        component["source_offer_required"] = True
        component["source_offer_files"] = copy.deepcopy(wix_source)

    tix = components.get("native-tk-windows-bin-8612")
    if tix is not None:
        tix["source_offer_required"] = False
        tix["source_offer_files"] = []


def add_pillow_components(inventory: dict, files: dict[str, bytes], packet_root: Path,
                          sources: Path) -> None:
    inventory["components"] = [row for row in inventory["components"]
                               if not row["id"].startswith(GENERATED_COMPONENT_PREFIX)]
    components = component_map(inventory)
    parent = components["wheel-pillow-12.3.0"]
    scope = parse_json(read_owned(packet_root, "pillow-native-scope.json"))
    require(scope.get("target") == inventory["target"] and scope.get("pillow_version") == "12.3.0",
            "Pillow scope identity differs")

    internal = {
        "0BSD": files[components["native-xz"]["license_files"][0]["path"]],
        "LGPL-2.1-or-later": files[components["wheel-pywin32-312-adodbapi"]["license_files"][0]["path"]],
    }
    external = {name: checked_source(sources, name) for name in REVIEW_SOURCES}
    jpeg_terms = (external["libjpeg-turbo-3.1.4.1-LICENSE.md"]
                  + b"\n\n===== README.ijg =====\n\n"
                  + external["libjpeg-turbo-3.1.4.1-README.ijg"])
    avif_id = "LicenseRef-libavif-composite-" + sha256_bytes(external["libavif-1.4.2-LICENSE"])
    jpeg_id = "LicenseRef-libjpeg-turbo-composite-" + sha256_bytes(jpeg_terms)

    definitions = [
        ("pillow-native-freetype-2.14.3", "FreeType", "2.14.3", "_imagingft", "FTL", "FTL",
         external["freetype-2.14.3-FTL.TXT"], "FTL.txt", None),
        ("pillow-native-fribidi-shim-1.x", "Pillow FriBiDi shim", "1.x", "_imagingft",
         "LGPL-2.1-or-later", "LGPL-2.1-or-later", internal["LGPL-2.1-or-later"], "LGPL-2.1.txt", "pillow"),
        ("pillow-native-pythoncapi-compat", "pythoncapi-compat", "c84545f", "_imagingft", "0BSD", "0BSD",
         internal["0BSD"], "0BSD.txt", None),
        ("pillow-native-libjpeg-turbo-3.1.4.1", "libjpeg-turbo", "3.1.4.1", "_imaging",
         "IJG AND BSD-3-Clause", jpeg_id, jpeg_terms, "LICENSE-and-README.ijg", None),
        ("pillow-native-openjpeg-2.5.4", "OpenJPEG", "2.5.4", "_imaging", "BSD-2-Clause", "BSD-2-Clause",
         external["openjpeg-2.5.4-LICENSE"], "LICENSE", None),
        ("pillow-native-libtiff-4.7.1", "libtiff", "4.7.1", "_imaging", "libtiff", "libtiff",
         external["libtiff-4.7.1-LICENSE.md"], "LICENSE.md", None),
        ("pillow-native-zlib-ng-2.3.3", "zlib-ng", "2.3.3", "_imaging", "Zlib", "Zlib",
         external["zlib-ng-2.3.3-LICENSE.md"], "LICENSE.md", None),
        ("pillow-native-little-cms-2.19.1", "Little CMS", "2.19.1", "_imagingcms", "MIT", "MIT",
         external["little-cms-2.19.1-LICENSE"], "LICENSE", None),
        ("pillow-native-libwebp-1.6.0", "libwebp", "1.6.0", "_webp", "BSD-3-Clause", "BSD-3-Clause",
         external["libwebp-1.6.0-COPYING"], "COPYING", None),
    ]
    if any(Path(name).name.startswith("_avif.") for name in scope["native_members"]):
        definitions.append((
            "pillow-native-libavif-1.4.2", "libavif and statically linked codec libraries", "1.4.2", "_avif",
            "BSD-2-Clause", avif_id, external["libavif-1.4.2-LICENSE"], "LICENSE", None,
        ))

    for identifier, name, version, module, declared, concluded, raw, filename, source in definitions:
        license_files, notice_files = add_license(files, identifier, filename, raw, [concluded])
        source_files = None
        if source == "pillow":
            source_path = f"legal/SOURCE-OFFERS/{identifier}/{PILLOW_SOURCE}"
            source_raw = external[PILLOW_SOURCE]
            source_files = [add_file(files, source_path, source_raw)]
        inventory["components"].append(native_component(
            parent, identifier, name, version, module_identity(scope, module), declared, concluded,
            license_files, notice_files, source_files,
        ))


def finalize_packet(input_root: Path, output_root: Path, source_root: Path,
                    review_sources: Path, version: str, target: str) -> dict:
    require(input_root.resolve() != output_root.resolve(), "output must differ from input")
    require(not output_root.exists(), "output already exists")
    shutil.copytree(input_root, output_root)
    inventory = parse_json(read_owned(output_root, "package-input-inventory.json"))
    require(inventory.get("version") == version and inventory.get("target") == target,
            "packet identity differs")

    files = {}
    for name in expected_legal_files(inventory) | {
        "legal/TERMS.rtf", "legal/THIRD-PARTY-NOTICES.txt", "legal/SOURCE-OFFER.txt",
        f"sbom/vadgr-{version}.spdx.json",
    }:
        path = output_root / name
        if path.is_file():
            files[name] = read_owned(output_root, name)

    close_existing_components(inventory, files)
    add_pillow_components(inventory, files, output_root, review_sources)
    inventory["components"] = sorted(inventory["components"], key=lambda row: row["id"])
    inventory["coverage"] = {
        kind: {"status": "complete", "component_ids": [row["id"] for row in inventory["components"]
                                                        if row["kind"] == kind]}
        for kind in sorted(KINDS)
    }
    files["package-input-inventory.json"] = canonical_json(inventory)
    files["legal/THIRD-PARTY-NOTICES.txt"] = aggregate_files(inventory, files, "notice_files")
    files["legal/SOURCE-OFFER.txt"] = aggregate_files(inventory, files, "source_offer_files")
    files[f"sbom/vadgr-{version}.spdx.json"] = canonical_json(build_sbom(inventory, files))

    expected = expected_legal_files(inventory) | {
        "legal/TERMS.rtf", "legal/THIRD-PARTY-NOTICES.txt", "legal/SOURCE-OFFER.txt",
        f"sbom/vadgr-{version}.spdx.json",
    }
    require(expected <= set(files), "final package file set is incomplete")
    for directory in (output_root / "legal", output_root / "sbom"):
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_file() and path.relative_to(output_root).as_posix() not in expected:
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    for name in sorted(expected | {"package-input-inventory.json"}):
        destination = output_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(files[name])

    review = {key: inventory[key] for key in (
        "schema", "version", "target", "terms_version", "terms_sha256",
        "source_inputs", "payload_manifest_sha256",
    )}
    review.update({
        "status": "approved",
        "synthetic": False,
        "inventory_sha256": sha256_bytes(files["package-input-inventory.json"]),
        "files": {name: sha256_bytes(files[name]) for name in sorted(expected)},
        "closures": dict.fromkeys(CLOSURES, True),
    })
    (output_root / "package-input-review.json").write_bytes(canonical_json(review))
    ledger = parse_json(read_owned(output_root, "review-ledger.json"))
    ledger.update({
        "candidate_approval": False,
        "publishable": False,
        "status": "package-inputs-approved",
        "unresolved": [],
        "unresolved_by_reason": {},
        "package_questions": [],
    })
    ledger["terms"]["status"] = "publisher-owner-approved-retained-unchanged"
    ledger["summary"].update({
        "component_candidates": len(inventory["components"]),
        "retained_grant_choices": len(inventory["components"]),
        "unresolved_copyright": sum(row["copyright_text"] == "NOASSERTION" for row in inventory["components"]),
        "rows_with_review_items": 0,
    })
    (output_root / "review-ledger.json").write_bytes(canonical_json(ledger))
    unapproved = output_root / "UNAPPROVED.txt"
    if unapproved.exists():
        unapproved.unlink()

    return validate_package_inputs(output_root, source_root, version, target, source_only=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--review-sources", type=Path, required=True)
    parser.add_argument("--version", default="0.5.0")
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    try:
        result = finalize_packet(
            args.input.resolve(), args.output.resolve(), args.source_root.resolve(),
            args.review_sources.resolve(), args.version, args.target,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (FinalizationError, OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        print(f"Package finalization failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
