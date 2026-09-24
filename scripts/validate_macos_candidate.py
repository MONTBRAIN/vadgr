#!/usr/bin/env python3
"""Validate an exact, open-PR macOS candidate without accessing signing material.

Production reads GitHub through `gh api` and the checked-out Git objects. A
single --fixtures JSON snapshot replaces both readers for offline tests; its
output is explicitly marked fixture_mode and is not signing provenance.
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

REPOSITORY = "MONTBRAIN/vadgr"
BRANCH = "feature/0.5.0-distribution"
BASE = "master"
SELF_CHECK = "validate-macos-candidate"
FILES = (
    "Cargo.toml", "Cargo.lock", "CHANGELOG.md", "packaging/toolchain.json",
    "packaging/cua/pins.toml", "packaging/cua/requirements.lock",
    ".github/workflows/ci.yml",
)
SHA = re.compile(r"[0-9a-f]{40}")
HASH = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
CONTEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._()/:-]{0,159}")


class Refused(Exception):
    """Only fixed categories and validated public check names reach stderr."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Refused(reason)


def matches(pattern: re.Pattern, value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def positive(value: object) -> bool:
    return type(value) is int and value > 0


def run(argv: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Refused("candidate metadata command could not complete") from None
    require(result.returncode == 0, "candidate metadata command failed")
    require(len(result.stdout) <= 16 * 1024 * 1024, "candidate metadata response is too large")
    try:
        # Keep Git blob newlines intact: input hashes describe committed bytes,
        # not the host's universal-newline translation of them.
        return result.stdout.decode("utf-8")
    except UnicodeError:
        raise Refused("candidate metadata is not UTF-8") from None


class GitHub:
    def get(self, endpoint: str, pages: bool = False):
        argv = ["gh", "api", "--method", "GET", "--hostname", "github.com",
                "-H", "Accept: application/vnd.github+json",
                "-H", "X-GitHub-Api-Version: 2022-11-28"]
        if pages:
            argv.extend(["--paginate", "--slurp"])
        # Authentication is inherited by gh, never copied into argv or output.
        value = json.loads(run([*argv, f"repos/{REPOSITORY}/{endpoint}".rstrip("/")]))
        if pages:
            require(isinstance(value, list) and bool(value), "GitHub pagination is unavailable")
        return value


def local_source(root: Path, sha: str) -> dict:
    git = lambda *args: run(["git", *args], root).strip()
    require(git("rev-parse", "--verify", "HEAD^{commit}") == sha, "checkout is not the requested commit")
    require(not git("status", "--porcelain", "--untracked-files=all"), "candidate checkout is not clean")
    return {
        "sha": sha,
        "tree": git("rev-parse", "--verify", f"{sha}^{{tree}}"),
        "clean": True,
        "files": {name: run(["git", "show", f"{sha}:{name}"], root) for name in FILES},
    }


def collect(root: Path, sha: str, api: GitHub) -> dict:
    local = local_source(root, sha)
    repo = api.get("")
    ref = f"git/ref/heads/{BRANCH}"
    branch = api.get(ref)
    pulls = [row for page in api.get(
        f"pulls?state=open&head={quote('MONTBRAIN:' + BRANCH, safe='')}&base={BASE}&per_page=100", True
    ) for row in page]
    checks = [row for page in api.get(
        f"commits/{sha}/check-runs?filter=latest&per_page=100", True
    ) for row in page["check_runs"]]
    status_pages = api.get(f"commits/{sha}/status?per_page=100", True)
    require(all(page["sha"] == sha for page in status_pages), "commit status provenance does not match")
    result = {
        "local": local, "repository": repo, "branch": branch,
        "pull_requests": pulls, "commit": api.get(f"git/commits/{sha}"),
        "rules": [row for page in api.get(f"rules/branches/{BASE}?per_page=100", True) for row in page],
        "check_runs": checks,
        "statuses": {"sha": sha, "statuses": [row for page in status_pages for row in page["statuses"]]},
        "tags": [row for page in api.get("tags?per_page=100", True) for row in page],
        "releases": [row for page in api.get("releases?per_page=100", True) for row in page],
    }
    # Re-read mutable identity after the check queries. A push or PR closure
    # during collection invalidates this snapshot instead of blessing old work.
    result["branch_end"] = api.get(ref)
    result["pull_request_end"] = (
        api.get(f"pulls/{pulls[0]['number']}")
        if len(pulls) == 1 and positive(pulls[0].get("number")) else None
    )
    return result


def validate_inputs(files: dict) -> tuple[str, dict]:
    require(all(isinstance(files.get(name), str) and files[name].strip() for name in FILES),
            "a required source, lock or toolchain input is missing")
    cargo = tomllib.loads(files["Cargo.toml"])
    version = cargo["package"]["version"]
    require(version == "0.5.0", "candidate package version does not match its branch")
    headings = re.findall(r"^## \[([^\]]+)\] - (.+)$", files["CHANGELOG.md"], re.MULTILINE)
    require(bool(headings) and headings[0] == (version, "Unreleased"), "candidate changelog does not match")
    lock = tomllib.loads(files["Cargo.lock"])
    packages = lock["package"]
    require(lock["version"] in (3, 4) and isinstance(packages, list) and bool(packages), "Cargo lock is invalid")
    require(sum(item.get("name") == "vadgr-daemon" and item.get("version") == version for item in packages) == 1,
            "Cargo lock package version does not match")
    for item in packages:
        source = item.get("source", "")
        if source.startswith("registry+"):
            require(matches(HASH, item.get("checksum")), "Cargo registry checksum is missing")
        elif source.startswith("git+"):
            require(matches(SHA, source.rsplit("#", 1)[-1]), "Cargo Git dependency is not pinned")
    pins = tomllib.loads(files["packaging/cua/pins.toml"])
    require(all(matches(VERSION, pins.get(name)) for name in ("cua", "python", "uv")), "runtime versions are not pinned")
    require(isinstance(pins.get("python_build"), str) and re.fullmatch(r"[0-9]{8}", pins["python_build"]),
            "Python build is not pinned")
    for target in ("aarch64-apple-darwin", "x86_64-apple-darwin"):
        require(all(matches(HASH, pins["targets"][target].get(name)) for name in ("python_sha256", "uv_sha256")),
                "a macOS runtime archive hash is missing")
    requirements = files["packaging/cua/requirements.lock"].replace("\\\n", " ")
    versions = {}
    for line in requirements.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry = re.match(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        hashes = re.findall(r"--hash=sha256:([^\s]+)", line)
        require(entry is not None and bool(hashes) and all(matches(HASH, value) for value in hashes),
                "a Python dependency is not hash-pinned")
        versions[entry[1]] = entry[2]
    require(versions.get("vadgr-computer-use") == pins["cua"], "CUA lock and runtime pin do not match")
    toolchain = json.loads(files["packaging/toolchain.json"])
    require(toolchain["schema"] == 1 and all(matches(VERSION, toolchain.get(name)) for name in ("dotnet_sdk", "wix")),
            "packaging toolchain is not pinned")
    require(all(matches(HASH, toolchain["appimagetool"][arch].get("sha256")) for arch in ("x86_64", "aarch64")),
            "packaging archive hashes are missing")
    actions = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", files[".github/workflows/ci.yml"], re.MULTILINE)
    require(any(action.startswith("dtolnay/rust-toolchain@") for action in actions), "Rust toolchain action is missing")
    require(all("@" in action and matches(SHA, action.rsplit("@", 1)[1]) for action in actions),
            "a CI toolchain action is not hash-pinned")
    return version, {name: hashlib.sha256(files[name].encode()).hexdigest() for name in FILES}


def validate(snapshot: dict, sha: str, repository: str, ref: str, self_check: str = SELF_CHECK) -> dict:
    require(matches(SHA, sha), "source must be a full lowercase commit SHA")
    require(repository == REPOSITORY and ref == BRANCH, "repository or candidate branch is not permitted")
    repo = snapshot["repository"]
    require(repo["full_name"] == REPOSITORY and repo["fork"] is False and repo["default_branch"] == BASE,
            "candidate repository identity is not permitted")
    for branch in (snapshot["branch"], snapshot["branch_end"]):
        require(branch["ref"] == f"refs/heads/{BRANCH}" and branch["object"]["type"] == "commit"
                and branch["object"]["sha"] == sha, "candidate is not the current remote branch head")
    local, commit = snapshot["local"], snapshot["commit"]
    tree = commit["tree"]["sha"]
    require(commit["sha"] == sha and matches(SHA, tree), "remote commit tree is unknown")
    require(local["sha"] == sha and local["tree"] == tree and local["clean"] is True,
            "checkout does not match the clean remote commit tree")
    pulls = snapshot["pull_requests"]
    require(isinstance(pulls, list) and len(pulls) == 1, "exactly one open candidate pull request is required")
    for pull in (pulls[0], snapshot["pull_request_end"]):
        require(pull["state"] == "open" and positive(pull["number"]), "candidate pull request is not open")
        require(pull["head"]["sha"] == sha and pull["head"]["ref"] == BRANCH and pull["base"]["ref"] == BASE,
                "pull request does not bind the requested head and base")
        require(all(pull[end]["repo"]["full_name"] == REPOSITORY and pull[end]["repo"]["fork"] is False
                    for end in ("head", "base")), "fork pull requests cannot authorize a candidate")
    require(pulls[0]["number"] == snapshot["pull_request_end"]["number"], "candidate pull request changed")
    version, hashes = validate_inputs(local["files"])
    require(all(tag["name"] != f"v{version}" for tag in snapshot["tags"]), "candidate version already has a tag")
    require(all(release["tag_name"] != f"v{version}" for release in snapshot["releases"]), "candidate version already has a release")
    required = set()
    for rule in snapshot["rules"]:
        if rule["type"] == "required_status_checks":
            for check in rule["parameters"]["required_status_checks"]:
                context, integration = check["context"], check.get("integration_id")
                require(matches(CONTEXT, context) and "://" not in context, "required check name is invalid")
                require(integration is None or positive(integration), "required check integration is invalid")
                require(context != self_check, "candidate validation cannot require its own check")
                required.add((context, integration))
    require(bool(required), "active rulesets declare no required checks; repair repository settings")
    runs = snapshot["check_runs"]
    for check in runs:
        require(check["head_sha"] == sha, "check run is not bound to the exact candidate head")
        require(positive(check["id"]) and positive(check["app"]["id"]), "check run identity is invalid")
    status = snapshot["statuses"]
    require(status["sha"] == sha, "commit statuses are not bound to the exact candidate head")
    statuses = {}
    for check in status["statuses"]:
        require(positive(check["id"]), "commit status identity is invalid")
        require(check["context"] not in statuses, "combined commit status contains duplicate contexts")
        statuses[check["context"]] = check
    for context, integration in sorted(required, key=lambda item: (item[0], item[1] or 0)):
        matching = [check for check in runs if check["name"] == context and (integration is None or check["app"]["id"] == integration)]
        legacy = statuses.get(context)
        require(bool(matching) or (integration is None and legacy is not None),
                f"required check is missing on the candidate head: {context}")
        require(all(check["status"] == "completed" and check["conclusion"] == "success" for check in matching)
                and (legacy is None or legacy["state"] == "success"), f"required check has not succeeded: {context}")
    return {"schema": 1, "repository": REPOSITORY, "ref": BRANCH, "source_sha": sha,
            "source_tree": tree, "version": version, "pull_request": pulls[0]["number"],
            "required_checks": sorted({name for name, _ in required}), "inputs_sha256": hashes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--self-check", default=SELF_CHECK)
    parser.add_argument("--checkout", type=Path, default=Path("."))
    parser.add_argument("--fixtures", type=Path, help="offline JSON snapshot; output is marked fixture_mode")
    args = parser.parse_args(argv)
    try:
        require(matches(SHA, args.sha), "source must be a full lowercase commit SHA")
        require(args.repository == REPOSITORY and args.ref == BRANCH, "repository or candidate branch is not permitted")
        if args.fixtures:
            snapshot = json.loads(args.fixtures.read_text(encoding="utf-8"))
        else:
            for name, value in (("GITHUB_SHA", args.sha), ("GITHUB_REPOSITORY", args.repository), ("GITHUB_REF_NAME", args.ref)):
                require(name not in os.environ or os.environ[name] == value, "workflow identity does not match the requested candidate")
            snapshot = collect(args.checkout, args.sha, GitHub())
        metadata = validate(snapshot, args.sha, args.repository, args.ref, args.self_check)
        metadata["fixture_mode"] = args.fixtures is not None
    except Refused as error:
        print(f"MACOS CANDIDATE REFUSED: {error}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError, AttributeError, OSError):
        print("MACOS CANDIDATE REFUSED: candidate metadata is missing or malformed", file=sys.stderr)
        return 1
    print(json.dumps(metadata, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
