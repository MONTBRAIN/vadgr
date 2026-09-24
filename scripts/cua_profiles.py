#!/usr/bin/env python3
"""Data-only admission for reviewed CUA release profiles.

Profile inputs are promoted through trusted source review. This module never
resolves a newest artifact, invents a pin, executes a wheel, or approves inputs.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess

if __package__:
    from scripts import cua_release_inputs as release
    from scripts.validate_package_inputs import (
        PackageInputError, parse_json, read_owned, relative_path, require, sha256_bytes, valid_hash,
    )
else:
    import cua_release_inputs as release
    from validate_package_inputs import (
        PackageInputError, parse_json, read_owned, relative_path, require, sha256_bytes, valid_hash,
    )

PROFILES = tuple(f"{system}-{arch}" for system in ("windows", "macos", "linux", "wsl")
                 for arch in ("x86_64", "aarch64"))
INPUTS = "packaging/cua/profile-inputs.json"
CATALOG = "packaging/cua/cua-profile-catalog.json"
BUNDLE = "packaging/cua/cua-profile-catalog.sigstore.json"
PUBLICATION = "packaging/cua/cua-profile-publication.json"
REPOSITORY = "MONTBRAIN/vadgr-computer-use"
WORKFLOW = ".github/workflows/profile-wheels.yml"
PREFIX = "computer_use/browser/"
MAX_EXPANDED = 1024 * 1024 * 1024
MAX_FILES = 20_000


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def document(raw):
    require(len(raw) <= release.MAX_METADATA, "profile metadata exceeds limit")
    value = parse_json(raw)
    require(canonical(value) == raw, "profile metadata is not canonical UTF-8 JSON")
    return value


def target_for(profile):
    require(profile in PROFILES, "unknown CUA release profile")
    system, arch = profile.split("-", 1)
    return arch + "-" + {"windows": "pc-windows-msvc", "macos": "apple-darwin",
                         "linux": "unknown-linux-gnu", "wsl": "unknown-linux-gnu"}[system]


def lock_path(profile):
    target_for(profile)
    return f"packaging/cua/profile-locks/{profile}.lock"


def native_profile(target):
    matches = [profile for profile in PROFILES if not profile.startswith("wsl-") and target_for(profile) == target]
    require(len(matches) == 1, "unknown native release profile")
    return matches[0]


def identity(row, key="filename"):
    require(isinstance(row, dict) and set(row) == {key, "size", "sha256"}
            and type(row["size"]) is int and (0 if key != "filename" else 1) <= row["size"] <= MAX_EXPANDED
            and valid_hash(row["sha256"]), "invalid profile file identity")
    relative_path(row[key])
    if key == "filename":
        require("/" not in row[key], "profile asset is not a basename")


def reviewed(source: Path, trusted: Path, profile: str):
    """Require the feature's entire mapping and selected lock to match master."""
    target = target_for(profile)
    for name in (INPUTS, CATALOG, BUNDLE, lock_path(profile), release.MANIFEST, release.BUNDLE):
        require(read_owned(source, name) == read_owned(trusted, name),
                "CUA profile input differs from trusted default-branch bytes")
    raw = read_owned(trusted, INPUTS)
    value = document(raw)
    require(set(value) == {"schema", "publication_state", "catalog_sha256", "bundle_sha256",
                           "artifact_id", "artifact_sha256", "publication_sha256", "profiles"}
            and type(value["schema"]) is int and value["schema"] == 1
            and value["publication_state"] in ("held", "released")
            and type(value["artifact_id"]) is int and value["artifact_id"] > 0
            and all(valid_hash(value[k]) for k in ("catalog_sha256", "bundle_sha256", "artifact_sha256"))
            and isinstance(value["profiles"], dict) and set(value["profiles"]) == set(PROFILES),
            "reviewed CUA profile input schema differs")
    for row in value["profiles"].values():
        require(isinstance(row, dict)
                and set(row) == {"requirements_sha256", "wheel_sha256", "role_manifest_sha256"}
                and all(valid_hash(digest) for digest in row.values()), "profile lock binding differs")
    if value["publication_state"] == "held":
        require(value["publication_sha256"] is None, "held inputs cannot claim publication")
    else:
        require(valid_hash(value["publication_sha256"]), "released inputs lack publication")
        publication = read_owned(trusted, PUBLICATION)
        require(read_owned(source, PUBLICATION) == publication
                and sha256_bytes(publication) == value["publication_sha256"],
                "reviewed publication record differs")
    catalog_raw, bundle = read_owned(trusted, CATALOG), read_owned(trusted, BUNDLE)
    require(sha256_bytes(catalog_raw) == value["catalog_sha256"]
            and sha256_bytes(bundle) == value["bundle_sha256"], "profile catalog binding differs")
    catalog = document(catalog_raw)
    require(set(catalog) == {"schema", "cua_version", "source_commit", "producer", "profiles", "standalone"}
            and type(catalog["schema"]) is int and catalog["schema"] == 1
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", catalog["cua_version"])
            and re.fullmatch(r"[0-9a-f]{40}", catalog["source_commit"])
            and set(catalog["profiles"]) == set(PROFILES), "profile catalog schema differs")
    producer = catalog["producer"]
    require(set(producer) == {"repository", "repository_id", "owner_id", "source_commit", "tooling_commit",
                              "workflow", "workflow_id", "ref", "event", "run_id", "attempt", "runner_environment"}
            and producer["repository"] == REPOSITORY and producer["workflow"] == WORKFLOW
            and producer["ref"] == "refs/heads/master" and producer["event"] == "workflow_dispatch"
            and type(producer["attempt"]) is int and producer["attempt"] == 1
            and producer["runner_environment"] == "github-hosted"
            and producer["source_commit"] == catalog["source_commit"]
            and re.fullmatch(r"[0-9a-f]{40}", producer["tooling_commit"])
            and all(type(producer[k]) is int and producer[k] > 0
                    for k in ("repository_id", "owner_id", "workflow_id", "run_id")),
            "profile producer identity differs")
    for selected_profile, entry in catalog["profiles"].items():
        require(set(entry) == {"interpreter", "wheel", "input_role_manifest", "evidence"},
                "profile catalog entry differs")
        identity(entry["wheel"])
        identity(entry["input_role_manifest"])
        pins = value["profiles"][selected_profile]
        require(pins["wheel_sha256"] == entry["wheel"]["sha256"]
                and pins["role_manifest_sha256"] == entry["input_role_manifest"]["sha256"],
                "profile selected artifact differs")
    lock = read_owned(trusted, lock_path(profile))
    pins = value["profiles"][profile]
    require(sha256_bytes(lock) == pins["requirements_sha256"], "profile transitive lock differs")
    selected = release.selected_lock(lock)
    require(selected.get("vadgr-computer-use") == (catalog["cua_version"], pins["wheel_sha256"]),
            "profile lock does not select its exact CUA wheel")
    native_raw, native = release.manifest(trusted)
    if target in release.CUSTOM_TARGETS:
        wheel = next(r for r in native["wheels"] if r["target"] == release.CUSTOM_TARGETS[target])
        require(selected.get("cryptography") == ("50.0.1", wheel["sha256"]),
                "profile lock does not select the reviewed native dependency")
    binding = {"target": target, "requirements_sha256": pins["requirements_sha256"],
               "wheel_manifest_sha256": sha256_bytes(native_raw), "release_profile": profile,
               "cua_profile_manifest_sha256": pins["role_manifest_sha256"]}
    return binding, value, catalog


def _gh(endpoint, binary=False):
    result = subprocess.run(["gh", "api", "--method", "GET", f"repos/{REPOSITORY}/{endpoint}"],
                            capture_output=True, timeout=180, check=False)
    require(result.returncode == 0 and len(result.stdout) <= MAX_EXPANDED,
            "reviewed profile origin unavailable")
    return result.stdout if binary else parse_json(result.stdout)


def producer_head(producer):
    """Return the landed workflow identity, not the separately built source."""
    value = producer.get("tooling_commit", "")
    require(re.fullmatch(r"[0-9a-f]{40}", value), "profile producer tooling identity differs")
    return value


def retrieve(trusted, inputs, catalog):
    """Verify the reviewed producer and retrieve an immutable retained closure."""
    from_scripts = __package__ is not None and bool(__package__)
    if from_scripts:
        from scripts.cua_wheelhouse import archive_members
    else:
        from cua_wheelhouse import archive_members
    producer = catalog["producer"]
    tooling_commit = producer_head(producer)
    require(sha256_bytes(read_owned(trusted, release.TRUSTED_ROOT)) == release.TRUSTED_ROOT_SHA256,
            "profile verifier root differs")
    verified = subprocess.run([
        "gh", "attestation", "verify", str(trusted / CATALOG), "--bundle", str(trusted / BUNDLE),
        "--repo", REPOSITORY, "--cert-identity",
        f"https://github.com/{REPOSITORY}/{WORKFLOW}@refs/heads/master",
        "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
        "--source-ref", "refs/heads/master", "--source-digest", tooling_commit,
        "--signer-digest", tooling_commit, "--deny-self-hosted-runners",
        "--custom-trusted-root", str(trusted / release.TRUSTED_ROOT), "--format", "json",
    ], capture_output=True, timeout=180, check=False)
    require(verified.returncode == 0 and verified.stdout, "profile attestation refused")
    repository = _gh("")
    require(repository.get("id") == producer["repository_id"]
            and repository.get("owner", {}).get("id") == producer["owner_id"],
            "profile repository identity differs")
    run = _gh(f"actions/runs/{producer['run_id']}")
    require(all(run.get(k) == v for k, v in {
        "head_sha": tooling_commit, "head_branch": "master", "run_attempt": 1,
        "event": "workflow_dispatch", "workflow_id": producer["workflow_id"],
        "conclusion": "success", "status": "completed", "path": WORKFLOW,
    }.items()), "profile producer run differs")
    jobs = set()
    for entry in catalog["profiles"].values():
        evidence = entry["evidence"]
        require(set(evidence) == {"build_sha256", "test_sha256", "sbom_sha256", "native_job_ids", "artifacts"}
                and all(valid_hash(evidence[k]) for k in ("build_sha256", "test_sha256", "sbom_sha256"))
                and evidence["native_job_ids"] and evidence["artifacts"], "profile producer evidence absent")
        for job_id in evidence["native_job_ids"]:
            require(type(job_id) is int and job_id > 0, "profile native job identity absent")
            if job_id in jobs:
                continue
            job = _gh(f"actions/jobs/{job_id}")
            require(job.get("run_id") == producer["run_id"] and job.get("head_sha") == tooling_commit
                    and job.get("conclusion") == "success" and job.get("runner_group_name") == "GitHub Actions"
                    and job.get("name") in ("native-x86_64", "native-aarch64"), "profile native job differs")
            jobs.add(job_id)
        for row in evidence["artifacts"]:
            require(set(row) == {"id", "sha256"} and type(row["id"]) is int and row["id"] > 0
                    and valid_hash(row["sha256"]), "profile native artifact identity absent")
            _artifact(row["id"], row["sha256"], producer)
    _artifact(inputs["artifact_id"], inputs["artifact_sha256"], producer)
    raw = _gh(f"actions/artifacts/{inputs['artifact_id']}/zip", binary=True)
    require(sha256_bytes(raw) == inputs["artifact_sha256"], "retained profile artifact changed")
    members = archive_members(raw, limit=MAX_EXPANDED)
    require(members.get("cua-profile-catalog.json") == read_owned(trusted, CATALOG)
            and members.get("cua-profile-catalog.sigstore.json") == read_owned(trusted, BUNDLE),
            "retained catalog differs")
    expected = {"cua-profile-catalog.json", "cua-profile-catalog.sigstore.json"}
    for entry in [*catalog["profiles"].values(), catalog["standalone"]]:
        for key in ("wheel", "input_role_manifest"):
            if key not in entry:
                continue
            row = entry[key]
            identity(row)
            data = members.get(row["filename"], b"")
            require(len(data) == row["size"] and sha256_bytes(data) == row["sha256"],
                    "retained profile bytes differ")
            expected.add(row["filename"])
    require(set(members) == expected, "retained profile artifact file set differs")
    if inputs["publication_state"] == "released":
        _verify_publication(trusted, catalog, members)
    return members


def _artifact(artifact_id, digest, producer):
    item = _gh(f"actions/artifacts/{artifact_id}")
    origin = item.get("workflow_run", {})
    require(item.get("id") == artifact_id and item.get("expired") is False
            and item.get("digest") == "sha256:" + digest and origin.get("id") == producer["run_id"]
            and origin.get("head_sha") == producer_head(producer) and origin.get("head_branch") == "master",
            "profile artifact unavailable or origin differs")


def _verify_publication(trusted, catalog, members):
    # The CUA publication producer emits compact canonical JSON, while the
    # pre-publication wheel catalog deliberately uses indented canonical JSON.
    raw = read_owned(trusted, PUBLICATION)
    publication = parse_json(raw)
    require((json.dumps(publication, sort_keys=True, separators=(",", ":")) + "\n").encode() == raw,
            "publication record is not canonical")
    require(publication.get("schema") == 1 and publication.get("repository") == REPOSITORY
            and publication.get("cua_version") == catalog["cua_version"]
            and publication.get("catalog_sha256") == sha256_bytes(read_owned(trusted, CATALOG))
            and publication.get("tag") == "v" + catalog["cua_version"], "publication binding differs")
    released = _gh(f"releases/{publication['release_id']}")
    require(released.get("immutable") is True and released.get("draft") is False
            and released.get("prerelease") is False and released.get("tag_name") == publication["tag"],
            "CUA release is not immutable and published")
    assets = {a["id"]: a for a in released.get("assets", [])}
    seen = set()
    for row in publication["assets"]:
        asset = assets.get(row["id"], {})
        require(row["filename"] in members and row["filename"] not in seen
                and asset.get("name") == row["filename"] and asset.get("size") == row["size"]
                and asset.get("digest") == "sha256:" + row["sha256"]
                and sha256_bytes(members[row["filename"]]) == row["sha256"], "CUA published asset differs")
        seen.add(row["filename"])
    require(seen == set(members), "CUA publication asset set differs")


def validate_members(members, profile, expected_manifest):
    """Reconstruct roles, archives and hashes independently, including nested PE."""
    if __package__:
        from scripts.cua_wheelhouse import archive_members, binary_architecture
    else:
        from cua_wheelhouse import archive_members, binary_architecture
    target_for(profile)
    manifest_path = PREFIX + f"profiles/{profile}/cua-profile-manifest.json"
    raw = members.get(manifest_path, b"")
    require(sha256_bytes(raw) == expected_manifest, "profile role manifest digest differs")
    manifest = document(raw)
    require(set(manifest) == {"schema", "cua_version", "source_commit", "release_profile", "interpreter",
                              "files", "executables", "archives", "helpers"}
            and manifest["schema"] == 1 and manifest["release_profile"] == profile,
            "profile role manifest identity differs")
    trust_path = PREFIX + "_profile_trust.py"
    try:
        tree = ast.parse(members[trust_path].decode("utf-8"))
        require(len(tree.body) == 1 and isinstance(tree.body[0], ast.Assign)
                and len(tree.body[0].targets) == 1 and isinstance(tree.body[0].targets[0], ast.Name)
                and tree.body[0].targets[0].id == "TRUST", "profile managed marker differs")
        trust = ast.literal_eval(tree.body[0].value)
    except (ValueError, SyntaxError, KeyError, UnicodeError):
        raise PackageInputError("profile managed marker is missing or invalid") from None
    require(trust == {"schema": 1, "mode": "managed", "release_profile": profile,
                      "manifest_sha256": {profile: expected_manifest}}, "profile cannot fall back to standalone")
    files = {}
    for row in manifest["files"]:
        identity(row, "wheel_path")
        path = row["wheel_path"]
        require(path not in files and path not in (manifest_path, trust_path), "profile file set repeats metadata")
        data = members.get(path, b"")
        require(len(data) == row["size"] and sha256_bytes(data) == row["sha256"], "profile file identity differs")
        files[path] = data
    # Wheel metadata generated after the manifest is admitted separately by the
    # wheel parser; executable metadata and unmanifested package files are not.
    metadata = {p for p in members if re.fullmatch(r"vadgr_computer_use-[^/]+\.dist-info/"
                                                r"(METADATA|WHEEL|RECORD|entry_points\.txt)", p)}
    require(set(members) == set(files) | metadata | {manifest_path, trust_path},
            "profile wheel has missing or extra files")
    os_name, arch = profile.split("-", 1)
    execution_os = "linux" if os_name == "wsl" else os_name
    executables, archives, budget = [], [], [0, 0]

    def visit(wheel_path, chain, data, depth):
        require(depth <= 4, "profile nested archive depth exceeded")
        name = chain[-1] if chain else wheel_path
        native = data.startswith((b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"))
        script = name.endswith((".py", ".sh", ".ps1"))
        require(not data.startswith(b"#!") or script, "profile executable disguised as data")
        if native or script:
            role, process_os = "runtime", execution_os
            if wheel_path.startswith(PREFIX + "winhost/") and native:
                role, process_os = "browser-relay", "windows"
            elif wheel_path.startswith(PREFIX + "winbroker/") and (native or name.endswith(".ps1")):
                role, process_os = "browser-broker", "windows"
            require(role == "runtime" or os_name in ("windows", "wsl"), "foreign helper profile refused")
            if native:
                kind, actual_arch = binary_architecture(data)
                require(kind == {"windows": "pe", "linux": "elf", "macos": "macho"}[process_os]
                        and actual_arch == arch, "profile native execution role or architecture differs")
            executables.append({"release_profile": profile, "role": role, "execution_os": process_os,
                                "architecture": arch, "wheel_path": wheel_path, "archive_members": chain,
                                "size": len(data), "sha256": sha256_bytes(data),
                                "component": "vadgr-computer-use" if not chain else "browser-broker-runtime",
                                "consumer": "computer_use.browser.windows_broker" if role == "browser-broker"
                                else "computer_use.setup.extension_setup" if role == "browser-relay"
                                else "computer_use.mcp_server"})
        elif name.lower().endswith((".exe", ".dll", ".pyd", ".so", ".dylib")):
            raise PackageInputError("profile native member has no recognized header")
        if data.startswith((b"PK\x03\x04", b"PK\x05\x06")):
            nested = archive_members(data)
            budget[0] += sum(map(len, nested.values()))
            budget[1] += len(nested)
            require(budget[0] <= MAX_EXPANDED and budget[1] <= MAX_FILES, "profile archive budget exceeded")
            archives.append({"wheel_path": wheel_path, "archive_members": chain, "size": len(data),
                             "sha256": sha256_bytes(data), "members": [
                                 {"path": p, "size": len(b), "sha256": sha256_bytes(b)} for p, b in sorted(nested.items())]})
            for path, payload in sorted(nested.items()):
                visit(wheel_path, chain + [path], payload, depth + 1)
        elif (name.lower().endswith((".zip", ".7z", ".tar", ".gz", ".xz", ".bz2"))
              or data.startswith((b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b", b"\xfd7zXZ", b"Rar!"))
              or data[257:262] == b"ustar"):
            raise PackageInputError("profile contains an opaque or malformed container")

    for path, data in sorted(files.items()):
        visit(path, [], data, 0)
    require(manifest["executables"] == executables and manifest["archives"] == archives,
            "profile executable or nested archive inventory differs")
    helper = manifest["helpers"]
    if os_name not in ("windows", "wsl"):
        require(helper is None, "native profile declares foreign helpers")
    else:
        require(isinstance(helper, dict) and set(helper) == {"architecture", "relay", "archive", "member_manifest"}
                and helper["architecture"] == arch, "profile helper architecture differs")
        for key, prefix in (("relay", "winhost/"), ("archive", "winbroker/"), ("member_manifest", "winbroker/")):
            row = helper[key]
            identity(row, "path")
            require(row["path"].startswith(PREFIX + prefix + arch + "/")
                    and row["path"] in files and len(files[row["path"]]) == row["size"]
                    and sha256_bytes(files[row["path"]]) == row["sha256"], "profile helper identity differs")
    return manifest
