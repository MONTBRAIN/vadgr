"""Artifact-only workflow transitions. Never executes candidate binaries or signs."""
from __future__ import annotations

import argparse
from pathlib import Path
import os
import shutil
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import candidate_claims as claims, cua_release_inputs as release
from scripts.candidate import cua_shared as shared, cua_helpers as helpers
from scripts.validate_package_inputs import read_owned, require, sha256_bytes, PackageInputError


def unpack(archive, output):
    require(not output.exists(), "WSL extraction destination exists")
    names, total = set(), 0
    with tarfile.open(archive, "r:*") as source:
        members = source.getmembers()
        require(len(members) <= 12000, "WSL archive member limit")
        for member in members:
            name = member.name.removeprefix("./").rstrip("/")
            if name in ("", ".") and member.isdir():
                continue
            helpers.relative_path(name)
            require(name.casefold() not in names and (member.isdir() or member.isfile()),
                    "WSL special or duplicate member")
            names.add(name.casefold())
            total += member.size
            require(total <= 2 * 1024**3 and not member.mode & 0o7000, "WSL archive limit or special mode")
        output.mkdir()
        for member in members:
            name = member.name.removeprefix("./").rstrip("/")
            if name in ("", "."):
                continue
            target = output / name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                with source.extractfile(member) as stream:
                    shared.write(target, stream.read())
                target.chmod(member.mode & 0o777)


def artifact_record(directory, metadata):
    require(metadata["run_id"] == int(os.environ["GITHUB_RUN_ID"])
            and metadata["run_attempt"] == 1 and metadata["producer_sha"] == os.environ["GITHUB_SHA"],
            "helper artifact producer differs")
    return {"id": metadata["artifact_id"], "sha256": metadata["artifact_digest"].removeprefix("sha256:"),
            "subjects": {key: sha256_bytes(read_owned(directory, path)) for key, path in (
                ("relay_sha256", "relay.exe"), ("archive_sha256", "broker.zip"),
                ("manifest_sha256", shared.MANIFEST), ("mapping_sha256", shared.MAPPING))}}


def verify_subject(subject, bundle, auth):
    from scripts.candidate.cua_profile_signing import verify_subject as verify_protected_subject
    verify_protected_subject(subject, bundle, auth)


def verify_runtime(root, auth):
    envelope = shared.read(root / "cua-runtime-authorization.json")
    require(envelope["payload_sha256"] == sha256_bytes(read_owned(root, "lib/cua/payload.json"))
            and envelope["installed_inventory_sha256"] == sha256_bytes(read_owned(root, "lib/cua/" + release.INVENTORY)),
            "runtime envelope does not bind installed inventory")
    verify_subject(root / "cua-runtime-authorization.json", root / "cua-runtime-authorization.sigstore.json", auth)
    return envelope


def verify_unattested(root, records, auth, windows):
    from scripts.candidate import cua_signing as signing
    if windows:
        signing.validate_records(records, auth)
    actual = signing.tree(root)
    mapping = claims.parse(read_owned(records, "input-output.json"))
    require(actual == {name: row["output"] for name, row in mapping.items()}, "sealed runtime tree differs")
    runtime = root / "payload" if windows else root
    require(read_owned(runtime, "cua-runtime-authorization.json") == read_owned(records, "cua-runtime-authorization.json"),
            "runtime envelope differs from sealed record")
    envelope = shared.read(runtime / "cua-runtime-authorization.json")
    require(envelope["payload_sha256"] == sha256_bytes(read_owned(runtime, "lib/cua/payload.json"))
            and envelope["installed_inventory_sha256"] == sha256_bytes(read_owned(runtime, "lib/cua/" + release.INVENTORY)),
            "sealed envelope does not bind runtime inventory")


def pack(root, output):
    require(not output.exists(), "held WSL vehicle exists")
    with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(root.rglob("*")):
            name = path.relative_to(root).as_posix()
            require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
                    "held WSL links refused")
            if path.is_file():
                read_owned(root, name)
            row = archive.gettarinfo(str(path), name)
            require(row.isdir() or row.isfile(), "held WSL special file")
            row.uid = row.gid = 0
            row.uname = row.gname = ""
            row.mtime = 1609459200
            if row.isfile():
                with path.open("rb") as stream:
                    archive.addfile(row, stream)
            else:
                archive.addfile(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    command = sub.add_parser("unpack")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True)
    command = sub.add_parser("authorize-helper")
    for name in ("authorization", "output", "metadata", "ledger", "native-observation", "wsl-observation", "out"):
        command.add_argument("--" + name, type=Path, required=True)
    command = sub.add_parser("seal-wsl")
    for name in ("authorization", "root", "metadata", "helper-records", "records"):
        command.add_argument("--" + name, type=Path, required=True)
    command = sub.add_parser("hold-wsl")
    for name in ("authorization", "root", "records", "out"):
        command.add_argument("--" + name, type=Path, required=True)
    command = sub.add_parser("verify-runtime")
    for name in ("authorization", "root"):
        command.add_argument("--" + name, type=Path, required=True)
    command = sub.add_parser("verify-unattested")
    for name in ("authorization", "root", "records"):
        command.add_argument("--" + name, type=Path, required=True)
    command.add_argument("--windows", action="store_true")
    args = parser.parse_args()
    try:
        if args.mode == "unpack":
            unpack(args.archive, args.out)
            return 0
        auth = claims.parse(args.authorization.read_bytes())
        claims.validate_authorization(auth, bound=True)
        if args.mode == "authorize-helper":
            ledger = shared.read(args.ledger)
            require(ledger["authorization_sha256"] == claims.digest(claims.canonical(auth))
                    and ledger["budget"] == auth["budget"], "helper ledger authorization differs")
            shared.authorize_directory(args.output, artifact_record(args.output, claims.parse(args.metadata.read_bytes())),
                ledger, shared.read(args.native_observation), shared.read(args.wsl_observation), args.out)
        elif args.mode == "seal-wsl":
            from scripts.candidate.cua_profile_signing import reseal_profile
            metadata = claims.parse(args.metadata.read_bytes())
            require(metadata["artifact_id"] == auth["wsl_artifact_id"]
                    and metadata["artifact_digest"] == auth["wsl_artifact_digest"]
                    and metadata["producer_sha"] == auth["trusted_sha"]
                    and metadata["run_id"] == auth["run_id"] and metadata["run_attempt"] == 1,
                    "WSL consumer artifact differs from authorization")
            reseal_profile(Path("."), auth, args.records, {}, args.helper_records, profile_root=args.root)
        elif args.mode == "verify-runtime":
            verify_runtime(args.root, auth)
        elif args.mode == "verify-unattested":
            verify_unattested(args.root, args.records, auth, args.windows)
        else:
            envelope = verify_runtime(args.root, auth)
            require(envelope["release_profile"].startswith("wsl-"), "held WSL profile differs")
            require(not args.out.exists(), "held WSL directory exists")
            args.out.mkdir()
            profile = envelope["release_profile"]
            vehicle = args.out / f"Vadgr-0.5.0-{profile}.tar.gz"
            pack(args.root, vehicle)
            shutil.copytree(args.records, args.out / "cua")
            shutil.copy2(args.root / "cua-runtime-authorization.sigstore.json", args.out / "runtime.sigstore.json")
            shared.write(args.out / "authorization.json", claims.canonical(auth))
            shared.write(args.out / "candidate-manifest.json", {"schema": 1, "status": "held-unpublished",
                "release_profile": profile, "source_commit": auth["source_sha"], "trusted_tooling_commit": auth["trusted_sha"],
                "runtime_authorization_sha256": sha256_bytes(read_owned(args.root, "cua-runtime-authorization.json")),
                "installed_inventory_sha256": envelope["installed_inventory_sha256"],
                "helper_claim_sha256": auth["helper_claim_sha256"], "wsl_artifact_id": auth["wsl_artifact_id"],
                "wsl_artifact_digest": auth["wsl_artifact_digest"],
                "files": {p.relative_to(args.out).as_posix(): {"size": p.stat().st_size,
                    "sha256": sha256_bytes(read_owned(args.out, p.relative_to(args.out).as_posix()))}
                    for p in sorted(args.out.rglob("*")) if p.is_file()}})
    except (PackageInputError, claims.Refused, KeyError, ValueError, TypeError, OSError, tarfile.TarError):
        print("CUA workflow transition refused.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
