"""Synthetic provenance for feature-held profile data; no signing authority."""

import base64
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import zipfile

import pytest

from scripts import cua_profiles as profiles
from scripts.validate_package_inputs import PackageInputError, sha256_bytes


def test_canonical_feature_data_keeps_identical_checkout_bytes():
    root = Path(__file__).resolve().parents[2]
    names = [profiles.INPUTS, profiles.CATALOG, profiles.BUNDLE, profiles.PUBLICATION,
             profiles.lock_path("windows-x86_64"), "packaging/cua/helper-signing/x86_64.json",
             "packaging/candidate-legal-approval.json"]
    result = subprocess.run(["git", "check-attr", "eol", "--", *names], cwd=root,
                            capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == [name + ": eol: lf" for name in names]


def write(root, name, raw):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def test_repository_origin_query_has_no_trailing_slash(monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=b'{"id":1}\n')

    monkeypatch.setattr(profiles.subprocess, "run", run)
    assert profiles._gh("") == {"id": 1}
    assert commands == [["gh", "api", "--method", "GET", "repos/MONTBRAIN/vadgr-computer-use"]]


@pytest.fixture
def admission(tmp_path, monkeypatch):
    source, trusted = tmp_path / "feature", tmp_path / "trusted"
    source.mkdir()
    trusted.mkdir()
    producer = {
        "repository": profiles.REPOSITORY, "repository_id": 1, "owner_id": 2,
        "source_commit": "a" * 40, "tooling_commit": "b" * 40,
        "workflow": profiles.WORKFLOW, "workflow_id": 3, "ref": "refs/heads/master",
        "event": "workflow_dispatch", "run_id": 4, "attempt": 1,
        "runner_environment": "github-hosted",
    }
    catalog = {"schema": 1, "cua_version": "0.7.9", "source_commit": "a" * 40,
               "producer": producer, "profiles": {}, "standalone": {}}
    inputs = {"schema": 1, "publication_state": "held", "artifact_id": 5,
              "publication_sha256": None, "profiles": {}}
    members = {}
    transitive = b"synthetic==1.0 --hash=sha256:" + b"c" * 64 + b"\n"
    for index, profile in enumerate(profiles.PROFILES):
        wheel = f"fixture-{profile}.whl"
        manifest = f"fixture-{profile}.json"
        members[wheel], members[manifest] = profile.encode(), b"{}\n"
        def identity(name):
            return {"filename": name, "size": len(members[name]),
                    "sha256": sha256_bytes(members[name])}
        catalog["profiles"][profile] = {
            "interpreter": {}, "wheel": identity(wheel), "input_role_manifest": identity(manifest),
            "evidence": {"build_sha256": "d" * 64, "test_sha256": "e" * 64,
                         "sbom_sha256": "f" * 64, "native_job_ids": [10 + index % 2],
                         "artifacts": [{"id": 20 + index % 2, "sha256": "d" * 64}]},
        }
        lock = transitive + b"vadgr-computer-use==0.7.9 --hash=sha256:" + sha256_bytes(members[wheel]).encode() + b"\n"
        inputs["profiles"][profile] = {
            "requirements_sha256": sha256_bytes(lock), "wheel_sha256": sha256_bytes(members[wheel]),
            "role_manifest_sha256": sha256_bytes(members[manifest]),
        }
        write(source, profiles.lock_path(profile), lock)
        write(trusted, profiles.release.lock_path(profiles.target_for(profile)), transitive)
    for name in (profiles.release.MANIFEST, profiles.release.BUNDLE):
        write(source, name, b"native fixture\n")
        write(trusted, name, b"native fixture\n")
    monkeypatch.setattr(profiles.release, "manifest", lambda root: (b"native fixture\n", {"wheels": []}))
    root = Path(__file__).resolve().parents[2]
    write(trusted, profiles.release.TRUSTED_ROOT, (root / profiles.release.TRUSTED_ROOT).read_bytes())
    catalog_raw, bundle = profiles.canonical(catalog), b"synthetic attestation\n"
    members["cua-profile-catalog.json"] = catalog_raw
    members["cua-profile-catalog.sigstore.json"] = bundle
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    archive_raw = buffer.getvalue()
    inputs.update(catalog_sha256=sha256_bytes(catalog_raw), bundle_sha256=sha256_bytes(bundle),
                  artifact_sha256=sha256_bytes(archive_raw))
    for name, raw in ((profiles.INPUTS, profiles.canonical(inputs)),
                      (profiles.CATALOG, catalog_raw), (profiles.BUNDLE, bundle)):
        write(source, name, raw)
    source_input = {"schema": 1, "source_commit": producer["source_commit"], "version": "0.7.9"}
    endpoints = {
        "": {"id": 1, "owner": {"id": 2}},
        "actions/runs/4": {"head_sha": producer["tooling_commit"], "head_branch": "master",
                           "run_attempt": 1, "event": "workflow_dispatch", "workflow_id": 3,
                           "conclusion": "success", "status": "completed", "path": profiles.WORKFLOW},
        f"contents/packaging/profiles/source-input.json?ref={producer['tooling_commit']}": {
            "type": "file", "encoding": "base64", "path": "packaging/profiles/source-input.json",
            "content": base64.b64encode(profiles.canonical(source_input)).decode()},
        "actions/artifacts/5/zip": archive_raw,
    }
    for job_id, arch in ((10, "x86_64"), (11, "aarch64")):
        endpoints[f"actions/jobs/{job_id}"] = {
            "run_id": 4, "head_sha": producer["tooling_commit"], "conclusion": "success",
            "runner_group_name": "GitHub Actions", "name": "native-" + arch,
        }
    for artifact_id, digest in ((5, inputs["artifact_sha256"]), (20, "d" * 64), (21, "d" * 64)):
        endpoints[f"actions/artifacts/{artifact_id}"] = {
            "id": artifact_id, "expired": False, "digest": "sha256:" + digest,
            "workflow_run": {"id": 4, "head_sha": producer["tooling_commit"], "head_branch": "master"},
        }
    commands = []
    verification = [{"verificationResult": {
        "signature": {"certificate": {
            "runInvocationURI": f"https://github.com/{profiles.REPOSITORY}/actions/runs/4/attempts/1",
            "sourceRepositoryDigest": producer["tooling_commit"],
            "buildSignerDigest": producer["tooling_commit"], "runnerEnvironment": "github-hosted"}},
        "statement": {"subject": [{"digest": {"sha256": inputs["catalog_sha256"]}}]},
    }}]
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=profiles.canonical(verification))
    monkeypatch.setattr(profiles.subprocess, "run", run)
    monkeypatch.setattr(profiles, "_gh", lambda endpoint, binary=False: copy.deepcopy(endpoints[endpoint]))
    return SimpleNamespace(source=source, trusted=trusted, inputs=inputs, catalog=catalog,
                           members=members, endpoints=endpoints, commands=commands, verification=verification)


def test_feature_held_data_is_admitted_without_advancing_signer_commit(admission):
    a = admission
    binding, inputs, catalog = profiles.reviewed(a.source, a.trusted, "linux-x86_64")
    assert binding["release_profile"] == "linux-x86_64"
    assert profiles.retrieve(a.trusted, inputs, catalog, source=a.source) == a.members
    command = a.commands[0]
    assert command[command.index("--source-digest") + 1] == "b" * 40
    assert command[command.index("--signer-digest") + 1] == "b" * 40
    assert command[3] == str(a.source / profiles.CATALOG)
    assert command[command.index("--custom-trusted-root") + 1] == str(a.trusted / profiles.release.TRUSTED_ROOT)


@pytest.mark.parametrize("name", [profiles.INPUTS, profiles.CATALOG, profiles.BUNDLE,
                                  profiles.lock_path("linux-x86_64")])
def test_existing_trusted_copy_still_requires_byte_equality(admission, name):
    a = admission
    write(a.trusted, name, b"changed\n")
    with pytest.raises(PackageInputError, match="differs from trusted"):
        profiles.reviewed(a.source, a.trusted, "linux-x86_64")


def test_feature_data_cannot_change_transitive_dependencies(admission):
    a = admission
    name = profiles.lock_path("linux-x86_64")
    raw = (a.source / name).read_bytes().replace(b"synthetic==1.0", b"synthetic==2.0")
    write(a.source, name, raw)
    a.inputs["profiles"]["linux-x86_64"]["requirements_sha256"] = sha256_bytes(raw)
    write(a.source, profiles.INPUTS, profiles.canonical(a.inputs))
    with pytest.raises(PackageInputError, match="transitive dependencies"):
        profiles.reviewed(a.source, a.trusted, "linux-x86_64")


@pytest.mark.parametrize("mutation", ["attestation", "run", "workflow", "branch", "job", "artifact",
                                      "source", "archive", "root", "attested-run", "attested-subject",
                                      "attested-tooling", "self-hosted"])
def test_feature_data_requires_independent_provenance(admission, monkeypatch, mutation):
    a = admission
    if mutation == "attestation":
        monkeypatch.setattr(profiles.subprocess, "run", lambda *args, **kwargs:
                            SimpleNamespace(returncode=1, stdout=b""))
    elif mutation.startswith("attested-") or mutation == "self-hosted":
        result = a.verification[0]["verificationResult"]
        if mutation == "attested-subject":
            result["statement"]["subject"][0]["digest"]["sha256"] = "f" * 64
        else:
            key = {"attested-run": "runInvocationURI", "attested-tooling": "buildSignerDigest",
                   "self-hosted": "runnerEnvironment"}[mutation]
            result["signature"]["certificate"][key] = "untrusted"
    elif mutation in ("run", "workflow", "branch"):
        key = {"run": "head_sha", "workflow": "workflow_id", "branch": "head_branch"}[mutation]
        a.endpoints["actions/runs/4"][key] = "untrusted"
    elif mutation == "job":
        a.endpoints["actions/jobs/10"]["head_sha"] = "a" * 40
    elif mutation == "artifact":
        a.endpoints["actions/artifacts/5"]["workflow_run"]["head_sha"] = "a" * 40
    elif mutation == "source":
        key = "contents/packaging/profiles/source-input.json?ref=" + "b" * 40
        a.endpoints[key]["content"] = base64.b64encode(profiles.canonical({
            "schema": 1, "source_commit": "c" * 40, "version": "0.7.9"})).decode()
    elif mutation == "archive":
        a.endpoints["actions/artifacts/5/zip"] += b"changed"
    else:
        write(a.trusted, profiles.release.TRUSTED_ROOT, b"untrusted root")
    with pytest.raises(PackageInputError):
        profiles.retrieve(a.trusted, a.inputs, a.catalog, source=a.source)


def test_retained_member_cannot_change_even_if_archive_metadata_matches(admission):
    a = admission
    members = dict(a.members)
    wheel = a.catalog["profiles"]["linux-x86_64"]["wheel"]["filename"]
    members[wheel] += b"changed"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    a.endpoints["actions/artifacts/5/zip"] = output.getvalue()
    a.inputs["artifact_sha256"] = sha256_bytes(output.getvalue())
    a.endpoints["actions/artifacts/5"]["digest"] = "sha256:" + a.inputs["artifact_sha256"]
    with pytest.raises(PackageInputError, match="profile bytes"):
        profiles.retrieve(a.trusted, a.inputs, a.catalog, source=a.source)


@pytest.mark.parametrize("mutation", [None, "not-immutable", "asset-digest", "trusted-copy",
                                      "extra-field", "boolean-schema", "extra-asset-field"])
def test_released_data_keeps_signer_stable_only_with_verified_publication(admission, mutation):
    a = admission
    rows = [{"id": index + 100, "filename": name, "size": len(raw), "sha256": sha256_bytes(raw)}
            for index, (name, raw) in enumerate(a.members.items())]
    publication = {"schema": 1, "repository": profiles.REPOSITORY, "cua_version": "0.7.9",
                   "catalog_sha256": a.inputs["catalog_sha256"], "tag": "v0.7.9",
                   "release_id": 900, "assets": rows}
    if mutation == "extra-field":
        publication["unreviewed"] = True
    elif mutation == "boolean-schema":
        publication["schema"] = True
    elif mutation == "extra-asset-field":
        rows[0]["unreviewed"] = True
    raw = (json.dumps(publication, sort_keys=True, separators=(",", ":")) + "\n").encode()
    write(a.source, profiles.PUBLICATION, raw)
    a.inputs.update(publication_state="released", publication_sha256=sha256_bytes(raw))
    write(a.source, profiles.INPUTS, profiles.canonical(a.inputs))
    a.endpoints["releases/900"] = {
        "immutable": True, "draft": False, "prerelease": False, "tag_name": "v0.7.9",
        "assets": [{"id": row["id"], "name": row["filename"], "size": row["size"],
                    "digest": "sha256:" + row["sha256"]} for row in rows],
    }
    if mutation == "not-immutable":
        a.endpoints["releases/900"]["immutable"] = False
    elif mutation == "asset-digest":
        a.endpoints["releases/900"]["assets"][0]["digest"] = "sha256:" + "f" * 64
    elif mutation == "trusted-copy":
        write(a.trusted, profiles.PUBLICATION, b"different\n")
    if mutation is None:
        _, inputs, catalog = profiles.reviewed(a.source, a.trusted, "linux-x86_64")
        assert profiles.retrieve(a.trusted, inputs, catalog, source=a.source) == a.members
    else:
        with pytest.raises(PackageInputError):
            _, inputs, catalog = profiles.reviewed(a.source, a.trusted, "linux-x86_64")
            profiles.retrieve(a.trusted, inputs, catalog, source=a.source)
