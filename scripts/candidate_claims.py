"""One-use signing claims. Candidate archives never supply executable policy."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile


REPOSITORY = "MONTBRAIN/vadgr"
PREFIX = f"repos/{REPOSITORY}/"
BASE_FIELDS = {"repository", "source_sha", "source_tree", "input_digest", "trusted_sha",
               "candidate_id", "architecture", "run_id", "run_attempt", "unsigned_artifact_id",
               "unsigned_artifact_digest", "files", "legal_hashes", "budget",
               "schema", "branch", "version", "pull_request", "cua_version", "python_version",
               "legal_approval_sha256", "required_checks", "rules_digest", "cua_inputs", "cua_payload"}
BOUND_FIELDS = {"qualification_artifact_id", "qualification_artifact_digest"}
PROFILE_FIELDS = {"helper_claim_sha256", "helper_policy_sha256", "helper_input_artifact_id",
                  "helper_input_artifact_digest", "wsl_artifact_id", "wsl_artifact_digest",
                  "helper_signing_operations", "outer_signing_operations", "signing_policy"}


class Refused(Exception):
    """A fixed non-secret reason safe for workflow output."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refused("invalid JSON number")))
    except (UnicodeError, ValueError) as error:
        raise Refused("invalid JSON record") from error


def positive(value):
    return type(value) is int and value > 0


def hashed(value, length=64):
    return isinstance(value, str) and re.fullmatch(f"[a-f0-9]{{{length}}}", value) is not None


def archive_digest(value):
    return isinstance(value, str) and value.startswith("sha256:") and hashed(value[7:])


def validate_authorization(auth, bound=False):
    profiled = isinstance(auth, dict) and isinstance(auth.get("cua_inputs"), dict) and "release_profile" in auth["cua_inputs"]
    require(isinstance(auth, dict) and set(auth) == BASE_FIELDS | (BOUND_FIELDS if bound else set())
            | (PROFILE_FIELDS if profiled else set()),
            "authorization fields do not match the trusted schema")
    require(auth["repository"] == REPOSITORY and auth["run_attempt"] == 1
            and type(auth["run_attempt"]) is int, "repository or attempt refused")
    require(type(auth["schema"]) is int and auth["schema"] == 1 and auth["version"] == "0.5.0"
            and isinstance(auth["branch"], str) and auth["branch"] not in {"", "master"}
            and (auth["pull_request"] is None or positive(auth["pull_request"])), "preflight identity refused")
    require(all(isinstance(auth[field], str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", auth[field])
                for field in ("cua_version", "python_version"))
            and all(hashed(auth[field]) for field in ("legal_approval_sha256", "rules_digest"))
            and isinstance(auth["required_checks"], list) and auth["required_checks"], "preflight policy refused")
    require(all(hashed(auth[field], 40) for field in ("source_sha", "source_tree", "trusted_sha")),
            "source identity is not immutable")
    require(hashed(auth["input_digest"]) and archive_digest(auth["unsigned_artifact_digest"]),
            "input digest refused")
    require(all(positive(auth[field]) for field in ("run_id", "unsigned_artifact_id", "budget")),
            "authorization count refused")
    require(auth["architecture"] in {"x64", "arm64"} and isinstance(auth["candidate_id"], str)
            and re.fullmatch(r"v0\.5\.0-rc-[1-9][0-9]*", auth["candidate_id"]),
            "candidate target refused")
    cua_inputs, cua_payload = auth["cua_inputs"], auth["cua_payload"]
    target = {"x64": "x86_64", "arm64": "aarch64"}[auth["architecture"]] + "-pc-windows-msvc"
    input_fields = {"target", "requirements_sha256", "wheel_manifest_sha256"}
    if isinstance(cua_inputs, dict) and "release_profile" in cua_inputs:
        input_fields |= {"release_profile", "cua_profile_manifest_sha256"}
        require(cua_inputs["release_profile"] == "windows-" + target.split("-", 1)[0]
                and hashed(cua_inputs["cua_profile_manifest_sha256"]), "CUA release profile refused")
    require(isinstance(cua_inputs, dict) and isinstance(cua_payload, dict)
            and set(cua_inputs) == input_fields
            and set(cua_payload) == set(cua_inputs) | {"installed_inventory_sha256"}
            and cua_inputs["target"] == target
            and all(cua_payload.get(key) == value for key, value in cua_inputs.items())
            and all(hashed(cua_payload[key]) for key in (
                "requirements_sha256", "wheel_manifest_sha256", "installed_inventory_sha256")),
            "CUA target, selected wheels or installed inventory refused")
    require(isinstance(auth["files"], dict) and auth["files"]
            and isinstance(auth["legal_hashes"], dict) and auth["legal_hashes"], "empty input inventory")
    require(all(hashed(value) for value in auth["legal_hashes"].values()), "legal hash refused")
    if profiled:
        require(all(hashed(auth[k]) for k in ("helper_claim_sha256", "helper_policy_sha256"))
                and all(positive(auth[k]) for k in ("helper_input_artifact_id", "wsl_artifact_id",
                                                    "helper_signing_operations", "outer_signing_operations"))
                and all(archive_digest(auth[k]) for k in ("helper_input_artifact_digest", "wsl_artifact_digest"))
                and auth["budget"] == auth["helper_signing_operations"] + auth["outer_signing_operations"],
                "profile shared helper identity or operation budget refused")
        policy = auth["signing_policy"]
        require(isinstance(policy, dict) and set(policy) == {"schema", "files"} and policy["schema"] == 1
                and isinstance(policy["files"], dict), "profile outer signing policy differs")
        native = {p for p in auth["files"] if p.lower().endswith((".exe", ".dll", ".pyd"))}
        omitted = native - set(policy["files"])
        require(set(policy["files"]) < native and len(omitted) == 1,
                "profile signing policy must omit exactly one shared helper relay")
        relay_path = next(iter(omitted))
        require(relay_path.endswith("/computer_use/browser/winhost/" + target.split("-", 1)[0] + "/vadgr-cua-host.exe")
                and relay_path.startswith("payload/lib/cua/environments/"), "profile omitted native file is not the shared relay")
        operations = 3  # MSI, detached Burn engine, reattached setup vehicle.
        for path, selected in policy["files"].items():
            require(isinstance(selected, dict) and set(selected) == {
                        "input_sha256", "trust_class", "signer_policy_sha256", "legal_approval_sha256", "signer",
                        "certificate_sha256", "chain_root_sha256", "digest_algorithm", "timestamp_algorithm"}
                    and selected.get("input_sha256") == auth["files"][path]["sha256"]
                    and selected.get("trust_class") in ("publisher-sign", "vendor-preserve"),
                    "profile signing classification absent")
            if selected["trust_class"] == "publisher-sign":
                operations += 1
            if selected["trust_class"] in ("publisher-sign", "vendor-preserve"):
                require(all(hashed(selected.get(k)) for k in ("signer_policy_sha256", "legal_approval_sha256",
                                                             "certificate_sha256", "chain_root_sha256"))
                        and selected.get("digest_algorithm") == "sha256"
                        and selected.get("timestamp_algorithm") == "rfc3161-sha256"
                        and isinstance(selected.get("signer"), str) and selected["signer"],
                        "profile signer identity, chain or legal policy missing")
        require(operations == auth["outer_signing_operations"], "profile outer signing operation count differs")
    # The artifact validator owns file formats. Claims preserve its entire inventory.
    canonical(auth)
    if bound:
        require(positive(auth["qualification_artifact_id"])
                and archive_digest(auth["qualification_artifact_digest"]), "qualification identity refused")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubAPI:
    def request(self, method, path, body=None, binary=False):
        require(path.startswith(PREFIX), "API target refused")
        token = os.environ.get("GH_TOKEN")
        require(bool(token), "GitHub authorization unavailable")
        request = urllib.request.Request("https://api.github.com/" + path, method=method,
            data=canonical(body) if body is not None else None,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        opener = urllib.request.build_opener(NoRedirect)
        try:
            response = opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise Refused("GitHub request uncertain; no retry was made") from error
        with response:
            status = response.code
            if binary and status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                url = urllib.parse.urlsplit(location)
                host = url.hostname or ""
                require(url.scheme == "https" and not url.username and not url.password
                        and (host.endswith(".blob.core.windows.net") or host.endswith(".githubusercontent.com")),
                        "artifact redirect refused")
                # Never forward the API token to artifact storage, even on redirects.
                try:
                    with opener.open(urllib.request.Request(location), timeout=30) as download:
                        raw = download.read(1_048_577)
                        require(len(raw) <= 1_048_576, "qualification archive exceeds bound")
                        return download.code, raw
                except (urllib.error.URLError, TimeoutError, OSError) as error:
                    raise Refused("artifact download failed; no retry was made") from error
            raw = response.read(4_194_305)
            require(len(raw) <= 4_194_304, "GitHub response exceeds bound")
            return status, raw if binary else (parse(raw) if raw else {})


def get(api, path):
    status, result = api.request("GET", PREFIX + path)
    require(status == 200, "GitHub read failed")
    return result


def pages(api, path, key=None):
    result = []
    for page in range(1, 101):
        value = get(api, path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
        rows = value[key] if key else value
        require(isinstance(rows, list), "GitHub page refused")
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise Refused("GitHub pagination exceeded bound")


def policy_digest(api):
    policies = []
    protected = set()
    for summary in pages(api, "rulesets?includes_parents=true&targets=tag"):
        rule = get(api, f"rulesets/{summary['id']}")
        if rule.get("enforcement") != "active" or rule.get("target") != "tag":
            continue
        refs = rule.get("conditions", {}).get("ref_name", {})
        includes = refs.get("include", [])
        # Accept only patterns whose coverage of both production and probe refs is exact.
        if not any(pattern in {"~ALL", "refs/tags/signing-claims/**"}
                   for pattern in includes):
            continue
        require(not refs.get("exclude"), "claim protection has exclusions")
        types = {item.get("type") for item in rule.get("rules", [])}
        if types & {"update", "deletion"}:
            require(rule.get("bypass_actors") == [], "claim mutation protection permits bypass")
            protected |= types & {"update", "deletion"}
        policies.append(rule)
    require(protected == {"update", "deletion"}, "claim mutation protections are missing")
    return digest(canonical(sorted(policies, key=lambda item: item["id"])))


def verify_run(api, auth):
    run = get(api, f"actions/runs/{auth['run_id']}/attempts/1")
    require(run.get("id") == auth["run_id"] and run.get("run_attempt") == 1
            and run.get("head_sha") == auth["trusted_sha"] and run.get("head_branch") == "master"
            and run.get("event") == "workflow_dispatch"
            and run.get("path") == ".github/workflows/candidate.yml"
            and run.get("repository", {}).get("full_name") == REPOSITORY
            and run["repository"].get("fork") is False, "workflow identity refused")


def identity(auth):
    return {field: auth[field] for field in ("repository", "run_id", "run_attempt", "trusted_sha")}


def qualification_valid(auth, record):
    require(isinstance(record, dict) and set(record) == {"schema", "identity", "policy_digest", "probe_ref", "probe_tag", "results"},
            "qualification schema refused")
    require(record["schema"] == 1 and record["identity"] == identity(auth)
            and hashed(record["policy_digest"]) and hashed(record["probe_tag"], 40)
            and record["probe_ref"] == f"refs/tags/signing-claims/probe/{auth['run_id']}-1"
            and record["results"] == {"create": 201, "duplicate": 422, "update_denied": True, "delete_denied": True},
            "qualification does not bind the run")


def bind(auth, record, artifact_id, artifact_digest):
    validate_authorization(auth)
    qualification_valid(auth, record)
    result = dict(auth, qualification_artifact_id=artifact_id, qualification_artifact_digest=artifact_digest)
    validate_authorization(result, bound=True)
    return result


def ref_get(api, ref):
    return get(api, "git/ref/" + ref.removeprefix("refs/"))


def check_ref(api, ref, sha):
    row = ref_get(api, ref)
    require(row.get("ref") == ref and row.get("object", {}).get("sha") == sha
            and row["object"].get("type") == "tag",
            "claim ref changed")


def tag_create(api, ref, target, message):
    status, result = api.request("POST", PREFIX + "git/tags",
        {"tag": ref.removeprefix("refs/tags/"), "message": canonical(message).decode(), "object": target, "type": "commit"})
    require(status == 201 and hashed(result.get("sha"), 40), "claim object creation failed; no retry")
    return result["sha"]


def probe(api, auth, allow_mutations=False):
    require(allow_mutations, "qualification mutation requires explicit permission")
    validate_authorization(auth)
    verify_run(api, auth)
    policy = policy_digest(api)
    ref = f"refs/tags/signing-claims/probe/{auth['run_id']}-1"
    require(api.request("GET", PREFIX + "git/ref/" + ref[5:])[0] == 404, "probe ref already exists")
    parent = get(api, "git/commits/" + auth["trusted_sha"])["parents"][0]["sha"]
    require(hashed(parent, 40) and parent != auth["trusted_sha"], "probe needs a distinct valid target")
    tag = tag_create(api, ref, auth["trusted_sha"], {"probe": identity(auth)})
    body = {"ref": ref, "sha": tag}
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [pool.submit(api.request, "POST", PREFIX + "git/refs", body) for _ in range(2)]
        results = [attempt.result() for attempt in attempts]
    require(sorted(status for status, _ in results) == [201, 422], "competing creates did not have one winner")
    duplicate = next(result for status, result in results if status == 422)
    require("already exists" in duplicate.get("message", "").lower(), "duplicate create was not refused")
    check_ref(api, ref, tag)
    mutation_path = PREFIX + "git/refs/" + ref[5:]
    for method, request in (("PATCH", {"sha": parent, "force": True}), ("DELETE", None)):
        status, result = api.request(method, mutation_path, request)
        require(status in {403, 422} and "rule" in result.get("message", "").lower(), "probe mutation was not denied by a rule")
        check_ref(api, ref, tag)
    require(policy_digest(api) == policy, "protections changed during qualification")
    return {"schema": 1, "identity": identity(auth), "policy_digest": policy,
            "probe_ref": ref, "probe_tag": tag,
            "results": {"create": 201, "duplicate": 422, "update_denied": True, "delete_denied": True}}


def download_qualification(api, auth):
    artifact = get(api, f"actions/artifacts/{auth['qualification_artifact_id']}")
    producer = artifact.get("workflow_run", {})
    require(artifact.get("id") == auth["qualification_artifact_id"] and artifact.get("expired") is False
            and artifact.get("digest") == auth["qualification_artifact_digest"]
            and producer.get("id") == auth["run_id"] and producer.get("head_sha") == auth["trusted_sha"]
            and producer.get("head_branch") == "master", "qualification artifact identity refused")
    status, raw = api.request("GET", PREFIX + f"actions/artifacts/{auth['qualification_artifact_id']}/zip", binary=True)
    require(status == 200 and "sha256:" + digest(raw) == auth["qualification_artifact_digest"], "qualification artifact digest refused")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            require(len(members) == 1 and members[0].filename == "qualification.json"
                    and members[0].file_size <= 65536 and not members[0].is_dir(), "qualification members refused")
            mode = members[0].external_attr >> 16
            require(mode & 0o170000 in {0, 0o100000}, "qualification member type refused")
            record = parse(archive.read(members[0]))
    except (zipfile.BadZipFile, RuntimeError, ValueError) as error:
        raise Refused("qualification archive refused") from error
    qualification_valid(auth, record)
    return record


def verify_qualification(api, auth, record):
    qualification_valid(auth, record)
    require(policy_digest(api) == record["policy_digest"], "qualification protections changed")
    check_ref(api, record["probe_ref"], record["probe_tag"])
    require(download_qualification(api, auth) == record, "qualification bytes differ")


def verify_approval(api, auth, completed=True):
    jobs = pages(api, f"actions/runs/{auth['run_id']}/attempts/1/jobs", "jobs")
    for name in ("claim-probe", "authorize-signing"):
        found = [job for job in jobs if job.get("name") == name]
        if name == "authorize-signing" and not completed:
            require(len(found) == 1 and found[0].get("status") == "in_progress"
                    and found[0].get("conclusion") is None, "protected authorization job is not running")
        else:
            require(len(found) == 1 and found[0].get("status") == "completed"
                    and found[0].get("conclusion") == "success", "protected authorization jobs are incomplete")
    environment = get(api, "environments/candidate-authorize")
    require(environment.get("can_admins_bypass") is False
            and environment.get("deployment_branch_policy") == {"protected_branches": False, "custom_branch_policies": True},
            "authorization environment protection refused")
    branches = pages(api, "environments/candidate-authorize/deployment-branch-policies", "branch_policies")
    require(len(branches) == 1 and branches[0].get("name") == "master" and branches[0].get("type") == "branch",
            "authorization environment ref refused")
    reviewers = {entry["reviewer"]["id"] for rule in environment.get("protection_rules", [])
                 if rule.get("type") == "required_reviewers" for entry in rule.get("reviewers", [])
                 if entry.get("type") == "User"}
    require(bool(reviewers), "direct owner reviewer is required")
    approvals = get(api, f"actions/runs/{auth['run_id']}/approvals")
    relevant = [item for item in approvals if any(env.get("id") == environment.get("id")
                and env.get("name") == "candidate-authorize" for env in item.get("environments", []))]
    require(bool(relevant) and all(item.get("state") == "approved" and item.get("user", {}).get("id") in reviewers
                                 for item in relevant), "explicit owner approval is missing or rejected")


def validate_live(api, auth, record):
    validate_authorization(auth, bound=True)
    verify_run(api, auth)
    verify_qualification(api, auth, record)
    verify_approval(api, auth)


def approve(api, auth, record):
    validate_authorization(auth, bound=True)
    verify_run(api, auth)
    verify_qualification(api, auth, record)
    verify_approval(api, auth, completed=False)


def fetch_qualification(api, auth):
    validate_authorization(auth, bound=True)
    verify_run(api, auth)
    record = download_qualification(api, auth)
    require(policy_digest(api) == record["policy_digest"], "qualification protections changed")
    check_ref(api, record["probe_ref"], record["probe_tag"])
    verify_approval(api, auth)
    return record


def claim_ref(auth):
    # A different ZIP envelope must not mint another claim for the same files.
    # The archive digest remains in the authorization for exact transport checks.
    key = {name: auth[name] for name in ("repository", "source_sha", "architecture", "input_digest")}
    key["files_digest"] = digest(canonical(auth["files"]))
    return "refs/tags/signing-claims/" + digest(canonical(key))


def create(api, auth, record):
    validate_live(api, auth, record)
    ref = claim_ref(auth)
    require(api.request("GET", PREFIX + "git/ref/" + ref[5:])[0] == 404, "signing inputs already claimed")
    message = {"schema": 1, "authorization": auth, "authorization_digest": digest(canonical(auth))}
    tag = tag_create(api, ref, auth["source_sha"], message)
    status, _ = api.request("POST", PREFIX + "git/refs", {"ref": ref, "sha": tag})
    require(status == 201, "claim creation failed or raced; no retry")
    result = {"schema": 1, "ref": ref, "tag": tag, "authorization_digest": message["authorization_digest"]}
    verify(api, auth, record, result)
    return result


def verify(api, auth, record, claim):
    validate_live(api, auth, record)
    require(isinstance(claim, dict) and set(claim) == {"schema", "ref", "tag", "authorization_digest"}
            and claim["schema"] == 1 and claim["ref"] == claim_ref(auth) and hashed(claim["tag"], 40)
            and claim["authorization_digest"] == digest(canonical(auth)), "claim tuple mismatch")
    check_ref(api, claim["ref"], claim["tag"])
    tag = get(api, "git/tags/" + claim["tag"])
    require(tag.get("sha") == claim["tag"] and tag.get("tag") == claim["ref"].removeprefix("refs/tags/")
            and tag.get("object", {}).get("sha") == auth["source_sha"] and tag["object"].get("type") == "commit"
            and parse(tag.get("message", "")) == {"schema": 1, "authorization": auth, "authorization_digest": digest(canonical(auth))},
            "claim object mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("probe", "bind", "approve", "fetch-qualification", "create", "verify"))
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--claim", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--artifact-id", type=int)
    parser.add_argument("--digest")
    parser.add_argument("--allow-probe-mutations", action="store_true")
    args = parser.parse_args()
    try:
        if args.mode in {"probe", "bind", "create", "fetch-qualification"}:
            require(args.out is not None and not args.out.exists(), "new output path required")
        auth = parse(args.authorization.read_bytes())
        require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
                and os.environ.get("GITHUB_RUN_ID") == str(auth.get("run_id"))
                and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                and os.environ.get("GITHUB_SHA") == auth.get("trusted_sha")
                and os.environ.get("GITHUB_REF") == "refs/heads/master", "current workflow context refused")
        record = parse(args.qualification.read_bytes()) if args.qualification else None
        api = GitHubAPI()
        if args.mode == "probe":
            result = probe(api, auth, args.allow_probe_mutations)
        elif args.mode == "bind":
            result = bind(auth, record, args.artifact_id, args.digest)
        elif args.mode == "create":
            result = create(api, auth, record)
        elif args.mode == "approve":
            approve(api, auth, record)
            result = None
        elif args.mode == "fetch-qualification":
            result = fetch_qualification(api, auth)
        else:
            require(args.claim is not None, "claim path required")
            verify(api, auth, record, parse(args.claim.read_bytes()))
            result = None
        if result is not None:
            require(args.out is not None, "output path required")
            with args.out.open("xb") as output:
                output.write(canonical(result) + b"\n")
        print("Candidate claim check passed.")
        return 0
    except (Refused, OSError, KeyError, TypeError, ValueError, IndexError):
        print("Candidate claim refused; inspect the protected non-secret record.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
