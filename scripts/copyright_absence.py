"""Conservative, reproducible copyright-absence evidence for exact source archives.

Only entirely decoded text archives qualify. Every ownership-marker occurrence
outside complete, pinned standard-license templates or reviewed documents is ambiguous.
This is evidence for review, not a declaration that a work has no copyright.
"""

import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import tarfile
import zipfile


BOILERPLATE = {
    # Complete MIT grant, without an owner statement, and complete Apache 2.0
    # standard text including the unchanged [yyyy]/[name] application template.
    "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5": "MIT-standard-grant-without-owner-statement",
    "0ffddef9e48f8a09aed5caf2d44f7ba1c1be2d9b8e0a6f693b1635b2d5566645": "Apache-2.0-standard-unfilled-template",
    "59d8f0ba87ad9a2f1a431123c8d16646e5b89ba53653e818f16d136d77263c99": "Apache-2.0-complete-terms-without-application-appendix",
    "7c9b48b52decb9837c70f608678129e1ac79e056829c8d1e82e8cdd8aed562f8": "MIT-standard-grant-with-heading-without-owner-statement",
    "6c0fe4001061a2cc11528179f3e52bd7d864efdbc714965aef4b7c61aecb4adc": "MIT-0-complete-standard-grant",
    "05d9f1a0af61535887a399e161c9d14d1f898043b61d05fe4854ed8c6460179c": "CC0-1.0-complete-standard-legal-code",
    "a796d5730b60337084397744dbaaad751d2995d421f96e8842e4a22007ee284f": "BSL-1.0-complete-standard-grant",
    "eb47aa3af9dca1d00dfefcf91f37f3518b1f06f88ee549a0d74fefcda5c79efa": "BSD-3-Clause-complete-grant-without-owner-statement",
    "958e28cd3f37c23ec02881fe20cb82d4151668349e1c7beb2daea4ce2640dcf0": "Apache-2.0-standard-unfilled-brace-template",
    "e8ba82e63ba908724aaee6043943c5a2629b9ebf1af581ea0eea19a713123685": "MPL-2.0-complete-standard-license-with-exhibits",
    "f42a00ac54d036890559853a40f95622ab3e63d52173f5714284134b2af11e3c": "Apache-2.0-standard-unfilled-template-with-LLVM-exception",
}
MARKERS = re.compile(r"copyright|\u00a9|&copy;|&#(?:169|x0*a9);|\bcopr\.|\(c\)\s*[12][0-9]{3}|^\s*(?://|#|\*)?\s*\(c\)\s+[A-Z]|all rights reserved|"
                     r"urheberrecht|derechos reservados|droit d.auteur|\u8457\u4f5c\u6a29|\u7248\u6743", re.I)
REVIEWED_DOCUMENTS = {
    # The entire retained organizational code was read. Its sole marker forbids
    # "copyright violation or misattribution"; it asserts no ownership or owner.
    "35073a462b7169eed28aefd71913871622afa80d92b8b6a229219bfa4691ad56":
        "Bytecode-Alliance-organizational-code-of-conduct-generic-compliance-clause",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_member(name, value):
    row = {"path": name, "size": len(value), "sha256": digest(value)}
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
        elif normalized in REVIEWED_DOCUMENTS:
            row.update(status="complete-reviewed-document-no-ownership-statement",
                       reviewed_document=REVIEWED_DOCUMENTS[normalized], normalized_sha256=normalized)
        else:
            mentions = [{"line": number, "text": line} for number, line in enumerate(text.splitlines(), 1)
                        if MARKERS.search(line)]
            row["status"] = "ambiguous-ownership-marker" if mentions else "decoded-no-ownership-markers"
            if mentions:
                row["mentions"] = mentions
    return row


def audit_result(files, expected):
    eligible = bool(files) and all(row["status"] in {"complete-standard-boilerplate", "decoded-no-ownership-markers",
                                   "complete-reviewed-document-no-ownership-statement"} for row in files)
    return {"schema": 1, "method": "complete-decoded-archive-and-exact-standard-boilerplate-v1",
            "archive_sha256": expected, "eligible_for_reviewed_NONE": eligible,
            "files": sorted(files, key=lambda row: row["path"]),
            "meaning": "No original copyright information detected under this complete-member audit. Not public domain; license rights and duties still apply. Exact package review approval remains mandatory."}


def source_tree_zip(members):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return output.getvalue()


def audit_source_tree_zip(raw, expected_tree_hash):
    """The whole observed tree, not a selected text-only subset, identifies this component."""
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("copyright source archive expansion limit exceeded")
    files, seen, total, contents = [], set(), 0, {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.comment:
            raise ValueError("uninspected copyright archive comment")
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if (not member.filename or path.is_absolute() or ".." in path.parts or "\\" in member.filename
                    or ":" in member.filename or path.as_posix() != member.filename):
                raise ValueError("unsafe copyright source member")
            mode = member.external_attr >> 16 & 0o170000
            if (member.filename.casefold() in seen or member.is_dir() or mode not in (0, 0o100000)
                    or member.flag_bits & 1 or member.comment or member.extra):
                raise ValueError("aliased, linked or uninspected copyright source member")
            seen.add(member.filename.casefold())
            total += member.file_size
            if member.file_size > 32 * 1024 * 1024 or total > 512 * 1024 * 1024 or len(files) >= 100000:
                raise ValueError("copyright archive expansion limit exceeded")
            contents[member.filename] = archive.read(member)
            files.append(inspect_member(member.filename, contents[member.filename]))
    if source_tree_zip(contents) != raw:
        raise ValueError("noncanonical or uninspected copyright source ZIP bytes")
    tree = {row["path"]: row["sha256"] for row in files}
    tree_hash = digest((json.dumps(tree, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))
    if tree_hash != expected_tree_hash:
        raise ValueError("copyright observed source tree identity differs")
    return {**audit_result(files, digest(raw)), "method": "complete-decoded-observed-source-tree-v1",
            "component_tree_sha256": tree_hash}


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
            files.append(inspect_member(member.name, archive.extractfile(member).read()))
    return audit_result(files, expected)
