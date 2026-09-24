#!/usr/bin/env python3
"""Extract the complete public installer contract without surrounding editorial text."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


HEADING = "### Vadgr packaged distribution terms"


def extract_terms(document: bytes) -> bytes:
    text = document.decode("utf-8").replace("\r\n", "\n")
    headings = list(re.finditer(r"^" + re.escape(HEADING) + r"$", text, re.M))
    if len(headings) != 1:
        raise ValueError("Expected one public terms block")
    start = headings[0].start()
    following = re.search(r"^#{1,3} ", text[headings[0].end():], re.M)
    end = headings[0].end() + following.start() if following else len(text)
    block = text[start:end].rstrip("\n") + "\n"
    clauses = re.findall(r"^#### (\d+)\. \S", block, re.M)
    if clauses != [str(number) for number in range(1, 13)]:
        raise ValueError("Expected all twelve public terms clauses")
    if not re.search(r"^\*\*Version \d+\.\d+\*\*$", block, re.M):
        raise ValueError("Expected a terms version")
    if re.search(r"\b(?:draft|roadmap|runbook|research basis|legal review|"
                 r"engineering note|development phase)\b|D-\d+", block, re.I):
        raise ValueError("Public terms contain editorial text")
    return block.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--check", type=Path, help="Compare with an existing UTF-8 terms file")
    args = parser.parse_args()
    try:
        terms = extract_terms(args.source.read_bytes())
        if args.check:
            if args.check.read_bytes() != terms:
                raise ValueError("Terms bytes differ")
            print("Public installer terms match.")
        else:
            sys.stdout.buffer.write(terms)
        return 0
    except (OSError, ValueError):
        print("Installer terms extraction failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
