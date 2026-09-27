"""Native build probes and independent data checks for Windows legal observations.

Only capture executes the installed interpreter. Validation never executes any
build output. These records are source-scope evidence, never package approval.
"""

import argparse
import io
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tomllib
import zipfile

if __package__:
    from scripts.validate_package_inputs import canonical_json, parse_json, read_owned, relative_path, require, sha256_bytes
else:
    from validate_package_inputs import canonical_json, parse_json, read_owned, relative_path, require, sha256_bytes


TARGETS = {"x64": "x86_64-pc-windows-msvc", "arm64": "aarch64-pc-windows-msvc"}
RECORD = "runtime-evidence/observation.json"
RUST_ZIP = "runtime-evidence/rust-target-libraries.zip"
RUST_MANIFEST = "runtime-evidence/rust-channel-manifest.toml"
BOUNDARY = {"status": "unapproved", "candidate_approval": False, "publishable": False}
LINK_MAPS = {"payload/vadgr.exe": "link-maps/vadgr.map",
             "payload/vadgr-app.exe": "link-maps/vadgr-app.map",
             "ba-functions.dll": "link-maps/ba-functions.map"}

# Isolated startup skips site initialization and .pth files. Only the exact
# installed wheel tree is added. The build step has already removed credentials.
PILLOW_PROBE = r'''
import ctypes, json, os, platform, sys
from ctypes import wintypes
sys.path.insert(0, sys.argv[1])
import PIL
from PIL import features
groups = {}
for group in ("modules", "codecs", "features"):
    names = sorted(getattr(features, group))
    check = getattr(features, "check_" + group.rstrip("s"))
    version = getattr(features, "version_" + group.rstrip("s"))
    groups[group] = {name: {"supported": bool(check(name)), "version": version(name)} for name in names}
psapi = ctypes.WinDLL("psapi", use_last_error=True)
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.GetCurrentProcess.restype = wintypes.HANDLE
psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
process = kernel.GetCurrentProcess()
modules = (wintypes.HMODULE * 2048)()
needed = wintypes.DWORD()
if not psapi.EnumProcessModulesEx(process, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3) or needed.value > ctypes.sizeof(modules):
    raise RuntimeError("Loaded module enumeration failed")
paths = []
for module in modules[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
    value = ctypes.create_unicode_buffer(32768)
    length = psapi.GetModuleFileNameExW(process, module, value, len(value))
    if not length or length >= len(value) - 1:
        raise RuntimeError("Loaded module path failed")
    paths.append(value.value)
print(json.dumps({"schema": 1, "machine": platform.machine(), "python": platform.python_version(),
    "pillow": PIL.__version__, "groups": groups, "loaded_modules": sorted(set(paths))}, sort_keys=True))
'''


def file_record(raw):
    return {"sha256": sha256_bytes(raw), "size": len(raw)}


def tree(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "linked runtime evidence path")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            relative_path(name)
            result[name] = read_owned(root, name)
    require(bool(result), "runtime evidence tree is empty")
    return result


def library_zip(members):
    require(sum(map(len, members.values())) < 750 * 1024 * 1024, "Rust target library evidence exceeds limit")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(members.items()):
            relative_path(name)
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, raw)
    return stream.getvalue()


def pillow_tree(raw_root):
    sites = [path for path in (raw_root / "payload/lib/cua/environments").glob("*/Lib/site-packages")
             if (path / "PIL/__init__.py").is_file()]
    require(len(sites) == 1, "observed Pillow installation is ambiguous")
    root = sites[0] / "PIL"
    return sites[0], {root.relative_to(raw_root).as_posix() + "/" + name: file_record(data)
                      for name, data in tree(root).items()}


def identity(value):
    return (isinstance(value, dict) and set(value) == {"size", "sha256"}
            and type(value["size"]) is int and value["size"] >= 0
            and isinstance(value["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]))


def capture(raw_root, architecture):
    require(os.name == "nt" and architecture in TARGETS, "runtime capture requires native Windows")
    expected = "AMD64" if architecture == "x64" else "ARM64"
    require(platform.machine().upper() == expected, "runtime capture host architecture differs")
    require(not any(os.environ.get(name) for name in ("GH_TOKEN", "GITHUB_TOKEN", "ES_USERNAME", "ES_PASSWORD",
        "ES_TOTP_SECRET", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")), "runtime capture must have no credentials")
    output = raw_root / "runtime-evidence"
    require(not output.exists(), "runtime evidence already exists")
    payload_raw = read_owned(raw_root, "payload/lib/cua/payload.json")
    payload = parse_json(payload_raw)
    require(payload["target"] == TARGETS[architecture], "runtime capture payload target differs")
    python_root = raw_root / "payload/lib/cua/python" / payload["python_version"]
    site, pillow_files = pillow_tree(raw_root)
    result = subprocess.run([str(python_root / "python.exe"), "-I", "-S", "-B", "-c", PILLOW_PROBE, str(site)],
        capture_output=True, timeout=120, check=False, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    require(result.returncode == 0 and len(result.stdout) < 1024 * 1024, "native Pillow probe failed")
    require(pillow_tree(raw_root)[1] == pillow_files, "Pillow probe changed installed files")
    probe = parse_json(result.stdout)
    require(probe["machine"].upper() == expected and probe["python"] == payload["python_version"], "Pillow probe interpreter differs")
    loaded = []
    system = Path(os.environ["SystemRoot"]).resolve()
    for name in probe.pop("loaded_modules"):
        path = Path(name).resolve()
        if path.is_relative_to(raw_root.resolve()):
            relative = path.relative_to(raw_root.resolve()).as_posix()
            loaded.append({"scope": "observed-input", "path": relative, **file_record(read_owned(raw_root, relative))})
        else:
            require(path.is_relative_to(system), "Pillow probe loaded an unobserved non-system binary")
            loaded.append({"scope": "operating-system-prerequisite", "path": path.relative_to(system).as_posix(),
                **file_record(path.read_bytes())})
    target = TARGETS[architecture]
    sysroot = Path(subprocess.check_output(["rustc", "--print", "sysroot"], text=True).strip())
    library_root = Path(subprocess.check_output(["rustc", "--print", "target-libdir", "--target", target], text=True).strip())
    require(library_root.resolve() == (sysroot / "lib/rustlib" / target / "lib").resolve(), "Rust target library directory differs")
    libraries = tree(library_root)
    rust_manifest = read_owned(sysroot, "lib/rustlib/multirust-channel-manifest.toml")
    manifest = tomllib.loads(rust_manifest.decode())
    rust_target = manifest["pkg"]["rust-std"]["target"][target]
    maps = {}
    for executable, path in LINK_MAPS.items():
        if not (raw_root / executable).is_file():
            continue
        data = read_owned(raw_root, path)
        require(bool(data.strip()), "Rust link map is absent")
        maps[executable] = {"executable": file_record(read_owned(raw_root, executable)), "path": path, **file_record(data)}
    libraries_raw = library_zip(libraries)
    record = {"schema": 1, **BOUNDARY, "architecture": architecture, "target": target,
        "payload_sha256": sha256_bytes(payload_raw),
        "pillow": {"probe": probe, "probe_source_sha256": sha256_bytes(PILLOW_PROBE.encode()),
            "files": pillow_files, "loaded_modules": sorted(loaded, key=lambda row: (row["scope"], row["path"]))},
        "rust": {"channel_manifest": file_record(rust_manifest), "target_distribution": rust_target,
            "library_archive": file_record(libraries_raw),
            "compiler_observation": file_record(read_owned(raw_root, "rustc-version.txt")),
            "members": {name: file_record(data) for name, data in libraries.items()}, "link_maps": maps},
        "limitation": "Native feature results and exact build inputs. Sysroot membership alone is not proof of linked symbols; link maps and target source scope require independent matching."}
    output.mkdir()
    (raw_root / RUST_ZIP).write_bytes(libraries_raw)
    (raw_root / RUST_MANIFEST).write_bytes(rust_manifest)
    (raw_root / RECORD).write_bytes(canonical_json(record))
    validate(raw_root, architecture)


def validate(raw_root, architecture):
    require(architecture in TARGETS, "unknown runtime evidence architecture")
    record = parse_json(read_owned(raw_root, RECORD))
    require(record["schema"] == 1 and all(record.get(key) == value for key, value in BOUNDARY.items())
            and record["architecture"] == architecture and record["target"] == TARGETS[architecture], "runtime evidence boundary differs")
    payload_raw = read_owned(raw_root, "payload/lib/cua/payload.json")
    payload = parse_json(payload_raw)
    require(record["payload_sha256"] == sha256_bytes(payload_raw) and payload["target"] == TARGETS[architecture], "runtime evidence payload differs")
    pillow = record["pillow"]
    require(pillow["probe_source_sha256"] == sha256_bytes(PILLOW_PROBE.encode()), "runtime probe source differs")
    require(pillow["files"] == pillow_tree(raw_root)[1], "Pillow file binding differs")
    probe = pillow["probe"]
    require(probe["schema"] == 1 and probe["machine"].upper() == ("AMD64" if architecture == "x64" else "ARM64")
            and probe["python"] == payload["python_version"]
            and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", probe["pillow"]), "Pillow probe interpreter differs")
    require(set(probe["groups"]) == {"modules", "codecs", "features"}, "Pillow probe groups differ")
    for rows in probe["groups"].values():
        require(isinstance(rows, dict) and bool(rows), "Pillow probe group is empty")
        for name, row in rows.items():
            require(re.fullmatch(r"[a-z0-9_]+", name) and set(row) == {"supported", "version"}
                    and type(row["supported"]) is bool and (row["version"] is None or
                        isinstance(row["version"], str) and len(row["version"]) < 256), "Pillow feature observation differs")
    seen = set()
    require(bool(pillow["loaded_modules"]), "Pillow loaded modules absent")
    for row in pillow["loaded_modules"]:
        require(row["scope"] in {"observed-input", "operating-system-prerequisite"}, "unknown loaded module scope")
        relative_path(row["path"])
        key = (row["scope"], row["path"].casefold())
        require(key not in seen and identity({key: row[key] for key in ("sha256", "size")}), "invalid loaded module identity")
        seen.add(key)
        if row["scope"] == "observed-input":
            require(file_record(read_owned(raw_root, row["path"])) == {key: row[key] for key in ("sha256", "size")}, "loaded module binding differs")
    rust = record["rust"]
    manifest_raw = read_owned(raw_root, RUST_MANIFEST)
    require(file_record(manifest_raw) == rust["channel_manifest"] and
            file_record(read_owned(raw_root, "rustc-version.txt")) == rust["compiler_observation"], "Rust compiler or manifest differs")
    manifest = tomllib.loads(manifest_raw.decode())
    require(rust["target_distribution"] == manifest["pkg"]["rust-std"]["target"][TARGETS[architecture]], "Rust target distribution differs")
    members, names = {}, set()
    archive_raw = read_owned(raw_root, RUST_ZIP)
    require(file_record(archive_raw) == rust["library_archive"] and len(archive_raw) < 750 * 1024 * 1024
            and archive_raw[-22:-18] == b"PK\x05\x06" and archive_raw[-2:] == b"\0\0", "unsafe Rust evidence archive")
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        require(not archive.comment and len(archive.infolist()) < 2000
                and sum(entry.file_size for entry in archive.infolist()) < 750 * 1024 * 1024, "unsafe Rust evidence archive")
        for entry in archive.infolist():
            relative_path(entry.filename)
            require(entry.filename.casefold() not in names and not entry.is_dir() and not entry.comment and not entry.extra
                    and not entry.flag_bits & 1 and entry.compress_type == zipfile.ZIP_DEFLATED
                    and entry.external_attr >> 16 == 0o100644 and entry.file_size < 256 * 1024 * 1024, "unsafe Rust evidence member")
            names.add(entry.filename.casefold())
            members[entry.filename] = file_record(archive.read(entry))
    require(bool(members) and members == rust["members"], "Rust target member set differs")
    require(set(rust["link_maps"]) == {name for name in LINK_MAPS if (raw_root / name).is_file()}
            and {"payload/vadgr.exe", "payload/vadgr-app.exe"} <= set(rust["link_maps"]), "Rust link-map set differs")
    for executable, row in rust["link_maps"].items():
        require(row["path"] == LINK_MAPS[executable] and row["size"] > 0
                and file_record(read_owned(raw_root, executable)) == row["executable"]
                and file_record(read_owned(raw_root, row["path"])) == {key: row[key] for key in ("sha256", "size")}, "Rust link-map binding differs")
    return record


def rust_source_binding(raw_root, record, component, archive_root):
    """Match observed target libraries to the pinned distribution, then map symbols."""
    descriptor = record["rust"]["target_distribution"]
    filename = component["download_location"].rsplit("/", 1)[-1]
    require(descriptor.get("available") is True and descriptor["xz_hash"] == component["sha256"]
            and descriptor["xz_url"].startswith("https://static.rust-lang.org/dist/")
            and descriptor["xz_url"].rsplit("/", 1)[-1] == filename, "Rust source distribution identity differs")
    raw = read_owned(archive_root, filename)
    require(sha256_bytes(raw) == component["sha256"], "Rust distribution archive differs")
    prefix = "/lib/rustlib/" + record["target"] + "/lib/"
    members, seen = {}, set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:xz") as archive:
        for member in archive:
            relative_path(member.name)
            require(member.name.casefold() not in seen and (member.isfile() or member.isdir()), "unsafe Rust distribution member")
            seen.add(member.name.casefold())
            if member.isfile() and prefix in member.name:
                require(member.size < 256 * 1024 * 1024, "oversized Rust distribution member")
                name = member.name.split(prefix, 1)[1]
                require(name not in members, "repeated Rust distribution library")
                members[name] = file_record(archive.extractfile(member).read())
    require(members and members == record["rust"]["members"], "observed Rust libraries differ from pinned distribution")
    libraries = {Path(name).stem: name for name in members if name.endswith(".rlib")}
    linked = {}
    for executable, row in record["rust"]["link_maps"].items():
        text = read_owned(raw_root, row["path"]).decode("utf-8-sig")
        require("Publics by Value" in text and "Lib:Object" in text and "entry point at" in text, "unknown Rust link-map format")
        references = {}
        for number, line in enumerate(text.splitlines(), 1):
            match = re.match(r"^\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8,16}\s+\S+\s+[0-9A-Fa-f]{8,16}\s+(?:f\s+)?(\S+):(\S+)\s*$", line)
            if match and match[1] in libraries:
                name = libraries[match[1]]
                references.setdefault(name, []).append({"line": number, "object": match[2]})
        require(any(name.startswith("libstd-") for name in references), "Rust standard library symbol binding absent")
        linked[executable] = {"executable": row["executable"], "map_sha256": row["sha256"],
            "libraries": {name: {**members[name], "symbols": references[name]} for name in sorted(references)}}
    scope = {name: {"identity": members[name], "referenced_by": sorted(
                 executable for executable, row in linked.items() if name in row["libraries"])}
             for name in sorted(members)}
    for row in scope.values():
        row["classification"] = "observed-public-symbol-reference" if row["referenced_by"] else "available-build-input-not-observed-in-public-symbol-map"
    return {"schema": 1, **BOUNDARY, "target": record["target"], "distribution_sha256": component["sha256"],
        "distribution_url": descriptor["xz_url"], "observed_library_count": len(members), "linked": linked,
        "library_scope": scope,
        "limitation": "Complete target sysroot equality and named public symbols in exact executable link maps. This does not assert every available library was linked or conclude the scope of third-party grants."}


PILLOW_FEATURES = {
    "pkg:generic/freetype2": ("modules", "freetype2"),
    "pkg:generic/fribidi": ("features", "fribidi"),
    "pkg:generic/harfbuzz": ("features", "harfbuzz"),
    "pkg:generic/libavif": ("modules", "avif"),
    "pkg:generic/libimagequant": ("features", "libimagequant"),
    "pkg:generic/libjpeg": ("features", "libjpeg_turbo"),
    "pkg:generic/libtiff": ("codecs", "libtiff"),
    "pkg:generic/libwebp": ("modules", "webp"),
    "pkg:generic/libxcb": ("features", "xcb"),
    "pkg:generic/littlecms2": ("modules", "littlecms2"),
    "pkg:generic/openjpeg": ("codecs", "jpg_2000"),
    "pkg:generic/zlib": ("features", "zlib_ng"),
}


def pillow_scope(record, catalogue):
    """Classify what the native probe establishes, never infer absence from no load."""
    pillow = record["pillow"]
    version = pillow["probe"]["pillow"]
    component = catalogue.get("metadata", {}).get("component", {})
    require(component.get("name", "").lower() == "pillow" and component.get("version") == version,
            "Pillow catalogue identity differs")
    members = {name: identity for name, identity in pillow["files"].items()
               if name.lower().endswith((".pyd", ".dll"))}
    loaded = {row["path"] for row in pillow["loaded_modules"] if row["scope"] == "observed-input"}
    rows, seen = [], set()
    for item in catalogue.get("components", []):
        reference = item.get("bom-ref")
        require(isinstance(reference, str) and reference and reference not in seen, "Pillow catalogue reference differs")
        seen.add(reference)
        row = {"bom_ref": reference, "name": item["name"], "declared_version": item.get("version"),
               "classification": "catalogue-entry-needs-build-scope"}
        if item["name"].startswith("PIL."):
            module = item["name"].removeprefix("PIL.")
            matches = {name: value for name, value in members.items() if Path(name).name.startswith(module + ".")}
            require(len(matches) <= 1, "ambiguous Pillow native module")
            row.update(observed_members=matches,
                loaded_by_probe=any(name in loaded for name in matches),
                classification="observed-installed-native-module" if matches else "catalogue-module-not-observed")
        else:
            selector = PILLOW_FEATURES.get(reference)
            if reference == f"pkg:pypi/pillow@{version}#thirdparty/raqm":
                selector = ("features", "raqm")
            if selector:
                value = pillow["probe"]["groups"][selector[0]].get(selector[1])
                row["feature_selector"] = list(selector)
                if value is not None:
                    row["native_feature"] = value
                    row["classification"] = "native-feature-supported" if value["supported"] else "native-feature-not-supported"
                    row["version_matches_declaration"] = value["version"] is not None and value["version"] == item.get("version")
        rows.append(row)
    require(bool(rows), "Pillow catalogue is empty")
    return {"schema": 1, **BOUNDARY, "target": record["target"], "pillow_version": version,
        "components": sorted(rows, key=lambda row: row["bom_ref"]),
        "native_members": {name: {**value, "loaded_by_probe": name in loaded} for name, value in sorted(members.items())},
        "limitations": ["An unloaded module remains shipped. An unsupported feature does not prove its transitive libraries are absent.",
                        "Catalogue/probe version differences remain visible; no version is normalized into equality.",
                        "No catalogue entry is classified build-only and no grant or source duty is concluded by this hook."]}


def retain_in_packet(packet, inputs, architecture, archive_root):
    if not (inputs / RECORD).exists():
        return
    record = validate(inputs, architecture)
    version = record["pillow"]["probe"]["pillow"]
    site, _ = pillow_tree(inputs)
    catalogue_name = (site.relative_to(inputs) / f"pillow-{version}.dist-info/sboms/pillow-{version}.cdx.json").as_posix()
    catalogue_raw = read_owned(inputs, catalogue_name)
    classification = pillow_scope(record, parse_json(catalogue_raw))
    classification["catalogue"] = {"path": catalogue_name, **file_record(catalogue_raw)}
    packet.put("pillow-native-scope.json", canonical_json(classification))
    for name in (RECORD, RUST_MANIFEST):
        packet.put("producer-evidence/" + name, read_owned(inputs, name))
    for row in record["rust"]["link_maps"].values():
        packet.put("producer-evidence/" + row["path"], read_owned(inputs, row["path"]))
    for identifier, name, data in (
            ("wheel-pillow-" + record["pillow"]["probe"]["pillow"], "runtime-feature-observation.json", record["pillow"]),
            ("runtime-rust-std-" + next(row["version"] for row in packet.components if row["id"].startswith("runtime-rust-std-")),
             "target-library-binding.json", None)):
        component = next(row for row in packet.components if row["id"] == identifier)
        if data is None:
            data = rust_source_binding(inputs, record, component, archive_root)
            pending = next(row for row in packet.pending if row["id"] == identifier)
            pending["items"] = [item for item in pending["items"] if item != "target-binary-to-source-mapping"]
        path = "legal/NOTICES/" + identifier + "/" + name
        raw = canonical_json(data)
        packet.put(path, raw)
        component["notice_files"].append({"path": path, "sha256": sha256_bytes(raw)})
        evidence = next(row for row in packet.evidence if row["id"] == identifier)
        evidence["native_runtime_observation"] = {"path": path, "sha256": sha256_bytes(raw),
            "scope": "exact-target-runtime-observation-not-license-approval"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "validate"))
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--architecture", choices=TARGETS, required=True)
    args = parser.parse_args()
    if args.command == "capture":
        capture(args.raw_root.resolve(), args.architecture)
    else:
        validate(args.raw_root.resolve(), args.architecture)
    print("Unapproved native runtime evidence validated.")


if __name__ == "__main__":
    main()
