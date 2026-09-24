#!/usr/bin/env python3
"""Build the two reviewed native dependency wheels without signing credentials."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request

if __package__:
    from scripts import validate_native_wheels as gate
else:
    import validate_native_wheels as gate


def run(command, *, cwd=None, env=None, capture=False):
    arguments = command if isinstance(command, str) else [str(x) for x in command]
    result = subprocess.run(arguments, cwd=cwd, env=env, check=True,
                            text=True, stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.STDOUT, timeout=5400)
    return result.stdout.strip() if capture else None


def fetch(row, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(row["url"], headers={"User-Agent": "vadgr-native-wheel-producer/1"})
    with urllib.request.urlopen(request, timeout=120) as source, destination.open("xb") as output:
        count = 0
        while block := source.read(1024 * 1024):
            count += len(block)
            gate.require(count <= 512 * 1024 * 1024, "source download limit exceeded")
            output.write(block)
    gate.require(gate.digest(destination.read_bytes()) == row["sha256"], "download digest mismatch")
    return destination


def extract(path, destination):
    destination.mkdir(parents=True, exist_ok=False)
    if path.name.endswith(".zip"):
        for name, data in gate.archive_members(path).items():
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
    else:
        with tarfile.open(path) as archive:
            members = archive.getmembers()
            gate.require(len(members) <= 100_000 and sum(m.size for m in members) <= 2 * 1024**3,
                         "source extraction limit exceeded")
            for member in members:
                gate.safe_name(member.name)
            # Standalone Python uses internal symlinks. The data filter rejects
            # paths or link targets outside this fresh, hash-verified input root.
            archive.extractall(destination, members=members, filter="data")


def wheel_command(uv, python, source, out):
    return [str(uv), "build", "--wheel", "--offline", "--no-build-isolation", "--no-sources",
            "--config-settings=build-args=--features=pyo3/abi3-py311",
            "--python", str(python), "--out-dir", str(out), str(source)]


def compiler_environment(configuration, image):
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith(("PIP_", "UV_", "CARGO_", "RUSTUP_TOOLCHAIN", "OPENSSL_")):
            environment.pop(key)
    if platform.system() == "Windows":
        vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
        installations = json.loads(run([vswhere, "-all", "-products", "*", "-format", "json"], capture=True))
        matches = [row for row in installations if row["installationVersion"] == image["visual_studio"]]
        gate.require(len(matches) == 1, "reviewed Visual Studio version unavailable")
        script = Path(matches[0]["installationPath"]) / "VC/Auxiliary/Build/vcvarsall.bat"
        gate.require(script.is_file() and not re.search(r'["%\r\n]', str(script))
                     and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", image["sdk"]),
                     "unsafe compiler initialization input")
        # cmd parses its own expression, not the C argv quoting used for programs.
        # Passing this expression through list2cmdline inserts literal backslashes.
        text = run(f'cmd.exe /d /v:off /s /c ""{script}" arm64 {image["sdk"]} >nul && set"', capture=True)
        allowed = {"path", "include", "lib", "libpath", "vctoolsinstalldir", "windowssdkdir",
                   "windowssdkversion", "universalcrtsdkdir", "ucrtversion", "vscmd_arg_tgt_arch"}
        for line in text.splitlines():
            key, separator, value = line.partition("=")
            if separator and key.lower() in allowed:
                environment[key.upper()] = value
        gate.require(environment.get("VSCMD_ARG_TGT_ARCH", "").lower() == "arm64", "MSVC target is not ARM64")
        return environment, {"visual_studio": image["visual_studio"], "sdk": image["sdk"],
                             "msvc_tools": environment.get("VCTOOLSINSTALLDIR", "")}
    environment["DEVELOPER_DIR"] = f'/Applications/Xcode_{image["xcode"]}.app/Contents/Developer'
    version = run(["xcodebuild", "-version"], env=environment, capture=True)
    gate.require(version == f'Xcode {image["xcode"]}\nBuild version {image["xcode_build"]}', "Xcode version changed")
    sdk = run(["xcrun", "--sdk", "macosx", "--show-sdk-version"], env=environment, capture=True)
    gate.require(sdk == image["sdk"], "macOS SDK version changed")
    environment["MACOSX_DEPLOYMENT_TARGET"] = configuration["deployment_floor"]
    environment["SDKROOT"] = run(["xcrun", "--sdk", "macosx", "--show-sdk-path"], env=environment, capture=True)
    return environment, {"xcode": version, "sdk": sdk,
                         "clang": run(["xcrun", "clang", "--version"], env=environment, capture=True)}


def build(inputs, target, work, out):
    descriptor = gate.read_json(inputs)
    gate.validate_descriptor(descriptor)
    gate.require(os.environ.get("GITHUB_REPOSITORY") == gate.REPOSITORY
                 and os.environ.get("GITHUB_REF") == "refs/heads/master"
                 and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "untrusted build invocation")
    configuration = descriptor["targets"][target]
    gate.require(platform.machine().lower() == configuration["machine"].lower(), "build interpreter is not native")
    image_version = os.environ.get("ImageVersion", "")
    gate.require(image_version in configuration["images"], "runner image needs a reviewed input update")
    image = configuration["images"][image_version]
    gate.require(not work.exists() and not out.exists(), "build/output roots must be new")
    gate.require(shutil.disk_usage(work.parent).free >= 10 * 1024**3, "native build needs 10 GiB free")
    work.mkdir()
    out.mkdir()
    environment, compiler = compiler_environment(configuration, image)
    downloads = work / "downloads"
    source_archives = {}
    for key, row in {"cryptography": descriptor["cryptography"], "openssl": descriptor["openssl"],
                     "python": configuration["python"], "uv": configuration["uv"]}.items():
        archive = fetch(row, downloads / row["filename"])
        extract(archive, work / key)
        source_archives[key] = {"url": row["url"], "sha256": row["sha256"]}
    rust_manifest = {"url": descriptor["rust"]["manifest_url"], "sha256": descriptor["rust"]["manifest_sha256"]}
    fetch(rust_manifest, downloads / "rust-channel.toml")
    rust_version = run(["rustc", "+1.97.1", "--version"], capture=True)
    sysroot = Path(run(["rustc", "+1.97.1", "--print", "sysroot"], capture=True))
    installed_manifest = tomllib.loads((sysroot / "lib/rustlib/multirust-channel-manifest.toml").read_text(encoding="utf-8"))
    approved_manifest = tomllib.loads((downloads / "rust-channel.toml").read_text(encoding="utf-8"))
    installed_components = gate.rust_components(installed_manifest, configuration["rust_target"])
    gate.require(installed_components == gate.rust_components(approved_manifest, configuration["rust_target"]),
                 "installed Rust manifest differs from pinned release")
    rust_report = {"rust": rust_version, "rust_components": installed_components,
                   "rust_verbose": run(["rustc", "+1.97.1", "-vV"], capture=True),
                   "cargo": run(["cargo", "+1.97.1", "-V"], capture=True)}
    gate.validate_rust(rust_report, configuration)
    environment["RUSTUP_TOOLCHAIN"] = "1.97.1"
    environment["CARGO_HOME"] = str(work / "cargo")
    environment["CARGO_TARGET_DIR"] = str(work / "cargo-target")
    environment["UV_NO_CONFIG"] = "1"
    environment["UV_NO_CACHE"] = "1"
    environment["UV_PYTHON_DOWNLOADS"] = "never"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    python = work / "python/python" / ("python.exe" if target.startswith("windows") else "bin/python3.12")
    observed = json.loads(run([python, "-I", "-c", "import json,platform; print(json.dumps([platform.python_version(),platform.machine()]))"], capture=True))
    gate.require(observed[0] == "3.12.14" and observed[1].lower() == configuration["machine"].lower(),
                 "bundled build Python identity mismatch")
    uv_candidates = list((work / "uv").rglob("uv.exe" if target.startswith("windows") else "uv"))
    uv_candidates = [p for p in uv_candidates if p.is_file()]
    gate.require(len(uv_candidates) == 1, "uv executable ambiguous")
    uv = uv_candidates[0]
    if platform.system() != "Windows":
        uv.chmod(0o755)
    gate.require(run([uv, "--version"], capture=True).startswith("uv 0.12.7"), "uv version mismatch")
    wheelhouse = work / "build-wheels"
    wheelhouse.mkdir()
    lock_lines = []
    for row in configuration["python_dependencies"]:
        fetch(row, wheelhouse / row["filename"])
        lock_lines.append(f'{row["name"]}=={row["version"]} --hash=sha256:{row["sha256"]}')
    build_lock = work / "build-requirements.lock"
    build_lock.write_bytes(("\n".join(lock_lines) + "\n").encode())
    venv = work / "venv"
    run([uv, "venv", "--python", python, venv], env=environment)
    interpreter = venv / ("Scripts/python.exe" if target.startswith("windows") else "bin/python")
    environment["VIRTUAL_ENV"] = str(venv)
    environment["PATH"] = str(interpreter.parent) + os.pathsep + environment["PATH"]
    run([uv, "pip", "sync", "--python", interpreter, "--offline", "--no-index", "--find-links", wheelhouse,
         "--require-hashes", "--only-binary", ":all:", build_lock], env=environment)
    source = work / "cryptography/cryptography-50.0.1"
    openssl = work / "openssl/openssl-4.0.2"
    cargo_lock = source / "Cargo.lock"
    gate.require(cargo_lock.is_file(), "upstream Cargo lock missing")
    gate.require(gate.digest(cargo_lock.read_bytes()) == descriptor["cryptography"]["cargo_lock_sha256"],
                 "upstream Cargo lock does not match approved source")
    run(["cargo", "fetch", "--locked", "--target", configuration["rust_target"]], cwd=source, env=environment)
    environment["CARGO_NET_OFFLINE"] = "true"
    environment["OPENSSL_STATIC"] = "1"
    environment["OPENSSL_DIR"] = str(work / "openssl-install")
    configure_target = "VC-WIN64-ARM" if target.startswith("windows") else "darwin64-x86_64-cc"
    run(["perl", "Configure", configure_target, "no-shared", "no-module", "no-zlib", "no-comp",
         "no-tests", "no-asm", "--prefix=" + environment["OPENSSL_DIR"]], cwd=openssl, env=environment)
    make = "nmake" if target.startswith("windows") else "/usr/bin/make"
    run([make, "build_libs"], cwd=openssl, env=environment)
    run([make, "install_dev"], cwd=openssl, env=environment)
    run(wheel_command(uv, interpreter, source, out), env=environment)
    wheels = list(out.glob("*.whl"))
    gate.require(len(wheels) == 1, "producer did not emit exactly one wheel")
    wheel = gate.inspect_wheel(wheels[0], target)
    run([uv, "pip", "install", "--python", interpreter, "--offline", "--no-index", "--no-deps", wheels[0]], env=environment)
    smoke = json.loads(run([interpreter, "-I", "-c",
        "import json,platform,cryptography; from cryptography.hazmat.backends.openssl.backend import backend; "
        "print(json.dumps([cryptography.__version__,platform.machine(),backend.openssl_version_text()]))"],
        env=environment, capture=True))
    gate.require(smoke[0] == "50.0.1" and smoke[1].lower() == configuration["machine"].lower()
                 and smoke[2].startswith("OpenSSL 4.0.2 "), "native crypto/OpenSSL smoke identity mismatch")
    run([interpreter, "-m", "pytest", "tests", "--junitxml=" + str(out / "tests.xml")], cwd=source, env=environment)
    tests = gate.test_counts((out / "tests.xml").read_bytes(), configuration["test_policy"])
    cargo = tomllib.loads(cargo_lock.read_text(encoding="utf-8"))
    components = [{"name": row["name"], "version": row["version"], "source": row.get("source", "upstream-source"),
                   "sha256": row.get("checksum")} for row in cargo["package"]]
    gate.require(gate.digest(gate.canonical(components)) == descriptor["cryptography"]["cargo_packages_sha256"],
                 "Cargo inventory does not match approved source")
    sbom = {"schema": 1, "kind": "build-input-inventory", "target": target,
            "cryptography": descriptor["cryptography"], "openssl": descriptor["openssl"],
            "static_openssl": True, "cargo_lock_sha256": gate.digest(cargo_lock.read_bytes()),
            "cargo_packages": components, "python_build_tools": configuration["python_dependencies"],
            "wheel_sha256": wheel["sha256"]}
    (out / "build-sbom.json").write_bytes(gate.canonical(sbom))
    report = {"schema": 1, "target": target, "input_sha256": gate.digest(gate.canonical(descriptor)),
              "producer_sha": os.environ["GITHUB_SHA"], "run_id": int(os.environ["GITHUB_RUN_ID"]),
              "run_attempt": 1, "image_version": image_version, "compiler": compiler,
              "rust": rust_version, "python": observed, "openssl": smoke[2], "tests": tests,
              "build_lock_sha256": gate.digest(build_lock.read_bytes()), "wheel_sha256": wheel["sha256"],
              "recipe_sha256": gate.recipe_digest(Path(__file__)), "sources": source_archives}
    report.update(rust_report)
    (out / "build-report.json").write_bytes(gate.canonical(report))
    print(f"Built and tested {wheel['filename']}; {tests['passed']} upstream tests passed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=Path("packaging/cua/native-wheels-input.json"))
    parser.add_argument("--target", choices=gate.TARGETS, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build(args.inputs.resolve(), args.target, args.work.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
