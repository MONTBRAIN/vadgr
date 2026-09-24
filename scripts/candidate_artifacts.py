#!/usr/bin/env python3
"""Inspect unsigned candidate bytes without executing an untrusted payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

if __package__:
    from scripts import candidate_policy, cua_release_inputs
    from scripts.validate_package_inputs import PackageInputError, validate_package_inputs
else:
    import candidate_policy  # trusted direct execution from scripts/
    import cua_release_inputs
    from validate_package_inputs import PackageInputError, validate_package_inputs

REPOSITORY = "MONTBRAIN/vadgr"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RESERVED = re.compile(r"(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z")
MAX_FILES = 12_000
MAX_COMPRESSED = 750 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024


class Refused(Exception):
    """Do not grant access to the code-signing credential."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Refused(reason)


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def safe_name(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/") or "\x00" in value:
        return False
    parts = value.rstrip("/").split("/")
    return all(part not in ("", ".", "..") and not part.endswith((" ", "."))
               and not RESERVED.fullmatch(part) and not any(char in part for char in ':$!;<>|"?*')
               and all(ord(char) >= 32 for char in part) for part in parts)


def allowed_name(name: str) -> bool:
    if name in ("ba-functions.dll", "TERMS.rtf"):
        return True
    parts = name.split("/")
    return len(parts) >= 2 and parts[0] == "payload" and (
        len(parts) == 2 and parts[1] in
        ("vadgr.exe", "vadgr-app.exe", "install-receipt.json", "README-OFFLINE.txt",
         "package-input-inventory.json", "package-input-review.json")
        or len(parts) >= 3 and parts[1] in ("legal", "sbom", "lib"))


def inspect(path: Path, *, expanded_limit: int = MAX_EXPANDED) -> dict[str, dict]:
    require(path.is_file() and path.stat().st_size <= MAX_COMPRESSED,
            "candidate archive is absent or too large")
    members: dict[str, dict] = {}
    seen: set[str] = set()
    size = 0
    try:
        with zipfile.ZipFile(path) as archive:
            require(len(archive.infolist()) <= MAX_FILES, "candidate has too many files")
            for info in archive.infolist():
                name = info.filename
                require(safe_name(name), "candidate has unsafe path")
                normalized = name.rstrip("/").casefold()
                require(normalized not in seen, "candidate has duplicate or case-colliding path")
                seen.add(normalized)
                # GitHub artifact ZIP folders are legal; only regular files
                # within the reviewed payload namespace may carry bytes.
                unix_type = (info.external_attr >> 16) & 0o170000
                require(unix_type in (0, 0o100000, 0o040000), "candidate contains a link or special file")
                require(not (info.external_attr & 0x400) and info.create_system in (0, 3),
                        "candidate contains a Windows reparse point or unknown platform member")
                require(not (info.flag_bits & 0x1), "encrypted archive member refused")
                if info.is_dir():
                    require(unix_type in (0, 0o040000), "invalid directory type")
                    continue
                require(unix_type in (0, 0o100000) and allowed_name(name),
                        "candidate contains an unexpected file")
                size += info.file_size
                require(size <= expanded_limit and info.file_size <= expanded_limit,
                        "candidate extraction limit exceeded")
                actual = hashlib.sha256()
                counted = 0
                with archive.open(info) as member:
                    for chunk in iter(lambda: member.read(1024 * 1024), b""):
                        counted += len(chunk)
                        require(counted <= info.file_size and counted <= expanded_limit,
                                "candidate member exceeds declared size")
                        actual.update(chunk)
                require(counted == info.file_size, "candidate member size mismatch")
                members[name] = {"sha256": actual.hexdigest(), "size": counted}
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise Refused("candidate archive cannot be read safely") from exc
    return members


def operation_budget(names: list[str]) -> int:
    require("ba-functions.dll" in names, "bootstrapper DLL missing")
    pe = [name for name in names if name.startswith("payload/")
          and name.lower().endswith((".exe", ".dll", ".pyd"))]
    require("payload/vadgr.exe" in pe and "payload/vadgr-app.exe" in pe,
            "product executables missing")
    return len(pe) + 4  # DLL, MSI, Burn engine, final setup EXE.


def verify_pe(data: bytes, architecture: str) -> None:
    require(len(data) >= 0x40 and data[:2] == b"MZ", "unsigned PE header missing")
    offset = int.from_bytes(data[0x3c:0x40], "little")
    require(offset <= len(data) - 6 and data[offset:offset + 4] == b"PE\0\0",
            "unsigned PE signature missing")
    expected = {"x64": 0x8664, "arm64": 0xAA64}
    require(architecture in expected and
            int.from_bytes(data[offset + 4:offset + 6], "little") == expected[architecture],
            "unsigned PE architecture mismatch")


def require_architecture(archive: Path, members: dict[str, dict], architecture: str) -> None:
    with zipfile.ZipFile(archive) as source:
        for name in members:
            if name == "ba-functions.dll" or (name.startswith("payload/") and
                 name.lower().endswith((".exe", ".dll", ".pyd"))):
                with source.open(name) as handle:
                    head = handle.read(1024 * 1024)
                verify_pe(head, architecture)


def read_json(path: Path):
    require(path.stat().st_size <= 10 * 1024 * 1024, "candidate metadata too large")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_metadata(data: dict, *, preflight: dict, archive: Path,
                      architecture: str) -> None:
    require(data.get("repository") == REPOSITORY and
            data.get("run_id") == int(os.environ.get("GITHUB_RUN_ID", "0")) and
            data.get("run_attempt") == 1 and
            data.get("producer_sha") == preflight["trusted_sha"] and
            data.get("architecture") == architecture and
            type(data.get("artifact_id")) is int and data["artifact_id"] > 0,
            "artifact was not produced by this trusted run")
    expected = data.get("artifact_digest", "")
    require(isinstance(expected, str) and expected.startswith("sha256:") and
            SHA256.fullmatch(expected[7:]) is not None and expected[7:] == digest(archive),
            "downloaded candidate artifact digest does not match")


def require_legal(source_root: Path, members: dict[str, dict], architecture: str) -> dict[str, str]:
    required = ("payload/legal/TERMS.txt", "payload/legal/TERMS.rtf", "payload/README-OFFLINE.txt",
                "payload/package-input-inventory.json", "payload/package-input-review.json")
    for name in required:
        require(name in members, f"candidate legal file missing: {name}")
    legal = {}
    sbom = {}
    target = {"x64": "x86_64", "arm64": "aarch64"}[architecture]
    compliance_root = source_root / "packaging/inputs" / f"windows-{target}"
    for name, info in members.items():
        if name.startswith(("payload/legal/", "payload/sbom/")) or name in (
            "TERMS.rtf", "payload/README-OFFLINE.txt", "payload/package-input-inventory.json",
                "payload/package-input-review.json"):
            original = (compliance_root / "legal/TERMS.rtf" if name == "TERMS.rtf"
                        else compliance_root / name.removeprefix("payload/"))
            require(original.is_file() and digest(original) == info["sha256"],
                    "legal or SBOM bytes differ from sealed source")
            if name.startswith("payload/sbom/"):
                sbom[name] = info["sha256"]
            elif name not in ("payload/package-input-inventory.json", "payload/package-input-review.json"):
                legal[name] = info["sha256"]
    require(len(sbom) == 1, "candidate must carry one version SBOM")
    require(members["TERMS.rtf"]["sha256"] == members["payload/legal/TERMS.rtf"]["sha256"],
            "package terms and installer terms differ")
    approved = candidate_policy.trusted_approval(architecture)
    if (source_root / "packaging/cua/profile-inputs.json").exists():
        trusted_root = Path(candidate_policy.__file__).resolve().parents[1]
        for suffix in (".json", "-outer.json"):
            name = f"packaging/cua/helper-signing/{target}{suffix}"
            original, trusted = source_root / name, trusted_root / name
            require(original.is_file() and trusted.is_file()
                    and digest(original) == digest(trusted) == approved["legal_hashes"].get(name),
                    "profile signing policy differs from exact trusted legal approval")
            legal[name] = digest(original)
    require(legal == approved["legal_hashes"]
            and list(sbom.values())[0] == approved["sbom_sha256"],
            "candidate compliance bytes do not match reviewed approval")
    generator = Path(candidate_policy.__file__).resolve().parent / "generate_legal_bundle.py"
    require(generator.is_file() and digest(generator) == approved["generator_sha256"],
            "trusted legal generator differs from reviewed approval")
    inventory = compliance_root / "package-input-inventory.json"
    require(inventory.is_file() and digest(inventory) == approved["inventory_sha256"],
            "sealed legal inventory differs from reviewed approval")
    return legal


def extract(archive: Path, target: Path, members: dict[str, dict]) -> None:
    require(not target.exists(), "verified extraction directory already exists")
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as source:
        for name in members:
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with source.open(name) as input_stream, output.open("xb") as result:
                for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                    result.write(chunk)
            require(digest(output) == members[name]["sha256"], "extracted file hash mismatch")


def verify_directory(directory: Path, expected: dict[str, dict]) -> None:
    require(not any(path.is_symlink() for path in directory.rglob("*")),
            "verified extraction contains a link")
    actual = {str(path.relative_to(directory)).replace(os.sep, "/"): path
              for path in directory.rglob("*") if path.is_file()}
    require(set(actual) == set(expected), "verified artifact file set changed")
    for name, info in expected.items():
        path = actual[name]
        require(not path.is_symlink() and path.stat().st_size == info["size"]
                and digest(path) == info["sha256"], "verified artifact bytes changed")


def download(args) -> None:
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY and
            os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and
            os.environ.get("GITHUB_RUN_ID") == str(args.run_id), "candidate run identity changed")
    cmd = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json",
           f"repos/{REPOSITORY}/actions/artifacts/{args.artifact_id}"]
    result = subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    require(result.returncode == 0, "artifact metadata request failed")
    meta = json.loads(result.stdout)
    workflow = meta.get("workflow_run", {})
    require(meta.get("id") == args.artifact_id and meta.get("expired") is False and
            meta.get("digest") == args.digest and
            workflow.get("id") == args.run_id and workflow.get("head_sha") == args.producer_sha,
            "artifact is expired, replaced or cross-run")
    require(meta.get("archive_download_url", "").startswith(f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/"),
            "artifact download origin mismatch")
    require(not args.out.exists() and not args.metadata.exists(), "artifact output already exists")
    require(args.out.parent.exists() and args.metadata.parent.exists(), "artifact output parent missing")
    with tempfile.NamedTemporaryFile(dir=args.out.parent, delete=False) as temporary:
        temp = Path(temporary.name)
        result = subprocess.run(["gh", "api", "--method", "GET", "-H",
                                 "Accept: application/vnd.github+json",
                                 f"repos/{REPOSITORY}/actions/artifacts/{args.artifact_id}/zip"],
                                stdout=temporary, stderr=subprocess.DEVNULL, timeout=300, check=False)
    try:
        require(result.returncode == 0 and temp.stat().st_size <= MAX_COMPRESSED
                and args.digest == f"sha256:{digest(temp)}", "artifact download digest mismatch")
        temp.replace(args.out)
    finally:
        temp.unlink(missing_ok=True)
    args.metadata.write_text(json.dumps({"repository": REPOSITORY, "run_id": args.run_id,
                              "run_attempt": 1, "producer_sha": args.producer_sha,
                              "architecture": args.architecture, "artifact_id": args.artifact_id,
                              "artifact_digest": args.digest}, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_subparsers(dest="command", required=True)
    down = group.add_parser("download")
    down.add_argument("--artifact-id", type=int, required=True)
    down.add_argument("--digest", required=True)
    down.add_argument("--run-id", type=int, required=True)
    down.add_argument("--run-attempt", type=int, default=1)
    down.add_argument("--repository", default=REPOSITORY)
    down.add_argument("--producer-sha", default=os.environ.get("GITHUB_SHA"))
    down.add_argument("--architecture", choices=("x64", "arm64"), default=os.environ.get("ARCHITECTURE"))
    down.add_argument("--out", type=Path, required=True)
    down.add_argument("--metadata", type=Path, required=True)
    check = group.add_parser("validate")
    check.add_argument("--archive", type=Path, required=True)
    check.add_argument("--metadata", type=Path, required=True)
    check.add_argument("--source-root", type=Path, required=True)
    check.add_argument("--preflight", type=Path, required=True)
    check.add_argument("--architecture", choices=("x64", "arm64"), required=True)
    check.add_argument("--extract", type=Path, required=True)
    check.add_argument("--out", type=Path, required=True)
    verify = group.add_parser("extract-verified")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--authorization", type=Path, required=True)
    verify.add_argument("--extract", type=Path, required=True)
    fetch = group.add_parser("fetch-verified")
    fetch.add_argument("--authorization", type=Path, required=True)
    fetch.add_argument("--extract", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
                and os.environ.get("GITHUB_REF") == "refs/heads/master"
                and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "untrusted candidate workflow")
        if args.command == "download":
            require(args.repository == REPOSITORY and args.run_attempt == 1
                    and args.artifact_id > 0 and args.digest.startswith("sha256:")
                    and SHA256.fullmatch(args.digest[7:]) is not None,
                    "invalid artifact identity")
            download(args)
        elif args.command == "validate":
            require(not args.out.exists(), "authorization record already exists")
            preflight, metadata = read_json(args.preflight), read_json(args.metadata)
            require(preflight["repository"] == REPOSITORY and preflight["architecture"] == args.architecture
                    and preflight["trusted_sha"] == os.environ.get("GITHUB_SHA"),
                    "source identity changed before artifact validation")
            validate_metadata(metadata, preflight=preflight, archive=args.archive,
                              architecture=args.architecture)
            files = inspect(args.archive)
            require_architecture(args.archive, files, args.architecture)
            legal = require_legal(args.source_root, files, args.architecture)
            budget = operation_budget(list(files))
            extract(args.archive, args.extract, files)
            target_arch = {"x64": "x86_64", "arm64": "aarch64"}[args.architecture]
            cua_inputs = cua_release_inputs.reviewed_inputs(
                args.source_root, Path(__file__).resolve().parents[1],
                f"{target_arch}-pc-windows-msvc")
            require(preflight.get("cua_inputs") == cua_inputs,
                    "reviewed CUA inputs changed after source preflight")
            cua_payload = cua_release_inputs.validate_payload(
                args.extract / "payload/lib/cua", cua_inputs)
            package_result = validate_package_inputs(
                args.extract / "payload", args.source_root, preflight["version"],
                f"{target_arch}-pc-windows-msvc")
            require(package_result.get("status") == "approved" and
                    package_result.get("scope") == "assembled-payload",
                    "assembled package input review failed")
            args.out.write_text(json.dumps({**preflight, "repository": REPOSITORY,
                "run_id": metadata["run_id"], "run_attempt": 1,
                "unsigned_artifact_id": metadata["artifact_id"],
                "unsigned_artifact_digest": metadata["artifact_digest"],
                "files": files, "legal_hashes": legal, "budget": budget,
                "cua_payload": cua_payload}, sort_keys=True, indent=2) + "\n",
                encoding="utf-8")
        else:
            record = read_json(args.authorization)
            require(record["repository"] == REPOSITORY and record["trusted_sha"] == os.environ.get("GITHUB_SHA")
                    and record["run_id"] == int(os.environ.get("GITHUB_RUN_ID", "0"))
                    and record["run_attempt"] == 1,
                    "authorization does not match trusted run")
            if args.command == "fetch-verified":
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary)
                    request = argparse.Namespace(artifact_id=record["unsigned_artifact_id"],
                        digest=record["unsigned_artifact_digest"], run_id=record["run_id"],
                        producer_sha=record["trusted_sha"], architecture=record["architecture"],
                        out=path / "archive.zip", metadata=path / "artifact.json")
                    download(request)
                    validate_metadata(read_json(request.metadata), preflight=record,
                                      archive=request.out, architecture=record["architecture"])
                    files = inspect(request.out)
                    require_architecture(request.out, files, record["architecture"])
                    require(files == record["files"], "downloaded candidate bytes changed")
                    extract(request.out, args.extract, files)
            else:
                files = inspect(args.archive)
                require_architecture(args.archive, files, record["architecture"])
                require(files == record["files"], "downloaded candidate bytes changed")
                extract(args.archive, args.extract, files)
            verify_directory(args.extract, files)
    except (Refused, PackageInputError, OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile,
            subprocess.SubprocessError) as exc:
        print("CANDIDATE ARTIFACT REFUSED: " + (str(exc) if isinstance(exc, Refused)
              else "invalid artifact metadata or bytes"), file=sys.stderr)
        return 1
    print("Candidate artifact accepted without executing payload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
