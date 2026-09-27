"""Exact source observations used by the Windows legal packet preparer.

These are data operations, never execution of upstream source or approval of
redistribution. Cargo graph reachability is distinguished from machine-code proof.
"""

from collections import defaultdict, deque
import io
import json
from pathlib import Path
import re
import struct
import tarfile
import tomllib

if __package__:
    from scripts.inspect_legal_crate_sources import inspect_archive
    from scripts.validate_package_inputs import canonical_json, read_owned, require, sha256_bytes
else:
    from inspect_legal_crate_sources import inspect_archive
    from validate_package_inputs import canonical_json, read_owned, require, sha256_bytes


WHEEL_SOURCES = {
    "pydantic_core-2.46.5.tar.gz": ("10416c15b8839ecc4ef4d0885da76da6fd0f67333a0eb8aff6d93c4b8f2910fc",
        "https://files.pythonhosted.org/packages/af/f9/8a06bea35ef8daf588f707784c973a7046e0034c8d8cfb08828eeffb8b75/pydantic_core-2.46.5.tar.gz"),
    "rpds_py-2026.6.3.tar.gz": ("1cebd1337c242e4ec2293e541f712b2da849b29f48f0c293684b71c0632625d4",
        "https://files.pythonhosted.org/packages/aa/2a/9618a122aeb2a169a28b03889a2995fe297588964333d4a7d67bdf46e147/rpds_py-2026.6.3.tar.gz"),
    "cryptography-50.0.1.tar.gz": ("5dd9bda1c12b4162f6ff568eeb5e0ff956c28d14406e875cfe8a63a2d414ff20",
        "https://files.pythonhosted.org/packages/bb/ad/5d6702db60b1e40b41ef513b6967ff5848f307d50f8449baf1634f5908f1/cryptography-50.0.1.tar.gz"),
}


EXTERNAL_CRATE_GRANTS = {
    "iroh": ("1.0.3", "f2eb930dda3779c6d852b72f3712aacd6e573ab1", "https://github.com/n0-computer/iroh",
        "iroh-f2eb930-LICENSE-APACHE.txt", "903131e2786f073a942fbf8fae122d9e576e4dad758c6da7f9f2ba58fd8611ab",
        "https://raw.githubusercontent.com/n0-computer/iroh/f2eb930dda3779c6d852b72f3712aacd6e573ab1/LICENSE-APACHE"),
    "cms": ("0.2.3", "5821a21553509dbd03eae593b0a1fad4e2083d4e", "https://github.com/RustCrypto/formats/tree/master/cms",
        "Apache-2.0-standard.txt", "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
        "https://www.apache.org/licenses/LICENSE-2.0.txt"),
}
EXTERNAL_CRATE_GRANTS["iroh-relay"] = EXTERNAL_CRATE_GRANTS["iroh"]


def crate_external_grant(component, raw, archive_root):
    """Bind a complete grant to the exact crate's explicit application declaration."""
    spec = EXTERNAL_CRATE_GRANTS.get(component["name"])
    if spec is None:
        return None
    version, revision, repository, filename, digest, url = spec
    require(component["version"] == version and sha256_bytes(raw) == component["sha256"],
            "external grant crate identity differs")
    root = component["name"] + "-" + version + "/"
    proof = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        def member(relative):
            data = archive.extractfile(root + relative).read()
            proof.append({"path": root + relative, "sha256": sha256_bytes(data), "size": len(data)})
            return data
        manifest = tomllib.loads(member("Cargo.toml").decode("utf-8"))["package"]
        vcs = json.loads(member(".cargo_vcs_info.json"))
    require(manifest["name"] == component["name"] and manifest["version"] == version
            and manifest["repository"] == repository and manifest["license"] in {"Apache-2.0 OR MIT", "MIT OR Apache-2.0"}
            and vcs["git"]["sha1"] == revision and vcs["path_in_vcs"] == component["name"],
            "external grant application or source revision differs")
    grant = read_owned(archive_root, filename)
    require(sha256_bytes(grant) == digest, "external grant text identity differs")
    return (filename, grant), {"archive_sha256": component["sha256"], "source_files": proof,
        "source_revision": revision, "url": url, "grant_sha256": digest,
        "application": "Exact crate manifest explicitly offers Apache-2.0 OR MIT. The complete Apache text is retained separately from original ownership evidence.",
        "status": "source-grant-proposal-not-package-approval"}


def complete_apache_reference(sources, archive_root):
    """A short application notice is not a grant; retain the complete referenced text."""
    application = []
    for name, raw in sources:
        text = " ".join(raw.decode("utf-8").split())
        if ('Licensed under the Apache License, Version 2.0 (the "License");' in text
                and "www.apache.org/licenses/LICENSE-2.0" in text):
            application.append({"path": name, "sha256": sha256_bytes(raw), "size": len(raw)})
        elif re.search(r'(?m)^__license__\s*=\s*[\'"]Apache-2\.0[\'"]\s*$', raw.decode("utf-8")):
            application.append({"path": name, "sha256": sha256_bytes(raw), "size": len(raw)})
    if not application:
        return None
    _, _, _, filename, digest, url = EXTERNAL_CRATE_GRANTS["cms"]
    grant = read_owned(archive_root, filename)
    require(sha256_bytes(grant) == digest, "referenced Apache text differs")
    return (filename, grant), {"application_files": application, "grant_sha256": digest, "url": url,
        "scope": "Complete text for the explicitly applied Apache-2.0 grant; original application notices remain included."}


def complete_mpl_reference(sources, archive_root):
    application = [{"path": name, "sha256": sha256_bytes(raw), "size": len(raw)} for name, raw in sources
        if all(part in " ".join(raw.decode("utf-8").split()) for part in (
            "This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.",
            "mozilla.org/MPL/2.0/"))]
    if not application:
        return None
    filename = "MPL-2.0-standard.txt"
    digest = "3f3d9e0024b1921b067d6f7f88deb4a60cbe7a78e76c64e3f1d7fc3b779b9d04"
    grant = read_owned(archive_root, filename)
    require(sha256_bytes(grant) == digest, "referenced MPL text differs")
    return (filename, grant), {"application_files": application, "grant_sha256": digest,
        "url": "https://www.mozilla.org/media/MPL/2.0/index.txt",
        "scope": "Complete text for the explicitly applied MPL-2.0 grant; source-form delivery remains separately assessed."}


CERTIFI_SOURCE_SHA256 = "024c88eeec92ca068db80f02b8b07c9cef7b9fe261d1d535abfd5abd6f6af432"

TIX_SOURCE_SHA256 = "f7b21d115867a41ae5fd7c635a4c234d3ca25126c3661eb36028c6e25601f85e"
TIX_HTML_SHA256 = "9149f81c6efd1c3cef68742b67dc6f1b6211f32f425f3b6d24cf5279668cfd27"


def tix_referenced_grant(sources, archive_root):
    """Resolve the exact named grant without calling its different terms TCL."""
    referenced = [(name, raw) for name, raw in sources if b"docs/license.html_lib" in raw]
    if not referenced:
        return None
    require(len({raw.replace(b"\r\n", b"\n") for _, raw in referenced}) == 1, "Tix grant reference is ambiguous")
    filename = "tix-8.4.3.6.tar.gz"
    raw = read_owned(archive_root, filename)
    require(sha256_bytes(raw) == TIX_SOURCE_SHA256, "Tix grant source identity differs")
    prefix = "cpython-source-deps-tix-8.4.3.6/"
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        primary = archive.extractfile(prefix + "license.terms").read()
        grant = archive.extractfile(prefix + "docs/license.html_lib").read()
    require(primary.replace(b"\r\n", b"\n") == referenced[0][1].replace(b"\r\n", b"\n"),
            "Tix observed license does not match referenced source")
    require(sha256_bytes(grant) == TIX_HTML_SHA256, "Tix HTML grant identity differs")
    identifier = "LicenseRef-Tix-HTML-" + TIX_HTML_SHA256
    return ("license.html_lib", grant), identifier, {
        "archive_sha256": TIX_SOURCE_SHA256,
        "archive_url": "https://github.com/python/cpython-source-deps/archive/refs/tags/tix-8.4.3.6.tar.gz",
        "source_revision": "6c27742f4c7695a35c6ca23b75d38f62a1414c9c",
        "reference_files": [{"path": name, "sha256": sha256_bytes(value)} for name, value in referenced],
        "source_license": {"path": prefix + "license.terms", "sha256": sha256_bytes(primary)},
        "referenced_grant": {"path": prefix + "docs/license.html_lib", "sha256": TIX_HTML_SHA256},
        "comparison": "Complete observed Tix license equals the source license after CRLF normalization.",
        "scope": "The Tix notice explicitly includes parts based on the HTML Library and names this separate grant. Both grants are retained conservatively; no absence of HTML-derived runtime code is inferred.",
        "limitation": "Grant-reference evidence, not a binary rebuild or source-version mapping. The HTML grant has distinct government-rights wording without the standard TCL override; custom-term and source-duty review remains open.",
    }


def compare_certifi_source(members, version, archive_root):
    filename = "certifi-2026.6.17.tar.gz"
    digest = CERTIFI_SOURCE_SHA256
    require(version == "2026.6.17" and set(members) == {"LICENSE", "__init__.py", "__main__.py", "core.py", "cacert.pem", "py.typed"},
            "certifi observed source scope differs")
    raw = read_owned(archive_root, filename)
    require(sha256_bytes(raw) == digest, "certifi source archive differs")
    records = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for name, observed in sorted(members.items()):
            path = "certifi-2026.6.17/" + ("" if name == "LICENSE" else "certifi/") + name
            original = archive.extractfile(path).read()
            expected = original
            if name == "__main__.py":
                expected = original.replace(b"from certifi import contents, where", b"from pip._vendor.certifi import contents, where")
            elif name == "core.py":
                expected = original.replace(b'"certifi"', b'"pip._vendor.certifi"')
            require(observed == expected, "certifi modification differs from exact import/resource relocation")
            records.append({"observed_path": name, "upstream_path": path, "upstream_sha256": sha256_bytes(original),
                "observed_sha256": sha256_bytes(observed), "changed": original != observed,
                "change": "pip vendor import/resource namespace relocation" if original != observed else "none"})
    return filename, raw, {"source_archive_sha256": digest,
        "source_url": "https://files.pythonhosted.org/packages/c9/c7/424b75da314c1045981bd9777432fad05a9e0c69daa4ed7e308bbaffe405/certifi-2026.6.17.tar.gz",
        "members": records, "source_delivery": "Complete published source distribution plus every actual shipped modified Python/data member in observed-source.zip."}


RMCP_GRANT_SHA256 = "0382b0057770ca05e9c350a50aa3b1c1fea84da0bc81d723bf00b9aa841be58a"


def crate_grant_scope(component, raw, base_expression, grants, cargo_features=None, retained_sources=()):
    """Read explicit upstream file-scope statements, never infer scope from filenames alone."""
    require(sha256_bytes(raw) == component["sha256"], "grant scope archive identity differs")
    if not base_expression:
        return None
    name = component["name"]
    root = name + "-" + component["version"] + "/"
    proof = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        def source(relative):
            member = archive.getmember(root + relative)
            require(member.isfile() and member.size <= 16 * 1024 * 1024, "grant scope source is invalid")
            data = archive.extractfile(member).read()
            proof.append({"path": member.name, "sha256": sha256_bytes(data), "size": len(data)})
            return " ".join(data.decode("utf-8").split())

        if name == "libsqlite3-sys":
            build = source("build.rs")
            if cargo_features is None or any("sqlcipher" in feature for feature in cargo_features):
                return None
            if ('if cfg!(any(feature = "sqlcipher", feature = "bundled-sqlcipher"))' not in build
                    or '"sqlcipher" } else { "sqlite3" }' not in build):
                return None
            source("sqlcipher/LICENSE")
            expression, accounted = base_expression, {"MIT", "BSD-3-Clause"}
            reason = "Exact observed Cargo features do not enable SQLCipher. The retained build script selects sqlite3 rather than the separately licensed SQLCipher subtree."
        elif name in {"lexical-parse-integer", "lexical-parse-float"}:
            text = source("LICENSE.md")
            scope = text.split("# License Terms", 1)[0]
            headings = re.findall(r"## `([^`]+)`", scope)
            if headings != ["write-floats, not(compact)", "write-floats, compact", "write-floats, radix", "parse-floats, compact"]:
                return None
            if not all(text in scope for text in ("lexical-write-float/src/radix.rs", "lexical-parse-float/src/bellerophon.rs",
                    "lexical-write-float/src/algorithm.rs", "Apache2 With LLVM Exceptions")):
                return None
            accounted = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSL-1.0", "LLVM-exception"}
            expression = base_expression if name == "lexical-parse-integer" else base_expression + " AND BSD-3-Clause"
            reason = "The upstream workspace license explicitly assigns additional algorithms to write-float or parse-float paths, never parse-integer. Parse-float retains its possible Go-derived Bellerophon BSD grant without inferring build features."
        elif name in {"iroh", "iroh-relay"}:
            text = source("LICENSE-BSD3")
            if "Tailscale" not in text or not {"Apache-2.0", "BSD-3-Clause"} <= grants:
                return None
            expression, accounted = "Apache-2.0 AND BSD-3-Clause", {"Apache-2.0", "BSD-3-Clause"}
            reason = "The exact crate retains BSD terms for Tailscale-derived portions in addition to its declared Apache-or-MIT grant."
        elif name == "epaint_default_fonts":
            hack = source("fonts/Hack-Regular.txt")
            if not all(text in hack for text in ("Source Foundry Authors and licensed under the MIT License",
                    "Bitstream Vera Sans Mono Copyright 2003 Bitstream Inc. and licensed under the Bitstream Vera License")):
                return None
            accounted = {"MIT", "Apache-2.0", "Bitstream-Vera", "OFL-1.1", "Ubuntu-font-1.0"}
            if grants != accounted:
                return None
            expression = "Apache-2.0 AND MIT AND Bitstream-Vera AND OFL-1.1 AND Ubuntu-font-1.0"
            reason = "The crate's code grant and all four separately inventoried embedded font grants are retained together; Hack explicitly includes both MIT and Bitstream Vera material."
        elif name == "accesskit_winit":
            members = sorted(member.name[len(root):] for member in archive.getmembers()
                if member.isfile() and member.name.startswith(root + "src/") and member.name.endswith(".rs"))
            if not members or base_expression != "Apache-2.0":
                return None
            for path in members:
                text = source(path)
                if not text.startswith("// Copyright ") or not all(clause in text[:250] for clause in (
                        "The AccessKit Authors. All rights reserved.",
                        "Licensed under the Apache License, Version 2.0 (found in", "the LICENSE-APACHE file).")):
                    return None
            expression, accounted = "Apache-2.0", {"MIT", "Apache-2.0", "BSD-3-Clause"}
            reason = "Every Rust member of this crate's src tree explicitly declares Apache-2.0 in its header, as does its package manifest. Retained workspace MIT and Chromium grant texts are not reassigned to these explicitly licensed files; separately inventoried AccessKit dependencies retain their own source grants."
        elif name == "rmcp":
            vcs = json.loads(source(".cargo_vcs_info.json"))
            if (vcs.get("git", {}).get("sha1") != "02c62aef2e331e5cf79c06c744eb1eb052cc8ebd"
                    or vcs.get("path_in_vcs") != "crates/rmcp"):
                return None
            candidates = [(path, value) for path, value in retained_sources if sha256_bytes(value) == RMCP_GRANT_SHA256]
            if len(candidates) != 1:
                return None
            path, value = candidates[0]
            proof.append({"path": path, "sha256": RMCP_GRANT_SHA256, "size": len(value),
                "source_url": "https://raw.githubusercontent.com/modelcontextprotocol/rust-sdk/" + vcs["git"]["sha1"] + "/LICENSE"})
            text = " ".join(value.decode("utf-8").split())
            if not all(clause in text for clause in (
                    'undergoing a licensing transition from the MIT License to the Apache License, Version 2.0',
                    'who have not yet granted explicit permission to relicense remain licensed under the MIT License.',
                    'Documentation contributions (excluding specifications) are licensed under CC-BY-4.0.',
                    'No rights beyond those granted by the applicable original license are conveyed')):
                return None
            expression, accounted = "Apache-2.0 AND MIT", {"Apache-2.0", "MIT"}
            reason = "The complete upstream transition notice explicitly retains MIT for unconsented contributions. Both code grants are retained conjunctively without assuming universal relicensing. The separate CC-BY-4.0 documentation statement remains in the notice; this runtime code proposal does not license documentation redistribution."
        elif name in {"accesskit", "accesskit_consumer", "accesskit_windows"}:
            paths = {"accesskit": ["src/lib.rs"], "accesskit_consumer": ["src/iterators.rs", "src/node.rs"],
                     "accesskit_windows": ["src/node.rs"]}[name]
            headers = [source(path) for path in paths]
            if not all("Derived from Chromium's accessibility abstraction." in text
                       and "found in the LICENSE.chromium file." in text for text in headers):
                return None
            if not {"MIT", "Apache-2.0", "BSD-3-Clause"} <= grants:
                return None
            expression, accounted = "Apache-2.0 AND BSD-3-Clause", {"MIT", "Apache-2.0", "BSD-3-Clause"}
            reason = "Named runtime source files explicitly retain Chromium's BSD grant in addition to AccessKit's Apache-or-MIT terms."
        elif name == "regex-syntax":
            source("src/unicode_tables/LICENSE-UNICODE")
            if not {"MIT", "Apache-2.0", "Unicode-DFS-2016"} <= grants:
                return None
            expression, accounted = "Apache-2.0 AND Unicode-DFS-2016", {"MIT", "Apache-2.0", "Unicode-DFS-2016"}
            reason = "The retained license in the Unicode table source subtree adds the Unicode data grant to the crate's Apache-or-MIT terms."
        elif name == "crossbeam-channel":
            text = source("README.md")
            if not all(item in text for item in ("#### Third party software", "[examples/matching.rs]",
                    "[tests/mpsc.rs]", "[tests/golang.rs]", "Copies of third party licenses can be found")):
                return None
            references = re.findall(r"\* \[([^]]+)\]", text.split("#### Third party software", 1)[1])
            if sorted(references) != ["examples/matching.rs", "tests/golang.rs", "tests/mpsc.rs"]:
                return None
            source("LICENSE-THIRD-PARTY")
            expression, accounted = base_expression, {"Apache-2.0", "MIT", "BSD-3-Clause"}
            reason = "Upstream maps the additional grant catalogue to examples/matching.rs, tests/mpsc.rs and tests/golang.rs, not the runtime library. All original notices remain retained."
        elif name == "ring":
            text = source("LICENSE-BoringSSL")
            if not all(item in text for item in ("Licenses for support code", "Parts of the TLS test suite are under the Go license",
                    "distributing code linked against BoringSSL does not trigger this license",
                    "The scripts which manage this, and the script for generating build metadata, are under the Chromium license")):
                return None
            expression, accounted = base_expression, {"Apache-2.0", "ISC", "BSD-3-Clause"}
            reason = "Upstream explicitly separates Go test-suite and Chromium build-infrastructure grants from linked BoringSSL code. The Apache and ISC runtime grants remain concluded."
        else:
            return None
    if grants - accounted:
        return None
    return {"archive_sha256": component["sha256"], "expression": expression,
            "accounted_grants": sorted(accounted), "source_files": proof, "reason": reason,
            "observed_cargo_features": cargo_features,
            "status": "source-scope-proposal-not-package-approval"}


def pe_imports(raw, architecture):
    require(len(raw) >= 64 and raw[:2] == b"MZ", "runtime member is not PE")
    offset = struct.unpack_from("<I", raw, 60)[0]
    require(offset + 264 <= len(raw) and raw[offset:offset + 4] == b"PE\0\0", "invalid runtime PE header")
    require(struct.unpack_from("<H", raw, offset + 4)[0] == {"x64": 0x8664, "arm64": 0xAA64}[architecture],
            "runtime PE architecture differs")
    optional = offset + 24
    require(struct.unpack_from("<H", raw, optional)[0] == 0x20B, "runtime PE is not 64-bit")
    sections = struct.unpack_from("<H", raw, offset + 6)[0]
    start = optional + struct.unpack_from("<H", raw, offset + 20)[0]
    require(start + sections * 40 <= len(raw), "runtime PE section table is truncated")

    def rva(value):
        for index in range(sections):
            size, address, raw_size, position = struct.unpack_from("<IIII", raw, start + index * 40 + 8)
            if address <= value < address + max(size, raw_size):
                result = position + value - address
                require(result < len(raw), "runtime import RVA is outside file")
                return result
        raise ValueError("unmapped runtime import RVA")

    require(not any(struct.unpack_from("<II", raw, optional + 216)), "runtime delayed imports need separate review")
    address = struct.unpack_from("<I", raw, optional + 120)[0]
    result = []
    if not address:
        return result
    position = rva(address)
    for _ in range(128):
        require(position + 20 <= len(raw), "runtime import table is truncated")
        fields = struct.unpack_from("<IIIII", raw, position)
        if not any(fields):
            return sorted(result)
        begin = rva(fields[3])
        end = raw.find(b"\0", begin, begin + 512)
        require(end >= 0, "runtime import name is unterminated")
        result.append(raw[begin:end].decode("ascii"))
        position += 20
    raise ValueError("runtime import table is unbounded")


def inspect_sources(components, cache, source_archives):
    result = {}
    for row in components:
        if row["kind"] != "cargo":
            continue
        key = (row["name"], row["version"])
        if key not in result:
            raw = read_owned(cache, row["name"] + "-" + row["version"] + ".crate")
            result[key] = inspect_archive(raw, row)
        require(result[key]["archive_sha256"] == row["sha256"], "crate evidence identity differs")
    workspace = []
    for filename, (digest, location) in WHEEL_SOURCES.items():
        raw = read_owned(source_archives, filename)
        row = {"name": filename, "version": "source-archive", "sha256": digest, "download_location": location}
        workspace.append(inspect_archive(raw, row))
    return result, workspace


def cfg_matches(expression, architecture):
    """Three-valued evaluation: unsupported/feature predicates remain possible."""
    if not expression.startswith("cfg("):
        return expression == architecture + "-pc-windows-msvc"
    tokens = re.findall(r'"[^"\\]*"|[A-Za-z_][A-Za-z_0-9]*|[(),=]', expression)
    position = 0
    values = {"target_os": "windows", "target_family": "windows", "target_env": "msvc",
              "target_arch": architecture, "target_pointer_width": "64", "target_endian": "little",
              "target_vendor": "pc"}

    def parse():
        nonlocal position
        require(position < len(tokens), "invalid source cfg")
        token = tokens[position]
        position += 1
        if position < len(tokens) and tokens[position] == "(":
            position += 1
            children = []
            while position < len(tokens) and tokens[position] != ")":
                children.append(parse())
                if position < len(tokens) and tokens[position] == ",":
                    position += 1
                elif position < len(tokens) and tokens[position] != ")":
                    raise ValueError("invalid source cfg separator")
            require(position < len(tokens), "invalid source cfg end")
            position += 1
            if token in ("cfg", "not"):
                require(len(children) == 1, "invalid unary source cfg")
                return children[0] if token == "cfg" or children[0] is None else not children[0]
            if token == "all":
                return False if False in children else None if None in children else True
            if token == "any":
                return True if True in children else None if None in children else False
            return None
        if position < len(tokens) and tokens[position] == "=":
            position += 1
            require(position < len(tokens), "invalid source cfg value")
            value = tokens[position].strip('"')
            position += 1
            return values[token] == value if token in values else None
        return {"windows": True, "unix": False}.get(token)

    result = parse()
    require(position == len(tokens), "unparsed source cfg")
    return result


def dependency_contexts(manifest, child_name, architecture):
    contexts = set()
    tables = [(None, manifest)] + list(manifest.get("target", {}).items())
    for target, table in tables:
        if target is not None and cfg_matches(target, architecture) is False:
            continue
        for group, context in (("dependencies", "target-link-relevant"),
                               ("build-dependencies", "build-or-generated-code"),
                               ("dev-dependencies", "development")):
            for alias, specification in table.get(group, {}).items():
                package = specification.get("package", alias) if isinstance(specification, dict) else alias
                if package == child_name:
                    contexts.add(context)
    return contexts


def nested_graph(sbom, manifests, architecture):
    root = sbom["metadata"]["component"]
    nodes = {row["bom-ref"]: row for row in [root, *sbom.get("components", [])]}
    edges = {row["ref"]: row.get("dependsOn", []) for row in sbom.get("dependencies", [])}
    found = defaultdict(set)
    missing = set()
    queue = deque([(root["bom-ref"], "target-link-relevant")])
    while queue:
        identifier, context = queue.popleft()
        if context in found[identifier]:
            continue
        found[identifier].add(context)
        row = nodes[identifier]
        manifest = manifests.get((row["name"], row.get("version")))
        for child_id in edges.get(identifier, []):
            require(child_id in nodes, "nested SBOM dependency is absent")
            child = nodes[child_id]
            child_manifest = manifests.get((child["name"], child.get("version")))
            if manifest is None:
                missing.add(identifier)
                child_contexts = {"source-edge-unresolved"}
            else:
                child_contexts = dependency_contexts(manifest, child["name"], architecture)
            if child_manifest and child_manifest.get("lib", {}).get("proc-macro"):
                child_contexts = {"build-or-generated-code"} if child_contexts else set()
            for child_context in child_contexts:
                if context in ("build-or-generated-code", "development", "source-edge-unresolved"):
                    child_context = context
                queue.append((child_id, child_context))
    return {identifier: sorted(contexts) for identifier, contexts in sorted(found.items())}, sorted(missing)


def classify_nested(packet, observations, workspace, architecture):
    import json
    manifests = {}
    for observation in [*observations.values(), *workspace]:
        workspace_packages = [manifest["workspace"].get("package", {})
                              for manifest in observation["manifests"].values() if "workspace" in manifest]
        # Published normalized Cargo.toml is preferred over Cargo.toml.orig.
        for path, manifest in observation["manifests"].items():
            if Path(path).name != "Cargo.toml":
                continue
            package = manifest.get("package", {})
            name, version = package.get("name"), package.get("version")
            if version == {"workspace": True}:
                versions = {row["version"] for row in workspace_packages if isinstance(row.get("version"), str)}
                require(len(versions) == 1, "workspace source version is ambiguous")
                version = next(iter(versions))
            if isinstance(name, str) and isinstance(version, str):
                manifests[(name, version)] = manifest
    graphs = {}
    contexts = defaultdict(set)
    for path, raw in list(packet.files.items()):
        if not path.startswith("nested-sboms/"):
            continue
        sbom = json.loads(raw)
        if "metadata" not in sbom or "component" not in sbom["metadata"] or "dependencies" not in sbom:
            continue
        if not any(row.get("purl", "").startswith("pkg:cargo/") for row in sbom.get("components", [])):
            continue
        graph, missing = nested_graph(sbom, manifests, architecture)
        graphs[path] = {"sha256": sha256_bytes(raw), "contexts": graph, "missing_source_manifests": missing}
        if not missing and all(row.get("purl", "").startswith("pkg:cargo/") for row in sbom.get("components", [])):
            parent_id = path.split("/")[1]
            parent = next((row for row in packet.evidence if row["id"] == parent_id), None)
            pending = next((row for row in packet.pending if row["id"] == parent_id), None)
            if parent is not None and pending is not None:
                parent.setdefault("classified_nested_catalogues", []).append({"path": path, "sha256": sha256_bytes(raw),
                    "scope": "Every retained Rust SBOM entry classified using source dependency kinds and target cfg; link relevance is conservative, not a binary symbol claim."})
                pending["items"] = [item for item in pending["items"] if item != "target-specific-nested-SBOM-scope"]
        for row in sbom.get("components", []):
            key = (row["name"], row.get("version"))
            contexts[key].update(graph.get(row["bom-ref"], ["not-target-reachable-in-source-graph"]))
    for row, evidence, pending in zip(packet.components, packet.evidence, packet.pending):
        if not row["id"].startswith("nested-"):
            continue
        found = sorted(contexts[(row["name"], row["version"])])
        evidence["source_graph_contexts"] = found
        if found and "source-edge-unresolved" not in found:
            evidence["scope"] = ("target-wheel-link-relevant" if "target-link-relevant" in found
                                 else "target-wheel-build-or-generated-code" if "build-or-generated-code" in found
                                 else "target-wheel-not-target-reachable")
            pending["items"] = [item for item in pending["items"] if item != "nested-build-versus-linked-scope"]
    packet.put("nested-source-scope.json", canonical_json({"schema": 1, "status": "source-observations-not-approval",
        "graphs": graphs, "limitation": "Exact wheel SBOM edges filtered by pinned source dependency kinds and Windows cfg. Optional feature edges are conservatively retained. Reachability is link relevance, not proof every symbol survives linking; generated-code obligations remain reviewable."}))


def map_wheel_native_sources(packet, architecture):
    records = []
    for path, raw in list(packet.files.items()):
        if not path.startswith("nested-sboms/wheel-cryptography-"):
            continue
        sbom = json.loads(raw)
        for subject in sbom.get("components", []):
            if subject.get("name") != "openssl" or not subject.get("purl", "").startswith("pkg:generic/openssl@"):
                continue
            source = next(row for row in packet.components if row["id"] == "native-cryptography-openssl")
            hashes = {row["content"] for row in subject["hashes"] if row["alg"] == "SHA-256"}
            urls = {row["url"] for row in subject["externalReferences"] if row["type"] == "distribution"}
            props = {row["name"]: row["value"] for row in subject.get("properties", [])}
            require(hashes == {source["sha256"]} and urls == {source["download_location"]}
                    and subject["version"] == source["version"], "wheel native source identity differs")
            require(props.get("build:operating-system") == "windows"
                    and props.get("build:architecture") == {"x64": "win64", "arm64": "arm64"}[architecture],
                    "wheel native source target differs")
            wheel_id = path.split("/")[1]
            wheel = next(row for row in packet.components if row["id"] == wheel_id)
            wheel_evidence = next(row for row in packet.evidence if row["id"] == wheel_id)
            observed = wheel_evidence.get("observed_native_members", {})
            require(bool(observed), "wheel native observed members are absent")
            record = {"component": source["id"], "source_sha256": source["sha256"],
                "source_url": source["download_location"], "wheel_sha256": wheel["sha256"],
                "producer_sbom": {"path": path, "sha256": sha256_bytes(raw)}, "build_properties": props,
                "observed_native_members": observed, "basis": "observed-wheel-producer-native-source-SBOM",
                "limitation": "Producer source/build declaration and exact installed wheel equality, not independent rebuild or symbol-by-symbol proof."}
            records.append(record)
            evidence = next(row for row in packet.evidence if row["id"] == source["id"])
            evidence.update(scope="native-source-declared-by-observed-wheel-SBOM", binary_mapping=record)
            pending = next(row for row in packet.pending if row["id"] == source["id"])
            pending["items"] = [item for item in pending["items"] if item != "target-binary-to-source-mapping"]
    packet.put("wheel-native-source-mapping.json", canonical_json({"schema": 1, "status": "source-observations-not-approval",
        "records": records, "limitation": "A missing target-wheel native catalogue is not filled from another architecture's catalogue or a package version string."}))


def nodriver_equality(packet, inputs, raw):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        source = {member.name.split("/", 1)[1]: archive.extractfile(member).read()
                  for member in archive.getmembers() if member.isfile() and "/nodriver/" in member.name}
    roots = [path for path in (inputs / "payload/lib/cua/environments").rglob("nodriver")
             if path.is_dir() and path.parent.name == "site-packages"]
    require(len(roots) == 1, "installed nodriver tree is ambiguous")
    observed = {"nodriver/" + path.relative_to(roots[0]).as_posix(): read_owned(roots[0], path.relative_to(roots[0]).as_posix())
                for path in roots[0].rglob("*") if path.is_file()}
    require(set(observed) == set(source), "nodriver source member set differs")
    require(all(value == source[name] for name, value in observed.items()), "nodriver installed source differs")
    packet.put("nodriver-source-equality.json", canonical_json({"schema": 1,
        "status": "exact-upstream-source-match-not-combination-approval", "source_archive_sha256": sha256_bytes(raw),
        "installed_root": roots[0].relative_to(inputs).as_posix(),
        "files": {name: sha256_bytes(value) for name, value in sorted(observed.items())},
        "limitation": "No nodriver source changes in the observed installed tree. This does not establish the AGPL boundary or Corresponding Source completeness of a larger combined work."}))


def map_python_native(packet, inputs, source, architecture):
    import json
    metadata_path = f"packaging/legal-review/supplement/sources/python/python-{architecture}/000-PYTHON.json"
    raw = read_owned(source, metadata_path)
    supplement = json.loads(read_owned(source, "packaging/legal-review/supplement/collection.json"))
    archive = next(row for row in supplement["groups"]["python"]["artifacts"] if row["architecture"] == architecture)
    proof = next(row for row in archive["sources"] if row["upstream_path"] == "python/PYTHON.json")
    require(sha256_bytes(raw) == proof["sha256"], "runtime source metadata identity differs")
    metadata = json.loads(raw)
    target = {"x64": "x86_64", "arm64": "aarch64"}[architecture] + "-pc-windows-msvc"
    require(metadata["target_triple"] == target and metadata["python_version"] == "3.12.14", "runtime source metadata differs")
    root = inputs / "payload/lib/cua/python/3.12.14"
    relationships = {}
    for identifier, extensions in {
        "native-bzip2": ["_bz2"], "native-expat": ["pyexpat"], "native-mpdecimal": ["_decimal"],
        "native-openssl-3.5": ["_ssl", "_hashlib"], "native-sqlite": ["_sqlite3"],
        "native-xz": ["_lzma"], "native-zlib": ["zlib"], "native-windows-libffi": ["_ctypes"],
        "native-tk-windows-bin-" + ("8612" if architecture == "x64" else "8614"): ["_tkinter"],
    }.items():
        records = [record for extension in extensions for record in metadata["build_info"]["extensions"][extension]]
        paths = set()
        imports = {}
        corrections = []
        for record in records:
            if record["in_core"]:
                paths.add("python312.dll")
            elif record.get("shared_lib"):
                paths.add(record["shared_lib"].removeprefix("install/"))
                name = record["shared_lib"].removeprefix("install/")
                imports[name] = pe_imports(read_owned(root, name), architecture)
            for link in record.get("links", []):
                if link.get("path_dynamic"):
                    name = link["path_dynamic"].removeprefix("install/")
                    if not (root / name).is_file():
                        require(identifier == "native-openssl-3.5", "producer native path is absent")
                        prefix = "libcrypto-3" if "libcrypto" in name else "libssl-3"
                        actual = {value for values in imports.values() for value in values if value.lower().startswith(prefix)}
                        require(len(actual) == 1, "actual OpenSSL import is ambiguous")
                        replacement = "DLLs/" + next(iter(actual))
                        corrections.append({"stale_producer_path": name, "actual_PE_import": replacement})
                        name = replacement
                    paths.add(name)
        binary = {"payload/lib/cua/python/3.12.14/" + path: sha256_bytes(read_owned(root, path)) for path in sorted(paths)}
        relationships[identifier] = {"basis": "pinned-producer-build-metadata-and-observed-installed-members",
            "extension_names": extensions, "producer_records": records, "observed_members": binary}
        relationships[identifier]["observed_PE_imports"] = imports
        relationships[identifier]["producer_metadata_corrections"] = corrections
        evidence = next(item for item in packet.evidence if item["id"] == identifier)
        evidence["scope"] = "runtime-native-source-mapped-by-producer-build-metadata"
        evidence["binary_mapping"] = relationships[identifier]
        pending = next(item for item in packet.pending if item["id"] == identifier)
        pending["items"] = [item for item in pending["items"] if item != "target-binary-to-source-mapping"]
    core = metadata["build_info"]["core"]
    require(core.get("shared_lib") == "install/python312.dll", "producer Python core mapping differs")
    for identifier, paths in {
        "native-cpython-3.12": ["python312.dll", "python.exe"],
        "runtime-cpython-3.12.14": sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()),
    }.items():
        relationships[identifier] = {"basis": "pinned-producer-core-metadata-and-exact-observed-runtime-tree",
            "producer_core_record": core,
            "observed_members": {"payload/lib/cua/python/3.12.14/" + path: sha256_bytes(read_owned(root, path)) for path in paths},
            "limitation": "Producer source/object mapping, not an unmodified-upstream or reproducible-build assertion. Third-party runtime components remain separately inventoried."}
        evidence = next(item for item in packet.evidence if item["id"] == identifier)
        evidence["scope"] = "runtime-native-source-mapped-by-producer-build-metadata"
        evidence["binary_mapping"] = relationships[identifier]
        pending = next(item for item in packet.pending if item["id"] == identifier)
        pending["items"] = [item for item in pending["items"] if item != "target-binary-to-source-mapping"]
    packet.put("python-native-source-mapping.json", canonical_json({"schema": 1,
        "status": "source-observations-not-approval", "target": target, "metadata_path": metadata_path,
        "metadata_sha256": sha256_bytes(raw), "components": relationships,
        "producer_full_archive_sha256": archive["sha256"],
        "limitation": "Producer-declared source/object relationships and exact observed binary identities. Not an independent bit-for-bit rebuild or a claim that optional dependencies from another platform ship."}))
