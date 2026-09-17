"""Synthetic boundary checks, not a vendor signature or release qualification."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import candidate_policy
from scripts.candidate import validate_manifest as gate


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def held(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "MONTBRAIN/vadgr")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/master")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ID", "12")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    payload = {"legal/TERMS.txt": b"Reviewed terms", "legal/NOTICE.txt": b"Notice",
               "sbom/vadgr.json": b"{}", "Vadgr-0.5.0-windows-x64-setup.exe": b"fixture",
               "Vadgr-0.5.0-windows-x64.msi": b"fixture MSI"}
    for name, data in payload.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    approval = {"legal_hashes": {"payload/" + name: sha(data) for name, data in payload.items()
                                 if name.startswith("legal/")},
                "sbom_sha256": sha(b"{}"), "inventory_sha256": "e" * 64,
                "generator_sha256": "f" * 64}
    monkeypatch.setattr(gate, "trusted_approval", lambda arch: approval)
    authorization = {"repository": "MONTBRAIN/vadgr", "version": "0.5.0", "architecture": "x64",
                     "trusted_sha": "a" * 40, "source_sha": "c" * 40, "source_tree": "d" * 40,
                     "run_id": 12, "run_attempt": 1, "candidate_id": "v0.5.0-rc-1",
                     "input_digest": "b" * 64, "cua_version": "0.7.8", "python_version": "3.12.9",
                     "legal_approval_sha256": sha(json.dumps(approval, sort_keys=True).encode())}
    manifest = {"schema": 1, "product": "vadgr", "version": "0.5.0", "release_sequence": 500,
                "tag": "v0.5.0", "source_commit": "c" * 40, "terms_version": "1.0",
                "terms_sha256": sha(payload["legal/TERMS.txt"]), "cua_version": "0.7.8",
                "python_version": "3.12.9", "artifacts": [{"name": "Vadgr-0.5.0-windows-x64-setup.exe",
                    "target": "windows-x86_64", "kind": "burn", "size": 7,
                    "sha256": sha(b"fixture"), "native_signature": "authenticode"}]}
    manifest["legal_hashes"] = {name: sha(data) for name, data in payload.items() if name.startswith("legal/")}
    manifest["sbom_hashes"] = {"sbom/vadgr.json": sha(b"{}")}
    for name, value in (("authorization.json", authorization), ("release-manifest.json", manifest)):
        (tmp_path / name).write_text(json.dumps(value))
    return tmp_path, manifest


def test_validated_manifest_preserves_exact_bytes(held):
    root, _ = held
    before = (root / "release-manifest.json").read_bytes()
    gate.validate(root, "x64")
    assert (root / "release-manifest.json").read_bytes() == before


@pytest.mark.parametrize("field,value", [("schema", True), ("source_commit", "e" * 40),
    ("release_sequence", 501), ("version", "0.5.1"), ("terms_sha256", "f" * 64),
    ("cua_version", "0.7.7"), ("extra", "not allowed"), ("legal_hashes", {}),
    ("sbom_hashes", {})])
def test_manifest_substitution_refused(held, field, value):
    root, manifest = held
    manifest[field] = value
    (root / "release-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(candidate_policy.Refused):
        gate.validate(root, "x64")


@pytest.mark.parametrize("mutation", ["target", "unsigned", "extra", "size", "hash"])
def test_artifact_substitution_refused(held, mutation):
    root, manifest = held
    artifact = manifest["artifacts"][0]
    if mutation == "extra":
        manifest["artifacts"].append(dict(artifact))
    else:
        key, value = {"target": ("target", "windows-aarch64"), "unsigned": ("native_signature", "none"),
                      "size": ("size", 8), "hash": ("sha256", "f" * 64)}[mutation]
        artifact[key] = value
    (root / "release-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(candidate_policy.Refused):
        gate.validate(root, "x64")


@pytest.mark.parametrize("path", ["legal/TERMS.txt", "legal/NOTICE.txt", "sbom/vadgr.json"])
def test_reviewed_bytes_tamper_refused(held, path):
    root, _ = held
    (root / path).write_bytes(b"changed")
    with pytest.raises(candidate_policy.Refused):
        gate.validate(root, "x64")


def test_extra_legal_file_refused(held):
    root, _ = held
    (root / "legal/extra.txt").write_bytes(b"unreviewed")
    with pytest.raises(candidate_policy.Refused):
        gate.validate(root, "x64")


@pytest.mark.parametrize("name,value", [("GITHUB_REF", "refs/heads/feature"),
    ("GITHUB_REPOSITORY", "other/vadgr"), ("GITHUB_RUN_ATTEMPT", "2"),
    ("GITHUB_RUN_ID", "13"), ("GITHUB_SHA", "e" * 40)])
def test_wrong_producer_refused(held, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(candidate_policy.Refused):
        gate.validate(held[0], "x64")


def test_duplicate_json_fields_refused(held):
    root, _ = held
    path = root / "release-manifest.json"
    path.write_text(path.read_text().replace('"schema": 1', '"schema": 1, "schema": 1'))
    with pytest.raises(candidate_policy.Refused):
        gate.validate(root, "x64")


def test_missing_trusted_legal_approval_refused(held, monkeypatch):
    def missing(_):
        raise candidate_policy.Refused("reviewed legal approval is not configured")
    monkeypatch.setattr(gate, "trusted_approval", missing)
    with pytest.raises(candidate_policy.Refused, match="approval"):
        gate.validate(held[0], "x64")


def test_public_root_replaces_offline_private_key_requirement():
    root = Path(__file__).resolve().parents[2] / "packaging/release-trusted-root.jsonl"
    candidate_policy.require_release_inputs(root.read_text(), "Final terms", True, True)
    with pytest.raises(candidate_policy.Refused):
        candidate_policy.require_release_inputs(root.read_text() + " ", "Final terms", True, True)
    with pytest.raises(candidate_policy.Refused):
        candidate_policy.require_release_inputs(root.read_text(), "pending legal review", True, True)
    with pytest.raises(candidate_policy.Refused):
        candidate_policy.require_release_inputs(root.read_text(), "Final terms", False, True)


def test_attestation_is_gated_single_subject_and_persisted():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/candidate.yml").read_text()
    job = workflow.split("\n  attest:", 1)[1]
    assert "needs: sign-windows" in job
    assert "secrets." not in job
    assert job.index("validate_manifest.py") < job.index("verify-held-windows.ps1") < job.index("actions/attest@")
    assert "subject-path: held/release-manifest.json" in job
    assert "held/**/*" not in job
    assert "release-manifest.json.bundle.jsonl" in job
    assert "--custom-trusted-root packaging/release-trusted-root.jsonl" in job
    assert "--source-ref refs/heads/master --deny-self-hosted-runners" in job
