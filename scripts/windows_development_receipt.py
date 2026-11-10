#!/usr/bin/env python3
"""Write the development receipt for an unsigned Windows qualification package.

The receipt records what the producer built, over the exact payload the MSI is
about to install. The installed daemon reads it back and refuses to start its
bundled runtime unless every inventoried byte still matches. That is package
consistency. It is never publisher authenticity, and it grants no release trust.

The receipt names no installation vehicle. The MSI carries the receipt, so the
receipt is sealed before the vehicle that would contain it exists, and a
development install caches no vehicle to compare against. Every field here is
checkable against the installed tree.

Run it after the payload is complete and before the MSI is built:

    python scripts/windows_development_receipt.py write \\
        --payload <payload dir> --architecture x86_64 --source-commit <sha>

It writes `development-receipt.json` into the payload and then rewrites the
payload's `install-receipt.json` to record that receipt's digest, which is the
link the daemon follows.
"""

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

# These two authorize the inventory, so the inventory cannot cover them: the
# install receipt records the development receipt's digest, and a receipt that
# inventoried itself could never hash to the value it carries.
EXCLUDED = ("install-receipt.json", "development-receipt.json")

ARCHITECTURES = ("x86_64", "aarch64")
RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{digit}" for digit in range(1, 10)),
    *(f"lpt{digit}" for digit in range(1, 10)),
}


class ReceiptError(Exception):
    """A refusal the producer must act on, printed without a traceback."""


def require(condition, message):
    if not condition:
        raise ReceiptError(message)


def digest(path):
    hash = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hash.update(chunk)
    return hash.hexdigest()


def canonical_json(value):
    """One byte sequence per value, so a rewrite that changes nothing is a no-op."""
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n"


def safe_name(name):
    if not name or len(name) > 255 or name in (".", ".."):
        return False
    if name.endswith(" ") or name.endswith("."):
        return False
    if any(character in name for character in '\\/:*?"<>|') or any(
        ord(character) < 32 for character in name
    ):
        return False
    return name.split(".", 1)[0].lower() not in RESERVED


def safe_path(path):
    parts = path.split("/")
    return bool(path) and len(path) <= 4096 and len(parts) <= 64 and all(
        safe_name(part) for part in parts
    )


def source_identity(root, expected):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

    require(re.fullmatch(r"[0-9a-f]{40}", expected), "the source commit must be a full identity")
    require(git("rev-parse", "HEAD") == expected, "source commit differs")
    require(
        not git("status", "--porcelain", "--untracked-files=all"),
        "the source must be clean, because the receipt names a tree",
    )
    return {"source_commit": expected, "source_tree": git("rev-parse", "HEAD^{tree}")}


def inventory(payload):
    """Every installed file, by relative POSIX path, sorted as the verifier reads."""
    payload = payload.resolve(strict=True)
    rows = []
    for path in payload.rglob("*"):
        relative = path.relative_to(payload).as_posix()
        info = path.lstat()
        require(
            not path.is_symlink(),
            f"the payload carries a link at {relative}, and the verifier follows none",
        )
        if path.is_dir():
            continue
        require(path.is_file(), f"the payload carries a special file at {relative}")
        require(safe_path(relative), f"the payload carries an unsafe path at {relative}")
        if relative in EXCLUDED:
            continue
        require(info.st_nlink == 1, f"the payload file {relative} carries another name")
        rows.append({"path": relative, "size": info.st_size, "sha256": digest(path)})
    require(rows, "the payload inventories no file")
    rows.sort(key=lambda row: row["path"])
    return rows


def write(payload, architecture, source_commit, root):
    require(architecture in ARCHITECTURES, "unsupported Windows architecture")
    identity = source_identity(root, source_commit)
    for name in EXCLUDED:
        require(
            (payload / name).is_file() or name == "development-receipt.json",
            f"the payload carries no {name}",
        )
    receipt = {
        "schema": 1,
        "development": True,
        "publishable": False,
        "signing": "disabled",
        "attestation": "absent",
        **identity,
        "platform": "windows",
        "architecture": architecture,
        "payload": inventory(payload),
    }
    target = payload / "development-receipt.json"
    bytes_written = canonical_json(receipt)
    target.write_bytes(bytes_written)

    # The install receipt is the only link from the installation to this record,
    # so it is rewritten last and from the bytes that were actually written.
    install = payload / "install-receipt.json"
    recorded = json.loads(install.read_bytes())
    require(
        recorded.get("package_kind") == "msi",
        "the install receipt does not describe a Windows MSI installation",
    )
    # The shipped receipt is the release form. A development installation is
    # not a release with one extra field: it carries no release manifest and no
    # release sequence, and the daemon's own mode check reads exactly that. So
    # the development form is written here rather than refused.
    for field in ("manifest_sha256", "release_sequence"):
        recorded.pop(field, None)
    recorded["development_receipt_sha256"] = hashlib.sha256(bytes_written).hexdigest()
    install.write_bytes(canonical_json(recorded))
    require(
        source_identity(root, source_commit) == identity,
        "the source changed while the receipt was written",
    )
    print(f"development receipt written over {len(receipt['payload'])} payload files")
    print(f"development-receipt.json sha256 {recorded['development_receipt_sha256']}")


def check(payload):
    """Re-derive the receipt from the payload and refuse any difference."""
    receipt = json.loads((payload / "development-receipt.json").read_bytes())
    require(receipt["payload"] == inventory(payload), "the payload differs from its receipt")
    recorded = json.loads((payload / "install-receipt.json").read_bytes())
    require(
        recorded.get("development_receipt_sha256")
        == digest(payload / "development-receipt.json"),
        "the install receipt does not record this development receipt",
    )
    require(
        recorded.get("manifest_sha256") is None and recorded.get("release_sequence") is None,
        "a development installation carries no release manifest or sequence",
    )
    print("the payload matches its development receipt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("write", "check"))
    parser.add_argument("--payload", type=pathlib.Path, required=True)
    parser.add_argument("--architecture", choices=ARCHITECTURES)
    parser.add_argument("--source-commit")
    parser.add_argument("--source-root", type=pathlib.Path, default=pathlib.Path.cwd())
    args = parser.parse_args()
    try:
        if args.mode == "write":
            require(
                args.architecture and args.source_commit,
                "writing a receipt requires the architecture and the source commit",
            )
            write(args.payload, args.architecture, args.source_commit, args.source_root)
        else:
            check(args.payload)
    except (ReceiptError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"development receipt refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
