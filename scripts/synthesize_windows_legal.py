#!/usr/bin/env python3
"""Create reproducible, explicitly incomplete legal review packets from observations.

This preparer does not replace the approved bundle generator or its validators.
Metadata reachability is recorded separately from proof of shipped machine code.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import re
import subprocess
import struct
import sys
import tarfile
import tomllib
import zipfile

if __package__:
    from scripts.windows_runtime_evidence import retain_in_packet as retain_runtime_evidence
    from scripts.windows_crypto_producer import retain_in_packet as retain_upstream_crypto
    from scripts.inspect_legal_crate_sources import statements as original_statements
    from scripts.copyright_absence import audit_archive, audit_source_tree_zip, source_tree_zip
    from scripts.windows_legal_source_evidence import inspect_sources, classify_nested, nodriver_equality, map_python_native, map_wheel_native_sources, map_custom_native_sources, crate_grant_scope, crate_external_grant, complete_apache_reference, complete_mpl_reference, compare_certifi_source, tix_referenced_grant
    from scripts.validate_package_inputs import (
        CLOSURES, KINDS, REQUIRED_FILES, canonical_json, parse_json,
        profile_source_inputs, read_owned, relative_path, render_rtf, require,
        sha256_bytes, aggregate_files, validate_conclusion, PackageInputError, extracted_license_info,
    )
else:
    from windows_runtime_evidence import retain_in_packet as retain_runtime_evidence
    from windows_crypto_producer import retain_in_packet as retain_upstream_crypto
    from inspect_legal_crate_sources import statements as original_statements
    from copyright_absence import audit_archive, audit_source_tree_zip, source_tree_zip
    from windows_legal_source_evidence import inspect_sources, classify_nested, nodriver_equality, map_python_native, map_wheel_native_sources, map_custom_native_sources, crate_grant_scope, crate_external_grant, complete_apache_reference, complete_mpl_reference, compare_certifi_source, tix_referenced_grant
    from validate_package_inputs import (
        CLOSURES, KINDS, REQUIRED_FILES, canonical_json, parse_json,
        profile_source_inputs, read_owned, relative_path, render_rtf, require,
        sha256_bytes, aggregate_files, validate_conclusion, PackageInputError, extracted_license_info,
    )


ARCHITECTURES = {"x64": "x86_64", "arm64": "aarch64"}
BOUNDARY = {"status": "draft", "candidate_approval": False, "publishable": False}
SOURCE_ARCHIVES = {
    "wheel-nodriver-0.50.3": ("nodriver-0.50.3.tar.gz", "24ca688d8646ef8ffad5c8ce65804e5e7671a779ad26a24d76f6465d5666c631"),
    "native-wix": ("wix-b8977d6.tar.gz", "aef765da7c8051919081235840a8fca10e6bc4f37aab83764a80974ffd1fe09b"),
}
FONT_ARCHIVE = "epaint_default_fonts-0.36.1.crate"
FONT_SHA256 = "18dee69613aac468922cf28a32025eb7d7ed6985b61f73245848e58f37876c98"
OBSERVATION_SHA256 = {
    "x64": "f55b7981dc530209017b0a69bacd0a0d9f7d395052cf51b2eca04b953ee43bc8",
    "arm64": "3a744f4d9c1a700804f46ff8d7e02f90c611178045c5756a6f9def20834e98ae",
}
MIT_GRANT = '''Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.'''
MIT_ZERO_GRANT = MIT_GRANT.replace(
    'furnished to do so, subject to the following conditions:\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.',
    'furnished to do so.')
SQLITE_BLESSING = '''The author disclaims copyright to this source code. In place of
a legal notice, here is a blessing:
May you do good and not evil.
May you find forgiveness for yourself and forgive others.
May you share freely, never taking more than you give.'''


def declared_expression(declared):
    """Preserve upstream alternatives; prose stays in the evidence, not SPDX syntax."""
    if isinstance(declared, list) and len(declared) == 1:
        declared = declared[0]
        if isinstance(declared, dict):
            declared = declared.get("expression")
    if not isinstance(declared, str):
        return None
    value = re.sub(r"\s*/\s*", " OR ", declared).strip()
    try:
        validate_conclusion(re.sub(r"\bOR\b", "AND", value))
    except PackageInputError:
        return None
    return value


def license_choice(declared, available=None):
    """Select an explicit permissive alternative, never discard an AND or exception."""
    if isinstance(declared, list) and len(declared) == 1:
        declared = declared[0]
        if isinstance(declared, dict):
            declared = declared.get("expression")
    if not isinstance(declared, str):
        return None
    expression = re.sub(r"\s*/\s*", " OR ", declared)
    # Reduce explicit parenthesized alternatives without removing a conjunction.
    def choose_group(match):
        selected = license_choice(match.group(1), available)
        return "(" + selected + ")" if selected else match.group(0)
    previous = None
    while previous != expression:
        previous = expression
        expression = re.sub(r"\(([^()]+ OR [^()]+)\)", choose_group, expression)
    if "AND" not in expression and "(" not in expression and ")" not in expression:
        alternatives = expression.split(" OR ")
        for choice in ("Apache-2.0", "MIT", "BSD-3-Clause", "ISC", "CC0-1.0", "MIT-0"):
            if choice in alternatives and (available is None or choice in available):
                expression = choice
                break
    try:
        validate_conclusion(expression)
    except PackageInputError:
        return None
    return expression


def font_copyright(data):
    """Read original copyright strings from a TrueType name table, without editing it."""
    count = struct.unpack_from(">H", data, 4)[0]
    tables = {data[12 + i * 16:16 + i * 16]: struct.unpack_from(">II", data, 20 + i * 16)
              for i in range(count)}
    offset, size = tables[b"name"]
    require(offset + size <= len(data), "font name table is truncated")
    _, count, strings = struct.unpack_from(">HHH", data, offset)
    result = set()
    for index in range(count):
        platform, _, _, name_id, length, start = struct.unpack_from(">HHHHHH", data, offset + 6 + index * 12)
        if name_id != 0:
            continue
        require(strings + start + length <= size, "font name string is truncated")
        raw = data[offset + strings + start:offset + strings + start + length]
        result.add(raw.decode("utf-16-be" if platform in (0, 3) else "mac_roman").strip())
    return "\n".join(sorted(result))


def license_atoms(data):
    """Recognize only distinctive complete grant text in the retained original file."""
    text = data.decode("utf-8", errors="replace")
    text = re.sub(r"(?m)^\s*//\s?", "", text)
    text = text.replace("``", '"').replace("''", '"').replace("\u201c", '"').replace("\u201d", '"')
    folded = " ".join(text.lower().split())
    result = set()
    if sha256_bytes(data) == "e271993808fec50ab29350b39539cdec611a9103f827e0aa26d61da70e2d33f8":
        result.add("CDLA-Permissive-2.0")
    if " ".join(SQLITE_BLESSING.lower().split()) in folded:
        result.add("blessing")
    if all(part in folded for part in ("the authors hereby grant permission to use, copy, modify, distribute, and license",
            "this notice is included verbatim in any distributions", "no written agreement, license, or royalty fee",
            "new terms are clearly indicated on the first page of each file",
            "in no event shall the authors or distributors be liable", "derivatives thereof",
            "the authors and distributors specifically disclaim any warranties",
            "no obligation to provide maintenance, support, updates, enhancements, or modifications",
            "government use", "restricted rights", "notwithstanding the foregoing",
            "permission to use and distribute the software in accordance with the terms specified in this license")):
        result.add("TCL")
    if all(part in folded for part in ("apache license", "version 2.0", "1. definitions", "2. grant of copyright license",
            "3. grant of patent license", "4. redistribution", "5. submission of contributions", "6. trademarks",
            "7. disclaimer of warranty", "8. limitation of liability", "9. accepting warranty", "end of terms and conditions")):
        result.add("Apache-2.0")
    if " ".join(MIT_GRANT.lower().split()) in folded:
        result.add("MIT")
    if " ".join(MIT_ZERO_GRANT.lower().split()) in folded:
        result.add("MIT-0")
    if all(part in folded for part in ("cc0 1.0 universal", "statement of purpose",
            "1. copyright and related rights", "2. waiver", "3. public license fallback",
            "4. limitations and disclaimers", "no trademark or patent rights held by affirmer",
            "creative commons is not a party to this document")):
        result.add("CC0-1.0")
    isc = folded.replace("and/or distribute", "and distribute").replace("authors disclaim", "author disclaims")
    if all(part in isc for part in ("permission to use, copy, modify, and distribute this software for any purpose with or without fee",
                                    "copyright notice and this permission notice appear in all copies",
                                    "disclaims all warranties", "in no event shall", "loss of use, data or profits",
                                    "whether in an action of contract", "use or performance of this software")):
        result.add("ISC")
    if all(part in isc for part in ("permission to use, copy, modify, and distribute this software for any purpose with or without fee is hereby granted.",
                                    "disclaims all warranties", "in no event shall", "loss of use, data or profits",
                                    "whether in an action of contract", "use or performance of this software")):
        result.add("0BSD")
    if all(part in folded for part in ("redistribution and use in source and binary forms", "this software is provided",
                                      "the origin of this software must not be misrepresented", "altered source versions must be plainly marked",
                                      "the name of the author may not be used to endorse or promote", "julian seward", "bzip2",
                                      "1. redistributions", "2. the origin", "3. altered source", "4. the name",
                                      "even if advised of the possibility of such damage")):
        result.add("bzip2-1.0.6")
    if all(part in folded for part in ("mit-cmu", "by obtaining, using, and/or copying this software",
            "permission to use, copy, modify and distribute", "both that copyright notice and this permission notice",
            "not be used in advertising or publicity", "without specific, written prior permission",
            "disclaims all warranties", "in no event shall", "loss of use, data or profits", "performance of this software")):
        result.add("MIT-CMU")
    if (any(header in folded for header in ("python software foundation license version 2", "psf license agreement for python 2.2"))
            and all(part in folded for part in ("psf hereby grants licensee",
            "brief summary of the changes", "psf makes no representations or warranties", "psf shall not be liable",
            "automatically terminate upon a material breach", "does not grant permission to use psf trademarks",
            "by copying, installing or otherwise using"))):
        result.add("PSF-2.0")
        if all(part in folded for part in ("beopen python open source license agreement version 1",
                "beopen hereby grants licensee", "beopen shall not be liable", "cnri", "license agreement for python",
                "cnri hereby grants licensee", "cnri shall not be liable", "cwi license agreement",
                "stichting mathematisch centrum", "permission to use, copy, modify, and distribute",
                "stichting mathematisch centrum disclaims all warranties")):
            result.add("Python-2.0")
    if all(part in folded for part in ("llvm exceptions to the apache 2.0 license", "as an exception",
            "embedded portions", "without complying", "sections 4(a), 4(b) and 4(d)", "gplv2",
            "retroactively and prospectively", "only with respect to the combined software")):
        result.add("LLVM-exception")
    if all(part in folded for part in ("permission to use, copy, modify, and distribute this software and its documentation",
            "for any purpose and without fee is hereby granted", "copyright notice appear in all copies",
            "both that copyright notice and this permission notice appear in supporting documentation",
            "disclaims all warranties", "in no event shall", "whether in an action of contract",
            "performance of this software")):
        result.add("HPND")
    if all(part in folded for part in ("unicode license v3", "permission is hereby granted", "deal in the data files",
            "copyright and permission notice appear", "provided \"as is\"", "shall not be used in advertising")):
        result.add("Unicode-3.0")
    if all(part in folded for part in ("unicode, inc. license agreement - data files and software",
            "permission is hereby granted, free of charge", "either (a) this copyright and permission notice",
            "(b) this copyright and permission notice appear in associated documentation",
            "noninfringement of third party rights", "in no event shall the copyright holder",
            "shall not be used in advertising", "written authorization of the copyright holder")):
        result.add("Unicode-DFS-2016")
    if all(part in folded for part in ("sil open font license", "version 1.1", "permission & conditions",
            "font software", "reserved font name", "termination", "disclaimer")):
        result.add("OFL-1.1")
    if all(part in folded for part in ("ubuntu font licence", "version 1.0", "permission & conditions",
            "termination", "disclaimer", "font software")):
        result.add("Ubuntu-font-1.0")
    if all(part in folded for part in ("bitstream vera", "permission is hereby granted", "font software",
            "the above copyright and trademark notices", "not containing either the words", "bitstream", "vera",
            "font software may be sold", "font software is provided", "without warranty of any kind")):
        result.add("Bitstream-Vera")
    if all(part in folded for part in ("microsoft reciprocal license", "1. definitions", "2. grant of rights",
            "3. conditions and limitations", "reciprocal grants", "no trademark license", "patent claim",
            "retain all copyright", "complete copy of this license", "licensed \"as-is")):
        result.add("MS-RL")
    bsd_complete = all(part in folded for part in (
        "redistribution and use in source and binary forms", "with or without modification",
        "are permitted provided that", "this list of conditions and the following disclaimer",
        "documentation and/or other materials provided with the distribution", "this software is provided",
        "express or implied warranties", "merchantability and fitness for a particular purpose",
        "are disclaimed", "direct, indirect, incidental, special", "procurement of substitute goods or services",
        "however caused and on any theory of liability", "strict liability", "including negligence or otherwise",
        "even if advised of the possibility of such damage"))
    if bsd_complete:
        if ("neither the name" in folded or "neither name" in folded) and all(part in folded for part in ("redistributions of source code must retain",
                "redistributions in binary form must reproduce", "in no event shall", "business interruption")):
            result.add("BSD-3-Clause")
        elif ("neither" not in folded and "redistributions of source code must retain" in folded
              and "redistributions in binary form must reproduce" in folded
              and "in no event shall" in folded and "loss of use, data, or profits" in folded):
            result.add("BSD-2-Clause")
    if all(part in folded for part in ("mozilla public license", "version 2.0", "1. definitions",
                                      "2. license grants and conditions", "3. responsibilities",
                                      "10. versions of the license", "exhibit b")):
        result.add("MPL-2.0")
    if all(part in folded for part in ("gnu affero general public license", "version 3, 19 november 2007",
                                      "13. remote network interaction", "16. limitation of liability",
                                      "end of terms and conditions")):
        result.add("AGPL-3.0-only")
    if all(part in folded for part in ("gnu general public license", "version 2, june 1991",
            "0. this license applies", "1. you may copy", "2. you may modify", "3. you may copy",
            "4. you may not copy", "5. you are not required", "6. each time you redistribute",
            "11. because the program", "12. in no event", "end of terms and conditions")):
        result.update({"GPL-2.0-only", "GPL-2.0-or-later"})
    if all(part in folded for part in ("bootloader exception", "unlimited permission to link or embed compiled bootloader",
            "without any restriction coming from the use of those files", "modification of the files",
            "not linked into a combined executable")):
        result.add("Bootloader-exception")
    if all(part in folded for part in ("gnu lesser general public license", "version 2.1, february 1999",
            "0. this license agreement applies", "1. you may copy", "2. you may modify", "3. you may opt",
            "4. you may copy", "5. a program", "6. as an exception", "15. because the library",
            "16. in no event", "end of terms and conditions")):
        result.update({"LGPL-2.1-only", "LGPL-2.1-or-later"})
    if "boost software license" in folded and "version 1.0" in folded:
        result.add("BSL-1.0")
    if "this software is provided 'as-is'" in folded and "altered source versions must be plainly marked" in folded:
        result.add("Zlib")
    return result


def copyright_lines(sources):
    result = set()
    for _, data in sources:
        result.update(statement["text"] for statement in original_statements(data.decode("utf-8", errors="replace")))
        text = " ".join(data.decode("utf-8", errors="replace").split())
        if "blessing" in license_atoms(data):
            result.add("The author disclaims copyright to this source code.")
        match = re.search(r"This software is copyrighted by (.+?)\.\s+The following terms apply", text)
        if match:
            result.add("This software is copyrighted by " + match.group(1) + ".")
    return "\n".join(sorted(result)) or "NOASSERTION"


def document(root, name):
    return parse_json(read_owned(root, name))


def slug(value):
    return re.sub(r"[^A-Za-z0-9.-]", "-", value)


def cargo_scopes(metadata):
    """Traverse target-filtered normal edges, separating proc macros/build/dev edges.

    A normal dependency is a linkage candidate, not a binary-symbol observation.
    Dependencies reached in multiple contexts retain every context.
    """
    packages = {row["id"]: row for row in metadata["packages"]}
    nodes = {row["id"]: row for row in metadata["resolve"]["nodes"]}
    root = metadata["resolve"]["root"]
    require(root in nodes and root in packages, "Cargo root is missing")
    found = defaultdict(set)
    queue = deque([(root, "target-normal")])
    while queue:
        identifier, context = queue.popleft()
        if context in found[identifier]:
            continue
        require(identifier in packages and identifier in nodes, "Cargo dependency is missing")
        found[identifier].add(context)
        for dep in nodes[identifier]["deps"]:
            child = packages[dep["pkg"]]
            macro = any("proc-macro" in target["kind"] for target in child["targets"])
            for edge in dep["dep_kinds"]:
                kind = edge["kind"]
                next_context = ("development" if kind == "dev" else
                                "build-or-generated-code" if kind == "build" or macro else context)
                if context == "development":
                    next_context = context
                elif context == "build-or-generated-code" and kind != "dev":
                    next_context = context
                queue.append((dep["pkg"], next_context))
    return {key: sorted(value) for key, value in sorted(found.items())}


def checked_sources(root, rows):
    result = []
    for row in rows:
        data = read_owned(root, row["path"])
        require(sha256_bytes(data) == row["sha256"], "source notice hash differs")
        result.append((row["path"], data))
    return result


def wheel_metadata(raw):
    """Read metadata/notices without extracting or executing a wheel."""
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(name.casefold() for name in names)), "wheel members alias")
        for name in names:
            relative_path(name.rstrip("/"))
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        require(len(metadata) == 1, "wheel metadata is ambiguous")
        message = BytesParser(policy=policy.default).parsebytes(archive.read(metadata[0]))
        notices = []
        sboms = []
        for name in sorted(names):
            base = name.rsplit("/", 1)[-1].lower()
            if name.endswith("/"):
                continue
            if any(word in base for word in ("license", "copying", "notice", "authors")):
                require(archive.getinfo(name).file_size <= 8 * 1024 * 1024, "notice is oversized")
                notices.append((name, archive.read(name)))
            if base.endswith(".json") and ("sbom" in name.lower() or "cyclonedx" in name.lower()):
                require(archive.getinfo(name).file_size <= 16 * 1024 * 1024, "SBOM is oversized")
                sboms.append((name, archive.read(name)))
        declared = message.get("License-Expression") or message.get("License")
        return message, declared, notices, sboms


class Packet:
    def __init__(self):
        self.files = {}
        self.components = []
        self.evidence = []
        self.pending = []

    def put(self, name, data):
        relative_path(name)
        require(name not in self.files or self.files[name] == data, "output path collision")
        self.files[name] = data

    def component(self, *, identifier, name, version, kind, digest, location,
                  declared, sources, scope, pending, origins=None, custom_grants=None):
        require(not any(row["id"] == identifier for row in self.components), "duplicate component")
        notices = []
        for index, (source_name, data) in enumerate(sources):
            target = f"legal/NOTICES/{identifier}/{index:03}-{slug(Path(source_name).name)}"
            self.put(target, data)
            notices.append({"path": target, "sha256": sha256_bytes(data)})
        # No choice of license, copyright ownership or source duty is inferred from a name.
        row = {"id": identifier, "name": name, "version": version, "kind": kind,
               "sha256": digest, "download_location": location,
               "copyright_text": copyright_lines(sources), "license_declared": (declared_expression(declared) or (declared if isinstance(declared, str)
                   else json.dumps(declared, sort_keys=True) if declared else "NOASSERTION")),
               "license_concluded": "NOASSERTION", "license_files": [],
               "notice_required": None, "notice_files": notices,
               "source_offer_required": None, "source_offer_files": []}
        grants = set().union(*(license_atoms(raw) for _, raw in sources))
        custom_grants = custom_grants or {}
        for grant_id, grant_digest in custom_grants.items():
            require(grant_id.startswith("LicenseRef-") and grant_id.endswith("-" + grant_digest)
                    and any(sha256_bytes(raw) == grant_digest for _, raw in sources), "custom source grant differs")
        grants.update(custom_grants)
        inferred = declared_expression(declared)
        python_scope = (inferred in {"Python-2.0", "PSF-2.0"}
            and grants == {"Python-2.0", "PSF-2.0", "HPND", "0BSD"}
            and any(b"ZERO-CLAUSE BSD LICENSE FOR CODE IN THE PYTHON DOCUMENTATION" in raw for _, raw in sources))
        if python_scope:
            inferred = "Python-2.0 AND 0BSD"
        inferable_grants = grants - {"PSF-2.0", "HPND"} if "Python-2.0" in grants else grants
        if inferred is None and len(inferable_grants) == 1 and (declared is None or isinstance(declared, str)
                                                      and len(declared) > 150):
            inferred = next(iter(inferable_grants))
            row["license_declared"] = inferred
        if inferred is None and declared in ("BSD 3-clause",):
            inferred = "BSD-3-Clause"
            row["license_declared"] = inferred
        selected = license_choice(inferred or declared, grants)
        if selected:
            atoms = set(re.findall(r"[A-Za-z0-9.-]+", selected)) - {"AND", "WITH"}
            covered = set()
            for index, (source_name, data) in enumerate(sources):
                ids = license_atoms(data) & atoms
                ids |= {identifier for identifier, digest in custom_grants.items() if sha256_bytes(data) == digest} & atoms
                if not ids:
                    continue
                target = f"legal/LICENSES/{identifier}/{index:03}-{slug(Path(source_name).name)}"
                self.put(target, data)
                row["license_files"].append({"path": target, "sha256": sha256_bytes(data), "license_ids": sorted(ids)})
                covered.update(ids)
            if covered == atoms:
                row["license_concluded"] = selected
                row["copyright_text"] = copyright_lines(sources)
                row["notice_required"] = True
                if not any(atom.startswith("LicenseRef-") for atom in atoms) and not atoms & {
                        "AGPL-3.0-only", "AGPL-3.0-or-later", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
                        "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later", "MPL-2.0", "MS-RL"}:
                    row["source_offer_required"] = False
                    pending = [item for item in pending if item != "notice-and-source-duty"]
                if row["copyright_text"] != "NOASSERTION":
                    pending = [item for item in pending if item != "license-choice-and-original-copyright"]
                declared_atoms = set(re.findall(r"[A-Za-z0-9.-]+", inferred or ""))
                if "Python-2.0" in declared_atoms:
                    declared_atoms.update({"PSF-2.0", "HPND"})
                # A complete GNU version text can support either declared
                # version suffix; it does not add a second scope by itself.
                for family in ("GPL-2.0", "LGPL-2.1"):
                    if declared_atoms & {family + "-only", family + "-or-later"}:
                        declared_atoms.update({family + "-only", family + "-or-later"})
                if grants - declared_atoms:
                    pending = [*pending, "additional-retained-grant-scope"]
        self.components.append(row)
        self.evidence.append({"id": identifier, "scope": scope, "origins": origins or [], "original_license_declaration": declared,
                              "retained_notice_count": len(notices)})
        if python_scope:
            self.evidence[-1]["grant_scope_basis"] = (
                "Complete cumulative Python terms and the explicitly named documentation-code 0BSD grant are both retained. "
                "The original upstream declaration remains separate from this composite proposal.")
        self.pending.append({"id": identifier, "items": sorted(set(pending))})


def verify_observation(observation_root, source, architecture, binding=None):
    binding = binding or {"source_sha": "fa2d4a4cfae7e7eb44aa8c9fc4724a9f68842542",
        "trusted_sha": "519c73500c53dcae9011dff3c9424009aa0c2d5d", "run_id": 36313384412,
        "observations": {arch: {"sha256": digest, "target": ARCHITECTURES[arch] + "-pc-windows-msvc"}
                         for arch, digest in OBSERVATION_SHA256.items()}}
    require(sha256_bytes(read_owned(observation_root, "preparation-observation.json"))
            == binding["observations"][architecture]["sha256"], "retained observation identity differs")
    observation = document(observation_root, "preparation-observation.json")
    require(observation["architecture"] == architecture
            and observation["status"] == "unapproved"
            and observation["candidate_approval"] is False
            and observation["publishable"] is False, "observation scope differs")
    profile = "windows-" + ARCHITECTURES[architecture]
    require(observation["release_profile"] == profile, "observation profile differs")
    require(observation["target"] == ARCHITECTURES[architecture] + "-pc-windows-msvc"
            and observation["target"] == binding["observations"][architecture]["target"]
            and observation["source"]["source_sha"] == binding["source_sha"]
            and observation["source"]["trusted_sha"] == binding["trusted_sha"]
            and observation["source"]["run_id"] == binding["run_id"],
            "observation target or producer differs")
    inputs = observation_root / "unsigned-inputs"
    actual = {path.relative_to(inputs).as_posix() for path in inputs.rglob("*") if path.is_file()}
    require(actual == set(observation["files"]), "observation file set differs")
    for name, record in observation["files"].items():
        raw = read_owned(inputs, name)
        require(len(raw) == record["size"] and sha256_bytes(raw) == record["sha256"],
                "observed file bytes differ")
    require(document(inputs, "preparation-source.json") == observation["source"], "preparation source record differs")
    source_inventory = document(observation_root / "source", "source-inventory.json")
    require(sha256_bytes(read_owned(observation_root / "source", "source-inventory.json"))
            == observation["source_files"]["source-inventory.json"]["sha256"], "source observation inventory changed")
    require(source_inventory["source_sha"] == observation["source"]["source_sha"], "source record differs")
    bindings = {}
    for name in sorted(profile_source_inputs(profile)):
        digest = sha256_bytes(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=source))
        require(digest == source_inventory["files"][name]["sha256"], "source input changed after observation")
        bindings[name] = digest
    payload = read_owned(inputs, "payload/lib/cua/payload.json")
    require(sha256_bytes(payload) == observation["payload_sha256"], "payload observation differs")
    require(sha256_bytes(read_owned(inputs, "payload/lib/cua/installed-inventory.json"))
            == observation["installed_inventory_sha256"], "installed inventory observation differs")
    return observation, inputs, bindings


def add_cargo(packet, inputs, source, target_collection):
    evidence = {row["id"]: row for row in target_collection["components"]}
    lock = tomllib.loads(read_owned(source, "Cargo.lock").decode())
    checksums = {(row["name"], row["version"]): row.get("checksum") for row in lock["package"]}
    scopes = defaultdict(set)
    identities = {}
    graphs = {}
    for filename in ("cargo-metadata.json", "ba-cargo-metadata.json"):
        metadata = document(inputs, filename)
        graph = cargo_scopes(metadata)
        graphs[filename] = graph
        for row in metadata["packages"]:
            key = (row["name"], row["version"])
            if row["id"] in graph:
                scopes[key].update(graph[row["id"]])
                identities[key] = row
    for key, contexts in sorted(scopes.items()):
        row = identities[key]
        identifier = "cargo-" + row["name"] + "-" + row["version"]
        # Build and proc-macro inputs remain visible in the graph, but are not
        # silently promoted to shipped components or treated as obligation-free.
        if "target-normal" not in contexts or row["source"] is None:
            continue
        prior = evidence.get(identifier)
        sources = checked_sources(source / target_collection["_root"], prior["source_files"]) if prior else []
        require(checksums.get(key), "Cargo archive checksum is unavailable")
        if prior:
            require(prior["sha256"] == checksums[key], "Cargo source archive changed")
        packet.component(identifier=slug(identifier), name=row["name"], version=row["version"],
                         kind="cargo", digest=checksums[key],
                         location=f"https://static.crates.io/crates/{row['name']}/{row['name']}-{row['version']}.crate",
                         declared=row["license"], sources=sources, scope="target-normal-dependency",
                         pending=["license-choice-and-original-copyright", "notice-and-source-duty"], origins=sorted(contexts))
    packet.put("cargo-scope.json", canonical_json({
        "schema": 1, **BOUNDARY, "graphs": graphs,
        "limitation": "Target-filtered dependency reachability is not a linker map. Build and proc-macro outputs need a generated-code review.",
    }))


def add_wheels(packet, inputs, source, target_collection):
    prior = {(row["name"].lower().replace("_", "-"), row["version"]): row
             for row in target_collection["components"] if row["kind"] == "wheel"}
    wheelhouse = document(inputs, "wheelhouse/wheelhouse.json")
    for wheel in wheelhouse["wheels"]:
        raw = read_owned(inputs, "wheelhouse/" + wheel["filename"])
        require(sha256_bytes(raw) == wheel["sha256"] and len(raw) == wheel["size"], "wheel identity differs")
        metadata, declared, notices, sboms = wheel_metadata(raw)
        raw_declared = declared
        name = metadata["Name"].lower().replace("_", "-")
        require(name == wheel["name"].lower().replace("_", "-") and metadata["Version"] == wheel["version"],
                "wheel metadata identity differs")
        old = prior.get((name, wheel["version"]))
        location = old["download_location"] if old and old["sha256"] == wheel["sha256"] else (
            "https://github.com/MONTBRAIN/vadgr-computer-use/actions/runs/"
            + str(document(source, "packaging/cua/cua-profile-catalog.json")["producer"]["run_id"])) if name == "vadgr-computer-use" else None
        if location is None:
            native = document(source, "packaging/cua/native-wheel-manifest.json")
            matched = [row for row in native["wheels"] if row["sha256"] == wheel["sha256"]
                       and row["filename"] == wheel["filename"] and row["target"] == wheelhouse["release_profile"]]
            require(len(matched) == 1, "native wheel acquisition provenance is unavailable")
            location = f"https://github.com/{native['repository']}/actions/runs/{native['run_id']}"
        require(location is not None, "wheel acquisition provenance is unavailable")
        identifier = slug("wheel-" + name + "-" + wheel["version"])
        issues = ["license-choice-and-original-copyright", "notice-and-source-duty"]
        if name == "nodriver":
            require("AGPL-3.0-only" in set().union(*(license_atoms(data) for _, data in notices)),
                    "nodriver full AGPL grant is absent")
            # Exact source headers reference this bundled version, not a later-version option.
            declared = "AGPL-3.0-only"
            issues += ["AGPL-corresponding-source-and-combined-work-review"]
        if sboms:
            issues += ["target-specific-nested-SBOM-scope"]
        if name == "pywin32":
            declared = pywin32_grant_scope(notices)
        packet.component(identifier=identifier, name=name, version=wheel["version"], kind="wheel",
                         digest=wheel["sha256"], location=location, declared=declared,
                         sources=notices, scope="installed-wheel", pending=issues)
        packet.evidence[-1]["original_license_declaration"] = raw_declared
        if name == "pywin32":
            packet.components[-1]["license_declared"] = raw_declared
            packet.evidence[-1]["grant_scope_basis"] = (
                "Composite wheel proposal retains the directory grants, IDLE's cumulative Python license, Scintilla's permission, "
                "the explicitly named Microsoft MAPI MIT grant and the separately inventoried adodbapi LGPL source. No single license replaces the others.")
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            native = {}
            for member in archive.namelist():
                if Path(member).suffix.lower() not in (".exe", ".dll", ".pyd"):
                    continue
                value = archive.read(member)
                candidates = [path for path in (inputs / "payload/lib/cua/environments").rglob(Path(member).name)
                              if path.is_file() and path.as_posix().endswith("/site-packages/" + member)]
                require(len(candidates) == 1 and read_owned(inputs, candidates[0].relative_to(inputs).as_posix()) == value,
                        "installed native wheel member differs")
                native[candidates[0].relative_to(inputs).as_posix()] = sha256_bytes(value)
            packet.evidence[-1]["observed_native_members"] = native
            source_claims = []
            for member in sorted(archive.namelist()):
                if member.endswith("/") or Path(member).suffix.lower() not in {".py", ".pyi", ".c", ".h", ".rs"}:
                    continue
                value = archive.read(member)
                claims = original_statements(value.decode("utf-8", errors="replace"))
                if claims:
                    source_claims.append({"path": member, "sha256": sha256_bytes(value), "statements": claims})
            add_original_claims(packet, identifier, source_claims)
        for index, (member, data) in enumerate(sboms):
            path = f"nested-sboms/{identifier}/{index:03}-{slug(Path(member).name)}"
            packet.put(path, data)
        if name == "pywin32":
            add_adodbapi(packet, raw, identifier, location)
            parent = next(row for row in packet.components if row["id"] == identifier)
            child = packet.components[-1]
            parent["source_offer_required"] = True
            parent["source_offer_files"] = list(child["source_offer_files"])
            question = next(row for row in packet.pending if row["id"] == identifier)
            question["items"] = [item for item in question["items"] if item != "notice-and-source-duty"]


def pywin32_grant_scope(sources):
    grants = set().union(*(license_atoms(raw) for _, raw in sources))
    require(grants == {"BSD-3-Clause", "HPND", "MIT", "Python-2.0", "PSF-2.0", "LGPL-2.1-only", "LGPL-2.1-or-later"},
            "pywin32 composite grant catalogue differs")
    lgpl = [name for name, raw in sources if "LGPL-2.1-only" in license_atoms(raw)]
    require(lgpl and all(name.endswith("adodbapi/license.txt") for name in lgpl), "pywin32 additional LGPL scope is unmapped")
    notices = [raw for name, raw in sources if name.endswith("win32comext/mapi/NOTICE.md")]
    require(len(notices) == 1 and b"`mapi.pyd` and `exchange.pyd` include compiled code licensed under the MIT License" in notices[0],
            "pywin32 MAPI native grant scope differs")
    return "BSD-3-Clause AND HPND AND MIT AND Python-2.0 AND LGPL-2.1-or-later"


def add_original_claims(packet, identifier, claims):
    if not claims:
        return
    component = next(row for row in packet.components if row["id"] == identifier)
    evidence = next(row for row in packet.evidence if row["id"] == identifier)
    pending = next(row for row in packet.pending if row["id"] == identifier)
    raw = canonical_json({"component_sha256": component["sha256"], "original_statement_files": claims,
        "scope": "Original statements from exact retained source members; no exclusive ownership assertion."})
    path = f"legal/NOTICES/{identifier}/observed-source-copyright.json"
    packet.put(path, raw)
    component["notice_files"].append({"path": path, "sha256": sha256_bytes(raw)})
    statements = {item["text"] for row in claims for item in row["statements"]}
    if component["copyright_text"] != "NOASSERTION":
        statements.update(component["copyright_text"].splitlines())
    component["copyright_text"] = "\n".join(sorted(statements))
    evidence["original_source_statement_count"] = len(claims)
    if component["license_concluded"] != "NOASSERTION":
        pending["items"] = [item for item in pending["items"] if item != "license-choice-and-original-copyright"]


def add_adodbapi(packet, wheel_raw, parent_id, location):
    """Retain the shipped LGPL Python library separately from broad wheel metadata."""
    import io
    with zipfile.ZipFile(io.BytesIO(wheel_raw)) as wheel:
        members = {name: wheel.read(name) for name in sorted(wheel.namelist())
                   if name.startswith("adodbapi/") and not name.endswith("/")}
    require({"adodbapi/adodbapi.py", "adodbapi/license.txt", "adodbapi/setup.py"} <= members.keys(),
            "adodbapi source scope differs")
    header = members["adodbapi/adodbapi.py"].decode("utf-8")
    require("version 2.1" in header and "any later version" in header,
            "adodbapi later-version declaration differs")
    version = re.search(r'(?m)^__version__ = "([0-9.]+)"', header)
    require(version is not None, "adodbapi source version is missing")
    require("LGPL-2.1-or-later" in license_atoms(members["adodbapi/license.txt"]),
            "adodbapi complete license is missing")
    packed = io.BytesIO()
    with zipfile.ZipFile(packed, "w", compression=zipfile.ZIP_STORED) as output:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, raw)
    identifier = parent_id + "-adodbapi"
    raw = packed.getvalue()
    packet.component(identifier=identifier, name="adodbapi (shipped pywin32 subtree)",
        version=version.group(1), kind="wheel", digest=sha256_bytes(raw),
        location=location, declared="LGPL-2.1-or-later",
        sources=[("license.txt", members["adodbapi/license.txt"]),
                 ("adodbapi.py.txt", members["adodbapi/adodbapi.py"])],
        scope="exact-shipped-python-source-subtree", pending=["LGPL-source-delivery-review"])
    path = f"legal/SOURCE-OFFERS/{identifier}/adodbapi-shipped-source.zip"
    packet.put(path, raw)
    packet.components[-1]["source_offer_required"] = True
    packet.components[-1]["source_offer_files"] = [{"path": path, "sha256": sha256_bytes(raw)}]
    packet.evidence[-1].update(parent_component=parent_id,
        original_license_declaration="adodbapi/adodbapi.py: LGPL version 2.1 or any later version",
        members={name: {"size": len(value), "sha256": sha256_bytes(value)} for name, value in members.items()},
        source_delivery_boundary="Exact shipped Python source, license, setup and tests; no claim about other wheel native modules.")


def add_supplement(packet, source, collection, architecture, archive_root):
    root = source / "packaging/legal-review/supplement"
    supplement = document(root, "collection.json")
    # Preserve exact source evidence. Inclusion here is not a claim that every
    # optional component in an upstream build catalogue reaches the target.
    for row in supplement["groups"]["nested_wheels"]["registry_components"]:
        origins = [item for item in row["origins"] if item["target"] == "windows-" + ARCHITECTURES[architecture]]
        if not origins:
            continue
        packet.component(identifier="nested-" + slug(row["id"]), name=row["name"], version=row["version"],
                         kind="cargo", digest=row["sha256"], location=row["download_location"],
                         declared=row["license_declared"], sources=checked_sources(root, row["source_files"]),
                         scope="target-wheel-SBOM-component-not-link-proof", origins=origins,
                         pending=["nested-build-versus-linked-scope", "license-choice-and-original-copyright",
                                  "notice-and-source-duty"])
    native_notice_scopes = []
    for row in supplement["groups"]["native_sources"]["components"]:
        if row["id"] == ("tk-windows-bin-8614" if architecture == "x64" else "tk-windows-bin-8612"):
            continue
        source_files = row["source_files"]
        # These are exact source paths, not license-name heuristics. The root
        # source license is distinct from test fixtures, templates and unrelated
        # platform installers included in a complete upstream source archive.
        if row["id"] in {"wix", "cpython-3.12", "zlib"}:
            selected = []
            for entry in source_files:
                path = entry["upstream_path"].split("/", 1)[1]
                retained = (path == "LICENSE.TXT" if row["id"] == "wix" else
                            path in {"LICENSE", "Python/getcopyright.c"} if row["id"] == "cpython-3.12" else
                            path == "LICENSE")
                native_notice_scopes.append({"component": "native-" + row["id"], "archive_sha256": row["sha256"],
                    **entry, "scope": "root-source-license-or-copyright" if retained else
                    "separate-platform-build-tool-test-template-or-contrib-source-not-the-mapped-runtime-component"})
                if retained:
                    selected.append(entry)
            source_files = selected
        sources = checked_sources(root, source_files)
        if row["id"] == "sqlite":
            selected = []
            for entry, (name, raw) in zip(source_files, sources):
                retained = "blessing" in license_atoms(raw)
                native_notice_scopes.append({"component": "native-sqlite", "archive_sha256": row["sha256"],
                    **entry, "scope": "SQLite-source-copyright-disclaimer" if retained else "autosetup-build-tool-license"})
                if retained:
                    selected.append((name, raw))
                else:
                    require(b"autosetup - A build environment" in raw, "SQLite separate tool scope differs")
            require(len(selected) == 1, "SQLite exact disclaimer is missing")
            sources = selected
        if row["id"] in {"windows-libffi", "xz"}:
            combined = " ".join(b"\n".join(raw for _, raw in sources).decode("utf-8").split())
            if row["id"] == "windows-libffi":
                require("only used as tooling to assist with the building and testing of libffi" in combined
                        and "libffi is in no way derived from this code" in combined, "libffi tooling scope differs")
                excluded = {"LICENSE-BUILDTOOLS"}
            else:
                require("liblzma is under the BSD Zero Clause License (0BSD)" in combined
                        and "These files don't affect the licensing of the binaries being built" in combined,
                        "liblzma source scope differs")
                excluded = {"COPYING.GPLv2", "COPYING.GPLv3", "COPYING.LGPLv2.1", "license-check.sh"}
            retained_sources = []
            for entry, (name, raw) in zip(source_files, sources):
                retained = Path(entry["upstream_path"]).name not in excluded
                native_notice_scopes.append({"component": "native-" + row["id"], "archive_sha256": row["sha256"],
                    **entry, "scope": "mapped-library-runtime" if retained else "upstream-explicit-build-tool-or-command-line-scope"})
                if retained:
                    retained_sources.append((name, raw))
            sources = retained_sources
        declared = row["license_declared"]
        if row["id"] in {"wix", "cryptography-openssl", "windows-libffi"}:
            grants = license_atoms(sources[0][1])
            require(len(grants) == 1, "primary native grant is ambiguous")
            declared = next(iter(grants))
        if row["id"] == "cryptography":
            require(b"*either*" in sources[0][1] and b"LICENSE.APACHE or LICENSE.BSD" in sources[0][1],
                    "cryptography source alternatives differ")
            declared = "Apache-2.0 OR BSD-3-Clause"
        if row["id"] == "cpython-3.12":
            require("Python-2.0" in set().union(*(license_atoms(raw) for _, raw in sources)), "complete Python license is absent")
            declared = "Python-2.0"
        if row["id"] == "sqlite":
            declared = "blessing"
        tix_grant = None
        custom_grants = {}
        if row["id"].startswith("tk-windows-bin-"):
            require(all("TCL" in license_atoms(raw) for _, raw in sources), "Tcl/Tk component terms need additional scope")
            declared = "TCL"
            tix_grant = tix_referenced_grant(sources, archive_root)
            if tix_grant:
                grant, grant_id, proof = tix_grant
                sources.append(grant)
                custom_grants[grant_id] = sha256_bytes(grant[1])
                declared += " AND " + grant_id
        packet.component(identifier="native-" + slug(row["id"]), name=row["name"], version=row["version"],
                         kind="framework" if row["id"] == "wix" else "runtime", digest=row["sha256"],
                         location=row["download_location"], declared=declared,
                         sources=sources, custom_grants=custom_grants, scope="source-build-input-needs-binary-mapping",
                         pending=["target-binary-to-source-mapping", "license-choice-and-original-copyright",
                                  "corresponding-source-delivery" if row["id"] == "wix" else "notice-and-source-duty"])
        if tix_grant:
            component = packet.components[-1]
            component["license_declared"] = row["license_declared"] or "NOASSERTION"
            packet.evidence[-1]["original_license_declaration"] = row["license_declared"]
            path = "legal/NOTICES/" + component["id"] + "/referenced-grant-provenance.json"
            data = canonical_json(proof)
            packet.put(path, data)
            component["notice_files"].append({"path": path, "sha256": sha256_bytes(data)})
            packet.pending[-1]["items"].append("nonstandard-government-rights-and-source-duty-review")
            packet.evidence[-1]["grant_scope_basis"] = proof["scope"] + " " + proof["limitation"]
    packet.put("native-source-notice-scope.json", canonical_json({"schema": 1, **BOUNDARY,
        "files": native_notice_scopes,
        "limitation": "Excluded source notices remain in the pinned upstream archives and acquisition evidence. Runtime redistribution terms of separately bundled Microsoft code are not waived by this classification."}))
    for row in collection["components"]:
        if row["kind"] not in ("runtime", "framework"):
            continue
        packet.component(identifier=slug(row["id"]), name=row["name"], version=row["version"], kind=row["kind"],
                         digest=row["sha256"], location=row["download_location"], declared=row["license_declared"],
                         sources=checked_sources(source / collection["_root"], row["source_files"]),
                         scope="runtime-archive" if row["kind"] == "runtime" else "installer-build-framework",
                         pending=["target-binary-to-source-mapping", "license-choice-and-original-copyright", "notice-and-source-duty"])


def add_observed_nested_crates(packet):
    """The actual wheel's pinned registry catalogue wins over older acquisition lists."""
    known = {(row["name"], row["version"]): row for row in packet.components if row["kind"] == "cargo"}
    for path, raw in sorted(packet.files.items()):
        if not path.startswith("nested-sboms/"):
            continue
        sbom = parse_json(raw)
        for row in sbom.get("components", []):
            if not row.get("purl", "").startswith("pkg:cargo/") or not row.get("bom-ref", "").startswith("registry+"):
                continue
            hashes = {entry["content"] for entry in row.get("hashes", []) if entry.get("alg") == "SHA-256"}
            require(len(hashes) == 1, "observed registry component hash is missing")
            digest = next(iter(hashes))
            require(re.fullmatch("[a-f0-9]{64}", digest) is not None, "observed registry component hash is invalid")
            key = (row["name"], row["version"])
            if key in known:
                require(known[key]["sha256"] == digest, "observed nested crate identity conflicts")
                continue
            name, version = key
            identifier = slug("nested-cargo-" + name + "-" + version)
            packet.component(identifier=identifier, name=name, version=version, kind="cargo", digest=digest,
                location=f"https://static.crates.io/crates/{name}/{name}-{version}.crate",
                declared=row.get("licenses"), sources=[], scope="target-wheel-SBOM-component-not-link-proof",
                pending=["nested-build-versus-linked-scope", "license-choice-and-original-copyright", "notice-and-source-duty"],
                origins=[{"path": path, "sha256": sha256_bytes(raw), "bom_ref": row["bom-ref"]}])
            known[key] = packet.components[-1]


def add_sqlite_source_scope(packet, archive_root):
    import io
    row = next(row for row in packet.components if row["id"] == "native-sqlite")
    filename = row["download_location"].rsplit("/", 1)[-1]
    raw = read_owned(archive_root, filename)
    require(sha256_bytes(raw) == row["sha256"], "SQLite source archive identity differs")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        name = filename.removesuffix(".tar.gz") + "/sqlite3.c"
        member = archive.getmember(name)
        require(member.isfile() and member.size <= 32 * 1024 * 1024, "SQLite amalgamation is absent or oversized")
        source = archive.extractfile(member).read()
    marker = source.index(b"The author disclaims copyright to this source code.")
    begin, end = source.rfind(b"/*", 0, marker), source.index(b"*/", marker) + 2
    require(0 <= begin < marker < end < 8192, "SQLite library header scope differs")
    header = source[begin:end]
    normalized = " ".join(re.sub(r"(?m)^\*\*\s?", "", header.decode("utf-8")).split())
    require(" ".join(SQLITE_BLESSING.split()) in normalized, "SQLite library disclaimer differs")
    path = "legal/NOTICES/native-sqlite/sqlite3-library-header.txt"
    packet.put(path, header)
    row["notice_files"].append({"path": path, "sha256": sha256_bytes(header)})
    evidence = next(item for item in packet.evidence if item["id"] == row["id"])
    evidence["grant_scope_basis"] = {"archive_sha256": row["sha256"], "source_member": name,
        "source_member_sha256": sha256_bytes(source), "header_byte_range": [begin, end],
        "header_sha256": sha256_bytes(header), "scope": "Actual core library amalgamation, not only the separate Tcl wrapper notice."}


def add_wix_source_mapping(packet, source, collection):
    from xml.etree import ElementTree
    records = []
    root = source / collection["_root"]
    for row in collection["components"]:
        if row["kind"] != "framework":
            continue
        specs = [(name, raw) for name, raw in checked_sources(root, row["source_files"]) if name.endswith(".nuspec")]
        require(len(specs) == 1, "WiX package source metadata is ambiguous")
        name, raw = specs[0]
        repository = [element for element in ElementTree.fromstring(raw).iter() if element.tag.endswith("}repository")]
        require(len(repository) == 1 and repository[0].attrib["commit"] == "b8977d6f88e7b68e000bac226a2814f236770570"
                and repository[0].attrib["url"] == "https://github.com/wixtoolset/wix", "WiX package source revision differs")
        records.append({"id": row["id"], "package_sha256": row["sha256"], "nuspec_path": name,
            "nuspec_sha256": sha256_bytes(raw), "source_commit": repository[0].attrib["commit"],
            "included_source_archive": "legal/SOURCE-OFFERS/" + SOURCE_ARCHIVES["native-wix"][0],
            "included_source_sha256": SOURCE_ARCHIVES["native-wix"][1],
            "scope": "build-package-source-revision-not-a-final-installer-runtime-membership-claim"})
    packet.put("wix-source-mapping.json", canonical_json({"schema": 1, **BOUNDARY, "packages": records,
        "remaining_artifact_evidence": "After installer assembly, enumerate actual Burn/BAL/Util runtime code and bind its member hashes to these source revisions; inspect any product modifications.",
        "remaining_owner_decision": "Official WiX build distribution terms and the actual legal/business facts required by OSMFEULA are not established by a source archive."}))


def add_archives_and_fonts(packet, inputs, archive_root):
    for identifier, (filename, expected) in SOURCE_ARCHIVES.items():
        raw = read_owned(archive_root, filename)
        require(sha256_bytes(raw) == expected, "corresponding source archive differs")
        path = "legal/SOURCE-OFFERS/" + filename
        packet.put(path, raw)
        component = next(row for row in packet.components if row["id"] == identifier)
        component["source_offer_required"] = True
        component["source_offer_files"] = [{"path": path, "sha256": expected}]
        if identifier == "wheel-nodriver-0.50.3":
            nodriver_equality(packet, inputs, raw)
        # This delivers the actual upstream source, not a promise or a mutable URL.
        # It does not establish completeness for an AGPL combined work or modified WiX code.
        issue = next(row for row in packet.pending if row["id"] == identifier)
        issue["items"] = [item for item in issue["items"] if item != "corresponding-source-delivery"]
        issue["items"].append("covered-combination-or-modification-source-completeness")
    raw = read_owned(archive_root, FONT_ARCHIVE)
    require(sha256_bytes(raw) == FONT_SHA256, "font crate differs")
    import io
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        binary = read_owned(inputs, "payload/vadgr.exe")
        for font, expression, license_name in (
                ("Hack-Regular", "MIT AND Bitstream-Vera", "Hack-Regular.txt"),
                ("NotoEmoji-Regular", "OFL-1.1", "OFL.txt"),
                ("Ubuntu-Light", "Ubuntu-font-1.0", "UFL.txt"),
                ("emoji-icon-font", "MIT", "emoji-icon-font-mit-license.txt")):
            member = f"epaint_default_fonts-0.36.1/fonts/{font}.ttf"
            data = archive.extractfile(member).read()
            require(data in binary, "font bytes are not present in observed daemon")
            license_member = f"epaint_default_fonts-0.36.1/fonts/{license_name}"
            notice = archive.extractfile(license_member).read()
            packet.component(identifier="asset-" + font, name=font, version="epaint_default_fonts-0.36.1",
                             kind="asset", digest=sha256_bytes(data),
                             location="https://static.crates.io/crates/epaint_default_fonts/epaint_default_fonts-0.36.1.crate",
                             declared=expression, sources=[(license_member, notice)],
                             scope="exact-full-font-bytes-found-in-payload/vadgr.exe",
                             origins=[{"archive_sha256": FONT_SHA256, "member": member,
                                       "binary_sha256": sha256_bytes(binary)}],
                             pending=["license-choice-and-original-copyright"])
            copyright_text = font_copyright(data)
            if copyright_text:
                packet.components[-1]["copyright_text"] = copyright_text
                if packet.components[-1]["license_concluded"] != "NOASSERTION":
                    packet.pending[-1]["items"] = []


def observed_source_zip(members):
    return source_tree_zip(members)


def add_installed_python(packet, inputs, collection, archive_root):
    runtime = next(row for row in collection["components"] if row["id"] == "runtime-cpython-3.12.14")
    site = inputs / "payload/lib/cua/python/3.12.14/Lib/site-packages"
    vendor_file = "pip/_vendor/vendor.txt"
    vendor_raw = read_owned(site, vendor_file)
    rows = re.findall(r"^\s*([A-Za-z0-9_-]+)==([^\s]+)\s*$", vendor_raw.decode(), re.M)
    require(len(rows) == 18, "runtime vendor catalogue changed")
    for name, version in rows:
        directory = "pkg_resources" if name == "setuptools" else name.lower().replace("-", "_")
        vendor_root = site / "pip/_vendor" / directory
        require(vendor_root.is_dir(), "runtime vendor directory is absent")
        members = {path.relative_to(vendor_root).as_posix(): sha256_bytes(read_owned(vendor_root, path.relative_to(vendor_root).as_posix()))
                   for path in vendor_root.rglob("*") if path.is_file()}
        notices = [(member, read_owned(vendor_root, member)) for member in sorted(members)
                   if any(token in Path(member).name.lower() for token in ("license", "copying", "notice"))]
        application = list(notices)
        if name == "requests":
            application.append(("__version__.py", read_owned(vendor_root, "__version__.py")))
        external = complete_apache_reference(application, archive_root) or complete_mpl_reference(application, archive_root)
        if external:
            if name == "requests":
                notices.append(("__version__.py.txt", application[-1][1]))
            notices.append(external[0])
        grants = set().union(*(license_atoms(raw) for _, raw in notices))
        # Multiple license files can cover different parts, not alternatives.
        declared = next(iter(grants)) if len(grants) == 1 else None
        if any(b"*either*" in raw and b"LICENSE.APACHE or LICENSE.BSD" in raw for _, raw in notices):
            bsd = grants & {"BSD-2-Clause", "BSD-3-Clause"}
            require(len(bsd) == 1, "vendor BSD alternative is ambiguous")
            declared = "Apache-2.0 OR " + next(iter(bsd))
        packet.component(identifier="python-vendor-" + slug(name.lower()), name=name, version=version,
                         kind="runtime", digest=sha256_bytes(canonical_json(members)), location=runtime["download_location"],
                         declared=declared, sources=notices, scope="observed-runtime-vendored-tree",
                         origins=[{"archive_sha256": runtime["sha256"], "vendor_manifest_sha256": sha256_bytes(vendor_raw),
                                   "path": "payload/lib/cua/python/3.12.14/Lib/site-packages/pip/_vendor/" + directory,
                                   "file_count": len(members), "hash_basis": "canonical-relative-path-to-sha256-map"}],
                         pending=["license-choice-and-original-copyright", "notice-and-source-duty"])
        if external:
            path = "legal/NOTICES/python-vendor-" + slug(name.lower()) + "/external-grant-provenance.json"
            raw = canonical_json(external[1])
            packet.put(path, raw)
            packet.components[-1]["notice_files"].append({"path": path, "sha256": sha256_bytes(raw)})
            packet.evidence[-1]["external_grant_basis"] = external[1]
        claims = []
        for member in sorted(members):
            if Path(member).suffix.lower() not in {".py", ".pyi", ".c", ".h"}:
                continue
            raw = read_owned(vendor_root, member)
            found = original_statements(raw.decode("utf-8", errors="replace"))
            if found:
                claims.append({"path": member, "sha256": sha256_bytes(raw), "statements": found})
        add_original_claims(packet, "python-vendor-" + slug(name.lower()), claims)
        component = packet.components[-1]
        if component["copyright_text"] == "NOASSERTION":
            raw = observed_source_zip({member: read_owned(vendor_root, member) for member in sorted(members)})
            audit = audit_source_tree_zip(raw, component["sha256"])
            if audit["eligible_for_reviewed_NONE"]:
                folder = "legal/SOURCE-OFFERS/" + component["id"] + "/"
                proof = {folder + "observed-source.zip": raw, folder + "copyright-absence.json": canonical_json(audit)}
                for path, value in proof.items():
                    packet.put(path, value)
                component.update(copyright_text="NONE", source_offer_required=True,
                    source_offer_files=[{"path": path, "sha256": sha256_bytes(value)} for path, value in sorted(proof.items())])
                packet.evidence[-1]["copyright_absence_audit"] = {"path": folder + "copyright-absence.json",
                    "sha256": sha256_bytes(canonical_json(audit)), "scope": "Every observed member, including original licenses and data; canonical tree hash equals component identity."}
                if component["license_concluded"] != "NOASSERTION":
                    packet.pending[-1]["items"] = [item for item in packet.pending[-1]["items"]
                                                  if item != "license-choice-and-original-copyright"]
        if name == "certifi":
            filename, raw, comparison = compare_certifi_source(
                {member: read_owned(vendor_root, member) for member in sorted(members)}, version, archive_root)
            require(component["license_concluded"] == "MPL-2.0"
                    and any(entry["path"].endswith("/observed-source.zip") for entry in component["source_offer_files"]),
                    "certifi complete grant and observed source delivery are absent")
            path = "legal/SOURCE-OFFERS/" + component["id"] + "/" + filename
            packet.put(path, raw)
            component["source_offer_files"].append({"path": path, "sha256": sha256_bytes(raw)})
            path = "legal/NOTICES/" + component["id"] + "/source-comparison.json"
            raw = canonical_json(comparison)
            packet.put(path, raw)
            component["notice_files"].append({"path": path, "sha256": sha256_bytes(raw)})
            packet.evidence[-1]["source_delivery_basis"] = comparison
            packet.pending[-1]["items"] = [item for item in packet.pending[-1]["items"] if item != "notice-and-source-duty"]
    for metadata_path in sorted(site.glob("*.dist-info/METADATA")):
        message = BytesParser(policy=policy.default).parsebytes(read_owned(site, metadata_path.relative_to(site).as_posix()))
        notices = [(path.relative_to(site).as_posix(), read_owned(site, path.relative_to(site).as_posix()))
                   for path in metadata_path.parent.rglob("*") if path.is_file()
                   and any(token in path.name.lower() for token in ("license", "copying", "notice"))]
        if message["Name"].lower() == "pip":
            for name, raw in notices:
                if "/src/pip/_vendor/" in name:
                    relative = name.split("/src/pip/_vendor/", 1)[1]
                    require(raw == read_owned(site / "pip/_vendor", relative), "pip vendor notice copy differs")
            notices = [(name, raw) for name, raw in notices if "/src/pip/_vendor/" not in name]
        packet.component(identifier="python-installed-" + slug(message["Name"]), name=message["Name"], version=message["Version"],
                         kind="runtime", digest=sha256_bytes(metadata_path.read_bytes()), location=runtime["download_location"],
                         declared=message.get("License-Expression") or message.get("License"), sources=notices,
                         scope="observed-runtime-distribution-metadata", pending=["license-choice-and-original-copyright", "notice-and-source-duty"],
                         origins=[{"archive_sha256": runtime["sha256"], "path": metadata_path.relative_to(inputs).as_posix(),
                                   "hash_basis": "exact-installed-METADATA"}])


def add_reviewed_helpers(packet, source, inputs, architecture):
    """Carry existing exact helper-only decisions, without extending them to outer files."""
    import io
    legal_name = f"packaging/cua/helper-legal/{ARCHITECTURES[architecture]}.json"
    raw_review = read_owned(source, legal_name)
    reviewed = parse_json(raw_review)
    require(reviewed["status"] == "approved" and reviewed["architecture"] == ARCHITECTURES[architecture]
            and reviewed["version"] == "0.7.9" and reviewed["source_offer_required"] is False
            and reviewed["scope"] == "cua-helper-input-redistribution-and-authenticode-transformation"
            and reviewed["source_commit"] == document(source, "packaging/cua/cua-profile-catalog.json")["source_commit"],
            "reviewed helper scope differs")
    root = inputs / "payload/lib/cua/environments"
    brokers = list(root.rglob("*broker*.zip"))
    relays = [path for path in root.rglob("vadgr-cua-host.exe") if "/browser/winhost/" in path.as_posix()]
    require(len(brokers) == len(relays) == 1, "helper closure is ambiguous")
    broker_raw = read_owned(inputs, brokers[0].relative_to(inputs).as_posix())
    members = {"vadgr-cua-host.exe": read_owned(inputs, relays[0].relative_to(inputs).as_posix())}
    with zipfile.ZipFile(io.BytesIO(broker_raw)) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), "broker members repeat")
        for member in archive.infolist():
            relative_path(member.filename)
            require(member.file_size <= 16 * 1024 * 1024, "broker member is oversized")
            members[member.filename] = archive.read(member)
    require(set(members) == set(reviewed["members"]), "reviewed helper members differ")
    for name, data in members.items():
        row = reviewed["members"][name]
        require(sha256_bytes(data) == row["input_sha256"] and len(data) == row["size"], "reviewed helper bytes differ")
    names = sorted({name for row in reviewed["members"].values() for name in row["license_and_notice_members"]})
    crt = members["PYTHON-LICENSE.txt"]
    start = crt.index(b"Additional Conditions for this Windows binary build")
    last = b"file, or by other licenses as marked."
    end = crt.index(last, start) + len(last)
    crt = crt[start:end]
    require(b"copyrighted by Microsoft Corporation" in crt and b"not to Python itself" in crt,
            "helper Windows redistribution conditions differ")
    crt_digest = sha256_bytes(crt)
    crt_id = "LicenseRef-Python-Windows-Redistribution-" + crt_digest
    mapping = {"CPython": "Python-2.0 AND 0BSD", "Microsoft-VC-runtime": crt_id,
        "bzip2": "bzip2-1.0.6", "libffi": "MIT", "liblzma": "0BSD", "mpdecimal": "BSD-2-Clause",
        "OpenSSL": "Apache-2.0", "expat": "MIT", "zlib": "Zlib", "vadgr-computer-use": "Apache-2.0",
        "Go-runtime-and-CUA-relay": "BSD-3-Clause AND Apache-2.0",
        "PyInstaller-bootloader-and-CUA": "GPL-2.0-or-later WITH Bootloader-exception AND Apache-2.0"}
    component_names = {name for member in reviewed["members"].values() for name in member["components"]} - {"distribution-notice"}
    require(component_names == set(mapping), "helper component classification changed")
    expressions = sorted(set(mapping.values()))
    combined = " AND ".join("(" + expression + ")" for expression in expressions)
    source_notices = [(name, members[name]) for name in names] + [("PYTHON-WINDOWS-CONDITIONS.txt", crt)]
    packet.component(identifier="runtime-cua-helper-closure-0.7.9", name="CUA Windows helper closure", version="0.7.9",
                     kind="runtime", digest=sha256_bytes(broker_raw),
                     location=f"https://github.com/MONTBRAIN/vadgr-computer-use/actions/runs/{reviewed['review_input']['run_id']}",
                     declared=combined, sources=source_notices, custom_grants={crt_id: crt_digest},
                     scope="exact-members-match-existing-helper-only-redistribution-review",
                     pending=[],
                     origins=[{"legal_review_sha256": sha256_bytes(raw_review), "legal_review_path": legal_name,
                               "broker_path": brokers[0].relative_to(inputs).as_posix(),
                               "relay_path": relays[0].relative_to(inputs).as_posix()}])
    packet.components[-1]["source_offer_required"] = False
    packet.components[-1]["notice_required"] = True
    packet.components[-1]["copyright_text"] = copyright_lines([(name, members[name]) for name in names])
    require(packet.components[-1]["license_concluded"] != "NOASSERTION", "helper component grant coverage is incomplete")
    # This copies the already-reviewed helper-only duty conclusion, after the
    # complete exact member comparison above. It is not extended to outer files.
    packet.pending[-1]["items"] = []
    packet.put("helper-spdx-mapping.json", canonical_json({"schema": 1, **BOUNDARY,
        "reviewed_helper_sha256": sha256_bytes(raw_review), "component_expressions": mapping,
        "members": {name: {"input_sha256": row["input_sha256"], "size": row["size"],
            "component_expressions": {component: mapping[component] for component in row["components"]
                                      if component != "distribution-notice"},
            "license_and_notice_members": row["license_and_notice_members"]} for name, row in reviewed["members"].items()},
        "scope": "Exact helper-only component mapping; no new approval and no outer-package redistribution conclusion."}))
    packet.put("reviewed-helper-inputs.json", raw_review)


def add_crate_evidence(packet, cache, archive_root, architecture, inputs):
    observations, workspace = inspect_sources(packet.components, cache, archive_root)
    cargo_raw = read_owned(inputs, "cargo-metadata.json")
    cargo_features = {node["id"]: node["features"] for node in parse_json(cargo_raw)["resolve"]["nodes"]}
    for index, row in enumerate(list(packet.components)):
        if row["kind"] != "cargo":
            continue
        fact = observations[(row["name"], row["version"])]
        evidence = packet.evidence[index]
        issue = packet.pending[index]
        # Remove only the preparer's index so retained original notice names do
        # not acquire a second generated prefix during evidence enrichment.
        sources = [(Path(entry["path"]).name[4:], packet.files[entry["path"]]) for entry in row["notice_files"]]
        seen = {sha256_bytes(raw) for _, raw in sources}
        for notice in fact["supplied_notices"]:
            raw = notice["text"].encode("utf-8")
            require(sha256_bytes(raw) == notice["sha256"], "source notice roundtrip differs")
            if notice["sha256"] not in seen:
                sources.append((notice["path"], raw))
                seen.add(notice["sha256"])
        crate_raw = read_owned(cache, row["name"] + "-" + row["version"] + ".crate")
        external = crate_external_grant(row, crate_raw, archive_root)
        if external:
            sources.append(external[0])
        renewed = Packet()
        renewed.component(identifier=row["id"], name=row["name"], version=row["version"], kind=row["kind"],
                          digest=row["sha256"], location=row["download_location"],
                          declared=evidence["original_license_declaration"], sources=sources,
                          scope=evidence["scope"], pending=issue["items"], origins=evidence["origins"])
        grants = set().union(*(license_atoms(raw) for _, raw in sources))
        scoped = crate_grant_scope(row, crate_raw,
            license_choice(evidence["original_license_declaration"], grants), grants,
            cargo_features.get("registry+https://github.com/rust-lang/crates.io-index#" + row["name"] + "@" + row["version"]), sources)
        if scoped:
            if scoped["observed_cargo_features"] is not None:
                scoped["cargo_metadata"] = {"path": "cargo-metadata.json", "sha256": sha256_bytes(cargo_raw)}
            renewed = Packet()
            renewed.component(identifier=row["id"], name=row["name"], version=row["version"], kind=row["kind"],
                digest=row["sha256"], location=row["download_location"], declared=scoped["expression"], sources=sources,
                scope=evidence["scope"], pending=issue["items"], origins=evidence["origins"])
            require(renewed.components[0]["license_concluded"] != "NOASSERTION", "scoped source grants are incomplete")
            renewed.components[0]["license_declared"] = row["license_declared"]
            renewed.evidence[0]["original_license_declaration"] = evidence["original_license_declaration"]
            renewed.evidence[0]["grant_scope_basis"] = scoped
            renewed.pending[0]["items"] = [item for item in renewed.pending[0]["items"] if item != "additional-retained-grant-scope"]
            path = "legal/NOTICES/" + row["id"] + "/source-grant-scope.json"
            raw = canonical_json(scoped)
            renewed.put(path, raw)
            renewed.components[0]["notice_files"].append({"path": path, "sha256": sha256_bytes(raw)})
        if external:
            path = "legal/NOTICES/" + row["id"] + "/external-grant-provenance.json"
            raw = canonical_json(external[1])
            renewed.put(path, raw)
            renewed.components[0]["notice_files"].append({"path": path, "sha256": sha256_bytes(raw)})
            renewed.evidence[0]["external_grant_basis"] = external[1]
        retained_text = " ".join(b"\n".join(raw for _, raw in sources).decode("utf-8").split())
        if row["name"] == "libm" and "rust-lang/libm as a whole is available for use under the MIT license" in retained_text:
            renewed.pending[0]["items"] = [item for item in renewed.pending[0]["items"] if item != "additional-retained-grant-scope"]
            renewed.evidence[0]["grant_scope_basis"] = "Retained license explicitly grants MIT for the whole library; Apache terms describe contributor alternatives."
        if row["name"] == "sha1_smol" and "src/simd.rs is licensed under the MIT license" in retained_text:
            renewed = Packet()
            renewed.component(identifier=row["id"], name=row["name"], version=row["version"], kind=row["kind"],
                digest=row["sha256"], location=row["download_location"], declared="BSD-3-Clause AND MIT", sources=sources,
                scope=evidence["scope"], pending=issue["items"], origins=evidence["origins"])
            renewed.pending[0]["items"] = [item for item in renewed.pending[0]["items"] if item != "additional-retained-grant-scope"]
            renewed.components[0]["license_declared"] = row["license_declared"]
            renewed.evidence[0]["original_license_declaration"] = evidence["original_license_declaration"]
            renewed.evidence[0]["grant_scope_basis"] = "Retained license explicitly maps src/simd.rs to MIT in addition to the library BSD-3-Clause grant."
        # Keep original statement provenance. Do not convert Cargo authors into a claim.
        # The inventory digest identifies the complete source archive. Statements
        # in tests remain attributed to their exact files, not promoted to a
        # claim about library ownership or discarded to create fictional absence.
        claims = list(fact["original_statements"])
        if external:
            grant_name, grant_raw = external[0]
            grant_claims = original_statements(grant_raw.decode("utf-8"))
            if grant_claims:
                claims.append({"path": grant_name, "sha256": sha256_bytes(grant_raw),
                    "source_url": external[1]["url"], "statements": grant_claims})
        statements = sorted({statement["text"] for claim in claims for statement in claim["statements"]})
        if statements:
            renewed.components[0]["copyright_text"] = "\n".join(statements)
            retained = canonical_json({"archive_sha256": row["sha256"], "original_statement_files": claims,
                "scope": "Original statements in the exact source archive or separately hash-bound upstream grant; not a claim of exclusive ownership of the whole component."})
            name = "legal/NOTICES/" + row["id"] + "/source-copyright-statements.json"
            renewed.put(name, retained)
            renewed.components[0]["notice_files"].append({"path": name, "sha256": sha256_bytes(retained)})
            if renewed.components[0]["license_concluded"] != "NOASSERTION":
                renewed.pending[0]["items"] = [item for item in renewed.pending[0]["items"]
                                               if item != "license-choice-and-original-copyright"]
        elif renewed.components[0]["copyright_text"] == "NOASSERTION":
            renewed.pending[0]["items"].append("no-original-copyright-statement-in-pinned-source")
            filename = row["name"] + "-" + row["version"] + ".crate"
            raw = read_owned(cache, filename)
            audit = audit_archive(raw, row["sha256"])
            audit_path = "source-copyright-audits/" + row["id"] + ".json"
            renewed.put(audit_path, canonical_json(audit))
            renewed.evidence[0]["copyright_absence_audit"] = {
                "path": audit_path, "sha256": sha256_bytes(canonical_json(audit)),
                "eligible_for_reviewed_NONE": audit["eligible_for_reviewed_NONE"]}
            folder = "legal/SOURCE-OFFERS/" + row["id"] + "/"
            proof_files = {folder + filename: raw, folder + "copyright-absence.json": canonical_json(audit)}
            for name, data in proof_files.items():
                renewed.put(name, data)
            renewed.components[0].update(source_offer_required=True,
                source_offer_files=[{"path": name, "sha256": sha256_bytes(data)} for name, data in sorted(proof_files.items())])
            if audit["eligible_for_reviewed_NONE"]:
                renewed.components[0]["copyright_text"] = "NONE"
                renewed.pending[0]["items"] = [item for item in renewed.pending[0]["items"]
                    if item != "no-original-copyright-statement-in-pinned-source"
                    and not (item == "license-choice-and-original-copyright" and renewed.components[0]["license_concluded"] != "NOASSERTION")]
        if renewed.components[0]["license_concluded"] == "MPL-2.0":
            filename = row["name"] + "-" + row["version"] + ".crate"
            raw = read_owned(cache, filename)
            name = "legal/SOURCE-OFFERS/" + row["id"] + "/" + filename
            renewed.put(name, raw)
            renewed.components[0]["source_offer_required"] = True
            if not any(item["path"] == name for item in renewed.components[0]["source_offer_files"]):
                renewed.components[0]["source_offer_files"].append({"path": name, "sha256": row["sha256"]})
            renewed.pending[0]["items"] = [item for item in renewed.pending[0]["items"] if item != "notice-and-source-duty"]
        renewed.evidence[0]["source_archive_observation"] = {
            "archive_sha256": fact["archive_sha256"], "archive_files_sha256": fact["archive_files_sha256"],
            "files_scanned": fact["files_scanned"], "non_test_statement_files": [claim["path"] for claim in claims],
            "copyright_observation": fact["copyright_observation"]}
        for name in list(packet.files):
            if name.startswith(("legal/NOTICES/" + row["id"] + "/", "legal/LICENSES/" + row["id"] + "/")):
                del packet.files[name]
        for name, raw in renewed.files.items():
            packet.put(name, raw)
        packet.components[index], packet.evidence[index], packet.pending[index] = (
            renewed.components[0], renewed.evidence[0], renewed.pending[0])
    classify_nested(packet, observations, workspace, ARCHITECTURES[architecture])
    packet.put("source-archive-observations.json", canonical_json({"schema": 1,
        "status": "source-observations-not-approval", "archives": [observations[key] for key in sorted(observations)],
        "wheel_source_archives": workspace}))


def synthesize(source, observation_root, architecture, created, archive_root, crate_cache, observation_binding):
    require(set(observation_binding) == {"schema", "status", "candidate_approval", "publishable", "source_sha",
            "trusted_sha", "run_id", "observations"} and observation_binding["schema"] == 1
            and observation_binding["candidate_approval"] is False and observation_binding["publishable"] is False,
            "invalid preparation binding")
    observation, inputs, bindings = verify_observation(observation_root, source, architecture, observation_binding)
    target_root = f"packaging/legal-review/windows-{ARCHITECTURES[architecture]}"
    collection = document(source, target_root + "/collection.json")
    collection["_root"] = target_root
    packet = Packet()
    packet.put("preparation-binding.json", canonical_json(observation_binding))
    for name in sorted(REQUIRED_FILES):
        original = "packaging/legal/" + name.removeprefix("legal/")
        packet.put(name, read_owned(source, original))
    terms = packet.files["legal/TERMS.txt"]
    require(sha256_bytes(terms) == observation["terms"]["sha256"], "terms changed after observation")
    packet.put("legal/TERMS.rtf", render_rtf(terms.decode("utf-8")))
    add_cargo(packet, inputs, source, collection)
    add_wheels(packet, inputs, source, collection)
    add_supplement(packet, source, collection, architecture, archive_root)
    add_observed_nested_crates(packet)
    add_sqlite_source_scope(packet, archive_root)
    add_wix_source_mapping(packet, source, collection)
    add_crate_evidence(packet, crate_cache, archive_root, architecture, inputs)
    add_archives_and_fonts(packet, inputs, archive_root)
    add_installed_python(packet, inputs, collection, archive_root)
    add_reviewed_helpers(packet, source, inputs, architecture)
    map_python_native(packet, inputs, source, architecture)
    map_wheel_native_sources(packet, architecture)
    map_custom_native_sources(packet, source, inputs, architecture)
    retain_upstream_crypto(packet, archive_root, architecture)
    retain_runtime_evidence(packet, inputs, architecture, archive_root)
    components = sorted(packet.components, key=lambda row: row["id"])
    inventory = {"schema": 1, "created": created, "version": "0.5.0", "target": observation["target"],
                 "terms_version": "1.0", "terms_sha256": sha256_bytes(terms), "source_inputs": bindings,
                 "payload_manifest_sha256": observation["payload_sha256"], "components": components,
                 "coverage": {kind: {"status": "incomplete", "component_ids": [row["id"] for row in components if row["kind"] == kind]}
                              for kind in sorted(KINDS)}}
    packet.put("package-input-inventory.json", canonical_json(inventory))
    packet.put("legal/THIRD-PARTY-NOTICES.txt", aggregate_files(inventory, packet.files, "notice_files"))
    packet.put("legal/SOURCE-OFFER.txt", aggregate_files(inventory, packet.files, "source_offer_files"))
    sbom = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": "vadgr-0.5.0-" + observation["target"] + "-unreviewed",
            "documentNamespace": "https://spdx.org/spdxdocs/vadgr-review-" + sha256_bytes(canonical_json(inventory)),
            "creationInfo": {"created": created, "creators": ["Tool: vadgr-windows-legal-preparation"]},
            "documentComment": "Incomplete review inventory, including separately classified build-source candidates. Not an approved shipped-component SBOM.",
            "packages": [{"SPDXID": "SPDXRef-" + row["id"], "name": row["name"], "versionInfo": row["version"],
                          "downloadLocation": row["download_location"], "filesAnalyzed": False,
                          "checksums": [{"algorithm": "SHA256", "checksumValue": row["sha256"]}],
                          "licenseDeclared": declared_expression(row["license_declared"]) or "NOASSERTION",
                          "licenseConcluded": row["license_concluded"],
                          "packageComment": "Original upstream declaration: " + str(next(
                              item["original_license_declaration"] for item in packet.evidence if item["id"] == row["id"])),
                          "copyrightText": row["copyright_text"]}
                         for row in components]}
    extracted = extracted_license_info(inventory, packet.files)
    if extracted:
        sbom["hasExtractedLicensingInfos"] = extracted
    packet.put("sbom/vadgr-0.5.0.spdx.json", canonical_json(sbom))
    review = {key: inventory[key] for key in ("schema", "version", "target", "terms_version", "terms_sha256", "source_inputs", "payload_manifest_sha256")}
    review.update({"status": "draft", "synthetic": False,
                   "inventory_sha256": sha256_bytes(packet.files["package-input-inventory.json"]),
                   "files": {name: sha256_bytes(raw) for name, raw in sorted(packet.files.items()) if name.startswith(("legal/", "sbom/")) or name == "README-OFFLINE.txt"},
                   "closures": dict.fromkeys(CLOSURES, False)})
    packet.put("package-input-review.json", canonical_json(review))
    by_reason = defaultdict(list)
    for row in packet.pending:
        for reason in row["items"]:
            by_reason[reason].append(row["id"])
    packet.put("review-ledger.json", canonical_json({
        "schema": 1, **BOUNDARY, "source_sha": observation["source"]["source_sha"],
        "trusted_sha": observation["source"]["trusted_sha"], "run_id": observation["source"]["run_id"],
        "observation_sha256": sha256_bytes(read_owned(observation_root, "preparation-observation.json")),
        "preparation_binding_sha256": sha256_bytes(packet.files["preparation-binding.json"]),
        "terms": {"version": "1.0", "sha256": sha256_bytes(terms), "status": "owner-approved-draft-retained-unchanged"},
        "components": sorted(packet.evidence, key=lambda row: row["id"]),
        "unresolved": sorted(packet.pending, key=lambda row: row["id"]),
        "unresolved_by_reason": {reason: sorted(ids) for reason, ids in sorted(by_reason.items())},
        "summary": {"component_candidates": len(components),
                    "retained_grant_choices": sum(row["license_concluded"] != "NOASSERTION" for row in components),
                    "unresolved_copyright": sum(row["copyright_text"] == "NOASSERTION" for row in components),
                    "evidence_bound_NONE_proposals": sum(row["copyright_text"] == "NONE" for row in components),
                    "rows_with_review_items": sum(bool(row["items"]) for row in packet.pending),
                    "scope_counts": {scope: sum(row["scope"] == scope for row in packet.evidence)
                                     for scope in sorted({row["scope"] for row in packet.evidence})}},
        "package_questions": ["actual-target-market-rights", "product-data-statements", "Cargo-linkage-and-generated-code-scope",
                              "Python-vendored-and-native-library-closure", "WiX-runtime-source-completeness-and-official-build-terms",
                              "nodriver-AGPL-source-and-combined-work-treatment"],
    }))
    packet.put("UNAPPROVED.txt", b"Incomplete legal review inputs. Not approved for signing, installation, publication or release.\n")
    return packet.files


def emit(files, output, verify):
    if verify:
        actual = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()}
        require(actual == set(files), "generated packet file set differs")
        require(all(read_owned(output, name) == data for name, data in files.items()), "generated packet bytes differ")
        return
    require(not output.exists(), "output already exists")
    require(output.parent.is_dir() and not output.parent.is_symlink(), "output parent is unsafe")
    require(not any(parent.is_symlink() or getattr(parent, "is_junction", lambda: False)()
                    for parent in (output.parent, *output.parent.parents)), "output parent is linked")
    output.mkdir()
    for name, data in sorted(files.items()):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--architecture", choices=ARCHITECTURES, required=True)
    parser.add_argument("--created", required=True)
    parser.add_argument("--source-archives", type=Path, required=True)
    parser.add_argument("--crate-cache", type=Path, required=True)
    parser.add_argument("--observation-bindings", type=Path, default=Path("packaging/inputs/windows-observation-bindings.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", args.created), "invalid creation time")
        files = synthesize(args.source_root.resolve(), args.observation.resolve(), args.architecture, args.created,
                           args.source_archives.resolve(), args.crate_cache.resolve(),
                           document(args.observation_bindings.absolute().parent, args.observation_bindings.name))
        emit(files, args.output.absolute(), args.verify)
        print(f"Draft legal packet: {len(files)} exact files; approval remains blocked.")
        return 0
    except (PackageInputError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(f"Legal synthesis refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
