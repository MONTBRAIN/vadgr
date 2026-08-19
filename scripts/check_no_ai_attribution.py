#!/usr/bin/env python3
"""Reject AI attribution in commit messages, pull request text and shipped files.

The rule is old and it was still broken: five commits reached a release branch
carrying a `Co-Authored-By` trailer naming a model. Prose did not stop it, so
this does.

**What counts as attribution** is a credit, not a mention. A commit that says
"the model returned a 429" is describing the product's own behaviour and is
fine. A commit that credits a model for the work, or advertises which tool wrote
it, is not, wherever it appears: a trailer, a body line, a pull request, a
generated file header.

It reads a git range, an event payload, or files given on the command line, so
one implementation serves the hook, the workflow and a person checking by hand.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

# A credit, not a mention. Each pattern is anchored on the crediting form so
# that writing *about* a model stays legal: this file itself must pass.
PATTERNS: list[tuple[str, str]] = [
    (r"(?im)^\s*co-authored-by:.*\b(claude|gpt|codex|copilot|gemini|anthropic|openai)\b",
     "a Co-Authored-By trailer crediting a model or its vendor"),
    (r"(?i)\b(generated|written|authored|created)\s+(with|by)\s+"
     r"(claude|chatgpt|gpt-[0-9]|codex|copilot|cursor|gemini|an?\s+(ai|llm))\b",
     "a generated-with credit"),
    (r"(?i)\b(claude|codex|copilot)\s+(code\s+)?(wrote|generated|authored)\b",
     "a claim that a tool wrote the work"),
    (r"(?i)^\s*(assisted|powered)\s+by\s+(claude|gpt|codex|copilot|ai)\b",
     "an assisted-by credit"),
    (r"(?i)\bnoreply@anthropic\.com\b", "a model's commit identity"),
]

# Files that exist to record the rule or to test it.
ALLOWED = {
    "scripts/check_no_ai_attribution.py",
    "scripts/tests/test_check_no_ai_attribution.py",
}


# A line that forbids the form is not an instance of it.
#
# Every document that states this rule has to quote what it forbids, and a gate
# that fires on the rule's own wording is one somebody deletes. The test is the
# line the match sits on: a prohibition names the form in order to reject it.
PROHIBITION = re.compile(
    r"(?i)\b(never|no|not|don't|do not|must not|forbidden|without|"
    r"reject\w*|refuse\w*|prohibit\w*|remove\w*|strip\w*|avoid\w*)\b"
)


def findings(text: str, where: str) -> list[str]:
    lines = text.splitlines()
    out = []
    for pattern, why in PATTERNS:
        for match in re.finditer(pattern, text):
            number = text[: match.start()].count("\n") + 1
            line = lines[number - 1] if number <= len(lines) else ""
            # The line before matters too, because prose wraps.
            previous = lines[number - 2] if number >= 2 else ""
            if PROHIBITION.search(line) or PROHIBITION.search(previous):
                continue
            out.append(f"{where}:{number}: {why}")
    return out


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    ).stdout


def check_range(git_range: str) -> list[str]:
    """Every commit message in the range, one report per commit."""
    revs = git("rev-list", git_range).split()
    problems = []
    for rev in revs:
        message = git("show", "-s", "--format=%B", rev)
        problems += findings(message, f"commit {rev[:12]}")
    return problems


def check_event(path: pathlib.Path) -> list[str]:
    """The pull request title and body, and any review or comment text."""
    try:
        event = json.loads(path.read_text())
    except Exception:
        return []
    problems = []
    for key, node in (("pull_request", event.get("pull_request")),
                      ("issue", event.get("issue")),
                      ("comment", event.get("comment")),
                      ("review", event.get("review"))):
        if not isinstance(node, dict):
            continue
        for field in ("title", "body"):
            value = node.get(field)
            if isinstance(value, str):
                problems += findings(value, f"{key}.{field}")
    return problems


def check_files(paths: list[pathlib.Path]) -> list[str]:
    problems = []
    for path in paths:
        rel = path.as_posix()
        if rel in ALLOWED or not path.is_file():
            continue
        try:
            problems += findings(path.read_text(errors="ignore"), rel)
        except OSError:
            continue
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-range")
    parser.add_argument("--event-file", type=pathlib.Path)
    parser.add_argument("paths", nargs="*", type=pathlib.Path)
    args = parser.parse_args()

    problems: list[str] = []
    if args.git_range:
        if subprocess.run(
            ["git", "rev-list", "--quiet", args.git_range],
            capture_output=True,
        ).returncode not in (0, 1):
            print("attribution check could not run: the requested Git range is not available")
            return 2
        problems += check_range(args.git_range)
    if args.event_file and args.event_file.exists():
        problems += check_event(args.event_file)
    if args.paths:
        problems += check_files(args.paths)

    if problems:
        print("AI ATTRIBUTION FOUND")
        for problem in problems:
            print(f"  {problem}")
        print()
        print("The work is the author's. Credit for it does not go to a tool, in a")
        print("commit trailer, a body line, a pull request or a generated file.")
        return 1

    print("ATTRIBUTION CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
