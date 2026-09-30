#!/usr/bin/env python3
"""Prepare a native Linux payload, then package it after exact input review.

Preparation has no signing, publication or legal-approval authority. Packaging
uses the same AppImage builder and approved-input validator as the final build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys

if __package__:
    from scripts import cua_wheelhouse, distribution_matrix
    from scripts.verify_appimage_runtime import verify as verify_appimage_runtime
    from scripts.validate_package_inputs import (
        PackageInputError, canonical_json, require, validate_package_inputs,
    )
else:
    import cua_wheelhouse
    import distribution_matrix
    from verify_appimage_runtime import verify as verify_appimage_runtime
    from validate_package_inputs import (
        PackageInputError, canonical_json, require, validate_package_inputs,
    )


ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = (
    "GH_TOKEN", "GITHUB_TOKEN", "ES_USERNAME", "ES_PASSWORD", "ES_TOTP_SECRET",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_identity(source, expected):
    require(re.fullmatch(r"[a-f0-9]{40}", expected) is not None, "exact source commit required")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()

    require(git("rev-parse", "HEAD") == expected, "source commit differs")
    require(not git("status", "--porcelain", "--untracked-files=all"), "source must be clean")
    return {"source_commit": expected, "source_tree": git("rev-parse", "HEAD^{tree}")}


def native_target(architecture):
    require(platform.system() == "Linux" and platform.machine() == architecture
            and architecture in ("x86_64", "aarch64"), "native Linux architecture differs")
    require("microsoft" not in platform.release().lower(), "WSL is not native Linux")
    return "linux-" + architecture, architecture + "-unknown-linux-gnu"


def inventory(root):
    """Record bytes, modes and safe relative links without recording host paths."""
    root = root.resolve(strict=True)
    rows = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(info.st_mode)}
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            require(not os.path.isabs(target) and path.resolve(strict=True).is_relative_to(root),
                    "payload link escapes preparation")
            row.update(kind="symlink", target=target)
        elif stat.S_ISREG(info.st_mode):
            require(info.st_nlink == 1, "hard-linked preparation file")
            row.update(kind="file", size=info.st_size, sha256=digest(path))
        elif stat.S_ISDIR(info.st_mode):
            continue
        else:
            raise PackageInputError("special preparation file")
        rows.append(row)
    return rows


def build_environment(profile):
    require(not any(os.environ.get(key) for key in CREDENTIALS),
            "compilation must have no GitHub, signing or identity credentials")
    environment = dict(os.environ)
    toolchains = set(re.findall(r"^\s+toolchain: ([0-9]+\.[0-9]+\.[0-9]+)\s*$",
                               (ROOT / ".github/workflows/candidate.yml").read_text(), re.M))
    require(len(toolchains) == 1, "candidate Rust toolchain is ambiguous")
    environment.update(VADGR_RELEASE_PROFILE=profile, VADGR_RELEASE_PAYLOAD_BUILD="1",
                       SOURCE_DATE_EPOCH="1609459200",
                       RUSTUP_TOOLCHAIN=next(iter(toolchains)), CARGO_TARGET_DIR=str(ROOT / "target"),
                       RUSTFLAGS=f"--remap-path-prefix={ROOT}=/vadgr-source")
    return environment


def write_new(path, value):
    with path.open("xb") as stream:
        stream.write(canonical_json(value))


def relocation_probe(payload, environment):
    relocated = payload.with_name("relocation-probe")
    require(not relocated.exists(), "relocation probe root already exists")
    payload.rename(relocated)
    try:
        environments = list((relocated / "lib/cua/environments").iterdir())
        require(len(environments) == 1, "private runtime environment is ambiguous")
        manifest = json.loads((relocated / "lib/cua/payload.json").read_bytes())
        command = [str(environments[0] / "bin/python"), "-I", "-B", "-c",
                   "import importlib.metadata, json, sys; import computer_use.mcp_server; "
                   "print(json.dumps({'python':sys.version.split()[0],"
                   "'cua':importlib.metadata.version('vadgr-computer-use')}))"]
        observed = json.loads(subprocess.check_output(command, env=environment, text=True))
        require(observed == {"python": manifest["python_version"], "cua": manifest["cua_version"]},
                "relocated runtime identity differs")
        return observed
    finally:
        relocated.rename(payload)


def prepare(output, wheelhouse, architecture, source_commit):
    identity = source_identity(ROOT, source_commit)
    profile, target = native_target(architecture)
    environment = build_environment(profile)
    require(not output.exists() and not output.is_symlink()
            and output.parent.is_dir(), "preparation output must be new")
    cua_wheelhouse.verify_materialized(ROOT, ROOT, target, wheelhouse, profile)
    output.mkdir(mode=0o700)
    subprocess.run(["cargo", "build", "--locked", "--release", "--features", "native-gui",
                    "--target", target, "--bin", "vadgr"], cwd=ROOT, env=environment, check=True)
    binary = ROOT / "target" / target / "release/vadgr"
    distribution_matrix.verify_binary(binary, profile)
    payload = output / "payload"
    subprocess.run([str(binary), "__payload-setup", "--install-root", str(payload),
                    "--payload-only", "--wheelhouse", str(wheelhouse)],
                   cwd=ROOT, env=environment, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/distribution_matrix.py"), "payload",
                    "--target", profile, "--root", str(payload), "--pins",
                    str(ROOT / "packaging/cua/pins.toml")], env=environment, check=True)
    probe = relocation_probe(payload, environment)
    shutil.copyfile(wheelhouse / "wheelhouse.json", output / "wheelhouse.json")
    shutil.copyfile(binary, output / "vadgr")
    (output / "vadgr").chmod(0o755)
    files = inventory(output)
    require(source_identity(ROOT, source_commit) == identity, "source changed during preparation")
    write_new(output / "preparation.json", {
        "schema": 1, "development": True, "publishable": False,
        "legal_approval": False, "signing": "disabled", "attestation": "absent",
        "platform": "linux", "architecture": architecture, "release_profile": profile,
        **identity, "relocation_probe": probe, "files": files,
    })


def package(preparation, appimagetool, architecture, source_commit, runtime=None):
    identity = source_identity(ROOT, source_commit)
    profile, target = native_target(architecture)
    environment = build_environment(profile)
    receipt_path = preparation / "preparation.json"
    receipt = json.loads(receipt_path.read_bytes())
    require(receipt_path.read_bytes() == canonical_json(receipt), "noncanonical preparation receipt")
    require(all(receipt.get(key) == value for key, value in {
        **identity, "schema": 1, "platform": "linux", "architecture": architecture,
        "release_profile": profile, "development": True, "publishable": False,
        "legal_approval": False, "signing": "disabled", "attestation": "absent",
    }.items()), "preparation identity differs")
    require([row for row in inventory(preparation) if row["path"] != "preparation.json"]
            == receipt["files"], "prepared bytes changed")
    pins = json.loads((ROOT / "packaging/toolchain.json").read_bytes())
    require(digest(appimagetool) == pins["appimagetool"][architecture]["sha256"],
            "appimagetool differs from reviewed pin")
    require(runtime is not None, "pinned AppImage runtime required")
    runtime_identity = verify_appimage_runtime(runtime, ROOT / "packaging/linux/runtime.json", architecture)
    payload = preparation / "payload"
    validate_package_inputs(ROOT / "packaging/inputs" / profile, ROOT, "0.5.0", target,
                            payload_manifest=payload / "lib/cua/payload.json")
    environment.update(APPIMAGETOOL=str(appimagetool), APPIMAGE_EXTRACT_AND_RUN="1",
                       APPIMAGE_RUNTIME=str(runtime),
                       VADGR_PACKAGE_PAYLOAD_ROOT=str(payload))
    subprocess.run(["sh", "packaging/linux/build.sh", "0.5.0", architecture],
                   cwd=ROOT, env=environment, check=True)
    vehicle = ROOT / "target/package" / f"Vadgr-0.5.0-linux-{architecture}-installer.AppImage"
    distribution_matrix.verify_binary(vehicle, profile)
    require(digest(ROOT / "target" / target / "release/vadgr") == digest(preparation / "vadgr"),
            "packaged executable differs from preparation")
    require(source_identity(ROOT, source_commit) == identity, "source changed during packaging")
    write_new(vehicle.with_suffix(".development.json"), {
        "schema": 1, "development": True, "publishable": False,
        "signing": "disabled", "attestation": "absent", **identity,
        "platform": "linux", "architecture": architecture,
        "artifact": {"filename": vehicle.name, "size": vehicle.stat().st_size,
                     "sha256": digest(vehicle)},
        "appdir": inventory(ROOT / "target/package" / profile / "Vadgr.AppDir"),
        "preparation_sha256": digest(receipt_path),
        "appimage_runtime": runtime_identity,
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "package"))
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--architecture", choices=("x86_64", "aarch64"), required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--appimagetool", type=Path)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            require(args.wheelhouse is not None, "verified wheelhouse required")
            prepare(args.preparation.absolute(), args.wheelhouse.absolute(), args.architecture,
                    args.source_commit)
        else:
            require(args.appimagetool is not None, "pinned appimagetool required")
            require(args.runtime is not None, "pinned AppImage runtime required")
            package(args.preparation.absolute(), args.appimagetool.absolute(), args.architecture,
                    args.source_commit, args.runtime.absolute())
    except (PackageInputError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("Unsigned Linux preparation failed; retained files remain for diagnosis.", file=sys.stderr)
        return 1
    print("Unsigned Linux " + args.mode + " completed. Output is nonpublishable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
