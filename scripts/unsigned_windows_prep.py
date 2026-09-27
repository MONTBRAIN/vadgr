#!/usr/bin/env python3
"""Measure unapproved Windows inputs for legal review. Never authorizes a candidate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tomllib
import unicodedata
from urllib.parse import quote
import zipfile

if __package__:
    from scripts import candidate_policy as gate, cua_wheelhouse, distribution_matrix, windows_runtime_evidence
    from scripts.validate_package_inputs import (
        PackageInputError, canonical_json, parse_json, read_owned, relative_path, sha256_bytes,
    )
else:
    import candidate_policy as gate
    import cua_wheelhouse
    import distribution_matrix
    import windows_runtime_evidence
    from validate_package_inputs import (
        PackageInputError, canonical_json, parse_json, read_owned, relative_path, sha256_bytes,
    )

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/unsigned-windows-preparation.yml"
BRANCH = "feature/0.5.0-distribution"
TARGETS = {"x64": ("windows-x86_64", "x86_64-pc-windows-msvc", "X64"),
           "arm64": ("windows-aarch64", "aarch64-pc-windows-msvc", "ARM64")}
BOUNDARY = {"status": "unapproved", "publishable": False, "candidate_approval": False,
            "scope": "unsigned-windows-legal-preparation"}


def workflow_identity():
    gate.require(os.environ.get("GITHUB_REPOSITORY") == gate.REPOSITORY
                 and os.environ.get("GITHUB_REF") == "refs/heads/master"
                 and os.environ.get("GITHUB_WORKFLOW_REF") ==
                 f"{gate.REPOSITORY}/{WORKFLOW}@refs/heads/master"
                 and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                 and gate.SHA.fullmatch(os.environ.get("GITHUB_SHA", "")) is not None
                 and re.fullmatch(r"[1-9][0-9]*", os.environ.get("GITHUB_RUN_ID", "")) is not None,
                 "unsigned preparation requires the trusted default-branch workflow")
    return {"workflow": WORKFLOW, "trusted_sha": os.environ["GITHUB_SHA"],
            "run_id": int(os.environ["GITHUB_RUN_ID"]), "run_attempt": 1}


def validate_paths(rows):
    names = set()
    for mode, kind, object_id, name in rows:
        relative_path(name)
        key = unicodedata.normalize("NFC", name).casefold()
        gate.require(key not in names and mode in ("100644", "100755") and kind == "blob"
                     and gate.SHA.fullmatch(object_id) is not None, "source path is linked or ambiguous")
        names.add(key)
    gate.require(not any("/".join(name.split("/")[:index]) in names
                         for name in names for index in range(1, len(name.split("/")))),
                 "source has a file/directory collision")


def admit(source, branch, sha):
    """Reuse the candidate's source/check gates, without asking for package approval."""
    identity = workflow_identity()
    gate.require(branch == BRANCH and gate.SHA.fullmatch(sha) is not None
                 and sha != identity["trusted_sha"], "preparation source identity is invalid")
    gate.require(gate.git(source, "rev-parse", "HEAD") == sha and
                 not gate.git(source, "status", "--porcelain", "--untracked-files=all"),
                 "preparation checkout is not the exact clean source")
    rows = gate.inventory(source, sha)
    validate_paths(rows)
    digest = gate.input_digest(rows)
    tree = gate.git(source, "rev-parse", f"{sha}^{{tree}}")
    gate.require_trusted_workflows(source, sha, rows)
    repo = gate.github("")
    gate.require(repo["full_name"] == gate.REPOSITORY and repo["fork"] is False
                 and repo["default_branch"] == gate.BASE, "repository identity differs")

    def check_branch():
        ref = gate.github(f"git/ref/heads/{quote(branch, safe='/')}")
        gate.require(ref["ref"] == f"refs/heads/{branch}" and ref["object"]["type"] == "commit"
                     and ref["object"]["sha"] == sha, "preparation source branch moved")

    check_branch()
    remote = gate.github(f"git/commits/{sha}")
    gate.require(remote["sha"] == sha and remote["tree"]["sha"] == tree, "remote source tree differs")
    pulls = gate.pages(f"pulls?state=open&head={quote('MONTBRAIN:' + branch, safe='')}&base=master&per_page=100")
    pull = gate.require_pull_requests(pulls, branch, sha)
    rules = gate.pages("rules/branches/master?per_page=100")
    checks = gate.pages(f"commits/{sha}/check-runs?filter=all&per_page=100", "check_runs")
    statuses = gate.github(f"commits/{sha}/status?per_page=100")
    gate.require(statuses["sha"] == sha, "check source differs")
    required = gate.require_checks(rules, checks, statuses["statuses"], sha)
    required = gate.require_trusted_check_runs(required, checks, sha, branch)
    cargo = tomllib.loads(gate.git(source, "show", f"{sha}:Cargo.toml"))
    gate.require(cargo["package"]["version"] == "0.5.0", "preparation version differs")
    gate.require(re.search(r"^## \[0\.5\.0\] - ",
                           gate.git(source, "show", f"{sha}:CHANGELOG.md"), re.M) is not None,
                 "preparation changelog missing")
    check_branch()
    gate.require(gate.pages("rules/branches/master?per_page=100") == rules,
                 "effective source rules changed")
    if pull is not None:
        gate.require_pull_requests([gate.github(f"pulls/{pull}")], branch, sha)
    return {"schema": 1, **BOUNDARY, **identity, "repository": gate.REPOSITORY,
            "branch": branch, "source_sha": sha, "source_tree": tree, "input_digest": digest,
            "version": "0.5.0", "pull_request": pull, "required_checks": required,
            "rules_digest": sha256_bytes(canonical_json(rules))}, rows


def source_snapshot(source, sha, rows, output):
    """Retain exact Git bytes, including every legal proposal, separately from the payload."""
    gate.require(not output.exists(), "source observation output exists")
    output.mkdir(parents=True)
    inventory = {}
    with zipfile.ZipFile(output / "source-inputs.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for mode, _, object_id, name in rows:
            if name == gate.EXCLUDED:
                continue
            data = gate.git(source, "show", f"{sha}:{name}", binary=True)
            inventory[name] = {"git_blob": object_id, "mode": mode,
                               "sha256": sha256_bytes(data), "size": len(data)}
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    (output / "source-inventory.json").write_bytes(canonical_json({
        "schema": 1, **BOUNDARY, "source_sha": sha, "excluded": [gate.EXCLUDED], "files": inventory}))


def verify_test_source(source, source_record):
    """Recheck the full admitted checkout offline before credential-free tests."""
    sha = source_record["source_sha"]
    gate.require(gate.SHA.fullmatch(sha) is not None
                 and gate.git(source, "rev-parse", "HEAD") == sha
                 and not gate.git(source, "status", "--porcelain", "--untracked-files=all"),
                 "source test checkout is not the exact clean admitted source")
    rows = gate.inventory(source, sha)
    validate_paths(rows)
    gate.require(gate.git(source, "rev-parse", f"{sha}^{{tree}}") == source_record["source_tree"]
                 and gate.input_digest(rows) == source_record["input_digest"],
                 "source test checkout differs from admission")
    read_owned(source, gate.EXCLUDED)


def terms_input(source):
    name = "packaging/legal/TERMS.txt"
    if not (source / name).is_file():
        return {"status": "unavailable", "reason": "exact proposed terms file is absent"}
    data = read_owned(source, name)
    text = data.decode("utf-8")
    versions = re.findall(r"^\*\*Version ([0-9]+\.[0-9]+)\*\*\s*$", text, re.M)
    if not data or versions != ["1.0"]:
        return {"status": "unavailable", "reason": "exact proposed terms version is not 1.0"}
    return {"status": "unapproved", "path": name, "version": "1.0", "sha256": sha256_bytes(data)}


def file_inventory(root, profile=None):
    rows = []
    for path in sorted(root.rglob("*")):
        gate.require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
                     "observation contains a linked path")
        if path.is_file():
            rows.append(("100644", "blob", "0" * 40, path.relative_to(root).as_posix()))
    validate_paths(rows)
    result = {}
    for _, _, _, name in rows:
        data = read_owned(root, name)
        record = {"sha256": sha256_bytes(data), "size": len(data)}
        if data[:2] == b"MZ":
            kind, architecture = cua_wheelhouse.binary_architecture(data)
            if profile:
                gate.require(architecture == profile.split("-", 1)[1], "native architecture differs")
            record.update({"format": kind, "architecture": architecture})
        result[name] = record
    return result


def verify_installed_inventory(payload):
    root = payload / "lib/cua"
    raw = read_owned(root, "installed-inventory.json")
    manifest = parse_json(read_owned(root, "payload.json"))
    gate.require(sha256_bytes(raw) == manifest.get("installed_inventory_sha256"),
                 "installed inventory hash differs from payload")
    inventory = parse_json(raw)
    gate.require(set(inventory) == {"schema", "target", "files"} and inventory["schema"] == 1
                 and inventory["target"] == manifest.get("target"), "installed inventory identity differs")
    actual = file_inventory(root)
    actual = {name: {"sha256": row["sha256"], "size": row["size"]}
              for name, row in actual.items() if name not in ("payload.json", "installed-inventory.json")}
    gate.require(actual == inventory["files"], "installed inventory file set or bytes differ")
    return manifest


def require_unsigned_pe(data):
    """Outer product binaries must not arrive with an embedded Authenticode table."""
    cua_wheelhouse.binary_architecture(data)
    offset = struct.unpack_from("<I", data, 0x3c)[0]
    optional = offset + 24
    gate.require(len(data) >= optional + 152 and
                 struct.unpack_from("<H", data, optional)[0] == 0x20b,
                 "outer executable has an invalid PE32+ optional header")
    gate.require(struct.unpack_from("<II", data, optional + 144) == (0, 0),
                 "outer executable already has an Authenticode certificate table")


def producer_record(architecture, source_record):
    run_id = source_record["run_id"]
    artifacts = gate.pages(f"actions/runs/{run_id}/artifacts?per_page=100", "artifacts")
    matches = [row for row in artifacts if row.get("name") ==
               f"unapproved-windows-preparation-raw-{architecture}"]
    gate.require(len(matches) == 1, "unsigned build artifact identity is ambiguous")
    artifact = matches[0]
    gate.require(artifact.get("expired") is False and type(artifact.get("id")) is int
                 and re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", "")) is not None
                 and artifact.get("workflow_run", {}).get("id") == run_id
                 and artifact["workflow_run"].get("head_sha") == source_record["trusted_sha"],
                 "unsigned build artifact producer differs")
    jobs = gate.pages(f"actions/runs/{run_id}/attempts/1/jobs?per_page=100", "jobs")
    matches = [row for row in jobs if row.get("name") == f"build-unsigned-{architecture}"]
    runner = "windows-latest" if architecture == "x64" else "windows-11-arm"
    gate.require(len(matches) == 1 and matches[0].get("conclusion") == "success"
                 and matches[0].get("head_sha") == source_record["trusted_sha"]
                 and runner in matches[0].get("labels", []), "native build job identity differs")
    return {"artifact_id": artifact["id"], "artifact_digest": artifact["digest"],
            "artifact_name": artifact["name"], "job_id": matches[0]["id"],
            "runner_labels": matches[0]["labels"]}


def cargo_notices(metadata_path, source, cargo_home, output):
    """Retain dependency metadata and supplied license bytes; do not conclude licenses."""
    metadata = parse_json(metadata_path.read_bytes())
    gate.require(not output.exists(), "Cargo notice output exists")
    output.mkdir(parents=True)
    records = []
    for package in metadata["packages"]:
        root = Path(package["manifest_path"]).resolve().parent
        gate.require(root.is_relative_to(source.resolve()) or
                     root.is_relative_to((cargo_home / "registry/src").resolve()),
                     "Cargo package is outside the prepared source and registry")
        key = sha256_bytes(package["id"].encode())
        files = {}
        paths = []
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if name not in ("target", ".git")]
            paths.extend(Path(directory) / name for name in names)
        for path in sorted(paths):
            relative = path.relative_to(root).as_posix()
            # Build products are not dependency notices. Local source includes nested BA targets.
            if any(part in ("target", ".git") for part in path.relative_to(root).parts):
                continue
            if path.is_file() and (path.name in ("Cargo.toml", "Cargo.toml.orig")
                                  or re.match(r"(?i)^(license|licence|copying|notice|copyright|patents)([._-]|$)", path.name)
                                  or relative == package.get("license_file")):
                data = read_owned(root, relative)
                destination = output / key / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                files[relative] = {"sha256": sha256_bytes(data), "size": len(data)}
        records.append({"id": package["id"], "name": package["name"], "version": package["version"],
                        "source": package["source"], "license_declared": package.get("license"),
                        "license_file": package.get("license_file"), "directory": key, "files": files})
    (output / "cargo-components.json").write_bytes(canonical_json({
        "schema": 1, **BOUNDARY, "packages": records, "resolve": metadata.get("resolve"),
        "limitation": "Declared metadata and supplied notices require independent legal review."}))


def observe(source, source_record, raw, architecture, output):
    profile, target, _ = TARGETS[architecture]
    gate.require(not output.exists(), "observation output exists")
    gate.require(parse_json(read_owned(raw, "preparation-source.json")) == source_record,
                 "build source admission differs from fresh source admission")
    cua_wheelhouse.verify_materialized(source, ROOT, target, raw / "wheelhouse", profile)
    manifest = verify_installed_inventory(raw / "payload")
    gate.require(manifest.get("schema") == 3 and manifest.get("release_profile") == profile,
                 "preparation requires the exact reviewed CUA profile")
    distribution_matrix.verify_payload(raw / "payload", profile, source / "packaging/cua/pins.toml")
    files = file_inventory(raw, profile)
    windows_runtime_evidence.validate(raw, architecture)
    for name in ("cargo-metadata.json", "cargo-notices/cargo-components.json", "rustc-version.txt", "cargo-version.txt"):
        gate.require(name in files and files[name]["size"] > 0, "dependency or compiler observation is absent")
    for name in ("payload/vadgr.exe", "payload/vadgr-app.exe"):
        gate.require(files.get(name, {}).get("format") == "pe", "required unsigned executable is absent")
        require_unsigned_pe(read_owned(raw, name))
    terms = terms_input(source)
    build = parse_json(read_owned(raw, "build-observation.json"))
    gate.require(build["terms"] == terms and build["architecture"] == architecture
                 and build["native_architecture"] == TARGETS[architecture][2], "build observation differs")
    if terms["status"] == "unapproved":
        gate.require(files.get("ba-functions.dll", {}).get("format") == "pe"
                     and read_owned(raw, "proposed-terms/TERMS.txt") == read_owned(source, terms["path"]),
                     "bootstrapper or exact proposed terms are absent")
        require_unsigned_pe(read_owned(raw, "ba-functions.dll"))
        for name in ("ba-cargo-metadata.json", "ba-cargo-notices/cargo-components.json"):
            gate.require(name in files and files[name]["size"] > 0, "bootstrapper dependency observation is absent")
    else:
        gate.require("ba-functions.dll" not in files, "bootstrapper was built without exact terms")
    producer = producer_record(architecture, source_record)
    output.mkdir(parents=True)
    # The observer never executes a build output. The copy retains hidden runtime files too.
    shutil.copytree(raw, output / "unsigned-inputs")
    rows = gate.inventory(source, source_record["source_sha"])
    source_snapshot(source, source_record["source_sha"], rows, output / "source")
    report = {"schema": 1, **BOUNDARY, "source": source_record, "producer": producer,
              "architecture": architecture,
              "target": target, "release_profile": profile, "terms": terms,
              "payload_sha256": files["payload/lib/cua/payload.json"]["sha256"],
              "installed_inventory_sha256": files["payload/lib/cua/installed-inventory.json"]["sha256"],
              "executable_hashes": {name: row["sha256"] for name, row in files.items()
                                    if row.get("format") == "pe"}, "files": files,
              "source_files": file_inventory(output / "source"),
              "limitations": ["No package, legal, signing or installation approval.",
                              "Unsigned native headers and exact bytes only; no trust qualification.",
                              "Cargo notices are reported build inputs, not concluded license rights."]}
    (output / "preparation-observation.json").write_bytes(canonical_json(report))
    (output / "UNAPPROVED-NONPUBLISHABLE.txt").write_text(
        "Unsigned observations for owner and legal review only.\n"
        "Not a candidate, release, legal approval or installation qualification.\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("admit", "observe"):
        command = commands.add_parser(name)
        command.add_argument("--source-root", type=Path, required=True)
        command.add_argument("--branch", required=True)
        command.add_argument("--source-sha", required=True)
        command.add_argument("--out", type=Path, required=True)
        if name == "admit":
            command.add_argument("--materialize", type=Path, required=True)
        else:
            command.add_argument("--raw", type=Path, required=True)
            command.add_argument("--architecture", choices=TARGETS, required=True)
    terms = commands.add_parser("terms")
    terms.add_argument("--source-root", type=Path, required=True)
    terms.add_argument("--out", type=Path, required=True)
    source_tests = commands.add_parser("verify-test-source")
    source_tests.add_argument("--source-root", type=Path, required=True)
    source_tests.add_argument("--source-record", type=Path, required=True)
    cargo = commands.add_parser("cargo-notices")
    cargo.add_argument("--metadata", type=Path, required=True)
    cargo.add_argument("--source-root", type=Path, required=True)
    cargo.add_argument("--cargo-home", type=Path, required=True)
    cargo.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command in ("admit", "observe"):
            record, rows = admit(args.source_root.resolve(), args.branch, args.source_sha)
            if args.command == "admit":
                gate.require(not args.out.exists(), "admission record exists")
                gate.materialize(args.source_root.resolve(), args.source_sha, rows, args.materialize.absolute())
                args.out.write_bytes(canonical_json(record))
            else:
                observe(args.source_root.resolve(), record, args.raw.resolve(), args.architecture, args.out.absolute())
        elif args.command == "terms":
            args.out.write_bytes(canonical_json(terms_input(args.source_root)))
        elif args.command == "verify-test-source":
            verify_test_source(args.source_root.resolve(), parse_json(args.source_record.read_bytes()))
        else:
            cargo_notices(args.metadata, args.source_root, args.cargo_home, args.out)
    except (gate.Refused, PackageInputError, distribution_matrix.Refused,
            OSError, ValueError, TypeError, KeyError, IndexError, zipfile.BadZipFile) as exc:
        print("UNSIGNED PREPARATION REFUSED: " + (str(exc) if isinstance(exc, gate.Refused)
              else "required input or observation is invalid"), file=sys.stderr)
        return 1
    print("Unsigned preparation recorded. Unapproved and nonpublishable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
