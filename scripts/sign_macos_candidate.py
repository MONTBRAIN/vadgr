#!/usr/bin/env python3
"""Sign one same-run macOS build inside the protected credential wrapper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unicodedata
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[1]
VERSION = "0.5.0"
APP = PurePosixPath("Applications/Vadgr.app")
HELPER = APP / "Contents/Library/LoginItems/Vadgr Computer Use.app"
SHIM = PurePosixPath("usr/local/bin/vadgr")
SHIM_TARGET = "/Applications/Vadgr.app/Contents/MacOS/vadgr"
LOCKS = ("Cargo.lock", "packaging/cua/pins.toml", "packaging/cua/requirements.lock", "packaging/toolchain.json")
MACHO_MAGICS = {bytes.fromhex(value) for value in (
    "feedface", "cefaedfe", "feedfacf", "cffaedfe", "cafebabe", "bebafeca", "cafebabf", "bfbafeca",
)}
BUNDLES = {".app", ".framework", ".xpc", ".bundle", ".plugin", ".appex"}


class SigningError(Exception):
    """A safe phase error, without command output or credential-bearing details."""


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run_tool(argv: list[str], phase: str, *, timeout: int = 180) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise SigningError(f"{phase} failed") from None
    if result.returncode:
        raise SigningError(f"{phase} failed")
    return result.stdout + result.stderr


def require_runner(env: dict[str, str]) -> None:
    if (sys.platform != "darwin" or env.get("GITHUB_ACTIONS") != "true"
            or env.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or env.get("GITHUB_REPOSITORY") != "MONTBRAIN/vadgr"
            or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}
            or env.get("GITHUB_HEAD_REF")):
        raise SigningError("signing requires a trusted GitHub-hosted macOS job")


def requirement(env: dict[str, str], repo: Path) -> str:
    value = env.get("MACOS_CUA_REQUIREMENT", "").strip()
    if not value:
        value = (repo / "packaging/macos/cua-designated-requirement.txt").read_text().strip()
    value = re.sub(r"^designated\s*=>\s*", "", value)
    if (not value or "UNCONFIGURED" in value or "=>" in value
            or 'identifier "com.montbrain.vadgr.cua"' not in value
            or "anchor apple generic" not in value
            or not re.search(r'certificate leaf\[subject\.OU\]\s*=\s*"[A-Z0-9]{10}"', value)):
        raise SigningError("the CUA designated requirement is not configured")
    return value


def read_metadata(path: Path, source: Path, arch: str, env: dict[str, str], repo: Path) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema") != 1 or data.get("unsigned_development") is not True:
        raise SigningError("build metadata schema or input classification is invalid")
    if arch not in {"arm64", "x86_64"}:
        raise SigningError("the architecture is invalid")
    expected = {"source_sha": env.get("SOURCE_SHA"), "source_tree": env.get("SOURCE_TREE"),
                "run_id": env.get("GITHUB_RUN_ID"), "run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
                "architecture": arch, "archive_name": f"Vadgr-{VERSION}-macos-{arch}-unsigned-root.tar.gz"}
    if (not re.fullmatch(r"[0-9a-f]{40}", expected["source_sha"] or "")
            or not re.fullmatch(r"[0-9a-f]{40}", expected["source_tree"] or "")
            or env.get("GITHUB_SHA") != expected["source_sha"]
            or not re.fullmatch(r"[1-9][0-9]*", expected["run_id"] or "")
            or not re.fullmatch(r"[1-9][0-9]*", expected["run_attempt"] or "")
            or any(data.get(key) != value for key, value in expected.items())
            or source.name != expected["archive_name"]):
        raise SigningError("build metadata does not match this source, tree, architecture or run")
    if source.is_symlink() or not source.is_file() or data.get("archive_sha256") != sha256(source):
        raise SigningError("the unsigned archive digest does not match build metadata")
    locks = data.get("lock_sha256")
    if not isinstance(locks, dict) or set(locks) != set(LOCKS):
        raise SigningError("build metadata does not identify the required locks")
    for name in LOCKS:
        path = repo / name
        if path.is_symlink() or not path.is_file() or locks[name] != sha256(path):
            raise SigningError("build metadata lock digests do not match the checkout")
    return data


def member_path(name: str) -> PurePosixPath:
    while name.startswith("./"):
        name = name[2:]
    name = name.rstrip("/")
    if not name or name == ".":
        return PurePosixPath(".")
    if "\\" in name or "\x00" in name or name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")):
        raise SigningError("the archive contains an unsafe path")
    return PurePosixPath(name)


def extract_archive(source: Path, destination: Path, expected_digest: str) -> None:
    # Validate the entire table before creating even the extraction directory.
    # Use one open file for hashing and extraction so a path replacement cannot
    # substitute different archive bytes after the digest check.
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected_digest:
            raise SigningError("the unsigned archive digest changed before extraction")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:*") as archive:
            members = {}
            aliases = {}
            total_size = 0
            for item in archive:
                path = member_path(item.name)
                if path == PurePosixPath("."):
                    if not item.isdir():
                        raise SigningError("the archive root is not a directory")
                    continue
                alias = unicodedata.normalize("NFD", str(path)).casefold()
                if alias in aliases:
                    raise SigningError("the archive contains duplicate paths")
                aliases[alias] = item
                if path not in {APP, SHIM} and APP not in path.parents:
                    if path not in {PurePosixPath("Applications"), *SHIM.parents} or not item.isdir():
                        raise SigningError("the archive contains an unexpected root")
                if not (item.isdir() or item.isfile() or item.issym()) or item.mode & 0o7000:
                    raise SigningError("the archive contains an unsupported entry")
                if path == SHIM and (not item.issym() or item.linkname != SHIM_TARGET):
                    raise SigningError("the archive CLI link is not canonical")
                if item.issym() and path != SHIM:
                    if path == APP or "\\" in item.linkname or "\x00" in item.linkname or item.linkname.startswith("/"):
                        raise SigningError("the archive contains an escaping link")
                    target = PurePosixPath(posixpath.normpath(str(path.parent / item.linkname)))
                    if target != APP and APP not in target.parents:
                        raise SigningError("the archive contains an escaping link")
                total_size += item.size
                if item.size < 0 or total_size > 12 * 1024**3 or len(members) >= 200_000:
                    raise SigningError("the archive exceeds package bounds")
                members[path] = item
            for path in members:
                for parent in path.parents:
                    ancestor = aliases.get(unicodedata.normalize("NFD", str(parent)).casefold())
                    if ancestor is not None and not ancestor.isdir():
                        raise SigningError("the archive writes below a link or file")
            # Resolve links against the archive table, including intermediate
            # links before '..'. Lexical normalization alone misses escapes
            # through a second link. No filesystem writes occur during checks.
            for path, item in members.items():
                if not item.issym() or path == SHIM:
                    continue
                resolved, pending, expansions = list(path.parent.parts), item.linkname.split("/"), 0
                while pending:
                    part = pending.pop(0)
                    if part in {"", "."}:
                        continue
                    if part == "..":
                        if len(resolved) <= len(APP.parts):
                            raise SigningError("the archive contains an escaping link chain")
                        resolved.pop()
                        continue
                    resolved.append(part)
                    target = aliases.get(unicodedata.normalize("NFD", "/".join(resolved)).casefold())
                    if target is not None and target.issym():
                        expansions += 1
                        if expansions > 40:
                            raise SigningError("the archive contains a cyclic or excessive link chain")
                        resolved.pop()
                        pending = target.linkname.split("/") + pending
            destination.mkdir(mode=0o700)
            for path, item in sorted(members.items(), key=lambda pair: (len(pair[0].parts), str(pair[0]))):
                output = destination.joinpath(*path.parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                if item.isdir():
                    output.mkdir(exist_ok=True)
                elif item.issym():
                    output.symlink_to(item.linkname)
                else:
                    data = archive.extractfile(item)
                    if data is None:
                        raise SigningError("an archive file could not be read")
                    with data, output.open("xb") as target:
                        shutil.copyfileobj(data, target)
                    output.chmod(item.mode & 0o777)


def signing_targets(root: Path) -> tuple[list[Path], set[Path]]:
    app = root.joinpath(*APP.parts)
    helper = root.joinpath(*HELPER.parts)
    for bundle, identifier, executable in ((app, "com.montbrain.vadgr", "vadgr-app"),
                                           (helper, "com.montbrain.vadgr.cua", "vadgr-cua-host")):
        info = bundle / "Contents/Info.plist"
        if info.is_symlink() or not info.is_file():
            raise SigningError("a required application identity is missing")
        values = plistlib.loads(info.read_bytes())
        if (values.get("CFBundleIdentifier") != identifier
                or values.get("CFBundleExecutable") != executable
                or values.get("CFBundleShortVersionString") != VERSION):
            raise SigningError("an application identity or version does not match")
    targets, binaries = {app, helper}, set()
    for directory, directories, files in os.walk(app, followlinks=False):
        for name in directories:
            path = Path(directory) / name
            if not path.is_symlink() and path.suffix in BUNDLES:
                targets.add(path)
        for name in files:
            path = Path(directory) / name
            if not path.is_symlink():
                with path.open("rb") as stream:
                    if stream.read(4) in MACHO_MAGICS:
                        targets.add(path)
                        binaries.add(path)
    required = {app / "Contents/MacOS/vadgr", app / "Contents/MacOS/vadgr-app", helper / "Contents/MacOS/vadgr-cua-host"}
    if not required <= binaries:
        raise SigningError("a required Mach-O executable is missing")
    return sorted(targets, key=lambda path: (-len(path.parts), str(path))), binaries


def credentials(env: dict[str, str]) -> tuple[str, str, Path, Path]:
    application, installer = env.get("APPLICATION_IDENTITY", ""), env.get("INSTALLER_IDENTITY", "")
    if not all(re.fullmatch(r"[A-Fa-f0-9]{40}", value) for value in (application, installer)):
        raise SigningError("verified signing fingerprints are missing")
    keychain = Path(env.get("VADGR_MACOS_KEYCHAIN", ""))
    key = Path(env.get("VADGR_NOTARY_KEY_FILE", ""))
    if (not keychain.is_absolute() or keychain.is_symlink() or not keychain.is_file()
            or not key.is_absolute() or key.is_symlink() or not key.is_file()
            or stat.S_IMODE(key.stat().st_mode) != 0o600 or key.stat().st_uid != os.getuid()
            or not re.fullmatch(r"[A-Za-z0-9]{8,32}", env.get("VADGR_NOTARY_KEY_ID", ""))
            or not re.fullmatch(r"[A-Fa-f0-9-]{36}", env.get("VADGR_NOTARY_ISSUER_ID", ""))):
        raise SigningError("the isolated signing credentials are unavailable")
    return application, installer, keychain, key


def sign_candidate(source: Path, metadata_path: Path, arch: str, output: Path, *,
                   env: dict[str, str] | None = None, repo: Path = REPO, run=run_tool) -> None:
    env = dict(os.environ) if env is None else env
    require_runner(env)
    expected_requirement = requirement(env, repo)
    metadata = read_metadata(metadata_path, source, arch, env, repo)
    if output.exists() or output.is_symlink():
        raise SigningError("the publication directory already exists")
    entitlements = repo / "packaging/macos/Vadgr.entitlements"
    if plistlib.loads(entitlements.read_bytes()) != {}:
        raise SigningError("only the reviewed empty entitlements are accepted")
    for revision, expected in (("HEAD", env["SOURCE_SHA"]), ("HEAD^{tree}", env["SOURCE_TREE"])):
        if run(["/usr/bin/git", "-C", str(repo), "rev-parse", revision], "checkout identity").strip() != expected:
            raise SigningError("the signing checkout does not match the build")
    temporary_root = Path(env.get("RUNNER_TEMP", ""))
    if not temporary_root.is_absolute() or not temporary_root.is_dir():
        raise SigningError("the runner temporary directory is unavailable")
    with tempfile.TemporaryDirectory(prefix="vadgr-macos-sign-", dir=temporary_root) as temporary:
        work = Path(temporary)
        root = work / "root"
        extract_archive(source, root, metadata["archive_sha256"])
        targets, binaries = signing_targets(root)
        application, installer, keychain, key = credentials(env)
        app, helper = root.joinpath(*APP.parts), root.joinpath(*HELPER.parts)
        for target in targets:
            if target in binaries:
                run(["/usr/bin/lipo", "-verify_arch", arch, str(target)], "Mach-O architecture")
            command = ["/usr/bin/codesign", "--force", "--options", "runtime", "--timestamp",
                       "--keychain", str(keychain), "--sign", application]
            if target in {app, helper}:
                command += ["--entitlements", str(entitlements)]
            if target == helper:
                command += ["--identifier", "com.montbrain.vadgr.cua", "--requirements", "=designated => " + expected_requirement]
            run(command + [str(target)], "nested code signing")
        for target in targets:
            run(["/usr/bin/codesign", "--verify", "--strict", str(target)], "nested signature verification")
            detail = run(["/usr/bin/codesign", "--display", "--verbose=4", str(target)], "signature attributes")
            if not re.search(r"flags=.*\bruntime\b", detail) or not re.search(r"^Timestamp=(?!none).+", detail, re.MULTILINE):
                raise SigningError("a signature lacks hardened runtime or a secure timestamp")
        for target in (app, helper):
            content = run(["/usr/bin/codesign", "--display", "--entitlements", ":-", str(target)], "signed entitlements")
            start, end = content.find("<plist"), content.rfind("</plist>")
            if start < 0 or end < start or plistlib.loads(content[start:end + 8].encode()) != {}:
                raise SigningError("signed entitlements differ from the reviewed set")
        run(["/usr/bin/codesign", "--verify", "--strict", "--test-requirement", "=" + expected_requirement, str(helper)], "CUA identity verification")
        displayed = run(["/usr/bin/codesign", "--display", "--requirements", "-", str(helper)], "CUA designated requirement")
        match = re.search(r"^designated\s*=>\s*(.+)$", displayed, re.MULTILINE)
        if not match:
            raise SigningError("the CUA designated requirement is missing")
        expected_blob, actual_blob = work / "expected.req", work / "actual.req"
        for expression, blob in ((expected_requirement, expected_blob), (match.group(1), actual_blob)):
            run(["/usr/bin/csreq", "-r", "=" + expression, "-b", str(blob)], "designated requirement compilation")
        if expected_blob.read_bytes() != actual_blob.read_bytes():
            raise SigningError("the CUA designated requirement changed")

        scripts, resources = work / "scripts", work / "resources"
        scripts.mkdir()
        resources.mkdir()
        for name in ("preinstall", "postinstall"):
            shutil.copyfile(repo / "packaging/macos/scripts" / name, scripts / name)
            (scripts / name).chmod(0o755)
        for name in ("WELCOME.txt", "CONCLUSION.txt"):
            shutil.copyfile(repo / "packaging/macos/resources" / name, resources / name)
        shutil.copyfile(app / "Contents/Resources/legal/TERMS.txt", resources / "TERMS.txt")
        distribution = ET.parse(repo / "packaging/macos/Distribution.xml")
        options = distribution.getroot().find("options")
        if options is None:
            raise SigningError("the installer architecture declaration is missing")
        options.set("hostArchitectures", arch)
        distribution_path = work / "Distribution.xml"
        distribution.write(distribution_path, encoding="utf-8", xml_declaration=True)
        component = work / "Vadgr-component.pkg"
        package_name = f"Vadgr-{VERSION}-macos-{arch}.pkg"
        package = work / package_name
        run(["/usr/bin/pkgbuild", "--root", str(root), "--identifier", "com.montbrain.vadgr.pkg",
             "--version", VERSION, "--install-location", "/", "--scripts", str(scripts),
             "--sign", installer, "--keychain", str(keychain), "--timestamp", str(component)], "component package signing")
        run(["/usr/bin/productbuild", "--distribution", str(distribution_path), "--resources", str(resources),
             "--package-path", str(work), "--sign", installer, "--keychain", str(keychain),
             "--timestamp", str(package)], "product package signing")
        response = run(["/usr/bin/xcrun", "notarytool", "submit", str(package), "--key", str(key),
                        "--key-id", env["VADGR_NOTARY_KEY_ID"], "--issuer", env["VADGR_NOTARY_ISSUER_ID"],
                        "--wait", "--timeout", "30m", "--output-format", "json"], "notarization", timeout=1900)
        try:
            accepted = json.loads(response).get("status") == "Accepted"
        except (ValueError, AttributeError):
            accepted = False
        if not accepted:
            raise SigningError("notarization was not accepted")
        run(["/usr/bin/xcrun", "stapler", "staple", str(package)], "package stapling")
        run(["/usr/bin/xcrun", "stapler", "validate", str(package)], "staple verification")
        run(["/usr/sbin/pkgutil", "--check-signature", str(package)], "package signature verification")
        run(["/usr/sbin/spctl", "--assess", "--type", "install", str(package)], "installer trust assessment")
        run(["/usr/sbin/spctl", "--assess", "--type", "execute", str(app)], "application trust assessment")
        pins = tomllib.loads((repo / "packaging/cua/pins.toml").read_text())
        provenance = {key: metadata[key] for key in ("source_sha", "source_tree", "run_id", "run_attempt", "architecture", "archive_sha256", "lock_sha256")}
        provenance.update(schema=1, version=VERSION, cua_version=pins["cua"], python_version=pins["python"],
                          package_name=package_name, package_sha256=sha256(package), package_size=package.stat().st_size,
                          bundle_ids=["com.montbrain.vadgr", "com.montbrain.vadgr.cua"],
                          requirement_sha256=sha256(actual_blob), notarization="Accepted", stapled=True,
                          input_unsigned_development=True, release_acceptance=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.mkdir(mode=0o700)
        try:
            shutil.copyfile(package, output / package_name)
            (output / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        except BaseException:
            shutil.rmtree(output)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--arch", required=True, choices=("arm64", "x86_64"))
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        sign_candidate(args.archive, args.metadata, args.arch, args.output_dir)
    except SigningError as error:
        print(f"macOS signing stopped: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("macOS signing stopped: package processing failed", file=sys.stderr)
        return 1
    print("macOS package signing, notarization and verification completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
