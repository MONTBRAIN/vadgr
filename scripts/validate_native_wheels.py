#!/usr/bin/env python3
"""Validate native dependency artifacts as data, without importing their code."""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile

REPOSITORY = "MONTBRAIN/vadgr"
WORKFLOW = ".github/workflows/native-wheels.yml"
TARGETS = {"windows-aarch64": "win_arm64", "macos-x86_64": "macosx_13_0_x86_64"}
SOURCE_SHA256 = "5dd9bda1c12b4162f6ff568eeb5e0ff956c28d14406e875cfe8a63a2d414ff20"
OPENSSL_SHA256 = "736b467530f916737b7031310ccb21d8218c6229e61e8e160cd1d3458cd543a8"
HASH = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024


class Refused(ValueError):
    """The input is not a qualified native dependency."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return (json.dumps(data, sort_keys=True, indent=2) + "\n").encode()


def recipe_digest(path):
    return digest(path.read_text(encoding="utf-8").encode())


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 16 * 1024 * 1024,
            "JSON input missing, linked or oversized")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def safe_name(name):
    require(isinstance(name, str) and name and "\\" not in name, "unsafe member path")
    parts = name.rstrip("/").split("/")
    for part in parts:
        require(part not in ("", ".", "..") and not part.endswith((" ", "."))
                and not re.search(r'[\x00-\x1f\x7f:$!;<>|"?*]', part)
                and not re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part),
                "unsafe member path")
    return name


def validate_descriptor(data):
    require(data.get("schema") == 1 and set(data.get("targets", {})) == set(TARGETS),
            "unsupported descriptor or target matrix")
    source, ssl, rust = data["cryptography"], data["openssl"], data["rust"]
    require(source.get("version") == "50.0.1" and source.get("sha256") == SOURCE_SHA256
            and source.get("commit") == "ffde75a2b594822c740a2e4748b56c00548302bf",
            "unreviewed cryptography source")
    require(ssl.get("version") == "4.0.2" and ssl.get("sha256") == OPENSSL_SHA256,
            "unreviewed OpenSSL source")
    require(rust.get("version") == "1.97.1" and rust.get("manifest_sha256") ==
            "03569b1886ceb5c05276b50c8431ab111de944cd6140fe1fa7d821dd8e0f29cf",
            "unreviewed Rust toolchain")
    rows = [source, ssl]
    for target, configuration in data["targets"].items():
        expected = ("windows-11-arm", "aarch64-pc-windows-msvc") if target.startswith("windows") else (
            "macos-15-intel", "x86_64-apple-darwin")
        require((configuration.get("runner"), configuration.get("rust_target")) == expected,
                "native runner or target mismatch")
        require(configuration.get("images") and configuration["python"].get("version") == "3.12.14"
                and configuration["uv"].get("version") == "0.12.7", "unreviewed runtime/tool pin")
        names = [row["name"] for row in configuration["python_dependencies"]]
        require(len(names) == len(set(names)) and {"maturin", "cffi", "pytest", "cryptography_vectors"} <= set(names),
                "incomplete or duplicate build closure")
        rows += [configuration["python"], configuration["uv"], *configuration["python_dependencies"]]
    for row in rows:
        require(HASH.fullmatch(row.get("sha256", "")), "invalid input digest")
        safe_name(row.get("filename"))
        require("/" not in row["filename"], "input filename is not a basename")
        url = urlsplit(row.get("url", ""))
        require(url.scheme == "https" and url.hostname in ("github.com", "files.pythonhosted.org")
                and not url.username and not url.password and not url.query and not url.fragment,
                "unreviewed input origin")


def archive_members(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_ARCHIVE,
            "archive absent, linked or oversized")
    contents, seen, total = {}, set(), 0
    with zipfile.ZipFile(path) as archive:
        require(len(archive.infolist()) <= 5000, "too many archive members")
        for info in archive.infolist():
            safe_name(info.filename)
            normalized = info.filename.rstrip("/").casefold()
            require(normalized not in seen, "duplicate or case-colliding archive member")
            seen.add(normalized)
            kind = stat.S_IFMT(info.external_attr >> 16)
            require(kind in (0, stat.S_IFREG, stat.S_IFDIR) and not info.flag_bits & 1
                    and not info.external_attr & 0x400, "archive link or unsupported member")
            if info.is_dir():
                continue
            total += info.file_size
            require(total <= MAX_EXPANDED, "expanded archive limit exceeded")
            data = archive.read(info)
            require(len(data) == info.file_size, "archive size mismatch")
            contents[info.filename] = data
    return contents


def native_imports(data, target):
    require(len(data) >= 64, "truncated native member")
    imports = []
    if target == "windows-aarch64":
        require(data[:2] == b"MZ", "native member is not PE")
        offset = struct.unpack_from("<I", data, 0x3c)[0]
        require(offset + 264 <= len(data) and data[offset:offset + 4] == b"PE\0\0", "invalid PE header")
        require(struct.unpack_from("<H", data, offset + 4)[0] == 0xAA64, "non-native PE architecture")
        optional = offset + 24
        require(struct.unpack_from("<H", data, optional)[0] == 0x20B, "PE is not 64-bit")
        require(struct.unpack_from("<H", data, offset + 20)[0] >= 240,
                "truncated PE optional header")
        require(not any(struct.unpack_from("<II", data, optional + 216)),
                "unreviewed PE delayed imports")
        sections = struct.unpack_from("<H", data, offset + 6)[0]
        start = optional + struct.unpack_from("<H", data, offset + 20)[0]
        require(start + sections * 40 <= len(data), "invalid PE section table")

        def rva(value):
            for i in range(sections):
                size, address, raw_size, raw = struct.unpack_from("<IIII", data, start + i * 40 + 8)
                if address <= value < address + max(size, raw_size):
                    position = raw + value - address
                    require(position < len(data), "PE RVA outside file")
                    return position
            raise Refused("unmapped PE import RVA")

        import_rva = struct.unpack_from("<I", data, optional + 120)[0]
        if import_rva:
            position = rva(import_rva)
            for _ in range(128):
                require(position + 20 <= len(data), "truncated PE import table")
                fields = struct.unpack_from("<IIIII", data, position)
                if not any(fields):
                    break
                name_start = rva(fields[3])
                end = data.find(b"\0", name_start, name_start + 512)
                require(end >= 0, "unterminated PE import")
                imports.append(data[name_start:end].decode("ascii"))
                position += 20
            else:
                raise Refused("unbounded PE import table")
    else:
        require(data[:4] == b"\xcf\xfa\xed\xfe" and struct.unpack_from("<I", data, 4)[0] == 0x1000007,
                "non-native Mach-O architecture")
        count, commands_size = struct.unpack_from("<II", data, 16)
        require(count < 4096 and 32 + commands_size <= len(data), "invalid Mach-O command table")
        position, floor = 32, None
        for _ in range(count):
            require(position + 8 <= 32 + commands_size, "truncated Mach-O command")
            command, size = struct.unpack_from("<II", data, position)
            require(size >= 8 and position + size <= 32 + commands_size, "invalid Mach-O command size")
            if command & 0x7fffffff in (0xC, 0x18, 0x1F, 0x23):
                require(size >= 24, "truncated dylib command")
                name_offset = struct.unpack_from("<I", data, position + 8)[0]
                require(24 <= name_offset < size, "invalid dylib name offset")
                name = data[position + name_offset:position + size].split(b"\0", 1)[0]
                imports.append(name.decode("utf-8"))
            if command == 0x32:
                require(size >= 24, "truncated build version")
                require(struct.unpack_from("<I", data, position + 8)[0] == 1, "native member is not macOS")
                floor = struct.unpack_from("<I", data, position + 12)[0]
            if command == 0x24:
                require(size >= 16, "truncated deployment version")
                floor = struct.unpack_from("<I", data, position + 8)[0]
            position += size
        require(floor is not None and floor <= (13 << 16), "macOS deployment floor raised")
    require(not any(re.search(r"(?i)(libcrypto|libssl|openssl)", value) for value in imports),
            "external OpenSSL dependency")
    return imports


def inspect_wheel(path, target):
    require(target in TARGETS, "unsupported native target")
    expected = f"cryptography-50.0.1-cp311-abi3-{TARGETS[target]}.whl"
    require(path.name == expected, "wheel filename or ABI does not match target")
    members = archive_members(path)
    prefix = "cryptography-50.0.1.dist-info/"
    require(all(name.startswith(("cryptography/", prefix)) for name in members), "unexpected wheel package member")
    require(prefix + "METADATA" in members and prefix + "WHEEL" in members, "wheel metadata absent")
    metadata = email.message_from_bytes(members[prefix + "METADATA"])
    wheel = email.message_from_bytes(members[prefix + "WHEEL"])
    require(metadata.get_all("Name") == ["cryptography"] and metadata.get_all("Version") == ["50.0.1"],
            "wheel package identity mismatch")
    require(wheel.get_all("Tag") == [f"cp311-abi3-{TARGETS[target]}"], "wheel tags mismatch")
    native = sorted(name for name in members if name.endswith((".pyd", ".so", ".dll", ".dylib")))
    require(native and any("_rust" in name for name in native), "wheel native binding missing")
    imports = {name: native_imports(members[name], target) for name in native}
    return {"filename": path.name, "sha256": digest(path.read_bytes()), "size": path.stat().st_size,
            "native_members": native, "imports": imports}


def test_counts(data):
    require(len(data) < 128 * 1024 * 1024 and b"<!DOCTYPE" not in data, "unsafe test report")
    root = ET.fromstring(data)
    cases = list(root.iter("testcase"))
    require(len(cases) >= 1000 and not list(root.iter("failure")) and not list(root.iter("error")),
            "upstream tests did not complete successfully")
    skips = [node.get("message", "") for node in root.iter("skipped")]
    require(all(skips) and len(cases) - len(skips) >= 1000, "insufficient passing tests or unexplained skip")
    return {"total": len(cases), "skipped": len(skips), "passed": len(cases) - len(skips),
            "skip_reasons": sorted(set(skips))}


def validate_reports(report, sbom, descriptor, target, counts, wheel_hash):
    configuration = descriptor["targets"][target]
    image = configuration["images"][report["image_version"]]
    require(report.get("schema") == 1 and report.get("tests") == counts
            and report.get("wheel_sha256") == wheel_hash
            and report.get("python") == ["3.12.14", configuration["machine"]]
            and report.get("rust", "").startswith("rustc 1.97.1 ")
            and report.get("openssl", "").startswith("OpenSSL 4.0.2 "), "build tool or test identity mismatch")
    compiler = report.get("compiler", {})
    require(compiler.get("sdk") == image["sdk"], "SDK identity mismatch")
    if target.startswith("windows"):
        require(compiler.get("visual_studio") == image["visual_studio"]
                and compiler.get("msvc_tools"), "MSVC identity mismatch")
    else:
        require(compiler.get("xcode") == f'Xcode {image["xcode"]}\nBuild version {image["xcode_build"]}'
                and compiler.get("clang"), "Xcode identity mismatch")
    expected_sources = {name: {"url": row["url"], "sha256": row["sha256"]}
                        for name, row in {"cryptography": descriptor["cryptography"],
                                          "openssl": descriptor["openssl"],
                                          "python": configuration["python"], "uv": configuration["uv"]}.items()}
    require(report.get("sources") == expected_sources, "source report mismatch")
    lock = "".join(f'{row["name"]}=={row["version"]} --hash=sha256:{row["sha256"]}\n'
                   for row in configuration["python_dependencies"])
    require(report.get("build_lock_sha256") == digest(lock.encode())
            and report.get("recipe_sha256") == recipe_digest(Path(__file__).with_name("build_native_wheels.py")),
            "producer recipe or build lock mismatch")
    require(sbom.get("schema") == 1 and sbom.get("kind") == "build-input-inventory"
            and sbom.get("target") == target and sbom.get("static_openssl") is True
            and sbom.get("cryptography") == descriptor["cryptography"]
            and sbom.get("openssl") == descriptor["openssl"]
            and sbom.get("python_build_tools") == configuration["python_dependencies"]
            and sbom.get("wheel_sha256") == wheel_hash and sbom.get("cargo_packages")
            and HASH.fullmatch(sbom.get("cargo_lock_sha256", "")), "build inventory identity mismatch")
    for package in sbom["cargo_packages"]:
        require(package.get("name") and package.get("version") and
                (package.get("source") == "upstream-source" or
                 (package.get("source") == "registry+https://github.com/rust-lang/crates.io-index"
                  and HASH.fullmatch(package.get("sha256", "")))), "unlocked Cargo component")


def github(endpoint):
    result = subprocess.run(["gh", "api", "--method", "GET", endpoint], check=True,
                            capture_output=True, timeout=90)
    require(len(result.stdout) < 32 * 1024 * 1024, "GitHub response oversized")
    return json.loads(result.stdout, object_pairs_hook=unique)


def validate_run():
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_REF") == "refs/heads/master"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "untrusted producer invocation")
    commit = os.environ.get("GITHUB_SHA", "")
    require(COMMIT.fullmatch(commit), "producer commit missing")
    run_id = int(os.environ["GITHUB_RUN_ID"])
    run = github(f"repos/{REPOSITORY}/actions/runs/{run_id}")
    require(run["head_sha"] == commit and run["head_branch"] == "master"
            and run["event"] == "workflow_dispatch" and run["run_attempt"] == 1
            and run["path"] == WORKFLOW and run["repository"]["full_name"] == REPOSITORY,
            "GitHub producer identity mismatch")
    return run


def seal(input_path, destination):
    descriptor = read_json(input_path)
    validate_descriptor(descriptor)
    run = validate_run()
    artifacts = github(f"repos/{REPOSITORY}/actions/runs/{run['id']}/artifacts?per_page=100")
    require(artifacts["total_count"] == 2, "unexpected producer artifact set")
    jobs = github(f"repos/{REPOSITORY}/actions/runs/{run['id']}/attempts/1/jobs?per_page=100")
    require(jobs["total_count"] <= 100, "unbounded producer jobs")
    destination.mkdir(parents=True, exist_ok=False)
    records = []
    for target in TARGETS:
        matches = [a for a in artifacts["artifacts"] if a["name"] == f"native-wheel-{target}"]
        require(len(matches) == 1 and not matches[0]["expired"], "native artifact absent or expired")
        artifact = matches[0]
        origin = artifact.get("workflow_run", {})
        require(origin.get("id") == run["id"] and origin.get("head_sha") == os.environ["GITHUB_SHA"]
                and origin.get("head_branch") == "master", "artifact producer identity mismatch")
        job_name = "build-windows" if target.startswith("windows") else "build-macos"
        job = [j for j in jobs["jobs"] if j["name"] == job_name]
        require(len(job) == 1 and job[0]["conclusion"] == "success", "native producer job did not pass")
        archive_path = destination / f"{target}.zip"
        with archive_path.open("xb") as output:
            subprocess.run(["gh", "api", f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"],
                           stdout=output, check=True, timeout=120)
        require(artifact.get("digest") == "sha256:" + digest(archive_path.read_bytes()), "artifact digest mismatch")
        members = archive_members(archive_path)
        wheel_name = f"cryptography-50.0.1-cp311-abi3-{TARGETS[target]}.whl"
        require(set(members) == {wheel_name, "build-report.json", "tests.xml", "build-sbom.json"},
                "unexpected producer output")
        report = json.loads(members["build-report.json"], object_pairs_hook=unique)
        require(report["target"] == target and report["input_sha256"] == digest(canonical(descriptor))
                and report["producer_sha"] == os.environ["GITHUB_SHA"] and report["run_id"] == run["id"]
                and report["run_attempt"] == 1 and report["image_version"] in descriptor["targets"][target]["images"],
                "build report is not bound to approved producer inputs")
        counts = test_counts(members["tests.xml"])
        wheel_path = destination / wheel_name
        wheel_path.write_bytes(members[wheel_name])
        record = inspect_wheel(wheel_path, target)
        sbom = json.loads(members["build-sbom.json"], object_pairs_hook=unique)
        validate_reports(report, sbom, descriptor, target, counts, record["sha256"])
        record.update({"target": target, "artifact_id": artifact["id"], "artifact_digest": artifact["digest"],
                       "job_id": job[0]["id"], "image_version": report["image_version"], "tests": counts,
                       "test_report_sha256": digest(members["tests.xml"]),
                       "build_report_sha256": digest(members["build-report.json"]),
                       "build_sbom_sha256": digest(members["build-sbom.json"])})
        records.append(record)
    manifest = {"schema": 1, "repository": REPOSITORY, "repository_id": run["repository"]["id"],
                "workflow": WORKFLOW, "workflow_id": run["workflow_id"], "producer_sha": os.environ["GITHUB_SHA"],
                "input_commit": os.environ["GITHUB_SHA"], "run_id": run["id"], "run_attempt": 1,
                "input_sha256": digest(canonical(descriptor)), "inputs": descriptor, "wheels": records}
    (destination / "native-wheel-manifest.json").write_bytes(canonical(manifest))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=Path("packaging/cua/native-wheels-input.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        seal(args.inputs, args.out)
    else:
        validate_descriptor(read_json(args.inputs))
        print("Native wheel input descriptor passed.")


if __name__ == "__main__":
    main()
