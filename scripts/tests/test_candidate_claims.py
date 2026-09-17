"""Each case owns its fake GitHub state; no test contacts a signing service."""

import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest


SPEC = importlib.util.spec_from_file_location(
    "candidate_claims", Path(__file__).resolve().parents[1] / "candidate_claims.py"
)
claims = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(claims)


def authorization():
    return dict(schema=1, branch="feat/installer", version="0.5.0", pull_request=None,
                cua_version="0.7.8", python_version="3.12.0", legal_approval_sha256="1" * 64,
                required_checks=[{"context": "ci", "integration_id": 15368}], rules_digest="2" * 64,
                repository="MONTBRAIN/vadgr", source_sha="a" * 40,
                source_tree="b" * 40, input_digest="c" * 64,
                trusted_sha="d" * 40, candidate_id="v0.5.0-rc-1", architecture="x64",
                run_id=123, run_attempt=1, unsigned_artifact_id=99,
                unsigned_artifact_digest="sha256:" + "e" * 64,
                files={"payload/vadgr.exe": {"sha256": "f" * 64, "size": 12}},
                legal_hashes={"TERMS.txt": "a" * 64}, budget=5)


class GitHub:
    def __init__(self):
        self.calls = []
        self.refs = {}
        self.tags = {}
        self.rules = dict(id=1, target="tag", enforcement="active", bypass_actors=[],
                          conditions={"ref_name": {"include": ["refs/tags/signing-claims/**"], "exclude": []}},
                          rules=[{"type": "update"}, {"type": "deletion"}])
        self.jobs = [dict(id=1, name="claim-probe", status="completed", conclusion="success"),
                     dict(id=2, name="authorize-signing", status="completed", conclusion="success")]
        self.approved = True
        self.allow_update = self.allow_delete = False
        self.run_sha = "d" * 40
        self.artifact = self.archive = None

    def request(self, method, path, body=None, binary=False):
        self.calls.append((method, path, body))
        suffix = path.removeprefix("repos/MONTBRAIN/vadgr/")
        if suffix.startswith("rulesets?"):
            return 200, [{"id": 1}] if "page=1" in suffix else []
        if suffix == "rulesets/1":
            return 200, self.rules
        if suffix == "actions/runs/123/attempts/1":
            return 200, dict(id=123, run_attempt=1, head_sha=self.run_sha, head_branch="master",
                             event="workflow_dispatch", path=".github/workflows/candidate.yml",
                             repository={"full_name": "MONTBRAIN/vadgr", "fork": False})
        if suffix.startswith("actions/runs/123/attempts/1/jobs?"):
            return 200, {"jobs": self.jobs if "page=1" in suffix else []}
        if suffix == "actions/runs/123/approvals":
            return 200, [{"state": "approved" if self.approved else "rejected", "user": {"id": 7},
                          "environments": [{"id": 4, "name": "candidate-authorize"}]}]
        if suffix == "environments/candidate-authorize":
            return 200, dict(id=4, can_admins_bypass=False,
                             deployment_branch_policy={"protected_branches": False, "custom_branch_policies": True},
                             protection_rules=[{"type": "required_reviewers", "reviewers": [{"type": "User", "reviewer": {"id": 7}}]}])
        if suffix.startswith("environments/candidate-authorize/deployment-branch-policies?"):
            return 200, {"branch_policies": [{"name": "master", "type": "branch"}] if "page=1" in suffix else []}
        if suffix == "git/commits/" + "d" * 40:
            return 200, {"parents": [{"sha": "9" * 40}]}
        if suffix == "git/tags" and method == "POST":
            tag_sha = str(len(self.tags) + 1).zfill(40)
            self.tags[tag_sha] = dict(body, sha=tag_sha, object={"sha": body["object"], "type": body["type"]})
            return 201, self.tags[tag_sha]
        if suffix.startswith("git/tags/"):
            return 200, self.tags[suffix.split("/")[-1]]
        if suffix == "git/refs" and method == "POST":
            name = body["ref"].removeprefix("refs/")
            if name in self.refs:
                return 422, {"message": "Reference already exists"}
            self.refs[name] = body["sha"]
            return 201, {"ref": body["ref"], "object": {"sha": body["sha"], "type": "tag"}}
        if suffix.startswith("git/ref/"):
            name = suffix.removeprefix("git/ref/")
            if name not in self.refs:
                return 404, {}
            return 200, {"ref": "refs/" + name, "object": {"sha": self.refs[name], "type": "tag"}}
        if suffix.startswith("git/refs/"):
            name = suffix.removeprefix("git/refs/")
            if method == "PATCH" and self.allow_update:
                self.refs[name] = body["sha"]
                return 200, {}
            if method == "DELETE" and self.allow_delete:
                del self.refs[name]
                return 204, {}
            return 422, {"message": "Repository rule violations found"}
        if suffix == "actions/artifacts/101":
            return 200, self.artifact
        if suffix == "actions/artifacts/101/zip":
            return 200, self.archive
        return 404, {}


def qualify(api, auth):
    record = claims.probe(api, auth, allow_mutations=True)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("qualification.json", claims.canonical(record))
    api.archive = stream.getvalue()
    digest = "sha256:" + claims.digest(api.archive)
    api.artifact = dict(id=101, expired=False, digest=digest,
                        workflow_run={"id": 123, "head_sha": "d" * 40, "head_branch": "master"})
    return claims.bind(auth, record, 101, digest), record


def test_probe_needs_explicit_permission():
    api = GitHub()
    with pytest.raises(claims.Refused):
        claims.probe(api, authorization(), allow_mutations=False)
    assert not api.calls


def test_probe_proves_denied_mutations_and_create_is_one_shot():
    api = GitHub()
    auth, record = qualify(api, authorization())
    assert [call[0] for call in api.calls].count("PATCH") == 1
    assert [call[0] for call in api.calls].count("DELETE") == 1
    api.calls.clear()
    claim = claims.create(api, auth, record)
    claims.verify(api, auth, record, claim)
    assert not any(method in {"PATCH", "DELETE"} for method, _, _ in api.calls)
    with pytest.raises(claims.Refused):
        claims.create(api, auth, record)
    assert len([name for name in api.refs if "/probe/" not in name]) == 1


def test_repacked_identical_files_cannot_obtain_another_signing_claim():
    api = GitHub()
    auth, record = qualify(api, authorization())
    claims.create(api, auth, record)
    repacked = dict(auth, unsigned_artifact_digest="sha256:" + "0" * 64)
    assert claims.claim_ref(repacked) == claims.claim_ref(auth)
    with pytest.raises(claims.Refused, match="already claimed"):
        claims.create(api, repacked, record)
    changed_files = dict(repacked, files={"payload/vadgr.exe": {"sha256": "1" * 64, "size": 12}})
    assert claims.claim_ref(changed_files) != claims.claim_ref(auth)


@pytest.mark.parametrize("field,value", [("run_attempt", 2), ("repository", "other/repo"),
                                         ("budget", True), ("source_sha", "master"),
                                         ("unsigned_artifact_id", -1)])
def test_invalid_authorization_stops_before_network(field, value):
    api = GitHub()
    auth = authorization()
    auth[field] = value
    with pytest.raises(claims.Refused):
        claims.probe(api, auth, allow_mutations=True)
    assert not api.calls


@pytest.mark.parametrize("attribute", ["allow_update", "allow_delete"])
def test_probe_fails_when_a_mutation_is_allowed(attribute):
    api = GitHub()
    setattr(api, attribute, True)
    with pytest.raises(claims.Refused):
        claims.probe(api, authorization(), allow_mutations=True)


@pytest.mark.parametrize("mutation", ["policy", "approval", "job", "archive", "artifact", "run", "tuple"])
def test_claim_fails_before_write_on_unbound_evidence(mutation):
    api = GitHub()
    auth, record = qualify(api, authorization())
    if mutation == "policy":
        api.rules["bypass_actors"] = [{"actor_id": 1}]
    elif mutation == "approval":
        api.approved = False
    elif mutation == "job":
        api.jobs[0]["conclusion"] = "failure"
    elif mutation == "archive":
        api.archive += b"tampered"
    elif mutation == "artifact":
        api.artifact["workflow_run"]["id"] = 999
    elif mutation == "run":
        api.run_sha = "8" * 40
    else:
        auth["run_id"] = 999
    api.calls.clear()
    with pytest.raises(claims.Refused):
        claims.create(api, auth, record)
    assert not any(method != "GET" for method, _, _ in api.calls)


def test_changed_approved_tuple_cannot_reuse_claim():
    api = GitHub()
    auth, record = qualify(api, authorization())
    claim = claims.create(api, auth, record)
    auth["budget"] += 1
    with pytest.raises(claims.Refused):
        claims.verify(api, auth, record, claim)


def test_preflight_and_artifact_schema_round_trip(tmp_path):
    """Synthetic producer-shaped data, not evidence of a signed source or legal approval."""
    from scripts import candidate_artifacts

    preflight = {
        "schema": 1, "repository": "MONTBRAIN/vadgr", "branch": "feat/installer",
        "source_sha": "a" * 40, "source_tree": "b" * 40, "input_digest": "c" * 64,
        "version": "0.5.0", "candidate_id": "v0.5.0-rc-1", "architecture": "x64",
        "pull_request": None, "cua_version": "0.7.8", "python_version": "3.12.0",
        "legal_approval_sha256": "1" * 64, "trusted_sha": "d" * 40,
        "required_checks": [{"context": "ci", "integration_id": 15368, "check_id": 456}],
        "rules_digest": "2" * 64,
    }
    archive_path = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("payload/vadgr.exe", b"synthetic-test-fixture-not-an-executable")
    files = candidate_artifacts.inspect(archive_path)
    assert isinstance(files, dict) and "payload/vadgr.exe" in files
    auth = {**preflight, "run_id": 123, "run_attempt": 1, "unsigned_artifact_id": 99,
            "unsigned_artifact_digest": "sha256:" + claims.digest(archive_path.read_bytes()),
            "files": files, "legal_hashes": {"payload/legal/TERMS.txt": "a" * 64}, "budget": 5}
    claims.validate_authorization(auth)
    api = GitHub()
    bound, qualification = qualify(api, auth)
    claim = claims.create(api, bound, qualification)
    claims.verify(api, bound, qualification, claim)
    stored = claims.parse(api.tags[claim["tag"]]["message"])["authorization"]
    assert all(stored[key] == value for key, value in preflight.items())
    assert stored["files"] == files


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(claims.Refused):
        claims.parse(b'{"run_id":1,"run_id":2}')


def test_authorization_job_checks_itself_while_running():
    api = GitHub()
    auth, record = qualify(api, authorization())
    api.jobs[1].update(status="in_progress", conclusion=None)
    claims.approve(api, auth, record)
    with pytest.raises(claims.Refused):
        claims.create(api, auth, record)
    api.jobs[1].update(status="completed", conclusion="success")
    assert claims.fetch_qualification(api, auth) == record


def test_stale_qualification_ref_is_not_trusted():
    api = GitHub()
    auth, record = qualify(api, authorization())
    api.refs[record["probe_ref"][5:]] = "7" * 40
    with pytest.raises(claims.Refused):
        claims.create(api, auth, record)


@pytest.mark.parametrize("mutation", ["missing", "exclude", "single_star", "changed"])
def test_exact_current_policy_is_required(mutation):
    api = GitHub()
    auth, record = qualify(api, authorization())
    if mutation == "missing":
        api.rules["rules"] = [{"type": "deletion"}]
    elif mutation == "exclude":
        api.rules["conditions"]["ref_name"]["exclude"] = ["refs/tags/signing-claims/probe/**"]
    elif mutation == "single_star":
        api.rules["conditions"]["ref_name"]["include"] = ["refs/tags/signing-claims/*"]
    else:
        api.rules["name"] = "changed after probe"
    with pytest.raises(claims.Refused):
        claims.create(api, auth, record)


def test_production_claim_loses_race_without_retry():
    api = GitHub()
    auth, record = qualify(api, authorization())
    request = api.request
    def raced(method, path, body=None, binary=False):
        if method == "POST" and path.endswith("git/refs"):
            api.calls.append((method, path, body))
            return 422, {"message": "Reference already exists"}
        return request(method, path, body, binary)
    api.request = raced
    api.calls.clear()
    with pytest.raises(claims.Refused):
        claims.create(api, auth, record)
    assert sum(method == "POST" and path.endswith("git/refs") for method, path, _ in api.calls) == 1


def test_transport_uncertainty_is_not_retried():
    api = GitHub()
    auth, record = qualify(api, authorization())
    request = api.request
    calls = []
    def uncertain(method, path, body=None, binary=False):
        if method == "POST" and path.endswith("git/refs"):
            calls.append(path)
            raise claims.Refused("uncertain")
        return request(method, path, body, binary)
    api.request = uncertain
    with pytest.raises(claims.Refused):
        claims.create(api, auth, record)
    assert len(calls) == 1


def test_denied_mutation_must_be_a_ruleset_denial():
    api = GitHub()
    request = api.request
    def limited(method, path, body=None, binary=False):
        if method in {"PATCH", "DELETE"}:
            return 403, {"message": "API rate limit exceeded"}
        return request(method, path, body, binary)
    api.request = limited
    with pytest.raises(claims.Refused):
        claims.probe(api, authorization(), allow_mutations=True)
