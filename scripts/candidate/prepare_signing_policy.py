"""Derive unsigned review inputs, never signature identities or legal approval."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.candidate import cua_helpers as helpers
from scripts.cua_wheelhouse import binary_architecture
from scripts.validate_package_inputs import (
    PackageInputError, parse_json, read_owned, relative_path, require, sha256_bytes,
)

CATALOG = "_internal/predecessor-catalog.json"
RELEASE_KEYS = {"version", "archive_sha256", "broker_relative_path", "broker_sha256",
                "manifest_sha256", "protocol_min", "protocol_max"}
REVIEW_FIELDS = sorted(helpers.POLICY_KEYS - {"input_sha256"})


def predecessor_policy(archive, architecture):
    """The retained native broker, not a guessed release list, supplies the rows."""
    helpers.pair(architecture)
    members = helpers.archive_members(archive)
    require(CATALOG in members, "embedded predecessor catalog absent")
    value = parse_json(members[CATALOG])
    require(set(value) == {"schema", "target", "releases"}
            and type(value["schema"]) is int and value["schema"] == 1
            and value["target"] == architecture + "-pc-windows-msvc"
            and isinstance(value["releases"], list), "predecessor catalog schema differs")
    versions = []
    for row in value["releases"]:
        require(isinstance(row, dict) and set(row) == RELEASE_KEYS
                and row["broker_relative_path"] == "vadgr-cua-browser-broker.exe"
                and type(row["protocol_min"]) is int and row["protocol_min"] == 1
                and type(row["protocol_max"]) is int and row["protocol_max"] == 1,
                "predecessor release schema differs")
        for key in ("archive_sha256", "broker_sha256", "manifest_sha256"):
            helpers.digest(row[key])
        versions.append(row["version"])
    require(versions == (["0.7.6", "0.7.7", "0.7.8"] if architecture == "x86_64" else []),
            "predecessor release set differs")
    return helpers.canonical(value)


def check_predecessors(policy_raw, archive, architecture):
    helpers.document(policy_raw)
    require(policy_raw == predecessor_policy(archive, architecture),
            "predecessor policy differs from embedded catalog")


def observed_bytes(root, inventory, name):
    relative_path(name)
    require(name in inventory and isinstance(inventory[name], dict), "observed input absent")
    row = inventory[name]
    require(type(row.get("size")) is int and row["size"] >= 0, "observed size absent")
    helpers.digest(row.get("sha256"))
    data = read_owned(root, name)
    require(sha256_bytes(data) == row["sha256"] and len(data) == row["size"],
            "observed input bytes differ")
    return data


def review_inputs(observation_raw, root):
    """Measure every declared native file and preserve an explicit review boundary."""
    observation = parse_json(observation_raw)
    require(type(observation.get("schema")) is int and observation["schema"] == 1
            and observation.get("candidate_approval") is False
            and observation.get("publishable") is False,
            "expected unapproved preparation observation")
    architecture = {"x64": "x86_64", "arm64": "aarch64"}.get(observation.get("architecture"))
    require(architecture is not None, "unsupported preparation architecture")
    profile = "windows-" + architecture
    require(observation.get("release_profile") == profile
            and observation.get("target") == architecture + "-pc-windows-msvc",
            "preparation target differs")
    inventory, executables = observation.get("files"), observation.get("executable_hashes")
    require(isinstance(inventory, dict) and isinstance(executables, dict), "preparation inventory absent")
    folded = set()
    for name, row in inventory.items():
        relative_path(name)
        key = unicodedata.normalize("NFC", name).casefold()
        require(key not in folded and isinstance(row, dict), "preparation paths collide")
        folded.add(key)
        if name.lower().endswith((".exe", ".dll", ".pyd")):
            require(row.get("format") == "pe", "native input omitted from inventory")
    native = {name: row.get("sha256") for name, row in inventory.items() if row.get("format") == "pe"}
    require(native and executables == native, "preparation native membership differs")
    suffix = "computer_use/browser/profiles/" + profile + "/cua-profile-manifest.json"
    matches = [name for name in inventory if name.startswith("payload/") and name.endswith("/" + suffix)]
    require(len(matches) == 1, "installed role manifest absent or ambiguous")
    manifest_path = matches[0]
    manifest_raw = observed_bytes(root, inventory, manifest_path)
    manifest = parse_json(manifest_raw)
    require(manifest.get("release_profile") == profile and isinstance(manifest.get("helpers"), dict),
            "installed role manifest profile differs")
    prefix = manifest_path.removesuffix(suffix)
    located, data = {}, {}
    for role in ("relay", "archive"):
        row = manifest["helpers"].get(role)
        require(isinstance(row, dict), "helper role absent")
        relative_path(row.get("path"))
        path = prefix + row["path"]
        data[role] = observed_bytes(root, inventory, path)
        require(row.get("sha256") == sha256_bytes(data[role]) and row.get("size") == len(data[role]),
                "helper role bytes differ")
        located[role] = path
    require(located["relay"] in native, "shared relay absent from native inventory")
    rows = {}
    for name in sorted(native):
        contents = observed_bytes(root, inventory, name)
        require(binary_architecture(contents) == ("pe", architecture)
                and inventory[name].get("architecture") == architecture,
                "observed PE architecture differs")
        if name == located["relay"]:
            continue
        require(name.startswith("payload/") or name == "ba-functions.dll", "unexpected outer input location")
        rows[name] = {"input_sha256": native[name], "size": len(contents),
                      "review_status": "required", "required_fields": REVIEW_FIELDS}
    ledger = {"schema": 1, "status": "review-input-only", "signing_approved": False,
              "architecture": architecture, "release_profile": profile,
              "observation_sha256": sha256_bytes(observation_raw),
              "role_manifest_sha256": sha256_bytes(manifest_raw),
              "excluded_shared_relay": {"path": located["relay"], "sha256": native[located["relay"]]},
              "broker_archive_sha256": sha256_bytes(data["archive"]), "files": rows}
    return ledger, predecessor_policy(data["archive"], architecture)


def check_outer(policy_raw, ledger):
    """Structural review only; native trust and legal authorization remain separate."""
    policy = helpers.document(policy_raw)
    require(isinstance(policy, dict) and set(policy) == {"schema", "files"}
            and type(policy["schema"]) is int and policy["schema"] == 1
            and isinstance(policy["files"], dict) and set(policy["files"]) == set(ledger["files"]),
            "outer policy membership differs")
    for name, row in policy["files"].items():
        require(isinstance(row, dict) and set(row) == helpers.POLICY_KEYS
                and row["input_sha256"] == ledger["files"][name]["input_sha256"],
                "outer policy input differs")
        require(row["trust_class"] in ("publisher-sign", "vendor-preserve")
                and isinstance(row["signer"], str) and bool(row["signer"].strip())
                and row["digest_algorithm"] == "sha256" and row["timestamp_algorithm"] == "rfc3161-sha256",
                "outer signature review incomplete")
        for field in ("signer_policy_sha256", "legal_approval_sha256", "certificate_sha256", "chain_root_sha256"):
            helpers.digest(row[field])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--ledger-out", type=Path)
    parser.add_argument("--predecessors-out", type=Path)
    parser.add_argument("--check-predecessors", type=Path)
    parser.add_argument("--check-outer", type=Path)
    args = parser.parse_args()
    try:
        require(any((args.ledger_out, args.predecessors_out, args.check_predecessors, args.check_outer)),
                "no review output or check selected")
        ledger, predecessors = review_inputs(read_owned(args.observation.parent, args.observation.name), args.inputs)
        if args.check_predecessors:
            require(read_owned(args.check_predecessors.parent, args.check_predecessors.name) == predecessors,
                    "predecessor policy differs from observed broker")
        if args.check_outer:
            check_outer(read_owned(args.check_outer.parent, args.check_outer.name), ledger)
        outputs = [(path, raw) for path, raw in ((args.ledger_out, helpers.canonical(ledger)),
                                                (args.predecessors_out, predecessors)) if path is not None]
        require(len({path.absolute() for path, _ in outputs}) == len(outputs)
                and all(not path.exists() for path, _ in outputs), "review output already exists")
        for path, raw in outputs:
            with path.open("xb") as stream:
                stream.write(raw)
        print(f"Verified {len(ledger['files'])} outer inputs for {ledger['architecture']}; no signing or legal approval.")
        return 0
    except (PackageInputError, OSError):
        print("Signing policy preparation refused: invalid, changed, incomplete or unavailable review inputs.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
