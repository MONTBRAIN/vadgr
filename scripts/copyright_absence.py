"""Conservative, reproducible copyright-absence evidence for exact source archives.

Only entirely decoded text or completely inspected, exact pinned binary records
qualify. Every ownership-marker occurrence outside complete, pinned standard
license templates or reviewed documents is ambiguous.
This is evidence for review, not a declaration that a work has no copyright.
"""

import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile
import zlib

if __package__:
    from scripts.reviewed_certificate_evidence import REVIEWED as REVIEWED_CERTIFICATES, inspect_certificate
else:
    from reviewed_certificate_evidence import REVIEWED as REVIEWED_CERTIFICATES, inspect_certificate


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

# These two small records were inspected completely, including every section,
# symbol, byte and archive padding. There are no data or unclassified sections.
# This is not a binary strings scan, a generic object-file exemption, or an
# inference from the source author. Any changed byte requires a new inspection.
REVIEWED_BINARY_RECORDS = {
    "174c31f5cf1136305232c0b83db0aaa422e8428ae84973e85116d799325850df": {
        "format": "WebAssembly-1-relocatable-cabi-realloc-trampoline",
        "size": 261,
        "parts": [
            (0, 8, "WebAssembly magic and version 1"),
            (8, 19, "One function type: four i32 parameters, one i32 result"),
            (19, 117, "Three env imports: __linear_memory, cabi_realloc_wit_bindgen_0_39_0, __indirect_function_table"),
            (117, 121, "One function using type zero"),
            (121, 139, "One function export named cabi_realloc"),
            (139, 159, "One code body: no locals, load parameters 0 through 3, call relocated function zero, end"),
            (159, 197, "linking version 2 symbol table: cabi_realloc definition and imported function reference"),
            (197, 215, "reloc.CODE: one function-index relocation at offset 12"),
            (215, 261, "target_features: mutable-globals and sign-ext"),
        ],
    },
    "b7b6a5fec27dd1abf3d888d387cb3e02dc66772fab86f5543cef301140a99fd6": {
        "format": "Unix-ar-containing-only-reviewed-cabi-realloc-object-and-symbol-index",
        "size": 412,
        "parts": [
            (0, 8, "Unix archive magic"),
            (8, 68, "Symbol-index member header, zero timestamp/user/group/mode, 22-byte content"),
            (68, 90, "One symbol at member offset 90: cabi_realloc, with terminator and zero padding"),
            (90, 150, "cabi_realloc.o member header, zero timestamp/user/group, mode 644, 261-byte content"),
            (150, 411, "Exact separately reviewed WebAssembly object: 174c31f5cf1136305232c0b83db0aaa422e8428ae84973e85116d799325850df"),
            (411, 412, "Required archive newline alignment byte"),
        ],
    },
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_reviewed_conda(value):
    """Recheck a complete pinned decoding observation, not arbitrary Zstandard data."""
    expected = "54303491a8418fbed24344b513546182c29b43bf282ceb433af65e2299f9271f"
    if digest(value) != expected:
        raise ValueError("reviewed nested archive identity differs")
    proof = json.loads((Path(__file__).parent / "legal_evidence/sigstore-empty-conda.json").read_bytes())
    proof_hash = digest(json.dumps(proof, sort_keys=True, separators=(",", ":")).encode())
    if proof_hash != "e2c835c737edea373e2d62cf608a654b192f375fc54ab70b3a43236c28892f1c":
        raise ValueError("reviewed nested decoding observation differs")
    files = []
    with zipfile.ZipFile(io.BytesIO(value)) as outer:
        if outer.comment or outer.namelist() != [row["path"] for row in proof["members"]]:
            raise ValueError("reviewed nested archive member scope differs")
        for row in proof["members"]:
            member = outer.getinfo(row["path"])
            raw = outer.read(member)
            if (digest(raw) != row["sha256"] or len(raw) != row["size"] or member.comment
                    or member.extra.hex() != row["extra_hex"] or member.flag_bits != 0
                    or member.compress_type != 0 or member.header_offset != row["header_offset"]):
                raise ValueError("reviewed nested archive metadata differs")
            if "text" in row:
                if raw != row["text"].encode():
                    raise ValueError("reviewed nested text differs")
                files.append(inspect_member(row["path"], raw))
                continue
            frame = proof["zstandard_frames"][digest(raw)]
            # Both complete frame outputs were inspected and are retained here.
            # The committed observation is bound to the exact compressed input;
            # no portable validator dependency on an external decoder is needed.
            decoded = zlib.decompress(base64.b64decode(frame["decoded_zlib_base64"], validate=True))
            if digest(decoded) != frame["decoded_sha256"] or len(decoded) != frame["decoded_size"]:
                raise ValueError("reviewed nested decoded bytes differ")
            offset = 0
            with tarfile.open(fileobj=io.BytesIO(decoded), mode="r:") as nested:
                members = nested.getmembers()
                if [item.name for item in members] != [item["path"] for item in row["decoded_members"]]:
                    raise ValueError("reviewed TAR member scope differs")
                for item, retained in zip(members, row["decoded_members"]):
                    if (not item.isfile() or item.pax_headers or item.uname or item.gname or item.linkname
                            or item.offset != offset or item.offset_data != offset + 512):
                        raise ValueError("uninspected reviewed TAR metadata")
                    header = decoded[offset:offset + 512]
                    if MARKERS.search(header.decode("ascii")):
                        raise ValueError("ownership statement in reviewed TAR header")
                    text = nested.extractfile(item).read()
                    if (digest(text) != retained["sha256"] or len(text) != retained["size"]
                            or text != retained["text"].encode()):
                        raise ValueError("reviewed nested member bytes differ")
                    end = item.offset_data + item.size
                    offset = (end + 511) // 512 * 512
                    if any(decoded[end:offset]):
                        raise ValueError("uninspected reviewed TAR padding")
                    files.append({**inspect_member(row["path"] + "/" + item.name, text), "decoded_text": text.decode()})
            if len(decoded) - offset != 1024 or any(decoded[offset:]):
                raise ValueError("uninspected reviewed TAR trailer")
    if not all(row["status"] == "decoded-no-ownership-markers" for row in files):
        raise ValueError("ambiguous statement in reviewed nested archive")
    return {"status": "complete-reviewed-nested-archive-no-ownership-statement",
        "decoding_observation_sha256": proof_hash, "format": proof["format"], "files": files,
        "decoding_observation": proof,
        "meaning": "Exact complete decoder observation, with all nested members and zero padding rechecked. Not an arbitrary compressed-file exemption or a package approval."}


def inspect_member(name, value):
    row = {"path": name, "size": len(value), "sha256": digest(value)}
    if row["sha256"] in REVIEWED_CERTIFICATES:
        return {**row, **inspect_certificate(value, MARKERS)}
    if row["sha256"] == "54303491a8418fbed24344b513546182c29b43bf282ceb433af65e2299f9271f":
        return {**row, **inspect_reviewed_conda(value)}
    reviewed = REVIEWED_BINARY_RECORDS.get(row["sha256"])
    if reviewed is not None:
        parts = reviewed["parts"]
        if (len(value) != reviewed["size"] or parts[0][0] != 0 or parts[-1][1] != len(value)
                or any(left[1] != right[0] for left, right in zip(parts, parts[1:]))):
            raise ValueError("incomplete reviewed binary byte coverage")
        return {**row, "status": "complete-reviewed-binary-record-no-ownership-statement",
            "format": reviewed["format"],
            "reviewed_byte_ranges": [{"offset": start, "end_exclusive": end,
                "interpretation": description, "hex": value[start:end].hex()} for start, end, description in parts],
            "meaning": "Every byte belongs to the listed inspected format fields. None is a copyright statement. No unparsed member, data section, comment or trailer is ignored."}
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
                                   "complete-reviewed-document-no-ownership-statement",
                                   "complete-reviewed-binary-record-no-ownership-statement",
                                   "complete-reviewed-nested-archive-no-ownership-statement"} for row in files)
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
    files, seen, total, retained = [], set(), 0, {}
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
            files.append(inspect_member(member.name, value))
            if expected == "1e6853b52649d4ac5c0bd02320cddc5ba956bdb407c4b75a2c6b75bf51500f8c":
                retained[member.name] = value
    if retained:
        inspect_exact_fdeflate_fixtures(files, retained)
    return audit_result(files, expected)


def inspect_exact_fdeflate_fixtures(files, retained):
    """Retain complete fixture bytes; only a fully decoded positive case qualifies."""
    tests = {"fdeflate-0.3.7/src/decompress.rs": "26eea8e94c41422b29b50b83e8077ef8ee37e116f26fc810c15e7e7f0224bc5e",
             "fdeflate-0.3.7/src/decompress/tests/test_utils.rs": "220c8813c35240b1d0dbbb63051b3ec62838ea8f682f5389315c738d4bdff488"}
    if any(digest(retained[name]) != value for name, value in tests.items()):
        raise ValueError("fuzz fixture source context differs")
    for row in files:
        if not row["path"].endswith(".zz"):
            continue
        raw = retained[row["path"]]
        row["fixture_source_context"] = tests
        row["complete_input_hex"] = raw.hex()
        if row["sha256"] == "215d6eafcce032f917f0559c3f35e575fdfcccd5548df8fed5092bc70cf24812":
            decoder = zlib.decompressobj(-15)
            decoded = decoder.decompress(raw[2:], 1024)
            prefix = bytes.fromhex("0800a2ff4000fc92")
            pattern = bytes.fromhex("01007ca8ff00a2ff4000fc250106fc92")
            expected = prefix + pattern * 17 + b"\xe0"
            if (raw[:2] != b"\x78\xda" or not decoder.eof or decoder.unconsumed_tail
                    or decoder.unused_data != raw[-4:] or decoded != expected
                    or len(decoded) != 281 or zlib.adler32(decoded) != 751299):
                raise ValueError("reviewed numerical fuzz decoding differs")
            row.update(status="complete-reviewed-binary-record-no-ownership-statement",
                format="Exact zlib fuzz fixture with complete raw-DEFLATE output and deliberately ignored checksum",
                decoded_hex=decoded.hex(), decoded_sha256=digest(decoded),
                decoded_structure={"prefix_hex": prefix.hex(), "repeat_hex": pattern.hex(), "repeat_count": 17, "suffix_hex": "e0"},
                observed_adler32=zlib.adler32(decoded), retained_checksum_hex=raw[-4:].hex(),
                meaning="All compressed input is consumed except the explicit four-byte checksum. The complete output is the listed numerical byte pattern, not text or an ownership statement. Its length and Adler value equal the exact upstream assertions.")
        else:
            # A negative fixture's decoder rejection does not prove absence.
            # Preserve its complete bytes and the source's expected error, but
            # keep its undecoded status and the whole-archive NONE gate closed.
            row["documented_expected_result"] = "BadLiteralLengthHuffmanTree; the upstream test documents a missing end-of-block symbol."
            row["remaining_review"] = "The malformed input has no complete standard decompression. Exact numerical fuzz bytes and source context are retained; no copyright absence is inferred from decoder rejection."
