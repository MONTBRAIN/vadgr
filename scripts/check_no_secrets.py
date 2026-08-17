#!/usr/bin/env python3
"""Reject tracked credential files and credential-shaped repository content."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import stat
import subprocess
import sys


PATTERNS = {
    "OpenAI or Anthropic API key": re.compile(
        rb"sk-((proj|svcacct|admin|ant)-[A-Za-z0-9_-]{16,}|[A-Za-z0-9_-]{32,})"
    ),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    # OAuth access and identity tokens are the credential this daemon mints at
    # runtime; they never appear in an env file, so only a shape check can
    # catch one. The signature floor keeps unsigned test tokens out.
    "signed JWT": re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "private key": re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
}
SENSITIVE_NAME = re.compile(
    r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|OPEN_?AI|GEMINI|ANTH?ROPHIC)",
    re.IGNORECASE,
)
ALLOW_TEST_FIXTURE = b"secret-scan: allow-test-fixture"
KNOWN_TEST_VALUES = (b"sk-ant-oat01-" + b"VERYSECRETTOKEN",)
WINDOWS_ACL_CHECK = r"""
$acl = Get-Acl -LiteralPath $args[0]
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$owner = $acl.Owner
try {
    $owner = (New-Object System.Security.Principal.NTAccount($owner)).Translate(
        [System.Security.Principal.SecurityIdentifier]
    ).Value
} catch { exit 1 }
if ($owner -ne $current) { exit 1 }
$broad = @("S-1-1-0", "S-1-5-11", "S-1-5-32-545")
foreach ($rule in $acl.Access) {
    if ($rule.AccessControlType -ne "Allow") { continue }
    try {
        $sid = $rule.IdentityReference.Translate(
            [System.Security.Principal.SecurityIdentifier]
        ).Value
    } catch { exit 1 }
    if ($broad -contains $sid) { exit 1 }
}
exit 0
"""


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def commits_for(git_range: str | None) -> list[str]:
    if not git_range:
        return []
    left = git_range.split("..", 1)[0]
    if not left or set(left) == {"0"}:
        return ["HEAD"]
    result = git("rev-list", "--reverse", git_range, check=False)
    if result.returncode != 0:
        raise RuntimeError("the requested Git range is not available")
    commits = result.stdout.decode().splitlines()
    return commits or ["HEAD"]


def tracked_paths(commit: str) -> list[str]:
    output = git("ls-tree", "-r", "-z", "--name-only", commit).stdout
    return [item.decode(errors="surrogateescape") for item in output.split(b"\0") if item]


def unsafe_env_path(path: str) -> bool:
    name = pathlib.PurePosixPath(path).name
    return (name == ".env" or name.startswith(".env.")) and name != ".env.example"


def has_unallowed_match(pattern: re.Pattern[bytes], line: bytes) -> bool:
    if ALLOW_TEST_FIXTURE in line:
        return False
    for value in KNOWN_TEST_VALUES:
        line = line.replace(value, b"")
    return pattern.search(line) is not None


def pattern_paths(commit: str, label: str, pattern: re.Pattern[bytes]) -> list[str]:
    result = git(
        "grep", "-I", "-l", "-E", "-e", pattern.pattern.decode(), commit, "--", check=False
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed for {label}")
    paths = []
    for line in result.stdout.decode(errors="replace").splitlines():
        path = line.split(":", 1)[-1]
        data = git("show", f"{commit}:{path}").stdout
        if any(has_unallowed_match(pattern, item) for item in data.splitlines()):
            paths.append(path)
    return paths


def worktree_pattern_paths(pattern: re.Pattern[bytes]) -> list[str]:
    paths = []
    for raw_path in git("ls-files", "-z").stdout.split(b"\0"):
        if not raw_path:
            continue
        path = pathlib.Path(os.fsdecode(raw_path))
        try:
            data = path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError):
            continue
        if b"\0" in data:
            continue
        if any(has_unallowed_match(pattern, item) for item in data.splitlines()):
            paths.append(path.as_posix())
    return paths


def load_local_secrets(path: pathlib.Path) -> list[bytes]:
    if path.is_symlink():
        raise RuntimeError("the local environment file must not be a symlink")
    info = path.stat()
    if os.name == "nt":
        acl_check = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", WINDOWS_ACL_CHECK, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if acl_check.returncode != 0:
            raise RuntimeError("the local environment file must have an owner-only Windows DACL")
    else:
        if info.st_uid != os.getuid():
            raise RuntimeError("the local environment file must be owned by the current user")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeError("the local environment file must have mode 0600")

    values = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        if not SENSITIVE_NAME.search(name):
            continue
        value = value.strip().strip("'\"")
        if len(value) >= 8:
            values.append(value.encode())
    return values


def exact_value_paths(values: list[bytes]) -> list[str]:
    findings = set()
    output = git("ls-files", "-z").stdout
    for raw_path in output.split(b"\0"):
        if not raw_path:
            continue
        path = pathlib.Path(os.fsdecode(raw_path))
        try:
            data = path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError):
            continue
        if any(value in data for value in values):
            findings.add(path.as_posix())
    return sorted(findings)


def exact_value_commit_paths(values: list[bytes], commit: str) -> list[str]:
    findings = set()
    changed = git(
        "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", commit
    ).stdout
    for raw_path in changed.split(b"\0"):
        if not raw_path:
            continue
        path = os.fsdecode(raw_path)
        content = git("show", f"{commit}:{path}", check=False)
        if content.returncode == 0 and any(value in content.stdout for value in values):
            findings.add(path)
    return sorted(findings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-range")
    parser.add_argument("--env-file", type=pathlib.Path)
    parser.add_argument("--event-file", type=pathlib.Path)
    args = parser.parse_args()

    findings: set[tuple[str, str, str]] = set()
    try:
        commits = commits_for(args.git_range)
        for path in git("ls-files", "-z").stdout.split(b"\0"):
            if path and unsafe_env_path(os.fsdecode(path)):
                findings.add(("worktree", os.fsdecode(path), "tracked environment file"))
        for label, pattern in PATTERNS.items():
            for path in worktree_pattern_paths(pattern):
                findings.add(("worktree", path, label))
        for commit in commits:
            short = git("rev-parse", "--short", commit).stdout.decode().strip()
            for path in tracked_paths(commit):
                if unsafe_env_path(path):
                    findings.add((short, path, "tracked environment file"))
            for label, pattern in PATTERNS.items():
                for path in pattern_paths(commit, label, pattern):
                    findings.add((short, path, label))

        if args.env_file:
            values = load_local_secrets(args.env_file.resolve())
            for path in exact_value_paths(values):
                findings.add(("worktree", path, "exact local credential value"))
            for commit in commits:
                short = git("rev-parse", "--short", commit).stdout.decode().strip()
                for path in exact_value_commit_paths(values, commit):
                    findings.add((short, path, "exact local credential value"))
        if args.event_file:
            event = args.event_file.read_bytes()
            for label, pattern in PATTERNS.items():
                if pattern.search(event):
                    findings.add(("event", "GitHub event text", label))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"secret check could not run: {error}", file=sys.stderr)
        return 2

    if findings:
        print("SECRET CHECK FAILED")
        for commit, path, reason in sorted(findings):
            print(f"  {commit}: {path}: {reason}")
        print("Rotate any exposed credential before removing it from Git history.")
        return 1

    print("SECRET CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
