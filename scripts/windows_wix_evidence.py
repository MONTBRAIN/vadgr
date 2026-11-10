"""Capture and bind unsigned WiX container membership, never redistribution approval.

Capture runs only a separately hash-pinned extraction tool, never a package or
payload. Offline import requires an independently retained observation digest.
"""

import argparse
from collections import Counter
import os
from pathlib import Path
import subprocess
from xml.etree import ElementTree

if __package__:
    from scripts.candidate_artifacts import verify_pe
    from scripts.generate_windows_payload_wxs import wix_id
    from scripts.windows_runtime_evidence import BOUNDARY, TARGETS, file_record, identity as valid_identity, tree
    from scripts.validate_package_inputs import canonical_json, parse_json, read_owned, relative_path, require, sha256_bytes
else:
    from candidate_artifacts import verify_pe
    from generate_windows_payload_wxs import wix_id
    from windows_runtime_evidence import BOUNDARY, TARGETS, file_record, identity as valid_identity, tree
    from validate_package_inputs import canonical_json, parse_json, read_owned, relative_path, require, sha256_bytes


RECORD = "wix-membership.json"
SOURCE_REVISION = "b8977d6f88e7b68e000bac226a2814f236770570"
SOURCE_SHA256 = "aef765da7c8051919081235840a8fca10e6bc4f37aab83764a80974ffd1fe09b"
DIRECTORIES = ("msi", "ba", "containers")
BURN_NAMESPACE = "{http://wixtoolset.org/schemas/v4/2008/Burn}"


def package_names(architecture):
    require(architecture in TARGETS, "unknown WiX architecture")
    return {"msi": f"Vadgr-0.5.0-windows-{architecture}.msi",
            "bundle": f"Vadgr-0.5.0-windows-{architecture}-setup.exe"}


def xml(raw):
    text = raw.decode("utf-8-sig")
    require(len(raw) < 32 * 1024 * 1024 and "<!DOCTYPE" not in text and "<!ENTITY" not in text,
            "unsafe WiX extraction XML")
    return ElementTree.fromstring(text)


def references(raw):
    result = {}
    for node in xml(raw).iter():
        kind = node.tag.rsplit("}", 1)[-1]
        if kind not in {"File", "Binary", "Icon"}:
            continue
        attribute = "Source" if kind == "File" else "SourceFile"
        name = node.attrib.get(attribute, "").replace("\\", "/")
        if name.startswith("SourceDir/"):
            name = "msi/" + name.removeprefix("SourceDir/")
        relative_path(name)
        require(name.startswith("msi/"), "decompiled member escapes extraction")
        key = (kind, node.attrib.get("Id"))
        require(key[1] and key not in result, "duplicate decompiled member identity")
        result[key] = name
    require(bool(result), "empty MSI extraction references")
    require(len({name.casefold() for name in result.values()}) == len(result), "aliased MSI member references")
    return result


def burn_membership(extracted):
    """Check both manifest payload sets, including nonnative bootstrapper assets."""
    manifest = xml(extracted["ba"]["manifest.xml"])
    require(manifest.tag == BURN_NAMESPACE + "BurnManifest", "unknown Burn manifest format")
    ux = manifest.findall(BURN_NAMESPACE + "UX")
    require(len(ux) == 1, "Burn UX manifest is missing or duplicated")
    names, identifiers, sources = {"manifest.xml"}, set(), set()
    rows = []
    for node in ux[0].findall(BURN_NAMESPACE + "Payload"):
        name = node.attrib["FilePath"].replace("\\", "/")
        source, identifier = node.attrib["SourcePath"], node.attrib["Id"]
        relative_path(name)
        relative_path(source)
        require(identifier and identifier not in identifiers and source not in sources
                and name.casefold() not in {item.casefold() for item in names}, "aliased Burn UX payload")
        names.add(name)
        identifiers.add(identifier)
        sources.add(source)
        rows.append({"path": "ba/" + name, "manifest_id": identifier})
    require(names == set(extracted["ba"]) and ux[0].attrib.get("PrimaryPayloadId") in identifiers,
            "Burn UX extraction and manifest differ")
    payloads = manifest.findall(BURN_NAMESPACE + "Payload")
    require(len(payloads) == 1 and payloads[0].attrib.get("Packaging") == "embedded",
            "Burn package manifest set differs")
    node = payloads[0]
    container = node.attrib["Container"].replace("\\", "/")
    filename = node.attrib["FilePath"].replace("\\", "/")
    relative_path(container)
    relative_path(filename)
    name = container + "/" + filename
    require(set(extracted["containers"]) == {name}
            and node.attrib.get("FileSize") == str(len(extracted["containers"][name])),
            "Burn attached extraction and manifest differ")
    rows.append({"path": "containers/" + name, "manifest_id": node.attrib["Id"]})
    return sorted(rows, key=lambda row: row["path"])


def classify(root, observation, architecture):
    """Derive membership from retained extraction bytes, not a supplied classification."""
    names = package_names(architecture)
    require(observation["architecture"] == architecture and observation["target"] == TARGETS[architecture]
            and observation["status"] == "unapproved" and observation["candidate_approval"] is False
            and observation["publishable"] is False, "WiX preparation boundary differs")
    extracted = {directory: tree(root / directory) for directory in DIRECTORIES}
    burn = burn_membership(extracted)
    refs = references(read_owned(root, "msi.wxs"))
    require(set(refs.values()) == {"msi/" + name for name in extracted["msi"]},
            "MSI extraction and table references differ")
    expected = {}
    for path, row in observation["files"].items():
        if path.startswith("payload/lib/"):
            identifier = wix_id("payload", "PrivatePayload/" + path.removeprefix("payload/lib/"))
        elif path in {"payload/vadgr.exe", "payload/vadgr-app.exe"}:
            identifier = "VadgrBackendFile" if path.endswith("/vadgr.exe") else "VadgrApplicationFile"
        else:
            continue
        require(identifier not in expected, "observed payload identifier collides")
        expected[identifier] = (path, {key: row[key] for key in ("sha256", "size")})
    require({"VadgrBackendFile", "VadgrApplicationFile"} <= set(expected), "observed native payload absent")
    rows = []
    for identifier, (original, identity) in sorted(expected.items()):
        require(("File", identifier) in refs, "observed payload member missing from MSI")
        path = refs["File", identifier]
        data = read_owned(root, path)
        require(file_record(data) == identity, "MSI member differs from preparation")
        rows.append({"path": path, **identity, "scope": "exact-observed-payload", "observed_path": original})
    reports = {}
    for kind, filename in (("msi", "utilca.dll"), ("bundle", "wixstdba.exe")):
        report = parse_json(read_owned(root, f"wix-vendor-{kind}.json"))
        require(report["schema"] == 1 and report["wix_version"] == "7.0.0"
                and report["name"] == filename and report["architecture"] == architecture,
                "WiX vendor member identity differs")
        reports[kind] = {key: report[key] for key in ("sha256", "size")}
        require(valid_identity(reports[kind]), "invalid WiX vendor member hash")
    assigned = {row["path"] for row in rows}
    counts = Counter()
    ba_identity = {key: observation["files"]["ba-functions.dll"][key] for key in ("sha256", "size")}
    for directory in ("msi", "ba"):
        for name, data in sorted(extracted[directory].items()):
            path = directory + "/" + name
            if path in assigned:
                if data[:2] == b"MZ":
                    verify_pe(data, architecture)
                continue
            identity = file_record(data)
            if data[:2] != b"MZ":
                rows.append({"path": path, **identity, "scope": "extracted-nonnative-data"})
                continue
            verify_pe(data, architecture)
            if directory == "msi" and identity == reports["msi"] and path in {
                    value for (kind, _), value in refs.items() if kind == "Binary"}:
                role, component = "wix-util-custom-action", "framework-wixtoolset.util.wixext-7.0.0"
            elif directory == "ba" and identity == reports["bundle"]:
                role, component = "wix-standard-bootstrapper", "framework-wixtoolset.bal.wixext-7.0.0"
            elif directory == "ba" and identity == ba_identity:
                role, component = "exact-observed-ba-functions", "product-ba-functions"
            else:
                require(False, "unmapped native installer member")
            counts[role] += 1
            rows.append({"path": path, **identity, "scope": role, "component_id": component})
    require(counts == Counter({"wix-util-custom-action": 1, "wix-standard-bootstrapper": 1,
                              "exact-observed-ba-functions": 1}), "WiX native membership is incomplete or duplicated")
    # This product embeds one MSI. Extraction warnings cannot be mistaken for
    # success: an omitted or additional attached package fails the exact match.
    msi = read_owned(root, names["msi"])
    require(msi.startswith(bytes.fromhex("d0cf11e0a1b11ae1")), "MSI compound-file header absent")
    require(len(extracted["containers"]) == 1 and next(iter(extracted["containers"].values())) == msi,
            "Burn attached package set differs")
    bundle = read_owned(root, names["bundle"])
    engine = read_owned(root, "burn-engine.exe")
    verify_pe(bundle, architecture)
    verify_pe(engine, architecture)
    rows.append({"path": "burn-engine.exe", **file_record(engine), "scope": "detached-burn-engine",
                 "component_id": "framework-wixtoolset.sdk-7.0.0"})
    return {"schema": 1, **BOUNDARY, "architecture": architecture, "target": TARGETS[architecture],
        "members": sorted(rows, key=lambda row: row["path"]),
        "burn_manifest_members": burn,
        "packages": {kind: {"path": name, **file_record(read_owned(root, name))} for kind, name in names.items()},
        "build_package_source_revision": SOURCE_REVISION, "included_source_archive_sha256": SOURCE_SHA256,
        "limitation": "Exact extraction membership and preparation/vendor-report byte equality only. The retained producer command binds the detached engine to the bundle. This is not an independently reproduced WiX build, source-completeness conclusion, signature qualification, official-build agreement or legal approval."}


def inventory(root):
    files = tree(root)
    require(len({name.casefold() for name in files}) == len(files), "aliased WiX evidence paths")
    return {name: file_record(raw) for name, raw in files.items() if name != RECORD}


def validate_tool(tool):
    files = tool["files"]
    require(tool["version"].split("+", 1)[0] in {"7.0.0", "7.0.0.0"}
            and isinstance(files, dict) and "wix.exe" in files
            and len({name.casefold() for name in files}) == len(files)
            and all(valid_identity(value) for value in files.values())
            and tool["files_sha256"] == sha256_bytes(canonical_json(files)),
            "WiX extraction tool identity differs")
    for name in files:
        relative_path(name)


def validate(root, observation_root, architecture, expected_sha256):
    raw = read_owned(root, RECORD)
    require(sha256_bytes(raw) == expected_sha256, "retained WiX observation identity differs")
    record = parse_json(raw)
    observation_raw = read_owned(observation_root, "preparation-observation.json")
    require(record["schema"] == 1 and all(record.get(key) == value for key, value in BOUNDARY.items())
            and record["architecture"] == architecture
            and record["preparation_observation_sha256"] == sha256_bytes(observation_raw),
            "WiX observation preparation binding differs")
    require(record["files"] == inventory(root), "retained WiX file set or bytes differ")
    require(record["commands"] == extraction_commands(architecture), "WiX extraction commands differ")
    validate_tool(record["tool"])
    result = classify(root, parse_json(observation_raw), architecture)
    require(record["membership"] == result, "WiX derived membership differs")
    return record


def extraction_commands(architecture):
    names = package_names(architecture)
    eula = ["-acceptEula", "wix7"]
    return [[*eula, "msi", "decompile", names["msi"], "-x", "msi", "-o", "msi.wxs", "-intermediateFolder", "temporary/msi"],
            [*eula, "burn", "extract", names["bundle"], "-o", "containers", "-oba", "ba", "-intermediateFolder", "temporary/burn"],
            [*eula, "burn", "detach", names["bundle"], "-engine", "burn-engine.exe", "-intermediateFolder", "temporary/engine"]]


def capture(package_root, observation_root, architecture, tool_root, tool_digest, output):
    require(os.name == "nt", "WiX extraction requires Windows")
    require(not any(os.environ.get(name) for name in ("GH_TOKEN", "GITHUB_TOKEN", "ES_USERNAME", "ES_PASSWORD",
        "ES_TOTP_SECRET", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")), "WiX extraction must have no credentials")
    require(not output.exists() and output.parent.is_dir(), "WiX evidence output must be new")
    require(not any(output.resolve().is_relative_to(path.resolve()) for path in
                    (package_root, observation_root, tool_root)), "WiX output overlaps retained inputs")
    tool_files = {name: file_record(raw) for name, raw in tree(tool_root).items()}
    require(sha256_bytes(canonical_json(tool_files)) == tool_digest and "wix.exe" in tool_files,
            "WiX extraction tool closure differs")
    executable = tool_root / "wix.exe"
    version = subprocess.check_output([str(executable), "--version"], text=True, timeout=30).strip()
    tool = {"version": version, "files": tool_files, "files_sha256": tool_digest}
    validate_tool(tool)
    output.mkdir()
    for name in (*package_names(architecture).values(), "wix-vendor-msi.json", "wix-vendor-bundle.json"):
        (output / name).write_bytes(read_owned(package_root, name))
    before = inventory(output)
    commands = extraction_commands(architecture)
    for index, command in enumerate(commands):
        (output / command[-1]).mkdir(parents=True)
        result = subprocess.run([str(executable), *command], cwd=output, capture_output=True, timeout=600)
        require(result.returncode == 0, "WiX extraction command failed")
        (output / f"command-{index}.log").write_bytes(result.stdout + result.stderr)
    require(all(file_record(read_owned(output, name)) == value for name, value in before.items()),
            "WiX extraction changed package inputs")
    require(tool_files == {name: file_record(raw) for name, raw in tree(tool_root).items()}, "WiX extraction tool changed")
    observation_raw = read_owned(observation_root, "preparation-observation.json")
    record = {"schema": 1, **BOUNDARY, "architecture": architecture,
        "preparation_observation_sha256": sha256_bytes(observation_raw), "commands": commands,
        "tool": tool,
        "membership": classify(output, parse_json(observation_raw), architecture), "files": inventory(output)}
    (output / RECORD).write_bytes(canonical_json(record))
    return sha256_bytes(read_owned(output, RECORD))


def retain_in_packet(packet, root, observation_root, architecture, expected_sha256):
    record = validate(root, observation_root, architecture, expected_sha256)
    mapping = parse_json(packet.files["wix-source-mapping.json"])
    expected = {row["id"] for row in mapping["packages"]}
    require(expected == {"framework-wixtoolset." + name + "-7.0.0" for name in ("sdk", "bal.wixext", "util.wixext")}
            and all(row["source_commit"] == SOURCE_REVISION and row["included_source_sha256"] == SOURCE_SHA256
                    for row in mapping["packages"]), "WiX source package mapping differs")
    mapping["runtime_membership"] = record["membership"]
    mapping["runtime_membership_observation_sha256"] = expected_sha256
    mapping["remaining_artifact_evidence"] = "Retained extraction is bound. Exact source/build reproducibility and modifications remain separate questions."
    packet.put("producer-evidence/" + RECORD, read_owned(root, RECORD))
    packet.put("wix-runtime-membership.json", canonical_json(mapping))
    mapped = {identifier: [row for row in record["membership"]["members"]
                           if row.get("component_id") == identifier] for identifier in expected}
    require(all(len(rows) == 1 for rows in mapped.values()), "WiX component member binding differs")
    mapped["native-wix"] = [row for identifier in sorted(expected) for row in mapped[identifier]]
    for identifier, members in mapped.items():
        evidence = [row for row in packet.evidence if row["id"] == identifier]
        pending = [row for row in packet.pending if row["id"] == identifier]
        require(len(evidence) == len(pending) == 1, "WiX review component is missing or duplicated")
        evidence[0]["scope"] = "observed-installer-members-with-declared-build-source"
        evidence[0]["native_runtime_observation"] = {
            "path": "wix-runtime-membership.json", "sha256": sha256_bytes(packet.files["wix-runtime-membership.json"]),
            "source_commit": SOURCE_REVISION, "source_archive_sha256": SOURCE_SHA256, "members": members,
            "limitation": "Source revision declared by the retained build packages, not an independently reproduced binary build or a source-completeness decision."}
        pending[0]["items"] = [item for item in pending[0]["items"] if item != "target-binary-to-source-mapping"]
        pending[0]["items"] = sorted(set([*pending[0]["items"], "WiX-source-completeness-and-modification-review"]))
    # Only the missing member-to-declared-source question is replaced. Duties,
    # official-build conditions, modification scope and approval remain open.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "validate"))
    parser.add_argument("--architecture", choices=TARGETS, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--tool-root", type=Path)
    parser.add_argument("--tool-sha256")
    args = parser.parse_args()
    if args.command == "capture":
        require(args.package_root and args.tool_root and args.tool_sha256, "WiX capture inputs absent")
        print(capture(args.package_root.resolve(), args.observation.resolve(), args.architecture,
                      args.tool_root.resolve(), args.tool_sha256, args.root.resolve()))
    else:
        require(args.expected_sha256, "independent WiX observation digest absent")
        validate(args.root.resolve(), args.observation.resolve(), args.architecture, args.expected_sha256)
        print("Unapproved WiX membership validated. No signature or legal approval claimed.")


if __name__ == "__main__":
    main()
