#!/usr/bin/env python3
"""Native build matrix and complete-candidate admission. Never signs or executes input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tomllib

if __package__:
    from scripts.validate_package_inputs import PackageInputError
else:
    from validate_package_inputs import PackageInputError


ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class Refused(ValueError):
    """The bytes or their recorded producer do not match the release matrix."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024,
            "record missing, linked or oversized")
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def matrix():
    document = read(ROOT / "packaging/distribution-matrix.json")
    require(document["schema"] == 1 and document["version"] == "0.5.0", "matrix version mismatch")
    rows = document["targets"]
    require(len(rows) == 8 and len({r["target"] for r in rows}) == 8, "matrix must have eight unique targets")
    return rows


def remaining_builds(architecture=None, wsl_architecture=None):
    selected = {system + "-" + {"x64": "x86_64", "arm64": "aarch64"}[arch]
                for system, arch in (("windows", architecture), ("wsl", wsl_architecture)) if arch is not None}
    return [row for row in matrix() if row["target"] not in selected]


def binary_architecture(data):
    if len(data) >= 64 and data[:2] == b"MZ":
        offset = struct.unpack_from("<I", data, 0x3c)[0]
        require(offset <= len(data) - 6 and data[offset:offset + 4] == b"PE\0\0", "invalid PE header")
        machine = struct.unpack_from("<H", data, offset + 4)[0]
        require(machine in (0x8664, 0xaa64), "unsupported PE architecture")
        return "pe", {0x8664: "x86_64", 0xaa64: "aarch64"}[machine]
    if len(data) >= 64 and data[:6] == b"\x7fELF\x02\x01":
        machine = struct.unpack_from("<H", data, 18)[0]
        require(machine in (62, 183), "unsupported ELF architecture")
        return "elf", {62: "x86_64", 183: "aarch64"}[machine]
    if len(data) >= 32 and data[:4] == b"\xcf\xfa\xed\xfe":
        machine = struct.unpack_from("<I", data, 4)[0]
        require(machine in (0x1000007, 0x100000c), "unsupported Mach-O architecture")
        return "macho", {0x1000007: "x86_64", 0x100000c: "aarch64"}[machine]
    if len(data) >= 8 and data[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
        count = struct.unpack_from(">I", data, 4)[0]
        width = 20 if data[3] == 0xbe else 32
        require(count in (1, 2) and len(data) >= 8 + count * width, "invalid universal Mach-O header")
        architectures = []
        for index in range(count):
            cpu = struct.unpack_from(">I", data, 8 + index * width)[0]
            require(cpu in (0x1000007, 0x100000c), "unsupported universal Mach-O architecture")
            architectures.append({0x1000007: "x86_64", 0x100000c: "aarch64"}[cpu])
        require(len(set(architectures)) == count, "duplicate universal Mach-O architecture")
        return "macho", "+".join(sorted(architectures))
    raise Refused("missing or unsupported native executable header")


def verify_binary(path, target):
    require(path.is_file(), "native executable missing")
    with path.open("rb") as stream:
        data = stream.read(1024 * 1024)
    kind, architecture = binary_architecture(data)
    platform, expected = target.split("-", 1)
    require(expected in architecture.split("+") and kind == {"windows": "pe", "macos": "macho", "linux": "elf", "wsl": "elf"}[platform],
            "cross-architecture or cross-platform executable refused")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_payload(root, target, pins_path):
    spec = next(row for row in matrix() if row["target"] == target)
    manifest = read(root / "lib/cua/payload.json")
    pins = tomllib.loads(pins_path.read_text(encoding="utf-8"))
    native_pins = pins["targets"][spec["rust_target"]]
    cua_version = pins["cua"]
    foreign = set()
    if manifest.get("schema") == 3:
        if __package__:
            from scripts import cua_profiles
        else:
            import cua_profiles
        source = pins_path.resolve().parents[2]
        binding, _, catalog = cua_profiles.reviewed(source, ROOT, target)
        require(all(manifest.get(k) == value for k, value in binding.items()), "profile payload differs from reviewed input")
        cua_version = catalog["cua_version"]
        role_paths = [path for path in (root / "lib/cua").rglob("cua-profile-manifest.json")
                      if path.parent.name == target and path.parent.parent.name == "profiles"]
        require(len(role_paths) == 1, "profile payload has ambiguous input role manifest")
        role_path = role_paths[0]
        role = read(role_path)
        package = role_path.parents[4]
        names = [row["wheel_path"] for row in role["files"]]
        names += [f"computer_use/browser/profiles/{target}/cua-profile-manifest.json", "computer_use/browser/_profile_trust.py"]
        members = {name: cua_profiles.read_owned(package, name) for name in names}
        cua_profiles.validate_members(members, target, binding["cua_profile_manifest_sha256"])
        if target.startswith("wsl-"):
            foreign.add((package / role["helpers"]["relay"]["path"]).resolve())
    require(manifest.get("target") == spec["rust_target"]
            and manifest.get("cua_version") == cua_version
            and manifest.get("python_version") == pins["python"]
            and manifest.get("python_build") == pins["python_build"]
            and manifest.get("python_archive_sha256") == native_pins["python_sha256"]
            and manifest.get("uv_archive_sha256") == native_pins["uv_sha256"],
            "private runtime target, version or archive pin mismatch")
    checked = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            require(path.exists() and path.resolve().is_relative_to(root.resolve()),
                    "private runtime link missing or escapes payload")
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            head = stream.read(4)
        if head[:2] == b"MZ" or head in (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
            verify_binary(path, "windows-" + target.split("-", 1)[1] if path.resolve() in foreign else target)
            checked += 1
    require(checked > 0, "private runtime contains no native executable")
    return checked


def validate_manifest(manifest, directory):
    expected = {row["target"]: row for row in matrix()}
    rows = manifest["artifacts"]
    require(len(rows) == 8 and {row["target"] for row in rows} == set(expected),
            "complete candidate requires exactly eight unique final vehicles")
    names = set()
    for row in rows:
        spec = expected[row["target"]]
        require(row["name"] == spec["vehicle"] and row["kind"] == spec["kind"]
                and row["native_signature"] == spec["native_signature"], "final vehicle identity mismatch")
        require(row["name"] not in names, "duplicate final vehicle")
        names.add(row["name"])
        path = directory / row["name"]
        require(path.is_file() and not path.is_symlink(), "final vehicle absent or linked")
        require(type(row["size"]) is int and row["size"] > 0 and path.stat().st_size == row["size"]
                and digest(path) == row["sha256"], "final vehicle bytes mismatch")
        if spec["kind"] in ("burn", "appimage"):
            verify_binary(path, spec["target"])
    actual = {path.name for path in directory.iterdir()
              if path.name.startswith("Vadgr-") or path.suffix.lower() in (".exe", ".pkg", ".appimage", ".deb", ".rpm")}
    # The MSI is an internal authenticated package, never a public vehicle.
    require(actual == names, "unexpected or missing public vehicle")


def validate_complete(records):
    expected = {row["target"]: row for row in matrix()}
    require(len(records) == 8 and {row["target"] for row in records} == set(expected),
            "complete candidate requires exactly eight unique final targets")
    identities, artifact_ids = set(), set()
    for row in records:
        spec = expected[row["target"]]
        require(all(row.get(key) == value for key, value in spec.items()), "target matrix metadata mismatch")
        require(row.get("name") == spec["vehicle"] and row.get("status") == "final-verified",
                "unsigned, renamed or partial vehicle cannot close a complete candidate")
        require(type(row.get("size")) is int and row["size"] > 0 and SHA256.fullmatch(row.get("sha256", "")),
                "invalid final vehicle size or hash")
        require(SHA.fullmatch(row.get("source_sha", "")) and SHA.fullmatch(row.get("trusted_sha", "")),
                "candidate source or tooling identity missing")
        require(re.fullmatch(r"v0\.5\.0-rc-[1-9][0-9]*", row.get("candidate_id", "")),
                "candidate identifier missing or malformed")
        require(type(row.get("run_attempt")) is int and row["run_attempt"] == 1
                and re.fullmatch(r"[1-9][0-9]*", str(row.get("run_id", ""))), "candidate run identity invalid")
        require(type(row.get("artifact_id")) is int and row["artifact_id"] > 0
                and re.fullmatch(r"sha256:[0-9a-f]{64}", row.get("artifact_digest", "")), "immutable artifact identity missing")
        require(row["artifact_id"] not in artifact_ids, "one artifact cannot stand in for two native targets")
        artifact_ids.add(row["artifact_id"])
        identities.add(tuple(row.get(key) for key in ("source_sha", "trusted_sha", "candidate_id", "run_id", "run_attempt")))
    require(len(identities) == 1, "mixed candidate source, tooling or run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("matrix")
    generate.add_argument("--except-windows", choices=("x64", "arm64"))
    generate.add_argument("--except-wsl", choices=("x64", "arm64"))
    check = commands.add_parser("manifest")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--directory", type=Path, required=True)
    complete = commands.add_parser("complete")
    complete.add_argument("--records", type=Path, required=True)
    binary = commands.add_parser("binary")
    binary.add_argument("--target", required=True, choices=[row["target"] for row in matrix()])
    binary.add_argument("--file", type=Path, action="append", required=True)
    payload = commands.add_parser("payload")
    payload.add_argument("--target", choices=[row["target"] for row in matrix()], required=True)
    payload.add_argument("--root", type=Path, required=True)
    payload.add_argument("--pins", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "matrix":
            print(json.dumps({"include": remaining_builds(args.except_windows, args.except_wsl)}, separators=(",", ":")))
        elif args.command == "manifest":
            validate_manifest(read(args.manifest), args.directory)
            print("Exact eight-target final vehicle inventory verified.")
        elif args.command == "complete":
            validate_complete(read(args.records))
            print("Exact eight-target final producer inventory verified; signatures remain an independent gate.")
        elif args.command == "payload":
            count = verify_payload(args.root, args.target, args.pins)
            print(f"Private runtime pins and architecture verified for {count} native files.")
        else:
            require(os.environ.get("RUNNER_ARCH", "").upper() == next(row["runner_arch"] for row in matrix() if row["target"] == args.target),
                    "build runner architecture differs from target")
            for path in args.file:
                verify_binary(path, args.target)
            print(f"Native architecture verified for {len(args.file)} executables.")
    except (Refused, PackageInputError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.exit(1, f"REFUSED: {error}\n")


if __name__ == "__main__":
    main()
