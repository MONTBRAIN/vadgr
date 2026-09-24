#!/usr/bin/env python3
"""Collect pinned upstream license evidence for review, without granting approval.

This source packet is not a package-input-inventory.json. License conclusions,
native subcomponents, source offers and redistribution duties require review.
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import email
import email.policy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tomllib
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename

from validate_package_inputs import canonical_json, relative_path, SOURCE_INPUTS, PackageInputError


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url):
    if not url.startswith("https://"):
        raise ValueError("HTTPS source required")
    request = urllib.request.Request(url, headers={"User-Agent": "vadgr-license-source-collector/1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def verified_archive(url, expected, path):
    data = path.read_bytes() if path.exists() else fetch(url)
    if digest(data) != expected:
        raise ValueError("archive digest mismatch")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(data)
    return data


def legal_members(data, filename):
    """Read legal files without extracting any archive paths to the filesystem."""
    result, names = {}, set()

    def accept(name, content):
        try:
            relative_path(name)
        except PackageInputError as error:
            raise ValueError("unsafe archive path") from error
        folded = name.casefold()
        if folded in names:
            raise ValueError("duplicate archive path")
        names.add(folded)
        base = PurePosixPath(name).name.lower()
        if (re.search(r"licen[cs]e|copying|copyright|notice|^[ou]fl(?:\.|$)|^unlicense$|^osmfeula", base)
                or ("fonts" in PurePosixPath(name).parts and base.endswith(".txt"))
                or "sbom" in name.lower()):
            if len(content) > 8 * 1024 * 1024:
                raise ValueError("oversized legal file")
            result[name] = content

    if filename.endswith((".zip", ".whl", ".nupkg")):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                if not member.is_dir():
                    accept(member.filename, archive.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive:
                if member.isfile():
                    accept(member.name, archive.extractfile(member).read())
    return result


def crate_source_identity(data):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        paths = [member for member in archive if member.name.endswith("/.cargo_vcs_info.json")]
        if len(paths) != 1:
            return None
        identity = json.loads(archive.extractfile(paths[0]).read())
    commit = identity.get("git", {}).get("sha1", "")
    path = identity.get("path_in_vcs", "")
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("invalid upstream commit")
    if path:
        relative_path(path)
    return commit, path


@lru_cache(maxsize=128)
def upstream_licenses(repository, commit, folder):
    match = re.fullmatch(r"https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?(?:/tree/[^?#]+)?/?", repository or "")
    if not match:
        return {}
    project = match[1]
    folders = [folder, *[str(parent) for parent in PurePosixPath(folder).parents]] if folder else ["."]
    result = {}
    for parent in folders:
        suffix = "" if parent == "." else "/" + parent
        api_path = f"repos/{project}/contents{suffix}?ref={commit}"
        process = subprocess.run(["gh", "api", api_path], capture_output=True, check=False)
        if process.returncode:
            continue
        for entry in json.loads(process.stdout):
            if entry.get("type") != "file" or not re.search(r"licen[cs]e|copying|copyright|notice", entry["name"], re.I):
                continue
            url = f"https://raw.githubusercontent.com/{project}/{commit}/{entry['path']}"
            result[url] = fetch(url)
    return result


def cargo_closure(resolve):
    nodes = {node["id"]: node for node in resolve["nodes"]}
    pending, seen = [resolve["root"]], set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(dep["pkg"] for dep in nodes[current]["deps"]
                       if any(kind["kind"] != "dev" for kind in dep["dep_kinds"]))
    return seen


def select_wheel(files, hashes, platform):
    tags = list(cpython_tags((3, 12), platforms=[platform]))
    tags += list(compatible_tags((3, 12), interpreter="cp312", platforms=[platform]))
    priority = {tag: index for index, tag in enumerate(tags)}
    candidates = []
    for item in files:
        if not item["filename"].endswith(".whl") or item["digests"]["sha256"] not in hashes:
            continue
        wheel_tags = parse_wheel_filename(item["filename"])[3]
        scores = [priority[tag] for tag in wheel_tags if tag in priority]
        if scores:
            candidates.append((min(scores), item["filename"], item))
    if not candidates:
        raise ValueError("no locked wheel for target")
    return min(candidates, key=lambda item: item[:2])[2]


def wheel_license_metadata(data):
    metadata = email.message_from_bytes(data, policy=email.policy.default)
    declared = metadata.get("License-Expression") or metadata.get("License")
    return {"license_declared": str(declared) if declared is not None else None,
            "license_classifiers": [str(value) for value in metadata.get_all("Classifier", []) if str(value).startswith("License ::")],
            "declared_license_files": [str(value) for value in metadata.get_all("License-File", [])]}


def wheel_metadata_headers(data):
    for boundary in (b"\r\n\r\n", b"\n\n"):
        if boundary in data:
            return data.split(boundary, 1)[0] + boundary
    return data


def record_component(root, identifier, name, version, kind, url, data, declared, sources):
    records = []
    for index, (original, content) in enumerate(sorted(sources.items())):
        suffix = re.sub(r"[^A-Za-z0-9._-]", "_", PurePosixPath(original).name)
        path = f"sources/{identifier}/{index:03d}-{suffix}"
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            output.write(content)
        records.append({"upstream_path": original, "path": path, "sha256": digest(content)})
    return {"id": identifier, "name": name, "version": version, "kind": kind,
            "download_location": url, "sha256": digest(data), "license_declared": declared,
            "license_concluded": None, "review_status": "unreviewed", "source_files": records}


def cargo_components(repo, root, cache, target):
    packages = {}
    for manifest, features in (("Cargo.toml", ["--features", "native-gui"]),
                               ("packaging/windows/ba-functions/Cargo.toml", [])):
        command = ["cargo", "metadata", "--locked", "--format-version", "1", "--filter-platform", target,
                   "--manifest-path", str(repo / manifest), *features]
        metadata = json.loads(subprocess.check_output(command, cwd=repo))
        selected = cargo_closure(metadata["resolve"])
        for item in metadata["packages"]:
            if item["id"] in selected and item["source"] is not None:
                packages[(item["name"], item["version"])] = item
    locked = {}
    for name in ("Cargo.lock", "packaging/windows/ba-functions/Cargo.lock"):
        for item in tomllib.loads((repo / name).read_text(encoding="utf-8"))["package"]:
            if "checksum" in item:
                locked[(item["name"], item["version"])] = item["checksum"]

    def component(pair):
        (name, version), metadata = pair
        if metadata["source"] != "registry+https://github.com/rust-lang/crates.io-index":
            raise ValueError("unhandled Cargo source")
        filename = f"{name}-{version}.crate"
        url = f"https://static.crates.io/crates/{name}/{filename}"
        local = list(cache.glob(f"registry/cache/*/{filename}"))
        path = local[0] if local else root / "archives" / filename
        data = verified_archive(url, locked[(name, version)], path)
        sources = legal_members(data, filename)
        identity = crate_source_identity(data)
        if not any(len(PurePosixPath(name).parts) == 2 for name in sources) and identity:
            sources.update(upstream_licenses(metadata.get("repository"), *identity))
        result = record_component(root, f"cargo-{name}-{version}", name, version, "cargo", url,
                                  data, metadata["license"], sources)
        result["upstream_commit"] = identity[0] if identity else None
        return result

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(component, sorted(packages.items())))


def wheel_components(repo, root, platform, failures):
    lock = (repo / "packaging/cua/requirements.lock").read_text(encoding="utf-8").replace("\\\n", " ")
    environment = default_environment()
    environment.update(sys_platform="win32", os_name="nt", platform_system="Windows",
                       platform_machine="ARM64" if platform == "win_arm64" else "AMD64",
                       python_version="3.12", python_full_version="3.12.14",
                       implementation_name="cpython", platform_python_implementation="CPython")
    requirements = []
    for line in lock.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        spec = line.split(" --hash=", 1)[0].strip()
        requirement = Requirement(spec)
        if requirement.marker is None or requirement.marker.evaluate(environment):
            requirements.append((requirement, set(re.findall(r"--hash=sha256:([a-f0-9]{64})", line))))

    def component(pair):
        requirement, hashes = pair
        version = next(iter(requirement.specifier)).version
        release = json.loads(fetch(f"https://pypi.org/pypi/{requirement.name}/{version}/json"))
        wheel = select_wheel(release["urls"], hashes, platform)
        data = verified_archive(wheel["url"], wheel["digests"]["sha256"], root / "archives" / wheel["filename"])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            metadata_paths = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata_paths) != 1:
                raise ValueError("ambiguous wheel metadata")
            metadata_bytes = archive.read(metadata_paths[0])
        metadata = wheel_license_metadata(metadata_bytes)
        sources = legal_members(data, wheel["filename"])
        sources[metadata_paths[0]] = wheel_metadata_headers(metadata_bytes)
        result = record_component(root, f"wheel-{requirement.name}-{version}", requirement.name, version,
                                  "wheel", wheel["url"], data, metadata["license_declared"], sources)
        result.update(metadata)
        result["metadata_scope"] = "Exact METADATA header block; unrelated description body excluded."
        return result

    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(component, pair): pair[0].name for pair in requirements}
        result = []
        for future in as_completed(pending):
            try:
                result.append(future.result())
            except (ValueError, OSError) as error:
                failures.append({"kind": "wheel", "name": pending[future], "error": type(error).__name__, "detail": str(error)})
        return result


def runtime_component(repo, root, target):
    pins = tomllib.loads((repo / "packaging/cua/pins.toml").read_text(encoding="utf-8"))
    filename = f"cpython-{pins['python']}+{pins['python_build']}-{target}-install_only.tar.gz"
    url = f"https://github.com/astral-sh/python-build-standalone/releases/download/{pins['python_build']}/{filename}"
    data = verified_archive(url, pins["targets"][target]["python_sha256"], root / "archives" / filename)
    return record_component(root, "runtime-cpython-" + pins["python"], "CPython standalone", pins["python"],
                            "runtime", url, data, None, legal_members(data, filename))


def nuget_metadata(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".nuspec")]
        if len(names) != 1:
            raise ValueError("ambiguous NuGet metadata")
        return names[0], archive.read(names[0])


def framework_components(repo, root, nuget_home):
    version = json.loads((repo / "packaging/toolchain.json").read_bytes())["wix"]
    results = []
    for name in ("wixtoolset.sdk", "wixtoolset.bal.wixext", "wixtoolset.util.wixext"):
        filename = f"{name}.{version}.nupkg"
        local = nuget_home / name / version / filename
        data = local.read_bytes()
        recorded = base64.b64decode(local.with_suffix(".nupkg.sha512").read_bytes())
        if hashlib.sha512(data).digest() != recorded:
            raise ValueError("NuGet cache digest mismatch")
        url = f"https://api.nuget.org/v3-flatcontainer/{name}/{version}/{filename}"
        upstream = fetch(url)
        if upstream != data:
            raise ValueError("NuGet upstream digest mismatch")
        sources = legal_members(data, filename)
        nuspec_name, nuspec = nuget_metadata(data)
        sources[nuspec_name] = nuspec
        document = ET.fromstring(nuspec)
        repository = next(element for element in document.iter() if element.tag.endswith("}repository"))
        commit = repository.attrib["commit"]
        license_url = f"https://raw.githubusercontent.com/wixtoolset/wix/{commit}/LICENSE.TXT"
        sources[license_url] = fetch(license_url)
        item = record_component(root, f"framework-{name}-{version}", name, version, "framework", url,
                                data, "MS-RL", sources)
        item["upstream_commit"] = commit
        results.append(item)
    return results


def rust_standard_library(repo, root, target):
    details = subprocess.check_output(["rustc", "-vV"], text=True)
    version = re.search(r"^release: (.+)$", details, re.M)[1]
    commit = re.search(r"^commit-hash: (.+)$", details, re.M)[1]
    workflow = (repo / ".github/workflows/candidate.yml").read_text(encoding="utf-8")
    if f"toolchain: {version}" not in workflow:
        raise ValueError("host Rust version differs from candidate pin")
    sysroot = Path(subprocess.check_output(["rustc", "--print", "sysroot"], text=True).strip())
    documentation = sysroot / "share/doc/rust"
    sources = {"rust-distribution/share/doc/rust/COPYRIGHT-library.html": (documentation / "COPYRIGHT-library.html").read_bytes()}
    sources.update({"rust-distribution/share/doc/rust/licenses/" + path.name: path.read_bytes()
                    for path in (documentation / "licenses").iterdir() if path.is_file()})
    filename = f"rust-std-{version}-{target}.tar.xz"
    url = "https://static.rust-lang.org/dist/" + filename
    expected = fetch(url + ".sha256").decode().split()[0]
    data = verified_archive(url, expected, root / "archives" / filename)
    result = record_component(root, "runtime-rust-std-" + version, "Rust standard library", version, "runtime",
                              url, data, "MIT OR Apache-2.0", sources)
    result["upstream_commit"] = commit
    result["license_source"] = "Exact matching installed Rust toolchain redistribution notices"
    return result


def write_draft_sbom(root, report):
    packages = []
    for component in report["components"]:
        packages.append({"SPDXID": "SPDXRef-" + component["id"], "name": component["name"],
                         "versionInfo": component["version"], "downloadLocation": component["download_location"],
                         "filesAnalyzed": False, "licenseConcluded": "NOASSERTION", "licenseDeclared": "NOASSERTION",
                         "copyrightText": "NOASSERTION",
                         "checksums": [{"algorithm": "SHA256", "checksumValue": component["sha256"]}]})
    sbom = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": "vadgr-unreviewed-source-inventory-" + report["target"],
            "documentNamespace": "https://spdx.org/spdxdocs/vadgr-source-review-" + digest(canonical_json(report)),
            "creationInfo": {"created": report["created"], "creators": ["Tool: vadgr-license-source-collector"]},
            "documentComment": "Unreviewed source evidence. Not a complete shipped inventory or legal approval.",
            "packages": packages,
            "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES",
                               "relatedSpdxElement": item["SPDXID"]} for item in packages]}
    (root / "unreviewed.spdx.json").write_bytes(canonical_json(sbom))


def collect(repo, root, cargo_home, target, nuget_home=None):
    if root.exists():
        raise ValueError("output already exists")
    root.mkdir(parents=True)
    report = {"schema": 1, "status": "incomplete", "target": target,
              "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "scope": "upstream license evidence; includes Cargo build dependencies",
              "source_inputs": {name: digest((repo / name).read_bytes()) for name in (*SOURCE_INPUTS, "Cargo.toml", "packaging/windows/ba-functions/Cargo.toml", "packaging/windows/ba-functions/Cargo.lock")},
              "public_text_sources": {path.name: digest(path.read_bytes()) for path in sorted((repo / "packaging/legal").glob("*.txt"))},
              "components": [], "failures": [],
              "outstanding_review": ["Classify shipped and build-only components.",
                                     "Review nested native libraries, fonts and assets.",
                                     "Conclude each license and reproduce required copyrights and notices.",
                                     "Resolve source-code distribution and source-offer duties.",
                                     "Review WiX and Rust standard-library redistribution.",
                                     "Bind final package bytes and obtain separate legal approval."]}
    steps = [("cargo", lambda: cargo_components(repo, root, cargo_home, target)),
             ("wheel", lambda: wheel_components(repo, root, "win_arm64" if target.startswith("aarch64") else "win_amd64", report["failures"])),
             ("runtime", lambda: [runtime_component(repo, root, target)]),
             ("rust-standard-library", lambda: [rust_standard_library(repo, root, target)])]
    if nuget_home:
        steps.append(("framework", lambda: framework_components(repo, root, nuget_home)))
    for kind, step in steps:
        try:
            report["components"].extend(step())
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            report["failures"].append({"kind": kind, "error": type(error).__name__, "detail": str(error)})
        report["components"].sort(key=lambda item: item["id"])
        (root / "collection.json").write_bytes(canonical_json(report))
        write_draft_sbom(root, report)
        print(f"{target}: {kind}: {len(report['components'])} components; {len(report['failures'])} failures", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--nuget-home", type=Path)
    parser.add_argument("--target", choices=["x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc"], required=True)
    args = parser.parse_args()
    report = collect(args.source_root.resolve(), args.output.resolve(), args.cargo_home.resolve(), args.target,
                     args.nuget_home.resolve() if args.nuget_home else None)
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
