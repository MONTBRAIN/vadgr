"""Synthetic complete profile insertion; attestation/native checks are mocked."""

import json

import pytest

from scripts.candidate import cua_helpers as helpers, cua_profile_signing as profile_signing, cua_signing as signing
from scripts.tests.test_cua_helpers import fixture, pe
from scripts.validate_package_inputs import canonical_json, sha256_bytes, PackageInputError


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def transition(tmp_path, monkeypatch):
    _, _, inputs, outputs, policy, reports, archive, input_manifest, claim = fixture()
    root, records, helper_root = tmp_path / "candidate", tmp_path / "records", tmp_path / "helpers"
    generation = "0.7.9-" + "3" * 12
    package = f"environments/{generation}/Lib/site-packages/"
    relay = "computer_use/browser/winhost/x86_64/vadgr-cua-host.exe"
    broker = "computer_use/browser/winbroker/x86_64/broker.zip"
    member_manifest = "computer_use/browser/winbroker/x86_64/broker.manifest.json"
    role = {"schema": 1, "release_profile": "windows-x86_64", "source_commit": "e" * 40,
            "helpers": {"architecture": "x86_64", "relay": {"path": relay, **signing.identity(inputs["relay.exe"])},
                        "archive": {"path": broker, **signing.identity(archive)},
                        "member_manifest": {"path": member_manifest, **signing.identity(input_manifest)}}}
    raw_role = canonical_json(role)
    binding = {"target": "x86_64-pc-windows-msvc", "requirements_sha256": "3" * 64,
               "wheel_manifest_sha256": "9" * 64, "release_profile": "windows-x86_64",
               "cua_profile_manifest_sha256": sha256_bytes(raw_role)}
    cua_files = {package + relay: inputs["relay.exe"], package + broker: archive, package + member_manifest: input_manifest,
                 package + "computer_use/browser/profiles/windows-x86_64/cua-profile-manifest.json": raw_role}
    for name, data in cua_files.items():
        write(root, signing.PREFIX + name, data)
    inventory = canonical_json({"schema": 1, "target": binding["target"],
                                "files": {p: signing.identity(b) for p, b in cua_files.items()}})
    payload = {"schema": 3, **binding, "cua_version": "0.7.9", "python_version": "3.12.14",
               "python_build": "20260825", "python_archive_sha256": "a" * 64, "uv_archive_sha256": "b" * 64,
               "installed_inventory_sha256": sha256_bytes(inventory)}
    write(root, signing.PREFIX + "installed-inventory.json", inventory)
    write(root, signing.PREFIX + "payload.json", canonical_json(payload))
    write(root, "payload/vadgr.exe", pe())
    auth = {"cua_inputs": binding, "cua_payload": {**binding, "installed_inventory_sha256": sha256_bytes(inventory)},
            "files": signing.tree(root), "helper_claim_sha256": sha256_bytes(helpers.canonical(claim)),
            "helper_policy_sha256": sha256_bytes(helpers.canonical(policy)), "helper_signing_operations": 2,
            "run_id": 1, "trusted_sha": "f" * 40, "input_digest": "1" * 64,
            "unsigned_artifact_digest": "sha256:" + claim["consumer_inputs"]["windows-x86_64"]["candidate_sha256"],
            "wsl_artifact_digest": "sha256:" + claim["consumer_inputs"]["wsl-x86_64"]["candidate_sha256"],
            "signing_policy": {"schema": 1, "files": {"payload/vadgr.exe": policy["files"]["relay.exe"]}}}
    signing.snapshot(root, auth, records)
    write(root, "payload/vadgr.exe", pe(True))
    receipt = {"payload/vadgr.exe": {"input": auth["files"]["payload/vadgr.exe"], "output": signing.identity(pe(True)),
                                    "trust_class": "publisher-sign", "signature_report_sha256": sha256_bytes(reports["relay.exe"])}}
    outer_reports = {"payload/vadgr.exe": helpers.document(reports["relay.exe"])}
    original_reseal = profile_signing.reseal_profile
    monkeypatch.setattr(profile_signing, "reseal_profile", lambda *args, **kwargs:
                        original_reseal(*args, signature_reports=outer_reports, **kwargs))
    claim_raw = helpers.canonical(claim)
    final_zip, final_manifest, mapping = helpers.finalize(claim_raw, inputs, outputs, policy, reports,
        relay_path="relay.exe", archive_path=broker, predecessor_catalog_sha256="6" * 64,
        input_archive=archive, input_manifest=input_manifest)
    final_closure = {"relay_sha256": sha256_bytes(outputs["relay.exe"]), "archive_sha256": sha256_bytes(final_zip),
                     "manifest_sha256": sha256_bytes(final_manifest)}
    artifact = {"id": 123, "sha256": "7" * 64, "subjects": {**final_closure, "mapping_sha256": sha256_bytes(mapping)}}
    authorization, receipts = helpers.authorize(claim_raw, final_manifest, mapping, outputs["relay.exe"], artifact,
        [{"pre_signing_claim_sha256": sha256_bytes(claim_raw), "helper_closure_id": claim["helper_closure_id"], "operations": 2}],
        observed_consumers={p: final_closure for p in helpers.pair("x86_64")})
    helper_data = {"pre-signing-claim.json": claim_raw, "broker-final-manifest.json": final_manifest,
                   "input-output.json": mapping, "publisher-policy.json": helpers.canonical(policy),
                   "signature-reports.json": helpers.canonical({p: helpers.document(b) for p, b in reports.items()}),
                   "helper-closure-authorization.json": authorization, "authorization.sigstore.json": b"synthetic-attestation",
                   "receipt-windows.json": receipts["windows-x86_64"], "receipt-wsl.json": receipts["wsl-x86_64"],
                   "relay.exe": outputs["relay.exe"], "broker.zip": final_zip}
    for name, data in helper_data.items():
        write(helper_root, name, data)
    monkeypatch.setattr(profile_signing, "verify_attestation", lambda *_: None)
    return root, auth, records, receipt, helper_root


def test_profile_reseal_emits_exact_runtime_envelope_and_complete_inventory(transition):
    root, auth, records, receipt, helpers_root = transition
    result = profile_signing.reseal_profile(root, auth, records, receipt, helpers_root)
    assert result == signing.validate_records(records, auth)
    runtime = json.loads((root / "payload/cua-runtime-authorization.json").read_bytes())
    payload = (root / signing.PREFIX / "payload.json").read_bytes()
    assert runtime["payload_sha256"] == sha256_bytes(payload)
    assert runtime["release_profile"] == "windows-x86_64"
    assert not (root / "payload/cua-runtime-authorization.sigstore.json").exists()
    assert runtime["installed_inventory_sha256"] != auth["cua_payload"]["installed_inventory_sha256"]
    assert any((root / signing.PREFIX).rglob("broker-final-manifest.json"))


@pytest.mark.parametrize("mutation", ["relay", "report", "extra", "claim", "receipt", "native-artifact", "wsl-artifact"])
def test_profile_reseal_refuses_changed_shared_output_without_rewriting_payload(transition, mutation):
    root, auth, records, receipt, helper_root = transition
    original = (root / signing.PREFIX / "payload.json").read_bytes()
    if mutation == "relay":
        write(helper_root, "relay.exe", pe(True) + b"changed")
    elif mutation == "report":
        write(helper_root, "signature-reports.json", helpers.canonical({}))
    elif mutation == "extra":
        write(helper_root, "extra", b"unreviewed")
    elif mutation == "claim":
        auth["helper_claim_sha256"] = "8" * 64
    elif mutation == "native-artifact":
        auth["unsigned_artifact_digest"] = "sha256:" + "8" * 64
    elif mutation == "wsl-artifact":
        auth["wsl_artifact_digest"] = "sha256:" + "8" * 64
    else:
        receipt["payload/vadgr.exe"]["output"]["sha256"] = "8" * 64
    with pytest.raises((PackageInputError, KeyError)):
        profile_signing.reseal_profile(root, auth, records, receipt, helper_root)
    assert (root / signing.PREFIX / "payload.json").read_bytes() == original


@pytest.mark.parametrize("field,value", [("signtool_exit", 1), ("chain_valid", False),
                                         ("timestamp_valid", False), ("certificate_sha256", "8" * 64)])
def test_held_outer_receipt_requires_full_matching_signature_report(transition, field, value):
    root, auth, records, receipt, helper_root = transition
    profile_signing.reseal_profile(root, auth, records, receipt, helper_root)
    reports = helpers.document((records / "outer-signature-reports.json").read_bytes())
    reports["payload/vadgr.exe"][field] = value
    (records / "outer-signature-reports.json").write_bytes(helpers.canonical(reports))
    receipt["payload/vadgr.exe"]["signature_report_sha256"] = sha256_bytes(helpers.canonical(reports["payload/vadgr.exe"]))
    (records / "outer-signature-receipt.json").write_bytes(canonical_json(receipt))
    with pytest.raises(PackageInputError):
        signing.validate_records(records, auth)


def test_runtime_attestation_binds_exact_protected_run(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "cua-runtime-authorization.json").write_bytes(b"synthetic-runtime")
    (root / "cua-runtime-authorization.sigstore.json").write_bytes(b"synthetic-bundle")
    auth = {"run_id": 123, "trusted_sha": "f" * 40}
    certificate = {"runInvocationURI": "https://github.com/MONTBRAIN/vadgr/actions/runs/123/attempts/1",
                   "sourceRepositoryDigest": "f" * 40, "buildSignerDigest": "f" * 40,
                   "runnerEnvironment": "github-hosted"}
    proof = [{"verificationResult": {"signature": {"certificate": certificate}, "statement": {
        "subject": [{"digest": {"sha256": sha256_bytes(b"synthetic-runtime")}}]}}}]
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(proof).encode())
    monkeypatch.setattr(profile_signing.subprocess, "run", run)
    profile_signing.verify_runtime(root, auth)
    assert "--deny-self-hosted-runners" in calls[0] and "--custom-trusted-root" in calls[0]
    certificate["runInvocationURI"] = "https://github.com/MONTBRAIN/vadgr/actions/runs/123/attempts/2"
    with pytest.raises(PackageInputError):
        profile_signing.verify_runtime(root, auth)
