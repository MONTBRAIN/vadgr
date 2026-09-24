#!/usr/bin/env python3
"""Independent, data-only binding of reviewed wheels and schema-2 CUA payloads.

This is release admission, not an input-approval generator. Missing reviewed
inputs never select the development lock or permit online package resolution.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unicodedata

if __package__:
    from scripts.validate_package_inputs import (
        PackageInputError, TARGETS, canonical_json, parse_json, read_owned,
        relative_path, require, sha256_bytes, valid_hash,
    )
else:
    from validate_package_inputs import (
        PackageInputError, TARGETS, canonical_json, parse_json, read_owned,
        relative_path, require, sha256_bytes, valid_hash,
    )

REPOSITORY = "MONTBRAIN/vadgr"
WORKFLOW = ".github/workflows/native-wheels.yml"
MANIFEST = "packaging/cua/native-wheel-manifest.json"
BUNDLE = MANIFEST + ".bundle.jsonl"
INVENTORY = "installed-inventory.json"
CUSTOM_TARGETS = {"aarch64-pc-windows-msvc": "windows-aarch64",
                  "x86_64-apple-darwin": "macos-x86_64"}
MAX_METADATA = 16 * 1024 * 1024
TRUSTED_ROOT = "packaging/release-trusted-root.jsonl"
TRUSTED_ROOT_SHA256 = "3c2cc7f357dc064ec527fdcd78da6e9245c21a381e1abaa0f2b62b186bcac1a1"


def lock_path(target: str) -> str:
    require(target in TARGETS, "unsupported CUA target")
    return f"packaging/cua/locks/{target}.lock"


def metadata(root: Path, name: str) -> tuple[bytes, dict]:
    raw = read_owned(root, name)
    require(len(raw) <= MAX_METADATA, "CUA metadata exceeds limit")
    return raw, parse_json(raw)


def manifest(root: Path) -> tuple[bytes, dict]:
    raw, value = metadata(root, MANIFEST)
    require(type(value.get("schema")) is int and value["schema"] == 1
            and value.get("repository") == REPOSITORY and value.get("workflow") == WORKFLOW
            and type(value.get("run_attempt")) is int and value["run_attempt"] == 1,
            "native wheel producer identity differs")
    require(all(type(value.get(key)) is int and value[key] > 0
                for key in ("repository_id", "workflow_id", "run_id")),
            "native wheel producer identity absent")
    require(isinstance(value.get("producer_sha"), str)
            and re.fullmatch(r"[0-9a-f]{40}", value["producer_sha"])
            and value.get("input_commit") == value["producer_sha"]
            and isinstance(value.get("inputs"), dict)
            and value.get("input_sha256") == sha256_bytes(canonical_json(value["inputs"])),
            "native wheel input descriptor differs")
    wheels = value.get("wheels")
    require(isinstance(wheels, list) and len(wheels) == 2
            and all(isinstance(row, dict) for row in wheels)
            and {row.get("target") for row in wheels} == set(CUSTOM_TARGETS.values()),
            "native wheel target set differs")
    require(len({row.get("artifact_id") for row in wheels}) == 2
            and len({row.get("job_id") for row in wheels}) == 2,
            "native wheel outputs reuse an identity")
    for row in wheels:
        require(all(type(row.get(key)) is int and row[key] > 0
                    for key in ("size", "artifact_id", "job_id"))
                and all(valid_hash(row.get(key)) for key in (
                    "sha256", "test_report_sha256", "build_report_sha256", "build_sbom_sha256"))
                and isinstance(row.get("artifact_digest"), str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", row["artifact_digest"])
                and isinstance(row.get("image_version"), str) and row["image_version"],
                "native wheel output identity absent")
        name = relative_path(row.get("filename"))
        platform = ("win_arm64" if row["target"] == "windows-aarch64"
                    else "macosx_13_0_x86_64")
        require(name == f"cryptography-50.0.1-cp311-abi3-{platform}.whl",
                "native wheel filename or ABI differs")
    return raw, value


def selected_lock(raw: bytes) -> dict[str, tuple[str, str]]:
    """One exact version and one selected wheel digest per distribution."""
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise PackageInputError("target lock is not UTF-8") from None
    result = {}
    text = text.replace("\\\r\n", " ").replace("\\\n", " ")
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)"
                             r"\s+--hash=sha256:([0-9a-f]{64})", line)
        require(match is not None, "target lock must select one exact wheel per package")
        name, version, digest = match.groups()
        name = re.sub(r"[-_.]+", "-", name).lower()
        require(name not in result, "target lock repeats a distribution")
        result[name] = (version, digest)
    require(result, "target lock is empty")
    return result


def reviewed_inputs(source: Path, trusted: Path, target: str) -> dict[str, str]:
    lock_name = lock_path(target)
    for name in (MANIFEST, BUNDLE, lock_name):
        require(read_owned(source, name) == read_owned(trusted, name),
                "CUA release input differs from reviewed default-branch bytes")
    raw, value = manifest(trusted)
    lock = read_owned(trusted, lock_name)
    selected = selected_lock(lock)
    if target in CUSTOM_TARGETS:
        wheel = next(row for row in value["wheels"] if row["target"] == CUSTOM_TARGETS[target])
        require(selected.get("cryptography") == ("50.0.1", wheel["sha256"]),
                "target lock does not select the reviewed native wheel")
    else:
        require(not any(digest == row["sha256"] for _, digest in selected.values()
                        for row in value["wheels"]), "custom wheel selected on a different target")
    return {"target": target, "wheel_manifest_sha256": sha256_bytes(raw),
            "requirements_sha256": sha256_bytes(lock)}


def github(endpoint: str):
    result = subprocess.run(["gh", "api", "--method", "GET",
                             f"repos/{REPOSITORY}/{endpoint}"],
                            capture_output=True, timeout=90, check=False)
    require(result.returncode == 0 and len(result.stdout) <= MAX_METADATA,
            "native wheel origin cannot be resolved")
    return parse_json(result.stdout)


def verify_attestation(root: Path, value: dict) -> None:
    # The fixed issuer, hosted-runner policy and exact reviewed producer SHA
    # are enforced by the verifier, not by self-reported predicate fields.
    require(sha256_bytes(read_owned(root, TRUSTED_ROOT)) == TRUSTED_ROOT_SHA256,
            "native wheel verifier trust root differs")
    result = subprocess.run([
        "gh", "attestation", "verify", str(root / MANIFEST),
        "--bundle", str(root / BUNDLE), "--repo", REPOSITORY,
        "--cert-identity", f"https://github.com/{REPOSITORY}/{WORKFLOW}@refs/heads/master",
        "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
        "--signer-workflow", f"{REPOSITORY}/{WORKFLOW}",
        "--signer-digest", value["producer_sha"],
        "--source-digest", value["input_commit"], "--source-ref", "refs/heads/master",
        "--custom-trusted-root", str(root / TRUSTED_ROOT),
        "--deny-self-hosted-runners", "--format", "json",
    ], capture_output=True, timeout=120, check=False)
    require(result.returncode == 0 and 0 < len(result.stdout) <= MAX_METADATA,
            "native wheel attestation verification failed")
    verified = json.loads(result.stdout)
    require(isinstance(verified, list) and verified,
            "native wheel verifier returned no verified attestation")


def verify_origin(trusted: Path) -> None:
    _, value = manifest(trusted)
    verify_attestation(trusted, value)
    run = github(f"actions/runs/{value['run_id']}")
    require(all(run.get(key) == expected for key, expected in {
        "id": value["run_id"], "head_sha": value["producer_sha"], "head_branch": "master",
        "event": "workflow_dispatch", "run_attempt": 1, "status": "completed",
        "conclusion": "success", "path": WORKFLOW, "workflow_id": value["workflow_id"],
    }.items()) and run.get("repository", {}).get("full_name") == REPOSITORY
        and run.get("repository", {}).get("id") == value["repository_id"],
        "native wheel run does not match reviewed successful producer")
    for row in value["wheels"]:
        job = github(f"actions/jobs/{row['job_id']}")
        windows = row["target"] == "windows-aarch64"
        expected_label = "windows-11-arm" if windows else "macos-15-intel"
        require(job.get("id") == row["job_id"] and job.get("run_id") == value["run_id"]
                and job.get("head_sha") == value["producer_sha"]
                and job.get("status") == "completed"
                and job.get("conclusion") == "success"
                and job.get("name") == ("build-windows" if windows else "build-macos")
                and job.get("runner_group_name") == "GitHub Actions"
                and expected_label in job.get("labels", []),
                "native wheel job does not match reviewed hosted producer")
        artifact = github(f"actions/artifacts/{row['artifact_id']}")
        origin = artifact.get("workflow_run", {})
        require(artifact.get("id") == row["artifact_id"] and artifact.get("expired") is False
                and artifact.get("name") == "native-wheel-" + row["target"]
                and artifact.get("digest") == row["artifact_digest"]
                and origin.get("id") == value["run_id"]
                and origin.get("head_sha") == value["producer_sha"]
                and origin.get("head_branch") == "master",
                "native wheel artifact is unavailable or changed")


def validate_payload(root: Path, binding: dict[str, str]) -> dict[str, str]:
    """Check the complete private runtime tree, never execute its interpreter."""
    _, payload = metadata(root, "payload.json")
    require(type(payload.get("schema")) is int and payload["schema"] == 2,
            "new candidate requires schema-2 CUA payload")
    require(set(binding) == {"target", "requirements_sha256", "wheel_manifest_sha256"}
            and binding["target"] in TARGETS
            and all(valid_hash(binding[key]) for key in ("requirements_sha256", "wheel_manifest_sha256"))
            and all(payload.get(key) == value for key, value in binding.items()),
            "CUA payload differs from reviewed target inputs")
    raw, inventory = metadata(root, INVENTORY)
    require(payload.get("installed_inventory_sha256") == sha256_bytes(raw),
            "installed CUA inventory digest differs")
    require(set(inventory) == {"schema", "target", "files"}
            and type(inventory["schema"]) is int and inventory["schema"] == 1
            and inventory["target"] == binding["target"]
            and isinstance(inventory["files"], dict) and inventory["files"],
            "installed CUA inventory schema differs")
    files = inventory["files"]
    require(len(files) <= 100_000, "installed CUA inventory exceeds limit")
    seen = set()
    for name, record in files.items():
        relative_path(name)
        normalized = unicodedata.normalize("NFC", name).casefold()
        require(normalized not in seen and name not in (INVENTORY, "payload.json"),
                "installed CUA inventory has duplicate or excluded path")
        seen.add(normalized)
        require(isinstance(record, dict) and set(record) == {"size", "sha256"}
                and type(record["size"]) is int and record["size"] >= 0
                and valid_hash(record["sha256"]), "installed CUA file identity invalid")
        data = read_owned(root, name)
        require(len(data) == record["size"] and sha256_bytes(data) == record["sha256"],
                "installed CUA file bytes differ")
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
                "installed CUA inventory contains unrecorded link")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(files) | {INVENTORY, "payload.json"},
            "installed CUA file set differs")
    return {**binding, "installed_inventory_sha256": sha256_bytes(raw)}
