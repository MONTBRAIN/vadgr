#!/usr/bin/env python3
"""Create reproducible, explicitly incomplete legal review packets from observations.

This preparer does not replace the approved bundle generator or its validators.
Metadata reachability is recorded separately from proof of shipped machine code.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import re
import subprocess
import struct
import sys
import tarfile
import tomllib
import zipfile

if __package__:
    from scripts.validate_package_inputs import (
        CLOSURES, KINDS, REQUIRED_FILES, canonical_json, parse_json,
        profile_source_inputs, read_owned, relative_path, render_rtf, require,
        sha256_bytes, aggregate_files, validate_conclusion, PackageInputError,
    )
else:
    from validate_package_inputs import (
        CLOSURES, KINDS, REQUIRED_FILES, canonical_json, parse_json,
        profile_source_inputs, read_owned, relative_path, render_rtf, require,
        sha256_bytes, aggregate_files, validate_conclusion, PackageInputError,
    )


ARCHITECTURES = {"x64": "x86_64", "arm64": "aarch64"}
BOUNDARY = {"status": "draft", "candidate_approval": False, "publishable": False}
SOURCE_ARCHIVES = {
    "wheel-nodriver-0.50.3": ("nodriver-0.50.3.tar.gz", "24ca688d8646ef8ffad5c8ce65804e5e7671a779ad26a24d76f6465d5666c631"),
    "native-wix": ("wix-b8977d6.tar.gz", "aef765da7c8051919081235840a8fca10e6bc4f37aab83764a80974ffd1fe09b"),
}
FONT_ARCHIVE = "epaint_default_fonts-0.36.1.crate"
FONT_SHA256 = "18dee69613aac468922cf28a32025eb7d7ed6985b61f73245848e58f37876c98"


def license_choice(declared):
    """Select an explicit permissive alternative, never discard an AND or exception."""
    if isinstance(declared, list) and len(declared) == 1:
        declared = declared[0]
        if isinstance(declared, dict):
            declared = declared.get("expression")
    if not isinstance(declared, str):
        return None
    expression = re.sub(r"\s*/\s*", " OR ", declared)
    # Reduce explicit parenthesized alternatives without removing a conjunction.
    def choose_group(match):
        selected = license_choice(match.group(1))
        return "(" + selected + ")" if selected else match.group(0)
    previous = None
    while previous != expression:
        previous = expression
        expression = re.sub(r"\(([^()]+ OR [^()]+)\)", choose_group, expression)
    if not any(token in expression for token in ("AND", "WITH", "(", ")")):
        alternatives = expression.split(" OR ")
        for choice in ("Apache-2.0", "MIT", "BSD-3-Clause", "ISC"):
            if choice in alternatives:
                expression = choice
                break
    try:
        validate_conclusion(expression)
    except PackageInputError:
        return None
    return expression


def font_copyright(data):
    """Read original copyright strings from a TrueType name table, without editing it."""
    count = struct.unpack_from(">H", data, 4)[0]
    tables = {data[12 + i * 16:16 + i * 16]: struct.unpack_from(">II", data, 20 + i * 16)
              for i in range(count)}
    offset, size = tables[b"name"]
    require(offset + size <= len(data), "font name table is truncated")
    _, count, strings = struct.unpack_from(">HHH", data, offset)
    result = set()
    for index in range(count):
        platform, _, _, name_id, length, start = struct.unpack_from(">HHHHHH", data, offset + 6 + index * 12)
        if name_id != 0:
            continue
        require(strings + start + length <= size, "font name string is truncated")
        raw = data[offset + strings + start:offset + strings + start + length]
        result.add(raw.decode("utf-16-be" if platform in (0, 3) else "mac_roman").strip())
    return "\n".join(sorted(result))


def license_atoms(data):
    """Recognize only distinctive complete grant text in the retained original file."""
    text = data.decode("utf-8", errors="replace")
    folded = " ".join(text.lower().split())
    result = set()
    if "apache license" in folded and "version 2.0" in folded and "grant of copyright license" in folded:
        result.add("Apache-2.0")
    if "permission is hereby granted, free of charge" in folded and "the software is provided" in folded:
        result.add("MIT")
    if "permission to use, copy, modify, and distribute this software for any purpose with or without fee" in folded:
        result.add("ISC")
    if "unicode license v3" in folded:
        result.add("Unicode-3.0")
    if "sil open font license" in folded and "version 1.1" in folded:
        result.add("OFL-1.1")
    if "ubuntu font licence" in folded and "version 1.0" in folded:
        result.add("Ubuntu-font-1.0")
    if "bitstream vera" in folded and "bitstream" in folded and "font" in folded:
        result.add("Bitstream-Vera")
    if "microsoft reciprocal license" in folded and "reciprocal grants" in folded:
        result.add("MS-RL")
    if "redistribution and use in source and binary forms" in folded and "this software is provided" in folded:
        if "neither the name" in folded:
            result.add("BSD-3-Clause")
        elif re.search(r"(?:^|\s)2[.)]", folded) and not re.search(r"(?:^|\s)3[.)]", folded):
            result.add("BSD-2-Clause")
    if "boost software license" in folded and "version 1.0" in folded:
        result.add("BSL-1.0")
    if "this software is provided 'as-is'" in folded and "altered source versions must be plainly marked" in folded:
        result.add("Zlib")
    return result


def copyright_lines(sources):
    result = set()
    for _, data in sources:
        for line in data.decode("utf-8", errors="replace").splitlines():
            if re.search(r"copyright\s*(?:\(c\)|©|\d{4})", line, re.I) and not any(
                    token in line.lower() for token in ("[yyyy]", "<year>", "[year]", "yyyy", "your name")):
                result.add(line.strip())
    return "\n".join(sorted(result)) or "NOASSERTION"


def document(root, name):
    return parse_json(read_owned(root, name))


def slug(value):
    return re.sub(r"[^A-Za-z0-9.-]", "-", value)


def cargo_scopes(metadata):
    """Traverse target-filtered normal edges, separating proc macros/build/dev edges.

    A normal dependency is a linkage candidate, not a binary-symbol observation.
    Dependencies reached in multiple contexts retain every context.
    """
    packages = {row["id"]: row for row in metadata["packages"]}
    nodes = {row["id"]: row for row in metadata["resolve"]["nodes"]}
    root = metadata["resolve"]["root"]
    require(root in nodes and root in packages, "Cargo root is missing")
    found = defaultdict(set)
    queue = deque([(root, "target-normal")])
    while queue:
        identifier, context = queue.popleft()
        if context in found[identifier]:
            continue
        require(identifier in packages and identifier in nodes, "Cargo dependency is missing")
        found[identifier].add(context)
        for dep in nodes[identifier]["deps"]:
            child = packages[dep["pkg"]]
            macro = any("proc-macro" in target["kind"] for target in child["targets"])
            for edge in dep["dep_kinds"]:
                kind = edge["kind"]
                next_context = ("development" if kind == "dev" else
                                "build-or-generated-code" if kind == "build" or macro else context)
                if context == "development":
                    next_context = context
                elif context == "build-or-generated-code" and kind != "dev":
                    next_context = context
                queue.append((dep["pkg"], next_context))
    return {key: sorted(value) for key, value in sorted(found.items())}


def checked_sources(root, rows):
    result = []
    for row in rows:
        data = read_owned(root, row["path"])
        require(sha256_bytes(data) == row["sha256"], "source notice hash differs")
        result.append((row["path"], data))
    return result


def wheel_metadata(raw):
    """Read metadata/notices without extracting or executing a wheel."""
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(name.casefold() for name in names)), "wheel members alias")
        for name in names:
            relative_path(name.rstrip("/"))
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        require(len(metadata) == 1, "wheel metadata is ambiguous")
        message = BytesParser(policy=policy.default).parsebytes(archive.read(metadata[0]))
        notices = []
        sboms = []
        for name in sorted(names):
            base = name.rsplit("/", 1)[-1].lower()
            if name.endswith("/"):
                continue
            if any(word in base for word in ("license", "copying", "notice", "authors")):
                require(archive.getinfo(name).file_size <= 8 * 1024 * 1024, "notice is oversized")
                notices.append((name, archive.read(name)))
            if base.endswith(".json") and ("sbom" in name.lower() or "cyclonedx" in name.lower()):
                require(archive.getinfo(name).file_size <= 16 * 1024 * 1024, "SBOM is oversized")
                sboms.append((name, archive.read(name)))
        declared = message.get("License-Expression") or message.get("License")
        return message, declared, notices, sboms


class Packet:
    def __init__(self):
        self.files = {}
        self.components = []
        self.evidence = []
        self.pending = []

    def put(self, name, data):
        relative_path(name)
        require(name not in self.files or self.files[name] == data, "output path collision")
        self.files[name] = data

    def component(self, *, identifier, name, version, kind, digest, location,
                  declared, sources, scope, pending, origins=None):
        require(not any(row["id"] == identifier for row in self.components), "duplicate component")
        notices = []
        for index, (source_name, data) in enumerate(sources):
            target = f"legal/NOTICES/{identifier}/{index:03}-{slug(Path(source_name).name)}"
            self.put(target, data)
            notices.append({"path": target, "sha256": sha256_bytes(data)})
        # No choice of license, copyright ownership or source duty is inferred from a name.
        row = {"id": identifier, "name": name, "version": version, "kind": kind,
               "sha256": digest, "download_location": location,
               "copyright_text": "NOASSERTION", "license_declared": (declared if isinstance(declared, str)
                   else json.dumps(declared, sort_keys=True) if declared else "NOASSERTION"),
               "license_concluded": "NOASSERTION", "license_files": [],
               "notice_required": None, "notice_files": notices,
               "source_offer_required": None, "source_offer_files": []}
        selected = license_choice(declared)
        if selected:
            atoms = set(re.findall(r"[A-Za-z0-9.-]+", selected)) - {"AND", "WITH"}
            covered = set()
            for index, (source_name, data) in enumerate(sources):
                ids = license_atoms(data) & atoms
                if not ids:
                    continue
                target = f"legal/LICENSES/{identifier}/{index:03}-{slug(Path(source_name).name)}"
                self.put(target, data)
                row["license_files"].append({"path": target, "sha256": sha256_bytes(data), "license_ids": sorted(ids)})
                covered.update(ids)
            if covered == atoms:
                row["license_concluded"] = selected
                row["copyright_text"] = copyright_lines(sources)
                row["notice_required"] = True
                if not atoms & {"AGPL-3.0-only", "AGPL-3.0-or-later", "GPL-2.0-only", "GPL-3.0-only", "MPL-2.0", "MS-RL"}:
                    row["source_offer_required"] = False
                    pending = [item for item in pending if item != "notice-and-source-duty"]
                if row["copyright_text"] != "NOASSERTION":
                    pending = [item for item in pending if item != "license-choice-and-original-copyright"]
        self.components.append(row)
        self.evidence.append({"id": identifier, "scope": scope, "origins": origins or [], "original_license_declaration": declared,
                              "retained_notice_count": len(notices)})
        self.pending.append({"id": identifier, "items": sorted(set(pending))})


def verify_observation(observation_root, source, architecture):
    observation = document(observation_root, "preparation-observation.json")
    require(observation["architecture"] == architecture
            and observation["status"] == "unapproved"
            and observation["candidate_approval"] is False
            and observation["publishable"] is False, "observation scope differs")
    profile = "windows-" + ARCHITECTURES[architecture]
    require(observation["release_profile"] == profile, "observation profile differs")
    inputs = observation_root / "unsigned-inputs"
    actual = {path.relative_to(inputs).as_posix() for path in inputs.rglob("*") if path.is_file()}
    require(actual == set(observation["files"]), "observation file set differs")
    for name, record in observation["files"].items():
        raw = read_owned(inputs, name)
        require(len(raw) == record["size"] and sha256_bytes(raw) == record["sha256"],
                "observed file bytes differ")
    source_inventory = document(observation_root / "source", "source-inventory.json")
    require(sha256_bytes(read_owned(observation_root / "source", "source-inventory.json"))
            == observation["source_files"]["source-inventory.json"]["sha256"], "source observation inventory changed")
    bindings = {}
    for name in sorted(profile_source_inputs(profile)):
        digest = sha256_bytes(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=source))
        require(digest == source_inventory["files"][name]["sha256"], "source input changed after observation")
        bindings[name] = digest
    payload = read_owned(inputs, "payload/lib/cua/payload.json")
    require(sha256_bytes(payload) == observation["payload_sha256"], "payload observation differs")
    require(sha256_bytes(read_owned(inputs, "payload/lib/cua/installed-inventory.json"))
            == observation["installed_inventory_sha256"], "installed inventory observation differs")
    return observation, inputs, bindings


def add_cargo(packet, inputs, source, target_collection):
    evidence = {row["id"]: row for row in target_collection["components"]}
    lock = tomllib.loads(read_owned(source, "Cargo.lock").decode())
    checksums = {(row["name"], row["version"]): row.get("checksum") for row in lock["package"]}
    scopes = defaultdict(set)
    identities = {}
    graphs = {}
    for filename in ("cargo-metadata.json", "ba-cargo-metadata.json"):
        metadata = document(inputs, filename)
        graph = cargo_scopes(metadata)
        graphs[filename] = graph
        for row in metadata["packages"]:
            key = (row["name"], row["version"])
            if row["id"] in graph:
                scopes[key].update(graph[row["id"]])
                identities[key] = row
    for key, contexts in sorted(scopes.items()):
        row = identities[key]
        identifier = "cargo-" + row["name"] + "-" + row["version"]
        # Build and proc-macro inputs remain visible in the graph, but are not
        # silently promoted to shipped components or treated as obligation-free.
        if "target-normal" not in contexts or row["source"] is None:
            continue
        prior = evidence.get(identifier)
        sources = checked_sources(source / target_collection["_root"], prior["source_files"]) if prior else []
        require(checksums.get(key), "Cargo archive checksum is unavailable")
        if prior:
            require(prior["sha256"] == checksums[key], "Cargo source archive changed")
        packet.component(identifier=slug(identifier), name=row["name"], version=row["version"],
                         kind="cargo", digest=checksums[key],
                         location=f"https://static.crates.io/crates/{row['name']}/{row['name']}-{row['version']}.crate",
                         declared=row["license"], sources=sources, scope="target-normal-dependency",
                         pending=["license-choice-and-original-copyright", "notice-and-source-duty"], origins=sorted(contexts))
    packet.put("cargo-scope.json", canonical_json({
        "schema": 1, **BOUNDARY, "graphs": graphs,
        "limitation": "Target-filtered dependency reachability is not a linker map. Build and proc-macro outputs need a generated-code review.",
    }))


def add_wheels(packet, inputs, source, target_collection):
    prior = {(row["name"].lower().replace("_", "-"), row["version"]): row
             for row in target_collection["components"] if row["kind"] == "wheel"}
    wheelhouse = document(inputs, "wheelhouse/wheelhouse.json")
    for wheel in wheelhouse["wheels"]:
        raw = read_owned(inputs, "wheelhouse/" + wheel["filename"])
        require(sha256_bytes(raw) == wheel["sha256"] and len(raw) == wheel["size"], "wheel identity differs")
        metadata, declared, notices, sboms = wheel_metadata(raw)
        name = metadata["Name"].lower().replace("_", "-")
        require(name == wheel["name"].lower().replace("_", "-") and metadata["Version"] == wheel["version"],
                "wheel metadata identity differs")
        old = prior.get((name, wheel["version"]))
        location = old["download_location"] if old and old["sha256"] == wheel["sha256"] else (
            "https://github.com/MONTBRAIN/vadgr-computer-use/actions/runs/"
            + str(document(source, "packaging/cua/cua-profile-catalog.json")["producer"]["run_id"])) if name == "vadgr-computer-use" else None
        if location is None:
            native = document(source, "packaging/cua/native-wheel-manifest.json")
            matched = [row for row in native["wheels"] if row["sha256"] == wheel["sha256"]
                       and row["filename"] == wheel["filename"] and row["target"] == wheelhouse["release_profile"]]
            require(len(matched) == 1, "native wheel acquisition provenance is unavailable")
            location = f"https://github.com/{native['repository']}/actions/runs/{native['run_id']}"
        require(location is not None, "wheel acquisition provenance is unavailable")
        identifier = slug("wheel-" + name + "-" + wheel["version"])
        issues = ["license-choice-and-original-copyright", "notice-and-source-duty"]
        if name == "nodriver":
            issues += ["AGPL-corresponding-source-and-combined-work-review"]
        if sboms:
            issues += ["target-specific-nested-SBOM-scope"]
        packet.component(identifier=identifier, name=name, version=wheel["version"], kind="wheel",
                         digest=wheel["sha256"], location=location, declared=declared,
                         sources=notices, scope="installed-wheel", pending=issues)
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            native = {}
            for member in archive.namelist():
                if Path(member).suffix.lower() not in (".exe", ".dll", ".pyd"):
                    continue
                value = archive.read(member)
                candidates = [path for path in (inputs / "payload/lib/cua/environments").rglob(Path(member).name)
                              if path.is_file() and path.as_posix().endswith("/site-packages/" + member)]
                require(len(candidates) == 1 and read_owned(inputs, candidates[0].relative_to(inputs).as_posix()) == value,
                        "installed native wheel member differs")
                native[candidates[0].relative_to(inputs).as_posix()] = sha256_bytes(value)
            packet.evidence[-1]["observed_native_members"] = native
        for index, (member, data) in enumerate(sboms):
            path = f"nested-sboms/{identifier}/{index:03}-{slug(Path(member).name)}"
            packet.put(path, data)


def add_supplement(packet, source, collection, architecture):
    root = source / "packaging/legal-review/supplement"
    supplement = document(root, "collection.json")
    # Preserve exact source evidence. Inclusion here is not a claim that every
    # optional component in an upstream build catalogue reaches the target.
    for row in supplement["groups"]["nested_wheels"]["registry_components"]:
        origins = [item for item in row["origins"] if item["target"] == "windows-" + ARCHITECTURES[architecture]]
        if not origins:
            continue
        packet.component(identifier="nested-" + slug(row["id"]), name=row["name"], version=row["version"],
                         kind="cargo", digest=row["sha256"], location=row["download_location"],
                         declared=row["license_declared"], sources=checked_sources(root, row["source_files"]),
                         scope="target-wheel-SBOM-component-not-link-proof", origins=origins,
                         pending=["nested-build-versus-linked-scope", "license-choice-and-original-copyright",
                                  "notice-and-source-duty"])
    for row in supplement["groups"]["native_sources"]["components"]:
        if row["id"] == ("tk-windows-bin-8614" if architecture == "x64" else "tk-windows-bin-8612"):
            continue
        packet.component(identifier="native-" + slug(row["id"]), name=row["name"], version=row["version"],
                         kind="framework" if row["id"] == "wix" else "runtime", digest=row["sha256"],
                         location=row["download_location"], declared=row["license_declared"],
                         sources=checked_sources(root, row["source_files"]), scope="source-build-input-needs-binary-mapping",
                         pending=["target-binary-to-source-mapping", "license-choice-and-original-copyright",
                                  "corresponding-source-delivery" if row["id"] == "wix" else "notice-and-source-duty"])
    for row in collection["components"]:
        if row["kind"] not in ("runtime", "framework"):
            continue
        packet.component(identifier=slug(row["id"]), name=row["name"], version=row["version"], kind=row["kind"],
                         digest=row["sha256"], location=row["download_location"], declared=row["license_declared"],
                         sources=checked_sources(source / collection["_root"], row["source_files"]),
                         scope="runtime-archive" if row["kind"] == "runtime" else "installer-build-framework",
                         pending=["target-binary-to-source-mapping", "license-choice-and-original-copyright", "notice-and-source-duty"])


def add_archives_and_fonts(packet, inputs, archive_root):
    for identifier, (filename, expected) in SOURCE_ARCHIVES.items():
        raw = read_owned(archive_root, filename)
        require(sha256_bytes(raw) == expected, "corresponding source archive differs")
        path = "legal/SOURCE-OFFERS/" + filename
        packet.put(path, raw)
        component = next(row for row in packet.components if row["id"] == identifier)
        component["source_offer_required"] = True
        component["source_offer_files"] = [{"path": path, "sha256": expected}]
        # This delivers the actual upstream source, not a promise or a mutable URL.
        # It does not establish completeness for an AGPL combined work or modified WiX code.
        issue = next(row for row in packet.pending if row["id"] == identifier)
        issue["items"] = [item for item in issue["items"] if item != "corresponding-source-delivery"]
        issue["items"].append("covered-combination-or-modification-source-completeness")
    raw = read_owned(archive_root, FONT_ARCHIVE)
    require(sha256_bytes(raw) == FONT_SHA256, "font crate differs")
    import io
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        binary = read_owned(inputs, "payload/vadgr.exe")
        for font, expression, license_name in (
                ("Hack-Regular", "MIT AND Bitstream-Vera", "Hack-Regular.txt"),
                ("NotoEmoji-Regular", "OFL-1.1", "OFL.txt"),
                ("Ubuntu-Light", "Ubuntu-font-1.0", "UFL.txt"),
                ("emoji-icon-font", "MIT", "emoji-icon-font-mit-license.txt")):
            member = f"epaint_default_fonts-0.36.1/fonts/{font}.ttf"
            data = archive.extractfile(member).read()
            require(data in binary, "font bytes are not present in observed daemon")
            license_member = f"epaint_default_fonts-0.36.1/fonts/{license_name}"
            notice = archive.extractfile(license_member).read()
            packet.component(identifier="asset-" + font, name=font, version="epaint_default_fonts-0.36.1",
                             kind="asset", digest=sha256_bytes(data),
                             location="https://static.crates.io/crates/epaint_default_fonts/epaint_default_fonts-0.36.1.crate",
                             declared=expression, sources=[(license_member, notice)],
                             scope="exact-full-font-bytes-found-in-payload/vadgr.exe",
                             origins=[{"archive_sha256": FONT_SHA256, "member": member,
                                       "binary_sha256": sha256_bytes(binary)}],
                             pending=["license-choice-and-original-copyright"])
            copyright_text = font_copyright(data)
            if copyright_text:
                packet.components[-1]["copyright_text"] = copyright_text
                if packet.components[-1]["license_concluded"] != "NOASSERTION":
                    packet.pending[-1]["items"] = []


def add_installed_python(packet, inputs, collection):
    runtime = next(row for row in collection["components"] if row["id"] == "runtime-cpython-3.12.14")
    site = inputs / "payload/lib/cua/python/3.12.14/Lib/site-packages"
    vendor_file = "pip/_vendor/vendor.txt"
    vendor_raw = read_owned(site, vendor_file)
    rows = re.findall(r"^\s*([A-Za-z0-9_-]+)==([^\s]+)\s*$", vendor_raw.decode(), re.M)
    require(len(rows) == 18, "runtime vendor catalogue changed")
    for name, version in rows:
        directory = "pkg_resources" if name == "setuptools" else name.lower().replace("-", "_")
        vendor_root = site / "pip/_vendor" / directory
        require(vendor_root.is_dir(), "runtime vendor directory is absent")
        members = {path.relative_to(vendor_root).as_posix(): sha256_bytes(read_owned(vendor_root, path.relative_to(vendor_root).as_posix()))
                   for path in vendor_root.rglob("*") if path.is_file()}
        notices = [(member, read_owned(vendor_root, member)) for member in sorted(members)
                   if any(token in Path(member).name.lower() for token in ("license", "copying", "notice"))]
        grants = set().union(*(license_atoms(raw) for _, raw in notices))
        # Multiple license files can cover different parts, not alternatives.
        declared = next(iter(grants)) if len(grants) == 1 else None
        packet.component(identifier="python-vendor-" + slug(name.lower()), name=name, version=version,
                         kind="runtime", digest=sha256_bytes(canonical_json(members)), location=runtime["download_location"],
                         declared=declared, sources=notices, scope="observed-runtime-vendored-tree",
                         origins=[{"archive_sha256": runtime["sha256"], "vendor_manifest_sha256": sha256_bytes(vendor_raw),
                                   "path": "payload/lib/cua/python/3.12.14/Lib/site-packages/pip/_vendor/" + directory,
                                   "file_count": len(members), "hash_basis": "canonical-relative-path-to-sha256-map"}],
                         pending=["license-choice-and-original-copyright", "notice-and-source-duty"])
    for metadata_path in sorted(site.glob("*.dist-info/METADATA")):
        message = BytesParser(policy=policy.default).parsebytes(read_owned(site, metadata_path.relative_to(site).as_posix()))
        notices = [(path.relative_to(site).as_posix(), read_owned(site, path.relative_to(site).as_posix()))
                   for path in metadata_path.parent.rglob("*") if path.is_file()
                   and any(token in path.name.lower() for token in ("license", "copying", "notice"))]
        packet.component(identifier="python-installed-" + slug(message["Name"]), name=message["Name"], version=message["Version"],
                         kind="runtime", digest=sha256_bytes(metadata_path.read_bytes()), location=runtime["download_location"],
                         declared=message.get("License-Expression") or message.get("License"), sources=notices,
                         scope="observed-runtime-distribution-metadata", pending=["license-choice-and-original-copyright", "notice-and-source-duty"],
                         origins=[{"archive_sha256": runtime["sha256"], "path": metadata_path.relative_to(inputs).as_posix(),
                                   "hash_basis": "exact-installed-METADATA"}])


def add_reviewed_helpers(packet, source, inputs, architecture):
    """Carry existing exact helper-only decisions, without extending them to outer files."""
    import io
    legal_name = f"packaging/cua/helper-legal/{ARCHITECTURES[architecture]}.json"
    raw_review = read_owned(source, legal_name)
    reviewed = parse_json(raw_review)
    require(reviewed["status"] == "approved" and reviewed["architecture"] == ARCHITECTURES[architecture]
            and reviewed["version"] == "0.7.9" and reviewed["source_offer_required"] is False
            and reviewed["scope"] == "cua-helper-input-redistribution-and-authenticode-transformation"
            and reviewed["source_commit"] == document(source, "packaging/cua/cua-profile-catalog.json")["source_commit"],
            "reviewed helper scope differs")
    root = inputs / "payload/lib/cua/environments"
    brokers = list(root.rglob("*broker*.zip"))
    relays = [path for path in root.rglob("vadgr-cua-host.exe") if "/browser/winhost/" in path.as_posix()]
    require(len(brokers) == len(relays) == 1, "helper closure is ambiguous")
    broker_raw = read_owned(inputs, brokers[0].relative_to(inputs).as_posix())
    members = {"vadgr-cua-host.exe": read_owned(inputs, relays[0].relative_to(inputs).as_posix())}
    with zipfile.ZipFile(io.BytesIO(broker_raw)) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), "broker members repeat")
        for member in archive.infolist():
            relative_path(member.filename)
            require(member.file_size <= 16 * 1024 * 1024, "broker member is oversized")
            members[member.filename] = archive.read(member)
    require(set(members) == set(reviewed["members"]), "reviewed helper members differ")
    for name, data in members.items():
        row = reviewed["members"][name]
        require(sha256_bytes(data) == row["input_sha256"] and len(data) == row["size"], "reviewed helper bytes differ")
    names = sorted({name for row in reviewed["members"].values() for name in row["license_and_notice_members"]})
    packet.component(identifier="runtime-cua-helper-closure-0.7.9", name="CUA Windows helper closure", version="0.7.9",
                     kind="runtime", digest=sha256_bytes(broker_raw),
                     location=f"https://github.com/MONTBRAIN/vadgr-computer-use/actions/runs/{reviewed['review_input']['run_id']}",
                     declared="Component-specific grants in the retained helper review", sources=[(name, members[name]) for name in names],
                     scope="exact-members-match-existing-helper-only-redistribution-review",
                     pending=["map-reviewed-helper-component-grants-to-SPDX"],
                     origins=[{"legal_review_sha256": sha256_bytes(raw_review), "legal_review_path": legal_name,
                               "broker_path": brokers[0].relative_to(inputs).as_posix(),
                               "relay_path": relays[0].relative_to(inputs).as_posix()}])
    packet.components[-1]["source_offer_required"] = False
    packet.components[-1]["notice_required"] = True
    packet.components[-1]["copyright_text"] = copyright_lines([(name, members[name]) for name in names])
    packet.put("reviewed-helper-inputs.json", raw_review)


def synthesize(source, observation_root, architecture, created, archive_root):
    observation, inputs, bindings = verify_observation(observation_root, source, architecture)
    target_root = f"packaging/legal-review/windows-{ARCHITECTURES[architecture]}"
    collection = document(source, target_root + "/collection.json")
    collection["_root"] = target_root
    packet = Packet()
    for name in sorted(REQUIRED_FILES):
        original = "packaging/legal/" + name.removeprefix("legal/")
        packet.put(name, read_owned(source, original))
    terms = packet.files["legal/TERMS.txt"]
    require(sha256_bytes(terms) == observation["terms"]["sha256"], "terms changed after observation")
    packet.put("legal/TERMS.rtf", render_rtf(terms.decode("utf-8")))
    add_cargo(packet, inputs, source, collection)
    add_wheels(packet, inputs, source, collection)
    add_supplement(packet, source, collection, architecture)
    add_archives_and_fonts(packet, inputs, archive_root)
    add_installed_python(packet, inputs, collection)
    add_reviewed_helpers(packet, source, inputs, architecture)
    components = sorted(packet.components, key=lambda row: row["id"])
    inventory = {"schema": 1, "created": created, "version": "0.5.0", "target": observation["target"],
                 "terms_version": "1.0", "terms_sha256": sha256_bytes(terms), "source_inputs": bindings,
                 "payload_manifest_sha256": observation["payload_sha256"], "components": components,
                 "coverage": {kind: {"status": "incomplete", "component_ids": [row["id"] for row in components if row["kind"] == kind]}
                              for kind in sorted(KINDS)}}
    packet.put("package-input-inventory.json", canonical_json(inventory))
    packet.put("legal/THIRD-PARTY-NOTICES.txt", aggregate_files(inventory, packet.files, "notice_files"))
    packet.put("legal/SOURCE-OFFER.txt", aggregate_files(inventory, packet.files, "source_offer_files"))
    sbom = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": "vadgr-0.5.0-" + observation["target"] + "-unreviewed",
            "documentNamespace": "https://spdx.org/spdxdocs/vadgr-review-" + sha256_bytes(canonical_json(inventory)),
            "creationInfo": {"created": created, "creators": ["Tool: vadgr-windows-legal-preparation"]},
            "documentComment": "Incomplete review inventory, including separately classified build-source candidates. Not an approved shipped-component SBOM.",
            "packages": [{"SPDXID": "SPDXRef-" + row["id"], "name": row["name"], "versionInfo": row["version"],
                          "downloadLocation": row["download_location"], "filesAnalyzed": False,
                          "checksums": [{"algorithm": "SHA256", "checksumValue": row["sha256"]}],
                          "licenseDeclared": row["license_concluded"], "licenseConcluded": row["license_concluded"],
                          "copyrightText": row["copyright_text"]}
                         for row in components]}
    packet.put("sbom/vadgr-0.5.0.spdx.json", canonical_json(sbom))
    review = {key: inventory[key] for key in ("schema", "version", "target", "terms_version", "terms_sha256", "source_inputs", "payload_manifest_sha256")}
    review.update({"status": "draft", "synthetic": False,
                   "inventory_sha256": sha256_bytes(packet.files["package-input-inventory.json"]),
                   "files": {name: sha256_bytes(raw) for name, raw in sorted(packet.files.items()) if name.startswith(("legal/", "sbom/")) or name == "README-OFFLINE.txt"},
                   "closures": dict.fromkeys(CLOSURES, False)})
    packet.put("package-input-review.json", canonical_json(review))
    by_reason = defaultdict(list)
    for row in packet.pending:
        for reason in row["items"]:
            by_reason[reason].append(row["id"])
    packet.put("review-ledger.json", canonical_json({
        "schema": 1, **BOUNDARY, "source_sha": observation["source"]["source_sha"],
        "trusted_sha": observation["source"]["trusted_sha"], "run_id": observation["source"]["run_id"],
        "observation_sha256": sha256_bytes(read_owned(observation_root, "preparation-observation.json")),
        "terms": {"version": "1.0", "sha256": sha256_bytes(terms), "status": "owner-approved-draft-retained-unchanged"},
        "components": sorted(packet.evidence, key=lambda row: row["id"]),
        "unresolved": sorted(packet.pending, key=lambda row: row["id"]),
        "unresolved_by_reason": {reason: sorted(ids) for reason, ids in sorted(by_reason.items())},
        "summary": {"component_candidates": len(components),
                    "retained_grant_choices": sum(row["license_concluded"] != "NOASSERTION" for row in components),
                    "unresolved_copyright": sum(row["copyright_text"] == "NOASSERTION" for row in components),
                    "rows_with_review_items": sum(bool(row["items"]) for row in packet.pending),
                    "scope_counts": {scope: sum(row["scope"] == scope for row in packet.evidence)
                                     for scope in sorted({row["scope"] for row in packet.evidence})}},
        "package_questions": ["actual-target-market-rights", "product-data-statements", "Cargo-linkage-and-generated-code-scope",
                              "Python-vendored-and-native-library-closure", "WiX-runtime-source-completeness-and-official-build-terms",
                              "nodriver-AGPL-source-and-combined-work-treatment"],
    }))
    packet.put("UNAPPROVED.txt", b"Incomplete legal review inputs. Not approved for signing, installation, publication or release.\n")
    return packet.files


def emit(files, output, verify):
    if verify:
        actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        require(actual == set(files), "generated packet file set differs")
        require(all(read_owned(output, name) == data for name, data in files.items()), "generated packet bytes differ")
        return
    require(not output.exists(), "output already exists")
    require(output.parent.is_dir() and not output.parent.is_symlink(), "output parent is unsafe")
    require(not any(parent.is_symlink() or getattr(parent, "is_junction", lambda: False)()
                    for parent in (output.parent, *output.parent.parents)), "output parent is linked")
    output.mkdir()
    for name, data in sorted(files.items()):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--architecture", choices=ARCHITECTURES, required=True)
    parser.add_argument("--created", required=True)
    parser.add_argument("--source-archives", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", args.created), "invalid creation time")
        files = synthesize(args.source_root.resolve(), args.observation.resolve(), args.architecture, args.created, args.source_archives.resolve())
        emit(files, args.output.absolute(), args.verify)
        print(f"Draft legal packet: {len(files)} exact files; approval remains blocked.")
        return 0
    except (PackageInputError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(f"Legal synthesis refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
