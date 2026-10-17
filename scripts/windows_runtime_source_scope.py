"""Pinned source facts for runtime review, without license or approval decisions."""

import io
from pathlib import PurePosixPath
import posixpath
import re
import tarfile
import tomllib

if __package__:
    from scripts.validate_package_inputs import canonical_json, read_owned, relative_path, require, sha256_bytes
    from scripts.windows_legal_source_evidence import cfg_matches
else:
    from validate_package_inputs import canonical_json, read_owned, relative_path, require, sha256_bytes
    from windows_legal_source_evidence import cfg_matches


BOUNDARY = {"status": "unapproved", "candidate_approval": False, "publishable": False}
PILLOW_ARCHIVE = "pillow-12.3.0.tar.gz"
PILLOW_SHA256 = "3b8182a766685eaa002637e28b4ec8d6b18819a0c71f579bf0dbaa5830297cce"
PILLOW_URL = "https://files.pythonhosted.org/packages/1c/3d/bb7fca845737cf9d7dbde16ed1843984665ff2e0a518f5db43e77ec540b9/pillow-12.3.0.tar.gz"


def identity(raw):
    return {"size": len(raw), "sha256": sha256_bytes(raw)}


def archive_members(raw, expected):
    require(sha256_bytes(raw) == expected, "runtime source archive digest differs")
    result, seen, total = {}, set(), 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
        for member in archive:
            relative_path(member.name)
            require(member.name.casefold() not in seen and (member.isfile() or member.isdir()),
                    "unsafe runtime source archive member")
            seen.add(member.name.casefold())
            if member.isfile():
                total += member.size
                require(member.size < 32 * 1024 * 1024 and total < 500 * 1024 * 1024 and len(seen) < 50000,
                        "oversized runtime source member set")
                result[member.name] = archive.extractfile(member).read()
    require(result and sum(map(len, result.values())) < 500 * 1024 * 1024, "runtime source archive is empty or too large")
    return result


def pillow_source_scope(record, catalogue, raw):
    require(record["pillow"]["probe"]["pillow"] == "12.3.0"
            and catalogue["metadata"]["component"]["version"] == "12.3.0", "unsupported Pillow source version")
    members = archive_members(raw, PILLOW_SHA256)
    prefix = "pillow-12.3.0/"
    paths = ("pyproject.toml", "setup.py", "src/_imagingft.c", "src/_imagingcms.c",
             "src/thirdparty/pythoncapi_compat.h", "src/thirdparty/fribidi-shim/fribidi.c")
    source = {path: members[prefix + path] for path in paths}
    rows = {row["bom-ref"]: row for row in catalogue["components"]}
    require(len(rows) == len(catalogue["components"]), "duplicate Pillow source catalogue reference")
    for reference, path in (("pkg:github/python/pythoncapi-compat", "src/thirdparty/pythoncapi_compat.h"),
                            ("pkg:pypi/pillow@12.3.0#thirdparty/fribidi-shim", "src/thirdparty/fribidi-shim/fribidi.c")):
        require(rows[reference]["hashes"] == [{"alg": "SHA-256", "content": sha256_bytes(source[path])}],
                "Pillow vendored source differs from observed catalogue")
    pybind = rows["pkg:pypi/pybind11"]
    require(pybind.get("scope") == "excluded" and "build-time dependency" in pybind["description"],
            "Pillow pybind11 declared scope differs")
    native = {path: value for path, value in record["pillow"]["files"].items()
              if PurePosixPath(path).name.startswith("_imagingft.") and path.endswith(".pyd")}
    require(len(native) == 1, "Pillow font extension source binding is ambiguous")
    scanned = {name: identity(value) for name, value in members.items()
               if PurePosixPath(name).suffix in {".py", ".pyi", ".c", ".h", ".cpp", ".hpp", ".toml"}}
    mentions = sorted(name for name in scanned if b"pybind11" in members[name])
    require(mentions == [prefix + "pyproject.toml", prefix + "setup.py"]
            and b"from pybind11.setup_helpers import ParallelCompile" in source["setup.py"]
            and b'ParallelCompile("MAX_CONCURRENCY", default).install()' in source["setup.py"],
            "Pillow pybind11 source use differs")
    require(b'#include "thirdparty/pythoncapi_compat.h"' in source["src/_imagingft.c"]
            and b"have_raqm = !!p_fribidi;" in source["src/_imagingft.c"]
            and b"vn = cmsGetEncodedCMMversion();" in source["src/_imagingcms.c"], "Pillow source review basis differs")
    facts = {
        "pkg:pypi/pybind11": {
            "classification": "upstream-declared-build-only-compilation-helper",
            "basis": "The observed wheel catalogue excludes this build-time dependency. The exact source uses only ParallelCompile in setup.py; no native or Python module source in this sdist mentions pybind11."},
        "pkg:github/python/pythoncapi-compat": {
            "classification": "source-header-relevant-to-installed-font-extension",
            "observed_native_members": native,
            "basis": "The catalogue pins the exact header. The font extension includes it unconditionally. This does not assert every inline function survived compilation."},
        "pkg:pypi/pillow@12.3.0#thirdparty/fribidi-shim": {
            "classification": "conditional-native-loader-needs-build-or-symbol-evidence",
            "basis": "A compiled shim can report HAVE_RAQM, HAVE_FRIBIDI and HAVE_HARFBUZZ false when its optional DLL does not load. The probe cannot establish absence of shim, Raqm or HarfBuzz code."}}
    return {"schema": 1, **BOUNDARY, "target": record["target"],
        "source_archive": {"filename": PILLOW_ARCHIVE, "url": PILLOW_URL, **identity(raw)},
        "reviewed_source_files": {name: {**identity(value), "text": value.decode("utf-8")} for name, value in source.items()},
        "scanned_source_members": scanned, "pybind11_mentions": mentions, "components": facts,
        "littlecms_version_boundary": "The probe formats cmsGetEncodedCMMversion(). 2.19.1 in the catalogue versus 2.19 in the binary remains a source/build identity question; neither value is normalized.",
        "limitation": "Exact source and catalogue facts, not wheel build attestation, complete native linkage, license choice, source completeness or approval."}


def rust_source_scope(record, binding, manifest_raw, raw):
    channel = tomllib.loads(manifest_raw.decode("utf-8"))
    descriptor = channel["pkg"]["rust-src"]["target"]["*"]
    require(descriptor.get("available") is True and descriptor["xz_url"].startswith("https://static.rust-lang.org/dist/"),
            "Rust source distribution identity differs")
    members = archive_members(raw, descriptor["xz_hash"])
    manifests = {}
    for name, data in members.items():
        if "/library/" in name and name.endswith("/Cargo.toml"):
            document = tomllib.loads(data.decode("utf-8"))
            if isinstance(document.get("package", {}).get("name"), str):
                manifests[name] = document
    references = set()
    for name, document in manifests.items():
        if document["package"]["name"] not in {"core", "alloc", "std"}:
            continue
        for group in ("dependencies",):
            for dependency in document.get(group, {}).values():
                if isinstance(dependency, dict) and isinstance(dependency.get("path"), str):
                    references.add(posixpath.normpath(str(PurePosixPath(name).parent / dependency["path"] / "Cargo.toml")))
    rows = {}
    for name, library in binding["library_scope"].items():
        match = re.fullmatch(r"(?:lib)?([a-z0-9_]+)-[a-f0-9]+\.(rlib|rmeta|dll|dll\.lib|pdb)", name)
        require(match is not None, "unknown Rust target library naming")
        package = match[1]
        candidates = [path for path, document in manifests.items()
                      if document.get("lib", {}).get("name", document["package"]["name"].replace("-", "_")) == package]
        if len(candidates) > 1:
            candidates = [path for path in candidates if path in references]
        require(len(candidates) == 1, "Rust library source package is ambiguous")
        path = candidates[0]
        document = manifests[path]
        table = document["package"]
        dependencies = []
        for target, context in [(None, document), *document.get("target", {}).items()]:
            applies = True if target is None else cfg_matches(target, record["target"].split("-", 1)[0])
            for group in ("dependencies", "build-dependencies", "dev-dependencies"):
                for alias, specification in context.get(group, {}).items():
                    dependencies.append({"name": alias, "kind": group, "target": target,
                        "target_predicate_matches": applies, "specification": specification})
        rows[name] = {**library, "source_manifest": {"path": path, **identity(members[path])},
            "package_name": table["name"], "package_version": table.get("version"),
            "license_declared": table.get("license"), "artifact_kind": match[2],
            "dependencies": dependencies}
    retained = {row["source_manifest"]["path"] for row in rows.values()}
    return {"schema": 1, **BOUNDARY, "target": record["target"],
        "channel_manifest_sha256": sha256_bytes(manifest_raw), "target_binding_sha256": sha256_bytes(canonical_json(binding)),
        "source_archive": {"url": descriptor["xz_url"], **identity(raw)}, "libraries": rows,
        "source_manifests": {path: {**identity(members[path]), "text": members[path].decode("utf-8")} for path in sorted(retained)},
        "limitation": "Every observed target library maps to one source package in the same pinned release. Public-symbol references are positive linkage evidence only. Dependency predicates do not resolve optional features, generated code, individual source exceptions, or third-party grant scope. No absence or legal approval follows from a missing symbol."}


def retain_source_scope(packet, inputs, record, catalogue, binding, archive_root, manifest_path):
    pillow = pillow_source_scope(record, catalogue, read_owned(archive_root, PILLOW_ARCHIVE))
    manifest_raw = read_owned(inputs, manifest_path)
    descriptor = tomllib.loads(manifest_raw.decode("utf-8"))["pkg"]["rust-src"]["target"]["*"]
    rust = rust_source_scope(record, binding, manifest_raw, read_owned(archive_root, descriptor["xz_url"].rsplit("/", 1)[-1]))
    packet.put("pillow-source-scope.json", canonical_json(pillow))
    packet.put("rust-source-package-scope.json", canonical_json(rust))
    for prefix, filename in (("wheel-pillow-", "pillow-source-scope.json"),
                             ("runtime-rust-std-", "rust-source-package-scope.json")):
        evidence = [row for row in packet.evidence if row["id"].startswith(prefix)]
        require(len(evidence) == 1, "runtime source scope component is ambiguous")
        evidence[0]["source_scope_observation"] = {"path": filename, "sha256": sha256_bytes(packet.files[filename]),
            "scope": "exact-source-and-native-observation-facts-not-license-approval"}
