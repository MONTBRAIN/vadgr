"""Synthetic signing seam tests, never paid/native signature evidence."""

import copy
import struct

import pytest

from scripts.candidate import cua_helpers as helpers
from scripts.validate_package_inputs import PackageInputError, sha256_bytes


def pe(signed=False, arch="x86_64"):
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0x8664 if arch == "x86_64" else 0xAA64)
    struct.pack_into("<H", data, 84, 240)
    struct.pack_into("<H", data, 88, 0x20B)
    if signed:
        struct.pack_into("<II", data, 232, 512, 16)
        data += struct.pack("<IHH", 16, 0x200, 2) + b"fixture!"
    return bytes(data)


def fixture(arch="x86_64"):
    inputs = {"relay.exe": pe(arch=arch), "broker.exe": pe(arch=arch),
              "vendor.dll": pe(True, arch), "LICENSE": b"fixture"}
    final = {**inputs, "relay.exe": pe(True, arch), "broker.exe": pe(True, arch)}
    policy = {"schema": 1, "files": {}}
    reports = {}
    for path, data in inputs.items():
        kind = "data" if path == "LICENSE" else "vendor-preserve" if path == "vendor.dll" else "publisher-sign"
        row = {key: None for key in helpers.POLICY_KEYS}
        row.update({"input_sha256": sha256_bytes(data), "trust_class": kind})
        if kind != "data":
            row.update({"signer_policy_sha256": "a" * 64, "legal_approval_sha256": "b" * 64,
                        "signer": "synthetic fixture", "certificate_sha256": "c" * 64, "chain_root_sha256": "d" * 64,
                        "digest_algorithm": "sha256", "timestamp_algorithm": "rfc3161-sha256"})
            reports[path] = helpers.canonical({**{k: v for k, v in row.items() if k != "input_sha256"},
                                              "schema": 1, "file_sha256": sha256_bytes(final[path]),
                                              "signtool_exit": 0, "authenticode_status": "Valid",
                                              "chain_valid": True, "timestamp_valid": True})
        policy["files"][path] = row
    input_archive = helpers.deterministic_archive({p: b for p, b in inputs.items() if p != "relay.exe"})
    input_manifest = b'{"fixture":"unsigned native member inventory"}\n'
    common = {"relay": {"sha256": sha256_bytes(inputs["relay.exe"])},
              "archive": {"sha256": sha256_bytes(input_archive)},
              "member_manifest": {"sha256": sha256_bytes(input_manifest)}}
    manifests = {profile: {"release_profile": profile, "cua_version": "0.7.9", "source_commit": "e" * 40,
                           "helpers": common} for profile in helpers.pair(arch)}
    request = {"architecture": arch, "cua_version": "0.7.9", "source_commit": "e" * 40,
               "tooling_commit": "f" * 40, "consumer_inputs": {p: {"candidate_sha256": "1" * 64,
               "catalog_sha256": "2" * 64, "lock_sha256": "3" * 64, "wheel_sha256": "4" * 64}
               for p in helpers.pair(arch)}, "legal_policy_sha256": "5" * 64,
               "signing_run_id": 1, "signing_job_id": "signed-shared-x86_64"}
    claim = helpers.prepare(request, manifests, inputs, policy, "relay.exe",
                            input_archive=input_archive, input_manifest=input_manifest)
    return request, manifests, inputs, final, policy, reports, input_archive, input_manifest, claim


def chain(arch="x86_64"):
    _, _, inputs, final, policy, reports, archive, original_manifest, claim = fixture(arch)
    claim_raw = helpers.canonical(claim)
    signed_archive, manifest_raw, mapping_raw = helpers.finalize(
        claim_raw, inputs, final, policy, reports, relay_path="relay.exe",
        archive_path=f"computer_use/browser/winbroker/{arch}/broker.zip", predecessor_catalog_sha256="6" * 64,
        input_archive=archive, input_manifest=original_manifest)
    final_closure = {"relay_sha256": sha256_bytes(final["relay.exe"]), "archive_sha256": sha256_bytes(signed_archive),
                     "manifest_sha256": sha256_bytes(manifest_raw)}
    ledger = [{"pre_signing_claim_sha256": sha256_bytes(claim_raw),
               "helper_closure_id": claim["helper_closure_id"], "operations": 2}]
    artifact = {"id": 123, "sha256": "7" * 64,
                "subjects": {**final_closure, "mapping_sha256": sha256_bytes(mapping_raw)}}
    authorization, receipts = helpers.authorize(claim_raw, manifest_raw, mapping_raw, final["relay.exe"], artifact, ledger,
        observed_consumers={p: final_closure for p in helpers.pair(arch)})
    return claim_raw, manifest_raw, authorization, list(receipts.values()), final_closure, ledger


@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
def test_shared_closure_has_one_budget_and_two_receipts(arch):
    claim, manifest, authorization, receipts, final, ledger = chain(arch)
    assert helpers.document(claim)["signing_operations"] == 2
    assert len(receipts) == 2
    assert all(helpers.document(r)["helper_closure_authorization_sha256"] == sha256_bytes(authorization) for r in receipts)
    assert helpers.document(manifest)["pre_signing_claim_sha256"] == sha256_bytes(claim)
    assert "helper_closure_authorization_sha256" not in helpers.document(manifest)
    assert helpers.document(authorization)["final_closure"] == final
    assert len(ledger) == 1


@pytest.mark.parametrize("mutation", ["vendor-change", "data-change", "code-change", "missing-report", "warning", "no-timestamp", "wrong-signer"])
def test_signature_transition_refuses_unapproved_transform(mutation):
    _, _, inputs, final, policy, reports, _, _, _ = fixture()
    if mutation == "vendor-change":
        final["vendor.dll"] += b"x"
    elif mutation == "data-change":
        final["LICENSE"] += b"x"
    elif mutation == "code-change":
        final["broker.exe"] = final["broker.exe"][:300] + b"X" + final["broker.exe"][301:]
    elif mutation == "missing-report":
        del reports["vendor.dll"]
    else:
        report = helpers.document(reports["broker.exe"])
        report[{"warning": "signtool_exit", "no-timestamp": "timestamp_valid", "wrong-signer": "signer"}[mutation]] = {
            "warning": 2, "no-timestamp": False, "wrong-signer": "different signer"}[mutation]
        reports["broker.exe"] = helpers.canonical(report)
    with pytest.raises(PackageInputError):
        helpers.verify_transform(inputs, final, policy, reports, "x86_64", "relay.exe")


def test_mismatched_consumers_refused_before_paid_work():
    request, manifests, inputs, _, policy, _, archive, manifest, _ = fixture()
    manifests = copy.deepcopy(manifests)
    manifests["wsl-x86_64"]["helpers"]["archive"]["sha256"] = "8" * 64
    with pytest.raises(PackageInputError):
        helpers.prepare(request, manifests, inputs, policy, "relay.exe", input_archive=archive, input_manifest=manifest)


def test_native_bytes_cannot_be_classified_as_data():
    _, _, inputs, _, policy, _, _, _, _ = fixture()
    policy["files"]["vendor.dll"] = {k: None for k in helpers.POLICY_KEYS}
    policy["files"]["vendor.dll"].update(input_sha256=sha256_bytes(inputs["vendor.dll"]), trust_class="data")
    with pytest.raises(PackageInputError):
        helpers.validate_policy(policy, inputs, "x86_64", "relay.exe")


def test_duplicate_claim_consumption_is_refused():
    claim, manifest, _, _, final, ledger = chain()
    with pytest.raises(PackageInputError):
        helpers.authorize(claim, manifest, helpers.canonical({"schema": 1, "files": []}), b"relay", {}, ledger * 2,
                          observed_consumers={})


def test_deterministic_zip_and_collision_refusal():
    assert helpers.deterministic_archive({"z": b"last", "a": b"first"}) == helpers.deterministic_archive({"a": b"first", "z": b"last"})
    with pytest.raises(PackageInputError):
        helpers.deterministic_archive({"A": b"one", "a": b"two"})
