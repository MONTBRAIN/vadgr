#!/usr/bin/env python3
"""Evidence travels on its own, and every boundary names the build it came from.

Two rules, both learned by breaking them.

**A change either files evidence or edits documents, never both.** A `git add
-A` swept an entire thrown-away e2e pass into a commit that was adding something
else, and it reached the default branch inside a pull request nobody read it in.
Evidence is the record a release rests on. It gets its own change, so a reviewer
looking at a diff of evidence is looking at evidence.

**Every boundary names the commit it was produced from.** A directory of results
that cannot say which build produced them is not evidence: three fixes landed
mid-pass in `vadgr 0.4.9`, the binaries moved three commits, and no cell in that
pass could name the artifact behind it. The whole pass was withdrawn.

    python3 scripts/check_evidence.py [--range <start>..<end>]

With no range it reads the working tree and the index. It prints one line per
check it performs, because a coverage list restated in prose is the fact that
drifts.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = "e2e_evidence/"
HEAD_LINE = re.compile(r"^\s*\w[\w -]*head:\s*([0-9a-f]{7,40})\s*$", re.MULTILINE)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    return result.stdout


def changed_paths(rev_range: str | None) -> list[str]:
    if rev_range:
        out = git("diff", "--name-only", rev_range)
    else:
        # `-uall` lists untracked files one by one. Without it git collapses a
        # new directory to a single entry with a trailing slash, and a whole
        # pass filed at once reads as one path too shallow to be a pass.
        out = git("status", "--porcelain", "-uall")
        return [line[3:].strip() for line in out.splitlines() if line[3:].strip()]
    return [line.strip() for line in out.splitlines() if line.strip()]


def evidence_travels_alone(paths: list[str]) -> list[str]:
    """Evidence and documents do not ride in the same change."""
    evidence = sorted(p for p in paths if p.startswith(EVIDENCE))
    other = sorted(p for p in paths if not p.startswith(EVIDENCE))
    if not evidence or not other:
        return []
    return [
        f"this change files evidence and edits {len(other)} other file(s) at once. "
        "Evidence gets its own change, so a reviewer reading a diff of evidence is "
        "reading evidence. First of each: "
        f"{evidence[0]} and {other[0]}"
    ]


def every_boundary_names_its_build(paths: list[str]) -> list[str]:
    """Each pass directory this change touches names the build behind it.

    Only what the change touches. Evidence already filed was filed under the
    rules of its day, and a check that reopens closed passes fires on finished
    work, which teaches everyone to ignore the output.
    """
    problems = []
    touched = set()
    for path in paths:
        if not path.startswith(EVIDENCE):
            continue
        parts = pathlib.PurePosixPath(path).parts
        # e2e_evidence/<repo>-<minor>/<pass>/...: anything shallower is a note
        # about the release rather than a pass of its own.
        if len(parts) >= 4:
            touched.add(pathlib.PurePosixPath(*parts[:3]))
    for pass_dir in sorted(touched):
        # A pass that is being withdrawn is correctly gone. Asking a deleted
        # directory to name its build fires on the repair rather than the fault.
        # An empty directory counts as gone: `git rm` leaves the parents behind,
        # git does not track them, and a directory holding nothing is not a pass.
        directory = ROOT / pass_dir
        if not directory.is_dir() or not any(directory.rglob("*")):
            continue
        host = ROOT / pass_dir / "host.txt"
        if not host.exists():
            problems.append(
                f"{pass_dir} carries no host.txt, so nothing in it can name "
                "the build that produced it"
            )
            continue
        if not HEAD_LINE.search(host.read_text()):
            problems.append(
                f"{pass_dir}/host.txt names no head; a result that cannot "
                "name its build is not a result"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--range", dest="rev_range", default=None)
    args = parser.parse_args()

    problems = []
    paths = changed_paths(args.rev_range)
    print("  ok    evidence and documents do not ride in one change")
    problems += evidence_travels_alone(paths)
    print("  ok    every pass this change touches names the commit it came from")
    problems += every_boundary_names_its_build(paths)

    print()
    if problems:
        for problem in problems:
            print(f"  EVIDENCE DEFECT: {problem}")
        print()
        print("  EVIDENCE REFUSED")
        return 1
    print("  EVIDENCE ACCOUNTED FOR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
