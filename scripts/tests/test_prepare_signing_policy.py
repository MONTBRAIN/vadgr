"""Synthetic preparation tests do not establish legal rights or native trust."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.candidate import cua_helpers as helpers
from scripts.candidate import prepare_signing_policy as review
from scripts.tests.test_cua_helpers import pe
from scripts.validate_package_inputs import PackageInputError, sha256_bytes

ROOT = Path(__file__).resolve().parents[2]


def catalog(architecture="x86_64"):
    releases = [{"version": version, "archive_sha256": "1" * 64,
                 "broker_relative_path": "vadgr-cua-browser-broker.exe", "broker_sha256": "2" * 64,
                 "manifest_sha256": "3" * 64, "protocol_min": 1, "protocol_max": 1}
                for version in ("0.7.6", "0.7.7", "0.7.8")]
    return {"schema": 1, "target": architecture + "-pc-windows-msvc",
            "releases": releases if architecture == "x86_64" else []}


def archive(value):
    return helpers.deterministic_archive({review.CATALOG: json.dumps(value, indent=2).encode()})


def inputs(tmp_path, architecture="x86_64"):
    root = tmp_path / "inputs"
    profile = "windows-" + architecture
    prefix = "payload/lib/cua/environments/fixture/Lib/site-packages/"
    relay = "computer_use/browser/winhost/" + architecture + "/vadgr-cua-host.exe"
    broker = "computer_use/browser/winbroker/" + architecture + "/broker.zip"
    data = {"payload/vadgr.exe": pe(arch=architecture), "ba-functions.dll": pe(arch=architecture),
            prefix + relay: pe(arch=architecture), prefix + broker: archive(catalog(architecture)),
            "payload/lib/cua/environments/fixture/Scripts/vadgr-cua-host.exe": pe(arch=architecture)}
    manifest = {"release_profile": profile, "helpers": {
        role: {"path": path, "size": len(data[prefix + path]), "sha256": sha256_bytes(data[prefix + path])}
        for role, path in (("relay", relay), ("archive", broker))}}
    manifest_path = prefix + "computer_use/browser/profiles/" + profile + "/cua-profile-manifest.json"
    data[manifest_path] = helpers.canonical(manifest)
    inventory = {}
    for name, raw in data.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        inventory[name] = {"sha256": sha256_bytes(raw), "size": len(raw)}
        if raw.startswith(b"MZ"):
            inventory[name].update(format="pe", architecture=architecture)
    observation = {"schema": 1, "candidate_approval": False, "publishable": False,
                   "architecture": "x64" if architecture == "x86_64" else "arm64",
                   "target": architecture + "-pc-windows-msvc", "release_profile": profile,
                   "files": inventory, "executable_hashes": {
                       name: row["sha256"] for name, row in inventory.items() if row.get("format") == "pe"}}
    return root, observation, prefix + relay, manifest_path


@pytest.mark.parametrize("architecture", ["x86_64", "aarch64"])
def test_review_is_deterministic_and_excludes_only_exact_shared_relay(tmp_path, architecture):
    root, observation, relay, _ = inputs(tmp_path, architecture)
    first = review.review_inputs(helpers.canonical(observation), root)
    assert first == review.review_inputs(helpers.canonical(observation), root)
    ledger, predecessors = first
    assert len(ledger["files"]) == 3
    assert relay not in ledger["files"]
    assert any(name.endswith("Scripts/vadgr-cua-host.exe") for name in ledger["files"])
    assert "ba-functions.dll" in ledger["files"]
    assert ledger["status"] == "review-input-only" and ledger["signing_approved"] is False
    assert all(row["review_status"] == "required" and "legal_approval_sha256" not in row
               for row in ledger["files"].values())
    assert helpers.document(predecessors) == catalog(architecture)


@pytest.mark.parametrize("mutation", ["hash", "size", "missing", "wrong-arch", "file-arch", "omit-native",
                                     "omit-extension", "case-alias", "traversal", "approved", "profile", "manifest"])
def test_preparation_refuses_changed_incomplete_or_unsafe_inputs(tmp_path, mutation):
    root, value, relay, manifest = inputs(tmp_path)
    if mutation == "hash":
        (root / "payload/vadgr.exe").write_bytes(pe() + b"changed")
    elif mutation == "size":
        value["files"][relay]["size"] += 1
    elif mutation == "missing":
        (root / relay).unlink()
    elif mutation == "wrong-arch":
        value["files"][relay]["architecture"] = "aarch64"
    elif mutation == "file-arch":
        raw = pe(arch="aarch64")
        (root / relay).write_bytes(raw)
        value["files"][relay]["sha256"] = sha256_bytes(raw)
        value["executable_hashes"][relay] = sha256_bytes(raw)
    elif mutation == "omit-native":
        value["executable_hashes"].pop(relay)
    elif mutation == "omit-extension":
        value["files"][relay].pop("format")
        value["executable_hashes"].pop(relay)
    elif mutation in ("case-alias", "traversal"):
        value["files"]["PAYLOAD/VADGR.EXE" if mutation == "case-alias" else "../escape"] = value["files"][relay]
    elif mutation == "approved":
        value["candidate_approval"] = True
    elif mutation == "profile":
        value["release_profile"] = "windows-aarch64"
    else:
        (root / manifest).write_bytes(b"{}")
    with pytest.raises(PackageInputError):
        review.review_inputs(helpers.canonical(value), root)


@pytest.mark.parametrize("mutation", ["wrong-target", "extra-field", "zero-hash", "protocol", "missing-release",
                                     "duplicate-release", "arm-release"])
def test_predecessor_schema_is_closed(mutation):
    value = catalog()
    architecture = "x86_64"
    if mutation == "wrong-target":
        value["target"] = "aarch64-pc-windows-msvc"
    elif mutation == "extra-field":
        value["approved"] = True
    elif mutation == "zero-hash":
        value["releases"][0]["archive_sha256"] = "0" * 64
    elif mutation == "protocol":
        value["releases"][0]["protocol_min"] = True
    elif mutation == "missing-release":
        value["releases"].pop()
    elif mutation == "duplicate-release":
        value["releases"][1] = copy.deepcopy(value["releases"][0])
    else:
        architecture = "aarch64"
        value["target"] = "aarch64-pc-windows-msvc"
    with pytest.raises(PackageInputError):
        review.predecessor_policy(archive(value), architecture)


def test_predecessor_policy_must_match_actual_embedded_bytes_semantically():
    value = catalog()
    review.check_predecessors(helpers.canonical(value), archive(value), "x86_64")
    changed = copy.deepcopy(value)
    changed["releases"][0]["broker_sha256"] = "4" * 64
    with pytest.raises(PackageInputError, match="differs from embedded"):
        review.check_predecessors(helpers.canonical(changed), archive(value), "x86_64")
    with pytest.raises(PackageInputError):
        review.check_predecessors(json.dumps(value).encode(), archive(value), "x86_64")
    source = (ROOT / "scripts/candidate/cua_shared.py").read_text()
    assert 'check_predecessors(predecessor, common["archive"], architecture)' in source


def policy_for(ledger):
    return {"schema": 1, "files": {name: {
        "input_sha256": row["input_sha256"], "trust_class": "publisher-sign",
        "signer": "synthetic fixture", "certificate_sha256": "1" * 64, "chain_root_sha256": "2" * 64,
        "signer_policy_sha256": "3" * 64, "legal_approval_sha256": "4" * 64,
        "digest_algorithm": "sha256", "timestamp_algorithm": "rfc3161-sha256"}
        for name, row in ledger["files"].items()}}


@pytest.mark.parametrize("mutation", [None, "missing", "extra", "hash", "data", "unreviewed", "empty-signer", "ledger"])
def test_outer_check_does_not_accept_missing_review_or_wrong_membership(tmp_path, mutation):
    root, observation, _, _ = inputs(tmp_path)
    ledger, _ = review.review_inputs(helpers.canonical(observation), root)
    policy = policy_for(ledger)
    row = policy["files"]["payload/vadgr.exe"]
    if mutation == "missing":
        policy["files"].pop("ba-functions.dll")
    elif mutation == "extra":
        policy["files"]["extra.exe"] = row
    elif mutation == "hash":
        row["input_sha256"] = "5" * 64
    elif mutation == "data":
        row["trust_class"] = "data"
    elif mutation == "unreviewed":
        row["legal_approval_sha256"] = None
    elif mutation == "empty-signer":
        row["signer"] = " "
    elif mutation == "ledger":
        policy = ledger
    if mutation is None:
        review.check_outer(helpers.canonical(policy), ledger)
    else:
        with pytest.raises(PackageInputError):
            review.check_outer(helpers.canonical(policy), ledger)


def test_cli_emits_review_only_and_refuses_overwriting(tmp_path):
    root, value, _, _ = inputs(tmp_path)
    observation = tmp_path / "observation.json"
    observation.write_bytes(helpers.canonical(value))
    output = tmp_path / "review.json"
    command = [sys.executable, str(ROOT / "scripts/candidate/prepare_signing_policy.py"),
               "--observation", str(observation), "--inputs", str(root), "--ledger-out", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert "no signing or legal approval" in completed.stdout
    original = output.read_bytes()
    repeated = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert repeated.returncode == 2 and output.read_bytes() == original
