"""Proposed legal data cannot replace protected owner approval or trusted code."""

import hashlib
import json

import pytest

from scripts import candidate_policy as policy
from scripts.candidate import cua_shared as shared
from scripts.validate_package_inputs import PackageInputError


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


@pytest.fixture
def proposed(tmp_path):
    source, trusted = tmp_path / "source", tmp_path / "trusted"
    for root in (source, trusted):
        (root / "packaging/cua").mkdir(parents=True)
    (source / "packaging/cua/profile-inputs.json").write_bytes(b"{}\n")
    target = {"legal_hashes": {"payload/legal/TERMS.txt": "a" * 64},
              "sbom_sha256": "b" * 64, "inventory_sha256": "c" * 64,
              "generator_sha256": "d" * 64}
    value = {"schema": 1, "version": "0.5.0", "terms_version": "1.0", "targets": {"x64": target}}
    path = source / "packaging/candidate-legal-approval.json"
    path.write_bytes(canonical(value))
    return source, trusted, path, value


def test_proposed_approval_is_bound_into_exact_authorization(proposed):
    source, trusted, _, value = proposed
    actual = policy.candidate_approval(source, trusted, "x64")
    assert actual == value["targets"]["x64"]
    auth = {"architecture": "x64", "legal_approval": actual,
            "legal_approval_sha256": hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest()}
    assert policy.authorization_approval(auth, trusted) == actual
    auth["legal_approval"]["sbom_sha256"] = "f" * 64
    with pytest.raises(policy.Refused):
        policy.authorization_approval(auth, trusted)


@pytest.mark.parametrize("mutation", ["unknown-field", "unknown-target", "boolean-schema", "unsafe-path",
                                      "digest", "noncanonical", "trusted-copy", "not-profile"])
def test_untrusted_approval_changes_are_refused(proposed, mutation):
    source, trusted, path, value = proposed
    if mutation == "unknown-field":
        value["owner_approved"] = True
    elif mutation == "unknown-target":
        value["targets"]["other"] = value["targets"]["x64"]
    elif mutation == "boolean-schema":
        value["schema"] = True
    elif mutation == "unsafe-path":
        value["targets"]["x64"]["legal_hashes"]["../unowned"] = "a" * 64
    elif mutation == "digest":
        value["targets"]["x64"]["inventory_sha256"] = "bad"
    elif mutation == "trusted-copy":
        (trusted / "packaging/candidate-legal-approval.json").write_bytes(b"{}\n")
    elif mutation == "not-profile":
        (source / "packaging/cua/profile-inputs.json").unlink()
    path.write_bytes(json.dumps(value).encode() if mutation == "noncanonical" else canonical(value))
    with pytest.raises((policy.Refused, PackageInputError)):
        policy.candidate_approval(source, trusted, "x64")


def test_proposed_policy_cannot_replace_trusted_publisher(proposed):
    _, trusted, _, _ = proposed
    (trusted / "scripts/signing").mkdir(parents=True)
    (trusted / "scripts/signing/publisher.json").write_bytes(canonical({
        "subject": "CN=Fixture", "sha256": "a" * 64, "sha1": "b" * 40}))
    row = {"trust_class": "publisher-sign", "signer": "CN=Fixture", "certificate_sha256": "a" * 64}
    policy.require_publisher_policy({"files": {"fixture.exe": row}}, trusted)
    row["certificate_sha256"] = "c" * 64
    with pytest.raises(policy.Refused):
        policy.require_publisher_policy({"files": {"fixture.exe": row}}, trusted)


@pytest.mark.parametrize("suffix", [".json", "-outer.json", "-predecessors.json"])
def test_feature_policy_requires_legal_hash_and_existing_trusted_equality(proposed, suffix):
    source, trusted, _, value = proposed
    name = "packaging/cua/helper-signing/x86_64" + suffix
    raw = canonical({"schema": 1, "files": {}})
    (source / name).parent.mkdir()
    (source / name).write_bytes(raw)
    target = value["targets"]["x64"]
    with pytest.raises(policy.Refused, match="legal binding"):
        policy.candidate_policy_data(source, trusted, name, target)
    target["legal_hashes"][name] = hashlib.sha256(raw).hexdigest()
    assert policy.candidate_policy_data(source, trusted, name, target) == raw
    (source / name).write_bytes(raw + b" ")
    with pytest.raises(policy.Refused, match="legal binding"):
        policy.candidate_policy_data(source, trusted, name, target)
    (source / name).write_bytes(raw)
    (trusted / name).parent.mkdir()
    (trusted / name).write_bytes(b"different\n")
    with pytest.raises(policy.Refused, match="trusted copy"):
        policy.candidate_policy_data(source, trusted, name, target)


@pytest.mark.parametrize("mutation", [None, "head", "tree", "dirty", "digest"])
def test_later_data_jobs_recheck_the_exact_preflight_source(proposed, monkeypatch, mutation):
    source, _, _, _ = proposed
    rows = [("100644", "blob", "a" * 40, "Cargo.toml"),
            ("100644", "blob", "b" * 40, policy.EXCLUDED)]
    auth = {"source_sha": "a" * 40, "source_tree": "b" * 40, "input_digest": policy.input_digest(rows)}
    answers = {("rev-parse", "HEAD"): auth["source_sha"],
               ("rev-parse", "HEAD^{tree}"): auth["source_tree"],
               ("status", "--porcelain", "--untracked-files=all"): ""}
    if mutation in ("head", "tree", "dirty"):
        key = {"head": ("rev-parse", "HEAD"), "tree": ("rev-parse", "HEAD^{tree}"),
               "dirty": ("status", "--porcelain", "--untracked-files=all")}[mutation]
        answers[key] = "changed"
    elif mutation == "digest":
        auth["input_digest"] = "c" * 64
    monkeypatch.setattr(policy, "git", lambda root, *args: answers[args])
    monkeypatch.setattr(policy, "inventory", lambda root, sha: rows)
    if mutation is None:
        shared.require_source(source, auth)
    else:
        with pytest.raises(PackageInputError, match="authorized source"):
            shared.require_source(source, auth)
