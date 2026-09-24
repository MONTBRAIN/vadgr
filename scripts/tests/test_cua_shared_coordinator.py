"""Synthetic coordinator seams only. No native, legal, approval or paid signing evidence."""
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

import pytest

from scripts.candidate import cua_helpers as helpers, cua_shared as shared, cua_workflow as workflow
from scripts.tests.test_cua_helpers import fixture
from scripts.tests.test_candidate_claims import profile_authorization
from scripts.validate_package_inputs import PackageInputError, sha256_bytes

ROOT = Path(__file__).resolve().parents[2]


def completed_ledger(tmp_path):
    auth = profile_authorization()
    path = tmp_path / "ledger.json"
    shared.ledger_init(path, auth)
    operations = [("shared-helper", "relay.exe", "8" * 64, auth["helper_claim_sha256"]),
                  ("shared-helper", "broker.exe", "9" * 64, auth["helper_claim_sha256"]),
                  ("outer", "payload/vadgr.exe", auth["files"]["payload/vadgr.exe"]["sha256"], "a" * 64)]
    operations += [("vehicle", name, "b" * 64, "c" * 64) for name in (
        "Vadgr-0.5.0-windows-x64.msi", "burn-engine.exe", "Vadgr-0.5.0-windows-x64-final.exe")]
    for unit, name, before, claim in operations:
        shared.ledger_update(path, auth, unit, name, before, claim)
        shared.ledger_update(path, auth, unit, name, before, claim, "d" * 64)
    return auth, path


def test_single_ledger_covers_exact_helper_outer_and_vehicle_operations(tmp_path):
    auth, path = completed_ledger(tmp_path)
    assert len(shared.ledger_complete(path, auth)["attempts"]) == 6
    with pytest.raises(PackageInputError):
        shared.ledger_update(path, auth, "vehicle", "extra.exe", "a" * 64, "b" * 64)


@pytest.mark.parametrize("mutation", ["missing", "uncertain", "duplicate", "vendor", "wrong-helper",
                                      "changed-input", "wrong-vehicle", "changed-auth", "extra-field"])
def test_final_ledger_refuses_incomplete_or_foreign_operation(tmp_path, mutation):
    auth, path = completed_ledger(tmp_path)
    ledger = shared.read(path)
    if mutation == "missing":
        ledger["attempts"].pop()
    elif mutation == "uncertain":
        ledger["attempts"][0]["status"] = "reserved"
    elif mutation == "duplicate":
        ledger["attempts"][1] = ledger["attempts"][0]
    elif mutation == "vendor":
        ledger["attempts"][2]["path"] = "payload/vendor.dll"
    elif mutation == "wrong-helper":
        ledger["attempts"][0]["claim_sha256"] = "7" * 64
    elif mutation == "changed-input":
        ledger["attempts"][2]["input_sha256"] = "7" * 64
    elif mutation == "wrong-vehicle":
        ledger["attempts"][-1]["path"] = "other.exe"
    elif mutation == "changed-auth":
        ledger["authorization_sha256"] = "7" * 64
    else:
        ledger["synthetic"] = True
    path.write_bytes(helpers.canonical(ledger))
    with pytest.raises(PackageInputError):
        shared.ledger_complete(path, auth)


def test_uncertain_attempt_remains_spent_and_cannot_retry(tmp_path):
    auth, path = profile_authorization(), tmp_path / "ledger.json"
    shared.ledger_init(path, auth)
    shared.ledger_update(path, auth, "shared-helper", "relay.exe", "a" * 64, "b" * 64)
    with pytest.raises(PackageInputError):
        shared.ledger_update(path, auth, "shared-helper", "relay.exe", "a" * 64, "b" * 64)
    with pytest.raises(PackageInputError):
        shared.ledger_update(path, auth, "shared-helper", "relay.exe", "c" * 64, "b" * 64, "d" * 64)
    assert shared.read(path)["attempts"][0]["status"] == "reserved"


def test_competing_local_reservations_have_exactly_one_winner(tmp_path):
    auth, path = profile_authorization(), tmp_path / "ledger.json"
    shared.ledger_init(path, auth)
    def reserve():
        try:
            shared.ledger_update(path, auth, "shared-helper", "relay.exe", "a" * 64, "b" * 64)
            return True
        except (OSError, PackageInputError):
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(outcomes) == [False, True]
    assert len(shared.read(path)["attempts"]) == 1
    assert not path.with_name("ledger.json.lock").exists()


@pytest.fixture
def shared_output(tmp_path):
    _, _, inputs, final, policy, reports, archive, input_manifest, claim = fixture()
    source, signed, output = [tmp_path / p for p in ("input", "signed", "output")]
    for name, raw in {shared.CLAIM: helpers.canonical(claim), shared.POLICY: helpers.canonical(policy),
                      "input-broker.zip": archive, "input-member-manifest.json": input_manifest,
                      "input-index.json": helpers.canonical({"relay_path": "relay.exe", "archive_path": "package/broker.zip",
                          "predecessor_catalog_sha256": "6" * 64, "locations": {
                              p: {"relay": "package/relay.exe", "archive": "package/broker.zip"}
                              for p in helpers.pair("x86_64")}})}.items():
        shared.write(source / name, raw)
    for name, raw in inputs.items():
        shared.write(source / "members" / name, raw)
    for name, raw in final.items():
        shared.write(signed / name, raw)
    shared.write(signed / shared.REPORTS, {name: helpers.document(raw) for name, raw in reports.items()})
    shared.finalize_directory(source, signed, output)
    auth = profile_authorization()
    auth["helper_claim_sha256"] = sha256_bytes(helpers.canonical(claim))
    ledger_path = tmp_path / "ledger.json"
    shared.ledger_init(ledger_path, auth)
    for name in claim["publisher_sign_paths"]:
        shared.ledger_update(ledger_path, auth, "shared-helper", name, sha256_bytes(inputs[name]), auth["helper_claim_sha256"])
        shared.ledger_update(ledger_path, auth, "shared-helper", name, sha256_bytes(inputs[name]), auth["helper_claim_sha256"],
                             sha256_bytes(final[name]))
    observations = []
    for profile in helpers.pair("x86_64"):
        root = tmp_path / profile
        shared.write(root / "package/relay.exe", inputs["relay.exe"])
        shared.write(root / "package/broker.zip", archive)
        observations.append(shared.observe(root, source, output, profile))
    artifact = {"id": 900, "sha256": "7" * 64, "subjects": {
        key: sha256_bytes((output / name).read_bytes()) for key, name in (
            ("relay_sha256", "relay.exe"), ("archive_sha256", "broker.zip"),
            ("manifest_sha256", shared.MANIFEST), ("mapping_sha256", shared.MAPPING))}}
    return source, output, shared.read(ledger_path), observations, artifact


def test_independent_copies_share_bytes_but_have_distinct_receipts(shared_output, tmp_path):
    _, output, ledger, observations, artifact = shared_output
    assert observations[0]["profile"] != observations[1]["profile"]
    assert observations[0]["final_closure"] == observations[1]["final_closure"]
    destination = tmp_path / "authorization"
    shared.authorize_directory(output, artifact, ledger, *observations, destination)
    native = shared.read(destination / "receipt-windows.json")
    wsl = shared.read(destination / "receipt-wsl.json")
    assert native["profile"] != wsl["profile"]
    assert native["helper_closure_authorization_sha256"] == wsl["helper_closure_authorization_sha256"]


@pytest.mark.parametrize("mutation", ["observation", "profile", "candidate", "reused-observation",
                                      "ledger-input", "ledger-output", "ledger-uncertain", "ledger-duplicate", "output"])
def test_helper_authorization_rejects_synthetic_or_changed_measurement(shared_output, tmp_path, mutation):
    _, output, ledger, observations, artifact = shared_output
    if mutation == "observation":
        observations[1]["final_closure"]["archive_sha256"] = "e" * 64
    elif mutation == "profile":
        observations[1]["profile"] = "wsl-aarch64"
    elif mutation == "candidate":
        observations[1]["input_candidate_sha256"] = "e" * 64
    elif mutation == "reused-observation":
        observations[1] = observations[0]
    elif mutation == "ledger-input":
        ledger["attempts"][0]["input_sha256"] = "e" * 64
    elif mutation == "ledger-output":
        ledger["attempts"][0]["output_sha256"] = "e" * 64
    elif mutation == "ledger-uncertain":
        ledger["attempts"][0]["status"] = "reserved"
    elif mutation == "ledger-duplicate":
        ledger["attempts"].append(ledger["attempts"][0])
    else:
        (output / "relay.exe").write_bytes(b"changed")
    with pytest.raises(PackageInputError):
        shared.authorize_directory(output, artifact, ledger, *observations, tmp_path / "authorization")


def test_finalize_is_immutable_and_preserves_nonpublisher_bytes(shared_output):
    source, output, _, _, _ = shared_output
    with pytest.raises(PackageInputError):
        shared.finalize_directory(source, output, output)
    members = helpers.archive_members((output / "broker.zip").read_bytes())
    assert members["LICENSE"] == (source / "members/LICENSE").read_bytes()
    assert members["vendor.dll"] == (source / "members/vendor.dll").read_bytes()


def protected_rule():
    return {"id": 10, "enforcement": "active", "target": "tag", "bypass_actors": [],
            "conditions": {"ref_name": {"include": ["refs/tags/cua-signing-claims/**"], "exclude": []}},
            "rules": [{"type": "update"}, {"type": "deletion"}]}


@pytest.mark.parametrize("mutation", ["disabled", "branch", "wrong-namespace", "exclusion", "bypass", "no-update", "no-delete"])
def test_shared_namespace_requires_real_nonbypassable_tag_protection(monkeypatch, mutation):
    rule = protected_rule()
    if mutation == "disabled":
        rule["enforcement"] = "disabled"
    elif mutation == "branch":
        rule["target"] = "branch"
    elif mutation == "wrong-namespace":
        rule["conditions"]["ref_name"]["include"] = ["refs/tags/signing-claims/**"]
    elif mutation == "exclusion":
        rule["conditions"]["ref_name"]["exclude"] = ["refs/tags/cua-signing-claims/x"]
    elif mutation == "bypass":
        rule["bypass_actors"] = [{"actor_id": 1}]
    else:
        rule["rules"] = [{"type": "deletion" if mutation == "no-update" else "update"}]
    monkeypatch.setattr(shared.claims, "pages", lambda *a: [{"id": 10}])
    monkeypatch.setattr(shared.claims, "get", lambda *a: rule)
    with pytest.raises(PackageInputError):
        shared.shared_policy(None)


@pytest.mark.parametrize("name,kind", [("../outside", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                                       ("link", tarfile.SYMTYPE), ("hard", tarfile.LNKTYPE),
                                       ("device", tarfile.CHRTYPE)])
def test_wsl_extraction_rejects_paths_and_special_members_before_writes(tmp_path, name, kind):
    archive = tmp_path / "runtime.tar"
    with tarfile.open(archive, "w") as stream:
        row = tarfile.TarInfo(name)
        row.type = kind
        row.linkname = "../outside"
        stream.addfile(row, io.BytesIO())
    with pytest.raises(PackageInputError):
        workflow.unpack(archive, tmp_path / "runtime")
    assert not (tmp_path / "runtime").exists()


def test_wsl_tar_root_dot_and_executable_mode_roundtrip(tmp_path):
    root = tmp_path / "original"
    shared.write(root / "bin/vadgr", b"synthetic executable bytes, never executed")
    (root / "bin/vadgr").chmod(0o755)
    archive = tmp_path / "runtime.tar"
    with tarfile.open(archive, "w") as stream:
        stream.add(root, arcname=".")
    workflow.unpack(archive, tmp_path / "copied")
    assert (tmp_path / "copied/bin/vadgr").read_bytes() == (root / "bin/vadgr").read_bytes()


def jobs():
    raw = (ROOT / ".github/workflows/candidate.yml").read_text()
    headers = list(re.finditer(r"^  ([a-z][a-z0-9-]*):\n", raw, re.M))
    return {m[1]: raw[m.end():headers[i + 1].start() if i + 1 < len(headers) else len(raw)]
            for i, m in enumerate(headers) if m[1] != "workflow_dispatch"}


def test_workflow_claims_precede_signing_and_attestations_are_separate():
    graph = jobs()
    for name in ("sign-shared-helper", "sign-windows-payload", "sign-windows"):
        job = graph[name]
        assert "environment: candidate-windows" in job
        assert "id-token: write" not in job
        assert "contents: write" not in job
        assert "inputs.source_sha" not in job
        assert "cargo " not in job
        assert "candidate_claims.py verify" in job
    for name in ("authorize-helper", "attest-windows-runtime", "attest-wsl-runtime"):
        assert "id-token: write" in graph[name]
        assert "secrets." not in graph[name]
        assert "inputs.source_sha" not in graph[name]
    assert "cua_shared.py claim" in graph["claim-signing"]
    assert "observe-windows" in graph["authorize-helper"] and "observe-wsl" in graph["authorize-helper"]
    assert "attest-windows-runtime" in graph["sign-windows"]
    assert "verify-unattested" in graph["attest-windows-runtime"]
    assert "verify-unattested" in graph["attest-wsl-runtime"]


def test_every_shared_fetch_binds_immutable_id_digest_and_same_run():
    graph = jobs()
    for job in graph.values():
        for line in job.splitlines():
            if "cua_shared.py fetch" in line:
                assert "--artifact-id " in line and "--digest " in line and "--architecture " in line
    source = (ROOT / "scripts/candidate/cua_shared.py").read_text()
    assert 'producer_sha=os.environ["GITHUB_SHA"]' in source
    assert 'run_id=int(os.environ["GITHUB_RUN_ID"])' in source
    assert "artifacts.download(" in source


def test_wrapper_preverifies_preserved_files_and_reserves_before_vendor_call():
    source = (ROOT / "scripts/signing/release.ps1").read_text()
    assert source.count("Invoke-Wrapper 'sign'") == 1
    assert source.index("Preserved signatures are prerequisites") < source.index("Reserve-Attempt $relative $inputHash")
    assert source.index("Reserve-Attempt $relative $inputHash") < source.index("Invoke-Wrapper 'sign'")
    assert "$entry.Value.trust_class -eq 'publisher-sign'" in source
    assert "Vendor-preserve or data bytes changed." in source
    assert "ledger-verify" in source and "ledger-complete" in source and "-ResumeLedger" not in source
    report = (ROOT / "scripts/signing/verify-policy.ps1").read_text()
    for evidence in ("verify /pa /all /tw /v", "TimeStamperCertificate", "chain.Build", "chain_root_sha256",
                     "verify-metadata", "certificate_sha256", "signer_policy_sha256", "legal_approval_sha256"):
        assert evidence in report
    assert "Invoke-Wrapper 'sign'" not in report


def test_powershell_files_parse_without_executing(tmp_path):
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell parser is unavailable on this runner")
    for name in ("signing/release.ps1", "signing/verify-policy.ps1", "candidate/reseal-cua.ps1", "candidate/hold-windows.ps1"):
        path = ROOT / "scripts" / name
        script = "$t=$null;$e=$null;[Management.Automation.Language.Parser]::ParseFile('" + str(path).replace("'", "''") + "',[ref]$t,[ref]$e)|Out-Null;if($e.Count){$e;exit 1}"
        result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
