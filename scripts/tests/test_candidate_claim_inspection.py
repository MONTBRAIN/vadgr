"""Each test owns synthetic API state. No credential or live mutation is used."""

import zipfile
from pathlib import Path

import pytest

from scripts import candidate_claim_inspection as inspection
from scripts import candidate_claims as claims
from scripts.candidate import cua_helpers as helpers
from scripts.candidate import cua_shared as shared
from scripts.tests.test_candidate_claims import GitHub, profile_authorization, qualify
from scripts.validate_package_inputs import PackageInputError


def prepared():
    api, inspector = GitHub(), GitHub()
    del api.rules["bypass_actors"]
    auth = profile_authorization()
    closure = {"relay": "a" * 64, "broker": "b" * 64}
    key = claims.digest(helpers.canonical({"architecture": "x86_64", "input_closure": closure}))
    raw = helpers.canonical({"architecture": "x86_64", "input_closure": closure,
        "helper_closure_id": key, "signing_claim_ref": "refs/tags/cua-signing-claims/" + key,
        "publisher_policy_sha256": auth["helper_policy_sha256"], "signing_operations": 2,
        "signing_run_id": 123, "signing_attempt": 1, "tooling_commit": auth["trusted_sha"]})
    auth["helper_claim_sha256"] = claims.digest(raw)
    auth, qualification = qualify(api, auth)
    api.jobs[1].update(status="in_progress", conclusion=None)
    api.calls.clear()
    return api, inspector, auth, qualification, raw


def test_both_probes_precede_claims_and_inspector_never_mutates():
    api, inspector, auth, record, raw = prepared()
    assert len(api.refs) == 2 and all("/probe/" in p for p in api.refs)
    claim, receipt = inspection.inspect_and_claim(api, inspector, auth, record, raw)
    assert len(api.refs) == 4
    assert all(method == "GET" for method, _, _ in inspector.calls)
    assert not any(method in {"PATCH", "DELETE"} for method, _, _ in api.calls)
    assert claim["inspection"]["shared_claim"] == receipt
    api.jobs[1].update(status="completed", conclusion="success")
    claims.verify(api, auth, record, claim, require_inspection=True)
    shared.verify_shared(api, auth, record, raw, receipt)


def test_spent_shared_input_refuses_before_creating_the_ordinary_claim():
    api, inspector, auth, record, raw = prepared()
    helper = shared.check_bound_helper(auth, raw)
    api.refs[helper["signing_claim_ref"][5:]] = "9" * 40
    with pytest.raises(claims.Refused, match="already claimed"):
        inspection.inspect_and_claim(api, inspector, auth, record, raw)
    assert not any(method != "GET" for method, _, _ in api.calls)


@pytest.mark.parametrize("value", ["missing", None, [{"actor_id": 7}], {}])
def test_full_inspection_rejects_unknown_or_nonempty_bypass_before_any_claim(value):
    api, inspector, auth, record, raw = prepared()
    if value == "missing":
        del inspector.rules["bypass_actors"]
    else:
        inspector.rules["bypass_actors"] = value
    with pytest.raises(claims.Refused):
        inspection.inspect_and_claim(api, inspector, auth, record, raw)
    assert not any(method != "GET" for method, _, _ in api.calls)


@pytest.mark.parametrize("namespace", inspection.NAMESPACES)
def test_missing_namespace_refuses_before_either_probe_or_claim(namespace):
    api = GitHub()
    api.rules["conditions"]["ref_name"]["include"] = [namespace]
    with pytest.raises(claims.Refused):
        claims.probe(api, profile_authorization(), allow_mutations=True)
    assert not any(method != "GET" for method, _, _ in api.calls)


@pytest.mark.parametrize("mutation", ["missing-record", "missing-ref", "wrong-tag", "failed-result"])
def test_neither_claim_can_precede_complete_shared_qualification(mutation):
    api, inspector, auth, record, raw = prepared()
    if mutation == "missing-record":
        del record["shared_probe"]
    elif mutation == "missing-ref":
        del api.refs[record["shared_probe"]["ref"][5:]]
    elif mutation == "wrong-tag":
        api.refs[record["shared_probe"]["ref"][5:]] = "9" * 40
    else:
        record["shared_probe"]["results"]["delete_denied"] = False
    with pytest.raises(claims.Refused):
        inspection.inspect_and_claim(api, inspector, auth, record, raw)
    assert not any(method != "GET" for method, _, _ in api.calls)


@pytest.mark.parametrize("method,path,body,binary", [
    ("POST", "git/refs", {}, False), ("PUT", f"rulesets/{inspection.RULESET_ID}", {}, False),
    ("DELETE", f"rulesets/{inspection.RULESET_ID}", None, False),
    ("GET", "git/ref/tags/test", None, False),
    ("GET", f"rulesets/{inspection.RULESET_ID}", {}, False),
    ("GET", f"rulesets/{inspection.RULESET_ID}", None, True),
])
def test_inspector_rejects_every_noninspection_request(monkeypatch, method, path, body, binary):
    monkeypatch.setenv("GH_TOKEN", "synthetic-workflow-token")
    monkeypatch.setenv("RULESET_INSPECT_TOKEN", "synthetic-inspection-token")
    monkeypatch.setattr(claims.GitHubAPI, "request", lambda *a, **k: pytest.fail("network reached"))
    with pytest.raises(claims.Refused):
        inspection.InspectionAPI().request(method, claims.PREFIX + path, body, binary)


def test_inspector_uses_distinct_token_name_and_exact_gets(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "synthetic-workflow-token")
    monkeypatch.setenv("RULESET_INSPECT_TOKEN", "synthetic-inspection-token")
    seen = []
    monkeypatch.setattr(claims.GitHubAPI, "request", lambda self, *args: seen.append((self.token_name, args)))
    inspection.InspectionAPI().request("GET", claims.PREFIX + f"rulesets/{inspection.RULESET_ID}")
    assert seen[0][0] == "RULESET_INSPECT_TOKEN"
    assert claims.GitHubAPI.token_name == "GH_TOKEN"


@pytest.mark.parametrize("ordinary,inspector", [(None, "inspect"), ("normal", None),
                                              ("normal", ""), ("same", "same")])
def test_inspector_rejects_missing_or_reused_credential_before_network(monkeypatch, ordinary, inspector):
    for name, value in (("GH_TOKEN", ordinary), ("RULESET_INSPECT_TOKEN", inspector)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setattr(claims.GitHubAPI, "request", lambda *a, **k: pytest.fail("network reached"))
    with pytest.raises(claims.Refused):
        inspection.InspectionAPI()


@pytest.mark.parametrize("mutation", ["timestamp", "hidden-bypass", "ref"])
def test_postinspection_failure_produces_no_witness_and_claims_remain_spent(mutation):
    api, inspector, auth, record, raw = prepared()
    original = inspector.request
    reads = 0
    def request(method, path, body=None, binary=False):
        nonlocal reads
        if path.endswith(f"rulesets/{inspection.RULESET_ID}"):
            reads += 1
            if reads == 2:
                if mutation == "timestamp":
                    inspector.rules["updated_at"] = "2026-09-29T04:00:00Z"
                elif mutation == "hidden-bypass":
                    inspector.rules["bypass_actors"] = [{"actor_id": 7}]
                else:
                    ref = next(p for p in api.refs if "/probe/" not in p)
                    api.refs[ref] = "9" * 40
        return original(method, path, body, binary)
    inspector.request = request
    with pytest.raises((claims.Refused, PackageInputError)):
        inspection.inspect_and_claim(api, inspector, auth, record, raw)
    assert len(api.refs) == 4


@pytest.mark.parametrize("mutation", ["missing", "run", "authorization", "pre", "post", "shared-ref", "claim-ref", "scope"])
def test_signer_requires_exact_protected_witness_and_both_refs(mutation):
    api, inspector, auth, record, raw = prepared()
    claim, receipt = inspection.inspect_and_claim(api, inspector, auth, record, raw)
    api.jobs[1].update(status="completed", conclusion="success")
    witness = claim["inspection"]
    if mutation == "missing":
        del claim["inspection"]
    elif mutation == "run":
        witness["identity"]["run_id"] += 1
    elif mutation == "authorization":
        witness["authorization_sha256"] = "0" * 64
    elif mutation in {"pre", "post"}:
        witness[mutation + "_policy_sha256"] = "0" * 64
    elif mutation == "shared-ref":
        api.refs[receipt["ref"][5:]] = "9" * 40
    elif mutation == "claim-ref":
        api.refs[claim["ref"][5:]] = "9" * 40
    else:
        witness["namespaces"] = inspection.NAMESPACES[:1]
    with pytest.raises((claims.Refused, PackageInputError)):
        claims.verify(api, auth, record, claim, require_inspection=True)


def test_viewer_fields_do_not_change_security_digest():
    api = GitHub()
    first = inspection.current_policy(api, full=True)
    api.rules.update(current_user_can_bypass="never", _links={"viewer": "different"})
    assert inspection.current_policy(api, full=True) == first
    del api.rules["bypass_actors"]
    assert inspection.current_policy(api) == inspection.projection(first)


def test_ruleset_timestamp_zones_preserve_exact_instants():
    api = GitHub()
    api.rules["updated_at"] = "2026-09-28T21:40:53.725-05:00"
    first = inspection.current_policy(api, full=True)
    api.rules["updated_at"] = "2026-09-29T02:40:53.725Z"
    assert inspection.current_policy(api, full=True) == first
    api.rules["updated_at"] = "2026-09-29T02:40:53.726Z"
    assert inspection.current_policy(api, full=True) != first


@pytest.mark.parametrize("value", [None, "", "2026-09-29T02:40:53", "2026-99-99T02:40:53Z"])
def test_ruleset_timestamp_requires_valid_explicit_zone(value):
    api = GitHub()
    api.rules["updated_at"] = value
    with pytest.raises(claims.Refused):
        inspection.current_policy(api)


def test_protected_workflow_owns_inspection_and_claims_before_any_signer():
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/candidate.yml").read_text()
    approved = workflow.split("\n  authorize-signing:", 1)[1].split("\n  sign-shared-helper:", 1)[0]
    assert "environment: candidate-authorize" in approved and "contents: write" in approved
    assert "artifact_id: ${{ steps.record.outputs.artifact-id }}" in approved
    assert "artifact_digest: sha256:${{ steps.record.outputs.artifact-digest }}" in approved
    assert "path: protected-claims/" in approved
    assert approved.index("candidate_claims.py approve") < approved.index("candidate_claim_inspection.py")
    assert approved.index("candidate_claim_inspection.py") < approved.index("name: signing-claim")
    assert workflow.count("secrets.RULESET_INSPECT_TOKEN") == 1
    assert "RULESET_INSPECT_TOKEN: ${{ secrets.RULESET_INSPECT_TOKEN }}" in approved
    assert "ES_PASSWORD" not in approved and "inputs.source_sha" not in approved
    assert "\n  claim-signing:" not in workflow
    assert "candidate_claims.py create" not in workflow and "cua_shared.py claim " not in workflow
    assert workflow.count("needs.authorize-signing.outputs.artifact_id") == 3


def test_protected_claim_archive_extracts_top_level_receipts(tmp_path, monkeypatch):
    api, inspector, auth, record, raw = prepared()
    claim, receipt = inspection.inspect_and_claim(api, inspector, auth, record, raw)
    output = tmp_path / "claim-record"
    def download(args):
        # upload-artifact uses the uploaded directory as its archive root.
        with zipfile.ZipFile(args.out, "w") as archive:
            archive.writestr("claim.json", claims.canonical(claim) + b"\n")
            archive.writestr("shared-claim.json", helpers.canonical(receipt))
        args.metadata.write_bytes(claims.canonical({"artifact_id": 123}))
    monkeypatch.setattr(shared.artifacts, "download", download)
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", auth["trusted_sha"])
    shared.fetch(123, "sha256:" + "1" * 64, output, "x64")
    assert claims.parse((output / "claim.json").read_bytes()) == claim
    assert shared.read(output / "shared-claim.json") == receipt
