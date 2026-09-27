"""Conservative, reproducible copyright-absence evidence for exact source archives.

Only entirely decoded text archives qualify. Every ownership-marker occurrence
outside two complete, pinned, unmodified standard-license templates is ambiguous.
This is evidence for review, not a declaration that a work has no copyright.
"""

import hashlib
import io
from pathlib import PurePosixPath
import re
import tarfile


BOILERPLATE = {
    # Complete MIT grant, without an owner statement, and complete Apache 2.0
    # standard text including the unchanged [yyyy]/[name] application template.
    "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5": "MIT-standard-grant-without-owner-statement",
    "0ffddef9e48f8a09aed5caf2d44f7ba1c1be2d9b8e0a6f693b1635b2d5566645": "Apache-2.0-standard-unfilled-template",
    "59d8f0ba87ad9a2f1a431123c8d16646e5b89ba53653e818f16d136d77263c99": "Apache-2.0-complete-terms-without-application-appendix",
}
MARKERS = re.compile(r"copyright|\u00a9|&copy;|&#(?:169|x0*a9);|\bcopr\.|(?<![A-Za-z0-9_])\(c\)\s+[A-Za-z0-9]|all rights reserved|"
                     r"urheberrecht|derechos reservados|droit d.auteur|\u8457\u4f5c\u6a29|\u7248\u6743", re.I)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def audit_archive(raw, expected):
    if len(raw) > 32 * 1024 * 1024 or digest(raw) != expected:
        raise ValueError("copyright source archive identity differs")
    files, seen, total = [], set(), 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name or ":" in member.name:
                raise ValueError("unsafe copyright source member")
            if member.name.casefold() in seen or not (member.isfile() or member.isdir()):
                raise ValueError("aliased or linked copyright source member")
            seen.add(member.name.casefold())
            if not member.isfile():
                continue
            total += member.size
            if member.size > 32 * 1024 * 1024 or total > 512 * 1024 * 1024 or len(files) >= 100000:
                raise ValueError("copyright archive expansion limit exceeded")
            value = archive.extractfile(member).read()
            row = {"path": member.name, "size": len(value), "sha256": digest(value)}
            try:
                text = value.decode("utf-8-sig")
                if "\0" in text:
                    raise UnicodeError("binary member")
            except UnicodeError:
                row["status"] = "undecoded-member-needs-review"
            else:
                normalized = digest(" ".join(text.split()).encode("utf-8"))
                if normalized in BOILERPLATE:
                    row.update(status="complete-standard-boilerplate", template=BOILERPLATE[normalized],
                               normalized_sha256=normalized)
                else:
                    mentions = [{"line": number, "text": line} for number, line in enumerate(text.splitlines(), 1)
                                if MARKERS.search(line)]
                    row["status"] = "ambiguous-ownership-marker" if mentions else "decoded-no-ownership-markers"
                    if mentions:
                        row["mentions"] = mentions
            files.append(row)
    eligible = bool(files) and all(row["status"] in {"complete-standard-boilerplate", "decoded-no-ownership-markers"}
                                   for row in files)
    return {"schema": 1, "method": "complete-decoded-archive-and-exact-standard-boilerplate-v1",
            "archive_sha256": expected, "eligible_for_reviewed_NONE": eligible,
            "files": sorted(files, key=lambda row: row["path"]),
            "meaning": "No original copyright information detected under this complete-member audit. Not public domain; license rights and duties still apply. Exact package review approval remains mandatory."}
