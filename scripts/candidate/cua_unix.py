"""Safe Unix runtime archive handling and identity measurement."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import unicodedata

from scripts.validate_package_inputs import relative_path, require, sha256_bytes


MEMBER_LIMIT = 12_000
BYTE_LIMIT = 2 * 1024**3


def _identity(data):
    return {"size": len(data), "sha256": sha256_bytes(data)}


def _name(raw):
    require(isinstance(raw, str) and "\\" not in raw and "\0" not in raw,
            "WSL archive path is not portable")
    while raw.startswith("./"):
        raw = raw[2:]
    raw = raw.rstrip("/")
    if raw in ("", "."):
        return ""
    relative_path(raw)
    path = PurePosixPath(raw)
    require(not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts),
            "WSL archive path escapes its root")
    normalized = path.as_posix()
    require(normalized == raw, "WSL archive path is not canonical")
    return normalized


def _target(name, link):
    require(isinstance(link, str) and link and "\\" not in link and "\0" not in link
            and all(ord(char) >= 32 and ord(char) != 127 for char in link),
            "WSL link target is invalid")
    raw = PurePosixPath(link)
    require(not raw.is_absolute(), "WSL link target is absolute")
    parts = list(PurePosixPath(name).parent.parts)
    for part in raw.parts:
        if part in ("", "."):
            continue
        if part == "..":
            require(parts, "WSL link target escapes its root")
            parts.pop()
        else:
            parts.append(part)
    require(parts, "WSL link target resolves to the archive root")
    return PurePosixPath(*parts).as_posix()


def _validate(entries):
    links = {name: row[1] for name, row in entries.items() if row[0] == "link"}
    for name in entries:
        parent = PurePosixPath(name).parent
        while parent != PurePosixPath("."):
            parent_name = parent.as_posix()
            require(parent_name not in entries or entries[parent_name][0] == "dir",
                    "WSL archive stores a member below a nondirectory")
            parent = parent.parent
    resolved = {}
    for name, link in links.items():
        current = _target(name, link)
        visited = {name}
        while current in links:
            require(current not in visited, "WSL link cycle")
            visited.add(current)
            current = _target(current, links[current])
        require(current in entries, "WSL link target is missing")
        kind = entries[current][0]
        if kind == "dir":
            require(PurePosixPath(name).name == "lib64" and link == "lib"
                    and PurePosixPath(current) == PurePosixPath(name).with_name("lib"),
                    "WSL directory link is not the approved lib64 link")
        else:
            require(kind == "file", "WSL link target is not a file")
        resolved[name] = (current, kind)
    return resolved


def unpack(archive_path, output):
    """Extract a validated Unix runtime without writing through archive links."""
    require(not output.exists(), "WSL extraction destination exists")
    entries = {}
    members = []
    normalized_names = set()
    total = 0
    with tarfile.open(archive_path, "r:*") as archive:
        raw_members = archive.getmembers()
        require(len(raw_members) <= MEMBER_LIMIT, "WSL archive member limit")
        for member in raw_members:
            name = _name(member.name)
            if not name:
                require(member.isdir(), "WSL archive root is not a directory")
                continue
            normalized = unicodedata.normalize("NFC", name)
            require(name not in entries and normalized not in normalized_names,
                    "WSL archive has a duplicate member")
            normalized_names.add(normalized)
            kind = "dir" if member.isdir() else "file" if member.isfile() else "link" if member.issym() else "special"
            require(kind != "special", "WSL archive contains a special member")
            require(not member.mode & 0o7000, "WSL archive contains a special mode")
            total += member.size
            require(total <= BYTE_LIMIT, "WSL archive byte limit")
            entries[name] = (kind, member.linkname if kind == "link" else "")
            members.append((name, member))
        resolved = _validate(entries)
        require(output.parent.is_dir() and not output.parent.is_symlink(),
                "WSL extraction parent is unavailable")
        temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.extract-", dir=output.parent))
        try:
            for name, member in members:
                if entries[name][0] == "dir":
                    (temporary / Path(name)).mkdir(parents=True, exist_ok=True)
            for name, member in members:
                if entries[name][0] != "file":
                    continue
                target = temporary / Path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                require(stream is not None, "WSL archive file has no content")
                data = stream.read()
                require(len(data) == member.size, "WSL archive file is truncated")
                target.write_bytes(data)
                target.chmod(member.mode & 0o777)
            for name, member in members:
                if entries[name][0] != "link":
                    continue
                target = temporary / Path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(member.linkname, target_is_directory=resolved[name][1] == "dir")
            temporary.replace(output)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


def tree(root):
    """Measure a validated Unix tree, including exact link identities."""
    require(root.is_absolute() and root.is_dir() and root.resolve() == root,
            "WSL tree must be an absolute unlinked directory")
    entries = {}
    paths = {}
    normalized_names = set()

    def visit(directory, prefix=""):
        for entry in os.scandir(directory):
            name = f"{prefix}/{entry.name}" if prefix else entry.name
            relative_path(name)
            normalized = unicodedata.normalize("NFC", name)
            require(name not in entries and normalized not in normalized_names,
                    "WSL tree has a duplicate member")
            normalized_names.add(normalized)
            path = Path(entry.path)
            if entry.is_symlink():
                entries[name] = ("link", os.readlink(path))
            elif entry.is_dir(follow_symlinks=False):
                entries[name] = ("dir", "")
                visit(path, name)
            elif entry.is_file(follow_symlinks=False):
                entries[name] = ("file", "")
            else:
                require(False, "WSL tree contains a special member")
            paths[name] = path

    visit(root)
    require(len(entries) <= MEMBER_LIMIT, "WSL tree member limit")
    resolved = _validate(entries)
    result = {}
    total = 0
    for name, (kind, link) in entries.items():
        if kind == "dir":
            continue
        if kind == "link":
            final, target_kind = resolved[name]
            if target_kind == "dir":
                row = {**_identity(link.encode("utf-8")), "directory_link": link}
            else:
                data = paths[final].read_bytes()
                row = _identity(data)
        else:
            data = paths[name].read_bytes()
            row = _identity(data)
        total += len(link.encode("utf-8")) if kind == "link" else row["size"]
        require(total <= BYTE_LIMIT, "WSL tree byte limit")
        result[name] = row
    return result
