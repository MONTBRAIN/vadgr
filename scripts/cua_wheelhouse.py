#!/usr/bin/env python3
"""Materialize the reviewed target closure for an offline, secret-free build.

Never resolves dependencies or approves a new hash. PyPI catalog entries must
match the reviewed selected digest; custom outputs use exact artifact IDs.
"""

from __future__ import annotations

import argparse
import email
import io
import itertools
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

if __package__:
    from scripts import cua_release_inputs as release
    from scripts import distribution_matrix
    from scripts.validate_package_inputs import (
        PackageInputError, canonical_json, parse_json, read_owned, relative_path,
        require, sha256_bytes,
    )
else:
    import cua_release_inputs as release
    import distribution_matrix
    from validate_package_inputs import (
        PackageInputError, canonical_json, parse_json, read_owned, relative_path,
        require, sha256_bytes,
    )

MAX_ARCHIVE = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def compatible(tag: str, target: str) -> bool:
    release.lock_path(target)
    fields = tag.split("-")
    if len(fields) != 3:
        return False
    python, abi, platform = fields
    abi_ok = ((python in ("py3", "py312", "cp312") and abi == "none")
              or (python == "cp312" and abi == "cp312")
              or (re.fullmatch(r"cp3[0-9]+", python) is not None
                  and 2 <= int(python[3:]) <= 12 and abi == "abi3"))
    if not abi_ok:
        return False
    if platform == "any":
        return abi == "none"
    architecture = target.split("-", 1)[0]
    if target.endswith("pc-windows-msvc"):
        return platform == {"aarch64": "win_arm64", "x86_64": "win_amd64"}[architecture]
    if target.endswith("apple-darwin"):
        match = re.fullmatch(r"macosx_([0-9]+)_([0-9]+)_(x86_64|arm64|universal2)", platform)
        return bool(match and (int(match[1]), int(match[2])) <= (13, 0)
                    and match[3] in ({"arm64", "universal2"} if architecture == "aarch64"
                                     else {"x86_64", "universal2"}))
    match = re.fullmatch(r"manylinux_2_([0-9]+)_(x86_64|aarch64)", platform)
    if match:
        # The shared Linux/WSL closure may not exceed WSL's glibc 2.35 floor.
        return int(match[1]) <= 35 and match[2] == architecture
    return platform in {f"manylinux2014_{architecture}"} | (
        {"manylinux1_x86_64", "manylinux2010_x86_64"} if architecture == "x86_64" else set())


def filename_tags(filename: str) -> tuple[str, str, set[str]]:
    require(relative_path(filename) == filename and "/" not in filename and filename.endswith(".whl"),
            "unsafe wheel filename")
    parts = filename[:-4].split("-")
    require(len(parts) in (5, 6), "invalid wheel filename")
    require(len(parts) == 5 or re.fullmatch(r"[0-9][A-Za-z0-9_]*", parts[2]),
            "invalid wheel build tag")
    package, version = parts[:2]
    require(re.fullmatch(r"[A-Za-z0-9_.]+", package) and re.fullmatch(r"[A-Za-z0-9_.!+]+", version),
            "invalid wheel package identity")
    tags = {"-".join(row) for row in itertools.product(*(part.split(".") for part in parts[-3:]))}
    return normalized(package), version, tags


def archive_members(data: bytes) -> dict[str, bytes]:
    require(len(data) <= MAX_ARCHIVE, "wheel archive exceeds size limit")
    members, seen, total = {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        require(len(archive.infolist()) <= 20_000, "wheel archive has too many members")
        for item in archive.infolist():
            name = item.filename.rstrip("/")
            relative_path(name)
            key = name.casefold()
            require(key not in seen, "wheel archive has duplicate or case-colliding members")
            seen.add(key)
            kind = (item.external_attr >> 16) & 0o170000
            require(not item.flag_bits & 1 and kind in (0, 0o100000, 0o040000)
                    and not item.external_attr & 0x400, "wheel archive contains link or special member")
            if item.is_dir():
                continue
            require(kind in (0, 0o100000), "wheel archive file has directory type")
            total += item.file_size
            require(total <= MAX_EXPANDED, "wheel archive expands beyond limit")
            contents = archive.read(item)
            require(len(contents) == item.file_size, "wheel archive member size differs")
            members[name] = contents
    return members


def validate_wheel(data, filename, name, version, target):
    package, wheel_version, tags = filename_tags(filename)
    require(package == name and wheel_version == version and any(compatible(tag, target) for tag in tags),
            "wheel target, ABI or package differs")
    members = archive_members(data)
    metadata_names = [key for key in members if key.endswith(".dist-info/METADATA")]
    require(len(metadata_names) == 1, "wheel has ambiguous package metadata")
    metadata_name = metadata_names[0]
    metadata_parts = metadata_name.removesuffix(".dist-info/METADATA").rsplit("-", 1)
    require("/" not in metadata_parts[0] and len(metadata_parts) == 2
            and normalized(metadata_parts[0]) == name and metadata_parts[1] == version,
            "wheel metadata directory differs from selected package")
    wheel_name = metadata_name.removesuffix("METADATA") + "WHEEL"
    require(wheel_name in members, "wheel tag metadata absent")
    metadata = email.message_from_bytes(members[metadata_name])
    wheel = email.message_from_bytes(members[wheel_name])
    require(metadata.get_all("Name") is not None and len(metadata.get_all("Name")) == 1
            and normalized(metadata["Name"]) == name and metadata.get_all("Version") == [version]
            and set(wheel.get_all("Tag", [])) == tags and len(wheel.get_all("Tag", [])) == len(tags),
            "wheel metadata does not match selected identity")
    expected = target.split("-", 1)[0]
    kind = "pe" if target.endswith("windows-msvc") else "macho" if target.endswith("apple-darwin") else "elf"
    for content in members.values():
        if content[:2] == b"MZ" or content[:4] in (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
            try:
                native_kind, architecture = distribution_matrix.binary_architecture(content)
            except distribution_matrix.Refused:
                raise PackageInputError("wheel native executable header is invalid") from None
            require(native_kind == kind and expected in architecture.split("+"),
                    "wheel includes incompatible native executable")
    return members


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def fetch(url: str, limit: int) -> bytes:
    address = urllib.parse.urlsplit(url)
    require(address.scheme == "https" and address.hostname in {"pypi.org", "files.pythonhosted.org"}
            and not address.username and not address.password and not address.query and not address.fragment
            and address.port in (None, 443), "wheel download origin refused")
    with urllib.request.build_opener(NoRedirect).open(url, timeout=90) as response:
        data = response.read(limit + 1)
    require(len(data) <= limit, "wheel response exceeds limit")
    return data


def upstream_wheel(name, version, digest, target):
    catalog = parse_json(fetch(f"https://pypi.org/pypi/{urllib.parse.quote(name, safe='')}/"
                               f"{urllib.parse.quote(version, safe='')}/json", release.MAX_METADATA))
    selected = [row for row in catalog.get("urls", []) if row.get("packagetype") == "bdist_wheel"
                and row.get("digests", {}).get("sha256") == digest and row.get("yanked") is False]
    require(len(selected) == 1, "reviewed upstream wheel is unavailable or ambiguous")
    row = selected[0]
    require(any(compatible(tag, target) for tag in filename_tags(row["filename"])[2]),
            "reviewed upstream wheel is incompatible")
    data = fetch(row["url"], MAX_ARCHIVE)
    require(type(row.get("size")) is int and len(data) == row["size"] and sha256_bytes(data) == digest,
            "upstream wheel bytes differ from reviewed lock")
    return row["filename"], data


def custom_wheel(row):
    result = subprocess.run(["gh", "api", "--method", "GET",
                             f"repos/{release.REPOSITORY}/actions/artifacts/{row['artifact_id']}/zip"],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, timeout=120, check=False)
    require(result.returncode == 0 and len(result.stdout) <= MAX_ARCHIVE
            and "sha256:" + sha256_bytes(result.stdout) == row["artifact_digest"],
            "reviewed native wheel artifact cannot be retrieved")
    members = archive_members(result.stdout)
    require(set(members) == {row["filename"], "build-report.json", "tests.xml", "build-sbom.json"},
            "native wheel artifact set differs")
    for member, field in (("build-report.json", "build_report_sha256"), ("tests.xml", "test_report_sha256"),
                          ("build-sbom.json", "build_sbom_sha256"), (row["filename"], "sha256")):
        require(sha256_bytes(members[member]) == row[field], "native wheel artifact member changed")
    require(len(members[row["filename"]]) == row["size"], "native wheel size changed")
    return row["filename"], members[row["filename"]]


def materialize(source: Path, trusted: Path, target: str, output: Path):
    require(output.is_absolute() and not output.exists() and output.parent.is_dir() and not output.is_symlink(),
            "wheelhouse output must be a new directory")
    require(all(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)()
                for path in (output.parent, *output.parent.parents)), "wheelhouse output parent is linked")
    binding = release.reviewed_inputs(source, trusted, target)
    release.verify_origin(trusted)
    _, manifest = release.manifest(trusted)
    selected = release.selected_lock(read_owned(trusted, release.lock_path(target)))
    with tempfile.TemporaryDirectory(prefix="vadgr-wheelhouse-", dir=output.parent) as temporary:
        stage = Path(temporary) / "closed"
        stage.mkdir()
        records = []
        for name, (version, digest) in sorted(selected.items()):
            custom = [row for row in manifest["wheels"] if row["sha256"] == digest]
            if custom:
                require(len(custom) == 1 and name == "cryptography" and version == "50.0.1"
                        and custom[0]["target"] == release.CUSTOM_TARGETS.get(target),
                        "custom wheel is not reviewed for this target")
                filename, data = custom_wheel(custom[0])
            else:
                filename, data = upstream_wheel(name, version, digest, target)
            require(sha256_bytes(data) == digest, "wheel differs from selected target lock")
            validate_wheel(data, filename, name, version, target)
            with (stage / filename).open("xb") as stream:
                stream.write(data)
            records.append({"filename": filename, "name": name, "version": version,
                            "size": len(data), "sha256": digest})
        (stage / "wheelhouse.json").write_bytes(canonical_json({"schema": 1, **binding, "wheels": records}))
        require(not output.exists(), "wheelhouse output appeared during materialization")
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", choices=sorted(release.TARGETS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        materialize(args.source.resolve(), Path(__file__).resolve().parents[1], args.target, args.out.absolute())
    except (PackageInputError, OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile,
            subprocess.SubprocessError):
        print("CUA wheelhouse refused: reviewed closure or producer verification failed.", file=sys.stderr)
        return 1
    print("Reviewed CUA wheelhouse materialized for offline assembly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
