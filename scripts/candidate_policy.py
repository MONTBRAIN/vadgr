#!/usr/bin/env python3
"""Trusted, secret-free source preflight for a held release candidate.

Only the copy on the approved default branch may execute in protected jobs.
The feature checkout provides data, never this program or its dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import quote

if __package__:
    from scripts import cua_release_inputs
    from scripts.validate_package_inputs import PackageInputError, validate_package_inputs
else:
    import cua_release_inputs
    from validate_package_inputs import PackageInputError, validate_package_inputs

REPOSITORY = "MONTBRAIN/vadgr"
TRUSTED_ROOT_SHA256 = "3c2cc7f357dc064ec527fdcd78da6e9245c21a381e1abaa0f2b62b186bcac1a1"
BASE = "master"
EXCLUDED = "E2E/0.5.0/e2e.md"
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
CANDIDATE = re.compile(r"v0\.5\.0-rc-[1-9][0-9]*\Z")
CONTEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._()/:-]{0,159}\Z")
CHECK_URL = re.compile(
    r"https://github\.com/MONTBRAIN/vadgr/actions/runs/([1-9][0-9]*)/job/([1-9][0-9]*)\Z"
)
WORKFLOW_CONTEXTS = {
    "secret-scan": ".github/workflows/secret-scan.yml",
}
TRUSTED_WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/secret-scan.yml")


class Refused(Exception):
    """A precondition is absent; do not request any signing operation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Refused(message)


def run(args: list[str], cwd: Path | None = None, *, binary: bool = False):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused("metadata command could not complete") from exc
    require(result.returncode == 0 and len(result.stdout) <= 32 * 1024 * 1024,
            "metadata command failed or returned too much data")
    if binary:
        return result.stdout
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeError as exc:
        raise Refused("metadata is not UTF-8") from exc


def git(root: Path, *args: str, binary: bool = False):
    return run(["git", *args], root, binary=binary)


def github(endpoint: str, *, paginate: bool = False):
    args = ["gh", "api", "--method", "GET", "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28"]
    if paginate:
        args += ["--paginate", "--slurp"]
    args += [f"repos/{REPOSITORY}/{endpoint}".rstrip("/")]
    try:
        data = json.loads(run(args))
    except (ValueError, TypeError) as exc:
        raise Refused("GitHub metadata is malformed") from exc
    if paginate:
        require(isinstance(data, list) and len(data) > 0, "GitHub pagination failed")
    return data


def pages(endpoint: str, key: str | None = None) -> list:
    response = github(endpoint, paginate=True)
    require(all(isinstance(page, (list if key is None else dict)) for page in response),
            "GitHub page is malformed")
    return [row for page in response for row in (page if key is None else page[key])]


def inventory(root: Path, sha: str) -> list[tuple[str, str, str, str]]:
    records = git(root, "ls-tree", "-r", "-z", sha, binary=True).split(b"\0")
    result = []
    for raw in records:
        if not raw:
            continue
        try:
            header, name = raw.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split(" ")
            path = name.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise Refused("tree contains an unsupported path") from exc
        result.append((mode, kind, object_id, path))
    return result


def input_digest(rows: list[tuple[str, str, str, str]]) -> str:
    data = bytearray()
    seen = set()
    for mode, kind, object_id, name in rows:
        require(mode in ("100644", "100755") and kind == "blob"
                and SHA.fullmatch(object_id) is not None, "tree contains a link or submodule")
        require(name not in seen and name and not name.startswith("/")
                and all(piece not in ("", ".", "..") for piece in name.split("/")),
                "tree has ambiguous path")
        seen.add(name)
        if name != EXCLUDED:
            data.extend(f"{mode} {kind} {object_id}\t{name}\0".encode("utf-8"))
    require(EXCLUDED in seen and bool(data), "candidate runbook or product inputs are missing")
    return hashlib.sha256(data).hexdigest()


def require_pull_requests(pulls: list, branch: str, sha: str) -> int | None:
    require(isinstance(pulls, list) and len(pulls) <= 1, "ambiguous implementation pull request")
    if not pulls:
        return None
    item = pulls[0]
    require(item["state"] == "open" and type(item["number"]) is int and item["number"] > 0,
            "implementation pull request is not open")
    require(item["head"]["sha"] == sha and item["head"]["ref"] == branch
            and item["base"]["ref"] == BASE, "implementation pull request changed")
    for end in ("head", "base"):
        require(item[end]["repo"]["full_name"] == REPOSITORY
                and item[end]["repo"]["fork"] is False, "forked pull request refused")
    return item["number"]


def require_checks(rules: list, checks: list, statuses: list, sha: str) -> list[dict]:
    required = set()
    require(isinstance(rules, list) and rules, "no effective branch rules found")
    for rule in rules:
        if rule.get("type") == "required_status_checks":
            for entry in rule["parameters"]["required_status_checks"]:
                context, issuer = entry["context"], entry.get("integration_id")
                require(isinstance(context, str) and CONTEXT.fullmatch(context) is not None,
                        "invalid required check context")
                require(issuer is None or (type(issuer) is int and issuer > 0),
                        "invalid required check issuer")
                required.add((context, issuer))
    require(required, "effective rules require no CI checks")
    selected = []
    for context, issuer in sorted(required, key=lambda value: (value[0], value[1] or 0)):
        matches = [c for c in checks if c.get("name") == context and
                   (issuer is None or c.get("app", {}).get("id") == issuer)]
        equivalent = [s for s in statuses if s.get("context") == context]
        if issuer is None:
            require(all(type(s.get("id")) is int for s in equivalent),
                    "status identity missing")
            all_results = [(c.get("started_at") or c.get("created_at") or "", c["id"],
                            "check", c) for c in matches if type(c.get("id")) is int]
            all_results += [(s.get("created_at") or "", s["id"], "status", s)
                            for s in equivalent]
            require(all_results, f"required check is missing: {context}")
            _, _, kind, latest = max(all_results, key=lambda row: (row[0], row[1]))
            if kind == "status":
                require(latest.get("state") == "success",
                        f"required status has not succeeded: {context}")
                selected.append({"context": context, "integration_id": None,
                                 "status_id": latest["id"]})
                continue
        if matches:
            require(all(c.get("head_sha") == sha and type(c.get("id")) is int and
                        type(c.get("app", {}).get("id")) is int for c in matches),
                    "check identity does not match source")
            # Query the complete history, never filter=latest: newer failures must win.
            latest = max(matches, key=lambda c: (c.get("started_at") or c.get("created_at") or "", c["id"]))
            require(latest.get("status") == "completed" and latest.get("conclusion") == "success",
                    f"required check has not succeeded: {context}")
            selected.append({"context": context, "integration_id": issuer,
                             "check_id": latest["id"]})
            continue
        require(issuer is None, f"required app check is missing: {context}")
        require(equivalent, f"required check is missing: {context}")
        require(all(type(s.get("id")) is int for s in equivalent), "status identity missing")
        latest = max(equivalent, key=lambda s: (s.get("created_at") or "", s["id"]))
        require(latest.get("state") == "success", f"required status has not succeeded: {context}")
        selected.append({"context": context, "integration_id": None,
                         "status_id": latest["id"]})
    return selected


def require_trusted_workflows(root: Path, sha: str, rows: list) -> None:
    """A feature checkout must not redefine the required GitHub Actions jobs."""
    names = {name for _, _, _, name in rows}
    trusted_root = Path(__file__).resolve().parents[1]
    for name in TRUSTED_WORKFLOWS:
        require(name in names and (trusted_root / name).is_file(),
                "required check workflow is absent")
        require(git(root, "show", f"{sha}:{name}", binary=True) ==
                (trusted_root / name).read_bytes(),
                "candidate redefines a required check workflow")


def require_trusted_check_runs(selected: list[dict], checks: list[dict],
                               sha: str, branch: str) -> list[dict]:
    """Bind every passing check to a specific, current workflow and its actual job."""
    indexed = {check["id"]: check for check in checks if type(check.get("id")) is int}
    workflows: dict[str, int] = {}
    runs: dict[int, dict] = {}
    result = []
    for entry in selected:
        context = entry["context"]
        workflow = (WORKFLOW_CONTEXTS[context] if context in WORKFLOW_CONTEXTS
                    else ".github/workflows/secret-scan.yml" if context.startswith("gate-tests (")
                    else ".github/workflows/ci.yml" if context.startswith((
                        "rust (", "installer (", "clean-install (", "wsl-clean-install"))
                    else None)
        require(workflow is not None and "check_id" in entry and
                entry["integration_id"] == 15368,
                "unrecognized or unbound required workflow context")
        check = indexed[entry["check_id"]]
        match = CHECK_URL.fullmatch(check.get("details_url", ""))
        require(match is not None, "required check has no GitHub Actions job identity")
        run_id, job_id = map(int, match.groups())
        require(job_id == check["id"], "required check job ID mismatch")
        if workflow not in workflows:
            definition = github("actions/workflows/" + workflow.rsplit("/", 1)[1])
            require(definition.get("path") == workflow and
                    definition.get("state") == "active" and
                    type(definition.get("id")) is int,
                    "trusted workflow identity is missing")
            workflows[workflow] = definition["id"]
        if run_id not in runs:
            runs[run_id] = github(f"actions/runs/{run_id}")
        run_record = runs[run_id]
        require(run_record.get("workflow_id") == workflows[workflow] and
                run_record.get("path") == workflow and
                run_record.get("head_sha") == sha and
                run_record.get("head_branch") == branch and
                run_record.get("event") in ("push", "pull_request") and
                run_record.get("run_attempt") == 1 and
                run_record.get("status") == "completed" and
                run_record.get("conclusion") == "success" and
                run_record.get("repository", {}).get("full_name") == REPOSITORY and
                run_record.get("head_repository", {}).get("full_name") == REPOSITORY,
                "required check did not run in the trusted workflow")
        job = github(f"actions/jobs/{job_id}")
        require(job.get("id") == job_id and job.get("run_id") == run_id and
                job.get("head_sha") == sha and job.get("name") == context and
                job.get("conclusion") == "success" and
                job.get("check_run_url") ==
                f"https://api.github.com/repos/{REPOSITORY}/check-runs/{job_id}",
                "required check is not the selected workflow job")
        result.append({**entry, "workflow_id": workflows[workflow], "workflow_run_id": run_id})
    return result


def require_release_inputs(trusted_root: str, terms: str, legal: bool, sbom: bool) -> None:
    require(hashlib.sha256(trusted_root.encode()).hexdigest() == TRUSTED_ROOT_SHA256,
            "candidate Sigstore public root differs from reviewed trust policy")
    require(bool(terms.strip()) and not re.search(r"draft|proposed|pending legal review", terms, re.I),
            "terms have not received final legal review")
    require(legal and sbom, "legal files, SBOM or pinned inputs are missing")


def trusted_approval(architecture: str) -> dict:
    path = Path(__file__).resolve().parents[1] / "packaging/candidate-legal-approval.json"
    require(path.is_file(), "reviewed legal approval is not configured in trusted tooling")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(data.get("schema") == 1 and data.get("version") == "0.5.0"
            and data.get("terms_version") == "1.0" and isinstance(data.get("targets"), dict)
            and isinstance(data["targets"].get(architecture), dict),
            "trusted legal approval has an invalid scope")
    target = data["targets"][architecture]
    require(isinstance(target.get("legal_hashes"), dict) and target["legal_hashes"]
            and all(SHA256.fullmatch(value) for value in target["legal_hashes"].values())
            and all(SHA256.fullmatch(target.get(key, "")) for key in
                    ("sbom_sha256", "inventory_sha256", "generator_sha256")),
            "trusted legal approval contains an unapproved file")
    return target


def materialize(root: Path, sha: str, rows: list[tuple[str, str, str, str]], target: Path) -> None:
    require(not target.exists(), "build directory must not exist before materialization")
    target.mkdir(parents=True)
    for mode, _, _, name in rows:
        if name == EXCLUDED:
            continue
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git(root, "show", f"{sha}:{name}", binary=True))
        path.chmod(int(mode, 8) & 0o777)


def preflight(args) -> dict:
    root = args.source_root.resolve()
    sha, branch = args.source_sha, args.branch
    require(SHA.fullmatch(sha) is not None and branch == "feature/0.5.0-distribution",
            "candidate source or branch is not permitted")
    require(args.version == "0.5.0" and CANDIDATE.fullmatch(args.candidate_id) is not None
            and args.architecture in ("x64", "arm64"), "candidate identity is invalid")
    require(git(root, "rev-parse", "HEAD") == sha and
            not git(root, "status", "--porcelain", "--untracked-files=all"),
            "candidate checkout does not match clean pushed source")
    tree = git(root, "rev-parse", f"{sha}^{{tree}}")
    rows = inventory(root, sha)
    digest = input_digest(rows)
    require_trusted_workflows(root, sha, rows)
    repo = github("")
    require(repo["full_name"] == REPOSITORY and repo["fork"] is False
            and repo["default_branch"] == BASE, "repository identity mismatch")
    def read_branch():
        row = github(f"git/ref/heads/{quote(branch, safe='/')}")
        require(row["ref"] == f"refs/heads/{branch}" and
                row["object"]["type"] == "commit" and row["object"]["sha"] == sha,
                "candidate branch moved")
    read_branch()
    remote = github(f"git/commits/{sha}")
    require(remote["sha"] == sha and remote["tree"]["sha"] == tree,
            "remote source tree mismatch")
    pulls = pages(f"pulls?state=open&head={quote('MONTBRAIN:' + branch, safe='')}&base=master&per_page=100")
    pull = require_pull_requests(pulls, branch, sha)
    rules = pages("rules/branches/master?per_page=100")
    checks = pages(f"commits/{sha}/check-runs?filter=all&per_page=100", "check_runs")
    status_pages = github(f"commits/{sha}/status?per_page=100")
    require(status_pages["sha"] == sha, "commit statuses source mismatch")
    required = require_checks(rules, checks, status_pages["statuses"], sha)
    required = require_trusted_check_runs(required, checks, sha, branch)
    def blob(name):
        return git(root, "show", f"{sha}:{name}")
    cargo = tomllib.loads(blob("Cargo.toml"))
    require(cargo["package"]["version"] == args.version, "package version mismatch")
    changelog = blob("CHANGELOG.md")
    require(re.search(rf"^## \[{re.escape(args.version)}\] - ", changelog, re.M) is not None,
            "candidate changelog missing")
    names = {name for _, _, _, name in rows}
    arch_name = {"x64": "x86_64", "arm64": "aarch64"}[args.architecture]
    legal_prefix = f"packaging/inputs/windows-{arch_name}/"
    require_release_inputs(git(root, "show", f"{sha}:packaging/release-trusted-root.jsonl",
                               binary=True).decode("utf-8"),
                           blob(legal_prefix + "legal/TERMS.txt"),
                           all(legal_prefix + name in names for name in
                               ("package-input-inventory.json", "package-input-review.json",
                                "README-OFFLINE.txt", "legal/TERMS.rtf")),
                           any(p.startswith(legal_prefix + "sbom/") for p in names))
    pins = tomllib.loads(blob("packaging/cua/pins.toml"))
    require(all(re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", pins.get(key, ""))
                for key in ("cua", "python")), "CUA or Python version is not pinned")
    trusted_root = Path(__file__).resolve().parents[1]
    cua_inputs = cua_release_inputs.reviewed_inputs(
        root, trusted_root, f"{arch_name}-pc-windows-msvc")
    cua_version = pins["cua"]
    if "release_profile" in cua_inputs:
        if __package__:
            from scripts import cua_profiles
        else:
            import cua_profiles
        _, _, catalog = cua_profiles.reviewed(root, trusted_root, cua_inputs["release_profile"])
        cua_version = catalog["cua_version"]
    cua_release_inputs.verify_origin(trusted_root)
    approval = trusted_approval(args.architecture)
    legal_root = root / legal_prefix
    package_validation = validate_package_inputs(
        legal_root, root, args.version, f"{arch_name}-pc-windows-msvc", source_only=True)
    require(package_validation.get("status") == "approved" and
            package_validation.get("scope") == "source-inputs", "legal source review is not approved")
    review = json.loads((legal_root / "package-input-review.json").read_text(encoding="utf-8"))
    require(review.get("terms_version") == "1.0", "reviewed terms version differs from release policy")
    for name, expected in approval["legal_hashes"].items():
        source_name = (name if name.startswith("packaging/cua/helper-signing/")
                       else legal_prefix + "legal/TERMS.rtf" if name == "TERMS.rtf"
                       else legal_prefix + name.removeprefix("payload/"))
        require(source_name in names and hashlib.sha256(
            git(root, "show", f"{sha}:{source_name}", binary=True)).hexdigest() == expected,
            "sealed legal source does not match reviewed bytes")
    if "release_profile" in cua_inputs:
        for suffix in (".json", "-outer.json"):
            name = f"packaging/cua/helper-signing/{arch_name}{suffix}"
            require(name in approval["legal_hashes"] and (trusted_root / name).is_file()
                    and hashlib.sha256((trusted_root / name).read_bytes()).hexdigest() == approval["legal_hashes"][name],
                    "profile signing policy lacks exact trusted legal approval")
    require(hashlib.sha256(git(root, "show", f"{sha}:{legal_prefix}package-input-inventory.json",
                                binary=True)).hexdigest() == approval["inventory_sha256"],
            "sealed dependency inventory differs from legal approval")
    require(not any(tag["name"] == f"v{args.version}" for tag in pages("tags?per_page=100")),
            "release tag already exists")
    require(not any(release["tag_name"] == f"v{args.version}" for release in pages("releases?per_page=100")),
            "release already exists")
    read_branch()
    rules_again = pages("rules/branches/master?per_page=100")
    require(rules_again == rules, "effective rules changed during validation")
    if pull is not None:
        fresh = github(f"pulls/{pull}")
        require_pull_requests([fresh], branch, sha)
    if args.materialize:
        materialize(root, sha, rows, args.materialize.resolve())
    return {"schema": 1, "repository": REPOSITORY, "branch": branch,
            "source_sha": sha, "source_tree": tree, "input_digest": digest,
            "version": args.version, "candidate_id": args.candidate_id,
            "architecture": args.architecture, "pull_request": pull,
            "cua_version": cua_version, "python_version": pins["python"],
            "cua_inputs": cua_inputs,
            "legal_approval_sha256": hashlib.sha256(json.dumps(approval, sort_keys=True).encode()).hexdigest(),
            "trusted_sha": os.environ.get("GITHUB_SHA", ""), "required_checks": required,
            "rules_digest": hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    operation = commands.add_parser("preflight")
    operation.add_argument("--source-root", type=Path, required=True)
    operation.add_argument("--branch", required=True)
    operation.add_argument("--source-sha", required=True)
    operation.add_argument("--version", required=True)
    operation.add_argument("--candidate-id", required=True)
    operation.add_argument("--architecture", choices=("x64", "arm64"), required=True)
    operation.add_argument("--out", type=Path, required=True)
    operation.add_argument("--materialize", type=Path)
    args = parser.parse_args()
    try:
        require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
                and os.environ.get("GITHUB_REF") == "refs/heads/master"
                and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                and SHA.fullmatch(os.environ.get("GITHUB_SHA", "")) is not None,
                "trusted workflow identity is invalid")
        result = preflight(args)
        require(result["trusted_sha"] != result["source_sha"],
                "candidate may not be the trusted bootstrap itself")
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (Refused, PackageInputError, OSError, ValueError, TypeError, KeyError, IndexError,
            subprocess.SubprocessError) as exc:
        print("CANDIDATE REFUSED: " + (str(exc) if isinstance(exc, Refused)
              else "required metadata is invalid"), file=sys.stderr)
        return 1
    print("Candidate source accepted: " + result["source_sha"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
