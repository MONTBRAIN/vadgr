#!/usr/bin/env python3
"""Generate deterministic WiX authoring for the private Windows payload."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import uuid
from xml.sax.saxutils import quoteattr

if __package__:
    from .candidate_artifacts import safe_name
else:
    from candidate_artifacts import safe_name


NAMESPACE = uuid.UUID("75ee9d4e-9488-43c2-8171-da5956dba58a")


def wix_id(kind: str, relative: str) -> str:
    digest = hashlib.sha256(relative.casefold().encode("utf-8")).hexdigest()[:24]
    return f"{kind}.{digest}"


def guid(kind: str, relative: str) -> str:
    return "{" + str(uuid.uuid5(NAMESPACE, f"{kind}:{relative.casefold()}")).upper() + "}"


def scan(root: Path) -> tuple[list[str], list[str]]:
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise SystemExit("payload lib must be an absolute real directory")
    directories: list[str] = []
    files: list[str] = []
    folded: set[str] = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise SystemExit(f"payload contains a link: {path.name}")
        relative = path.relative_to(root).as_posix()
        if not safe_name(relative):
            raise SystemExit("payload contains an unsafe relative path")
        key = relative.casefold()
        if key in folded:
            raise SystemExit("payload contains a Windows case-folding collision")
        folded.add(key)
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            files.append(relative)
        else:
            raise SystemExit(f"payload contains a special file: {path.name}")
    if not files:
        raise SystemExit("payload lib is empty")
    return directories, files


def render(root: Path, directories: list[str], files: list[str], *, directory_id: str = "PrivateLibFolder", group_id: str = "PrivatePayload") -> str:
    def identifier(kind: str, relative: str) -> str:
        return wix_id(kind, group_id + "/" + relative)

    def component_guid(kind: str, relative: str) -> str:
        return guid(kind, group_id + "/" + relative)

    children: dict[str, list[str]] = {"": []}
    by_directory: dict[str, list[str]] = {"": []}
    for directory in directories:
        parent = Path(directory).parent.as_posix()
        if parent == ".":
            parent = ""
        children.setdefault(parent, []).append(directory)
        children.setdefault(directory, [])
        by_directory.setdefault(directory, [])
    for file in files:
        parent = Path(file).parent.as_posix()
        if parent == ".":
            parent = ""
        by_directory.setdefault(parent, []).append(file)

    component_ids: list[str] = []
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">',
        "  <Fragment>",
        f"    <DirectoryRef Id={quoteattr(directory_id)}>",
    ]

    def emit(directory: str, indent: str) -> None:
        if directory:
            nested_id = identifier("dir", directory)
            lines.append(f"{indent}<Directory Id={quoteattr(nested_id)} Name={quoteattr(Path(directory).name)}>")
            indent += "  "
        for relative in sorted(by_directory.get(directory, []), key=str.casefold):
            component_id = identifier("file", relative)
            component_ids.append(component_id)
            source = str(root.joinpath(*Path(relative).parts))
            lines.extend(
                [
                    f"{indent}<Component Id={quoteattr(component_id)} Guid={quoteattr(component_guid('file', relative))}>",
                    f"{indent}  <File Id={quoteattr(identifier('payload', relative))} Source={quoteattr(source)} />",
                    f"{indent}  <RegistryValue Root=\"HKCU\" Key=\"Software\\MONTBRAIN\\Vadgr\\Payload\" Name={quoteattr(component_id)} Type=\"integer\" Value=\"1\" KeyPath=\"yes\" />",
                    f"{indent}</Component>",
                ]
            )
        for child in sorted(children.get(directory, []), key=str.casefold):
            emit(child, indent)
        if directory:
            cleanup_id = identifier("cleanup", directory)
            component_ids.append(cleanup_id)
            lines.extend(
                [
                    f"{indent}<Component Id={quoteattr(cleanup_id)} Guid={quoteattr(component_guid('directory', directory))}>",
                    f"{indent}  <RegistryValue Root=\"HKCU\" Key=\"Software\\MONTBRAIN\\Vadgr\\PayloadFolders\" Name={quoteattr(cleanup_id)} Type=\"integer\" Value=\"1\" KeyPath=\"yes\" />",
                    f"{indent}  <RemoveFolder Id={quoteattr(identifier('remove', directory))} On=\"uninstall\" />",
                    f"{indent}</Component>",
                ]
            )
            indent = indent[:-2]
            lines.append(f"{indent}</Directory>")

    emit("", "      ")
    lines.extend(["    </DirectoryRef>", "  </Fragment>", "  <Fragment>", f"    <ComponentGroup Id={quoteattr(group_id)}>"])
    for component_id in component_ids:
        lines.append(f"      <ComponentRef Id={quoteattr(component_id)} />")
    lines.extend(["    </ComponentGroup>", "  </Fragment>", "</Wix>", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-lib", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--directory-id", choices=("PrivateLibFolder", "LegalFolder", "SbomFolder"), default="PrivateLibFolder")
    parser.add_argument("--group-id", choices=("PrivatePayload", "LegalPayload", "SbomPayload"), default="PrivatePayload")
    args = parser.parse_args()
    root = args.payload_lib.resolve(strict=True)
    directories, files = scan(root)
    contents = render(root, directories, files, directory_id=args.directory_id, group_id=args.group_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
