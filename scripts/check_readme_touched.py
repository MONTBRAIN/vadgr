#!/usr/bin/env python3
"""A change that ships a new version touches its README, or says it did not.

`README.md` is the file most people read and the one nobody remembers to open.
A minor that deletes a surface, renames a command, moves a directory or changes
what the product is has changed the README, and it is updated in the same pull
request.

**The rule is old and it was broken in all three repositories at once**, for
three minors: one README was the untouched framework template, one called the
daemon a workflow engine after that concept had been deleted whole, and one sold
a product name that no longer existed with an install command pointing at the
repository's former name. Nobody noticed, because nothing fails when a README
rots.

**What this checks is narrow on purpose.** It cannot read a README for truth. It
can see that a pull request bumped the version and left every README untouched
without saying so, which is the shape every one of those three had.

The escape is a sentence, not a flag: write `README: nothing changed` in the pull
request body, and mean it. A rule that cannot be answered is one people route
around.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

VERSION_FILES = ("Cargo.toml", "rust/Cargo.toml", "pyproject.toml", "pubspec.yaml")
DECLARATION = re.compile(r"(?i)README\s*:\s*nothing changed")


def changed_files(git_range: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", git_range], capture_output=True, text=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def version_changed(git_range: str, files: list[str]) -> bool:
    """Whether this range edits a version line in a manifest."""
    for path in files:
        if not any(path.endswith(v) for v in VERSION_FILES):
            continue
        diff = subprocess.run(
            ["git", "diff", git_range, "--", path], capture_output=True, text=True
        ).stdout
        for line in diff.splitlines():
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                if re.match(r"[+-]\s*version\s*[:=]", line):
                    return True
    return False


def touches_readme(files: list[str]) -> bool:
    return any(pathlib.Path(f).name.lower() == "readme.md" for f in files)


def declared(event_file: pathlib.Path | None) -> bool:
    if not event_file or not event_file.exists():
        return False
    try:
        event = json.loads(event_file.read_text())
    except Exception:
        return False
    body = ((event.get("pull_request") or {}).get("body")) or ""
    return bool(DECLARATION.search(body))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-range", required=True)
    parser.add_argument("--event-file", type=pathlib.Path)
    args = parser.parse_args()

    if subprocess.run(
        ["git", "rev-list", "--quiet", args.git_range], capture_output=True
    ).returncode not in (0, 1):
        print("readme check could not run: the requested Git range is not available")
        return 2

    files = changed_files(args.git_range)
    if not version_changed(args.git_range, files):
        print("README CHECK PASSED (no version change in this range)")
        return 0
    if touches_readme(files):
        print("README CHECK PASSED (the version moved and a README moved with it)")
        return 0
    if declared(args.event_file):
        print("README CHECK PASSED (the version moved and the body says nothing changed)")
        return 0

    print("A VERSION MOVED AND NO README DID")
    print()
    print("  README.md is the file most people read and the one nobody remembers")
    print("  to open. If this release deletes a surface, renames a command, moves")
    print("  a directory or changes what the product is, its README has changed.")
    print()
    print("  Update it, or write 'README: nothing changed' in the pull request")
    print("  body and mean it.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
