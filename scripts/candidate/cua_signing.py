"""Bind authorized installed inputs to native-signed outputs without executing them.

The Windows wrapper independently verifies every native signature before reseal.
The receipt comes only from the trusted signing process, never the candidate.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__:
    from scripts import cua_release_inputs as release
    from scripts.validate_package_inputs import (
        PackageInputError, canonical_json, parse_json, read_owned, relative_path,
        require, sha256_bytes, valid_hash,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import cua_release_inputs as release
    from validate_package_inputs import (
        PackageInputError, canonical_json, parse_json, read_owned, relative_path,
        require, sha256_bytes, valid_hash,
    )

PREFIX = "payload/lib/cua/"
NAMES = {"pre-payload.json", "pre-inventory.json", "payload.json",
         "installed-inventory.json", "input-output.json"}


def identity(data):
    return {"size": len(data), "sha256": sha256_bytes(data)}


def valid_identity(value):
    return (isinstance(value, dict) and set(value) == {"size", "sha256"}
            and type(value["size"]) is int and value["size"] >= 0 and valid_hash(value["sha256"]))


def native(name):
    return Path(name).suffix.lower() in (".exe", ".dll", ".pyd")


def authorized(auth):
    binding = auth["cua_inputs"]
    require(binding["target"] in ("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc"),
            "this signer transition requires a reviewed Windows target")
    require(set(binding) == {"target", "requirements_sha256", "wheel_manifest_sha256"}
            and all(valid_hash(binding[key]) for key in ("requirements_sha256", "wheel_manifest_sha256")),
            "invalid reviewed CUA binding")
    require(auth["cua_payload"] == {**binding, "installed_inventory_sha256":
                                   auth["cua_payload"]["installed_inventory_sha256"]}
            and valid_hash(auth["cua_payload"]["installed_inventory_sha256"]),
            "invalid authorized payload binding")
    files = auth["files"]
    require(isinstance(files, dict) and 0 < len(files) <= 100_000, "empty or oversized authorized file set")
    folded = set()
    for name, row in files.items():
        relative_path(name)
        require(name.casefold() not in folded and valid_identity(row), "invalid authorized file identity")
        folded.add(name.casefold())
    return files


def tree(root):
    require(root.is_absolute() and root.is_dir() and root.resolve() == root,
            "signing tree must be an absolute unlinked directory")
    result = {}
    for path in root.rglob("*"):
        require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
                "signing tree contains a link")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            result[name] = identity(read_owned(root, name))
        else:
            require(path.is_dir(), "signing tree contains a special file")
    return result


def snapshot(root, auth, output):
    files = authorized(auth)
    require(not output.exists() and not output.is_relative_to(root), "pre-signing records must be new and outside payload")
    require(tree(root) == files, "pre-signing tree differs from authorization")
    require(release.validate_payload(root / "payload/lib/cua", auth["cua_inputs"]) == auth["cua_payload"],
            "pre-signing CUA identity differs from authorization")
    payload = read_owned(root, PREFIX + "payload.json")
    inventory = read_owned(root, PREFIX + release.INVENTORY)
    output.mkdir()
    (output / "pre-payload.json").write_bytes(payload)
    (output / "pre-inventory.json").write_bytes(inventory)


def original(records, auth):
    files = authorized(auth)
    raw_payload = read_owned(records, "pre-payload.json")
    raw_inventory = read_owned(records, "pre-inventory.json")
    require(identity(raw_payload) == files[PREFIX + "payload.json"]
            and identity(raw_inventory) == files[PREFIX + release.INVENTORY]
            and sha256_bytes(raw_inventory) == auth["cua_payload"]["installed_inventory_sha256"],
            "pre-signing metadata differs from authorization")
    payload, inventory = parse_json(raw_payload), parse_json(raw_inventory)
    require(payload.get("schema") == 2 and type(payload["schema"]) is int
            and all(payload.get(key) == value for key, value in auth["cua_payload"].items()),
            "pre-signing payload binding differs")
    expected = {name.removeprefix(PREFIX): row for name, row in files.items()
                if name.startswith(PREFIX) and name not in (PREFIX + "payload.json", PREFIX + release.INVENTORY)}
    require(inventory == {"schema": 1, "target": auth["cua_inputs"]["target"], "files": expected}
            and type(inventory["schema"]) is int, "pre-signing inventory differs from authorized files")
    return payload, inventory


def reseal(root, auth, records, receipt):
    files = authorized(auth)
    payload, inventory = original(records, auth)
    require(set(tree(records)) == {"pre-payload.json", "pre-inventory.json"}, "signer records were already sealed")
    actual = tree(root)
    require(set(actual) == set(files), "signed file set differs from authorization")
    signed = {name for name in files if native(name)}
    require(isinstance(receipt, dict) and set(receipt) == signed, "signer receipt omits or adds a native file")
    for name, before in files.items():
        if name in signed:
            require(receipt[name] == {"input": before, "output": actual[name]},
                    "signer receipt differs from exact input or output bytes")
        else:
            require(actual[name] == before, "non-native input changed during signing")
    inventory["files"] = {name: actual[PREFIX + name] for name in inventory["files"]}
    final_inventory = canonical_json(inventory)
    final_payload = canonical_json({**payload, "installed_inventory_sha256": sha256_bytes(final_inventory)})
    actual[PREFIX + release.INVENTORY] = identity(final_inventory)
    actual[PREFIX + "payload.json"] = identity(final_payload)
    mapping = {name: {"input": row, "output": actual[name], "operation":
                     "authenticode" if name in signed else
                     "inventory" if name == PREFIX + release.INVENTORY else
                     "payload-manifest" if name == PREFIX + "payload.json" else "unchanged"}
               for name, row in files.items()}
    # Build and validate the complete record before replacing either runtime file.
    (records / "input-output.json").write_bytes(canonical_json(mapping))
    (records / release.INVENTORY).write_bytes(final_inventory)
    (records / "payload.json").write_bytes(final_payload)
    result = validate_records(records, auth)
    (root / PREFIX / release.INVENTORY).write_bytes(final_inventory)
    (root / PREFIX / "payload.json").write_bytes(final_payload)
    require(release.validate_payload(root / "payload/lib/cua", auth["cua_inputs"]) == result["final"],
            "final CUA tree differs from sealed output")
    return result


def validate_records(records, auth):
    files = authorized(auth)
    before, inventory = original(records, auth)
    actual_records = tree(records)
    require(set(actual_records) == NAMES, "held CUA record set differs")
    mapping = parse_json(read_owned(records, "input-output.json"))
    require(set(mapping) == set(files), "input-output mapping omits or adds a file")
    for name, row in mapping.items():
        operation = ("authenticode" if native(name) else
                     "inventory" if name == PREFIX + release.INVENTORY else
                     "payload-manifest" if name == PREFIX + "payload.json" else "unchanged")
        require(set(row) == {"input", "output", "operation"} and valid_identity(row["input"])
                and row["input"] == files[name]
                and valid_identity(row["output"]) and row["operation"] == operation,
                "input-output mapping has an unauthorized transform")
        if operation == "unchanged":
            require(row["output"] == row["input"], "non-native input changed in held mapping")
    raw_inventory = read_owned(records, release.INVENTORY)
    raw_payload = read_owned(records, "payload.json")
    expected_inventory = {**inventory, "files": {name: mapping[PREFIX + name]["output"]
                                                for name in inventory["files"]}}
    require(raw_inventory == canonical_json(expected_inventory), "final inventory and mapped outputs differ")
    require(raw_payload == canonical_json({**before, "installed_inventory_sha256": sha256_bytes(raw_inventory)}),
            "final payload changed approved inputs")
    for name, raw in ((release.INVENTORY, raw_inventory), ("payload.json", raw_payload)):
        require(mapping[PREFIX + name]["output"] == identity(raw), "final metadata mapping differs")
    return {"pre_signing": auth["cua_payload"],
            "final": {**auth["cua_inputs"], "installed_inventory_sha256": sha256_bytes(raw_inventory)},
            "hashes": {"cua/" + name: row["sha256"] for name, row in actual_records.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("snapshot", "reseal", "verify"))
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    try:
        auth = parse_json(args.authorization.read_bytes())
        records = args.records.absolute()
        if args.mode == "snapshot":
            snapshot(args.root.resolve(), auth, records)
        elif args.mode == "reseal":
            reseal(args.root.resolve(), auth, records, parse_json(args.receipt.read_bytes()))
        else:
            validate_records(records, auth)
            if args.root:
                mapping = parse_json(read_owned(records, "input-output.json"))
                require(tree(args.root.resolve()) == {name: row["output"] for name, row in mapping.items()},
                        "final installed files changed after reseal")
    except (PackageInputError, KeyError, TypeError, ValueError, OSError, AttributeError):
        print("CUA signing transition refused; no candidate can proceed.", file=sys.stderr)
        return 1
    print("CUA input and output records verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
