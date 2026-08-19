#!/usr/bin/env python3
"""Reject a branch cut from another branch's work.

Every branch starts from a freshly pulled default branch. A branch cut from a
feature branch carries that feature's commits, and a squash merge replays the
whole diff, so merging it merges the feature too: **under the wrong title and
without its gate**.

That is not a hypothetical. Three doctrine pull requests were cut from a release
branch and merging them put an entire unfinished CLI into the default branch,
while its e2e was still running on two operating systems.

**The signal is ancestry.** If another open pull request's head is an ancestor of
this one, this branch was cut from that branch rather than from the default
branch, and it carries work that belongs to the other review.

It reads the open pull requests from the GitHub CLI when one is available, so the
same script runs in CI and by hand.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def is_ancestor(candidate: str, head: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", candidate, head],
            capture_output=True,
        ).returncode
        == 0
    )


def inherited(head: str, others: list[dict], ancestry=is_ancestor) -> list[str]:
    """The open pull requests whose work this branch already contains.

    `others` excludes this pull request; each entry needs `number`, `title` and
    `head`. A head we cannot resolve is skipped rather than guessed at: a branch
    deleted mid-run is not evidence of anything.
    """
    problems = []
    for other in others:
        sha = other.get("head")
        if not sha or sha == head:
            continue
        if ancestry(sha, head):
            problems.append(
                f"#{other['number']} ({other['title']}) is an ancestor of this branch"
            )
    return problems


def open_pull_requests(number: int | None) -> list[dict]:
    out = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--json", "number,title,headRefOid"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return []
    rows = json.loads(out.stdout or "[]")
    return [
        {"number": r["number"], "title": r["title"], "head": r["headRefOid"]}
        for r in rows
        if r["number"] != number
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-number", type=int)
    args = parser.parse_args()

    head = subprocess.run(
        ["git", "rev-parse", args.head], capture_output=True, text=True
    ).stdout.strip()
    if not head:
        print("branch point check could not run: no such revision")
        return 2

    problems = inherited(head, open_pull_requests(args.pr_number))
    if problems:
        print("THIS BRANCH WAS CUT FROM ANOTHER BRANCH")
        for problem in problems:
            print(f"  {problem}")
        print()
        print("A squash merge replays the whole diff, so merging this would merge")
        print("that work too, under this title and without its gate. Re-cut the")
        print("branch from the default branch and cherry-pick your own commits.")
        return 1

    print("BRANCH POINT CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
