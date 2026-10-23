"""Bind the two local accessibility fixes to complete, reviewed source identities."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tomllib

REGISTRY = "packaging/rust-patches.json"
SOURCE_INPUTS = {"Cargo.toml", REGISTRY}
BASES = {
    "accesskit_atspi_common": ("0.18.1", "1e8c61bee90b42a772d39d06a740207dc71a4e780004ace1db8d99fb1baaa954"),
    "accesskit_unix": ("0.21.1", "b016ca8db0ea0ea2ceff29a9d6240391492d960716aa471967c00e8cc8cb197c"),
}
CONCLUSIONS = {"accesskit_atspi_common": "Apache-2.0 AND BSD-3-Clause",
               "accesskit_unix": "Apache-2.0 AND MIT"}
LICENSE_HASHES = {
    "LICENSE-APACHE": "62c7a1e35f56406896d7aa7ca52d0cc0d272ac022b5d2796e7d6905db8a3636a",
    "LICENSE-MIT": "23f18e03dc49df91622fe2a76176497404e46ced8a715d9d2b67a7446571cca3",
    "LICENSE.chromium": "845022e0c1db1abb41a6ba4cd3c4b674ec290f3359d9d3c78ae558d4c0ed9308",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(root, name):
    for ancestor in (root.absolute(), *root.absolute().parents):
        require(not ancestor.is_symlink() and not getattr(ancestor, "is_junction", lambda: False)(), "linked patch root")
    relative = PurePosixPath(name)
    require(isinstance(name, str) and bool(name) and str(relative) == name
            and not relative.is_absolute() and ".." not in relative.parts
            and "\\" not in name and ":" not in name
            and not any(ord(c) < 32 for c in name), "unsafe patch path")
    path = root
    for part in relative.parts:
        path = path / part
        require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "linked patch path")
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "unsafe patch file")
    raw = path.read_bytes()
    # Patch manifests bind repository text, including native Windows checkouts.
    if b"\r\n" in raw:
        raw.decode("utf-8")
        require(b"\r" not in raw.replace(b"\r\n", b""), "mixed patch line endings")
        raw = raw.replace(b"\r\n", b"\n")
    return raw


def document(root, name):
    raw = read(root, name)
    value = json.loads(raw)
    require(raw == canonical(value), "noncanonical patch manifest")
    return value


def load(root):
    """Validate every registered byte; absence is valid only without overrides."""
    root = Path(root)
    cargo = tomllib.loads(read(root, "Cargo.toml").decode())
    overrides = cargo.get("patch", {})
    if not overrides:
        require(not (root / REGISTRY).exists(), "unselected patch registry")
        return {}
    require(set(overrides) == {"crates-io"} and set(overrides["crates-io"]) == set(BASES), "unregistered Cargo patch")
    registry = document(root, REGISTRY)
    require(set(registry) == {"schema", "patches"} and type(registry["schema"]) is int
            and registry["schema"] == 1 and isinstance(registry["patches"], list)
            and len(registry["patches"]) == 2, "invalid patch registry")
    result = {}
    lock = tomllib.loads(read(root, "Cargo.lock").decode())["package"]
    for item in registry["patches"]:
        require(set(item) == {"name", "version", "path", "manifest", "manifest_sha256",
                              "upstream_archive_url", "upstream_archive_sha256"}, "invalid patch registration")
        name = item["name"]
        require(name in BASES and name not in result, "unexpected patch component")
        version, upstream = BASES[name]
        directory = f"vendor/{name}-{version}"
        manifest = f"packaging/rust-patches/{name}-{version}.json"
        require(item["version"] == version and item["path"] == directory and item["manifest"] == manifest
                and item["upstream_archive_sha256"] == upstream
                and item["upstream_archive_url"] == f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
                and overrides["crates-io"][name] == {"path": directory}, "patch base or mapping differs")
        matches = [p for p in lock if p["name"] == name]
        require(len(matches) == 1 and matches[0]["version"] == version
                and "source" not in matches[0] and "checksum" not in matches[0], "patch lock identity differs")
        raw = read(root, manifest)
        require(digest(raw) == item["manifest_sha256"], "patch source manifest changed")
        contents = document(root, manifest)
        require(set(contents) == {"schema", "name", "version", "files"} and contents["schema"] == 1
                and contents["name"] == name and contents["version"] == version, "patch manifest identity differs")
        crate = root / directory
        require(crate.is_dir() and not crate.is_symlink(), "unsafe patch directory")
        actual = set()
        for path in crate.rglob("*"):
            require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "linked patch member")
            if path.is_file():
                actual.add(path.relative_to(crate).as_posix())
            else:
                require(path.is_dir(), "special patch member")
        names = set()
        for row in contents["files"]:
            require(set(row) == {"path", "mode", "bytes", "sha256"} and row["path"] not in names,
                    "invalid patch file row")
            data = read(crate, row["path"])
            require(type(row["mode"]) is int and row["mode"] in (0o644, 0o755)
                    and type(row["bytes"]) is int and row["bytes"] == len(data)
                    and digest(data) == row["sha256"], "patch file bytes differ")
            if os.name != "nt":
                actual_mode = stat.S_IMODE((crate / row["path"]).stat().st_mode)
                # Git binds the executable bit; ordinary shared checkouts add group write.
                require(actual_mode in (row["mode"], row["mode"] | 0o020), "patch file mode differs")
            names.add(row["path"])
        require(names == actual and "PATCHES.md" in names, "patch file membership differs")
        for filename, checksum in LICENSE_HASHES.items():
            require(digest(read(crate, filename)) == checksum, "patch license grant differs")
        package = tomllib.loads(read(crate, "Cargo.toml").decode())["package"]
        require(package["name"] == name and package["version"] == version
                and package["license"] == "MIT OR Apache-2.0", "patch package identity differs")
        result[name] = {**item, "manifest_bytes": raw, "files": contents["files"]}
    require(set(result) == set(BASES), "incomplete patch registry")
    return result


def component(root, metadata, patches):
    name = metadata["name"]
    require(name in patches and metadata["version"] == patches[name]["version"]
            and metadata["source"] is None, "unbound local Cargo dependency")
    item = patches[name]
    require(Path(metadata["manifest_path"]).resolve() == (Path(root) / item["path"] / "Cargo.toml").resolve(),
            "local Cargo path differs")
    return item


def location(root, item):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(re.fullmatch("[a-f0-9]{40}", commit), "invalid patch source commit")
    raw = subprocess.check_output(["git", "show", commit + ":" + item["manifest"]], cwd=root)
    require(raw == item["manifest_bytes"], "patch manifest is not committed")
    return f"https://raw.githubusercontent.com/MONTBRAIN/vadgr/{commit}/{item['manifest']}"


def location_commit(item, url):
    match = re.fullmatch(r"https://raw\.githubusercontent\.com/MONTBRAIN/vadgr/([a-f0-9]{40})/"
                         + re.escape(item["manifest"]), url)
    require(match is not None, "patched source location differs")
    return match[1]


def verify_location(root, item, url):
    """Review-time historical provenance check; requires the retained Git object."""
    commit = location_commit(item, url)
    try:
        raw = subprocess.check_output(["git", "show", commit + ":" + item["manifest"]], cwd=root,
                                      stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as error:
        raise ValueError("patched source URL commit unavailable") from error
    require(raw == item["manifest_bytes"], "patched source URL bytes differ")
    return {"source_commit": commit, "path": item["manifest"], "sha256": digest(raw),
            "historical_git_blob_verified": True, "network_authentication": False}
