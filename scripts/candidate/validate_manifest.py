"""Check held manifest bytes before keyless attestation; never execute a payload.

This trusted default-branch tool follows read_held.py and precedes fresh native
signature verification. It cannot by itself prove a vendor signature or grant
permission to publish. Its input is only the protected signing job's exact
artifact ID and digest, never a caller-supplied release manifest.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

if __package__:
    from scripts.candidate_policy import REPOSITORY, SHA, SHA256, Refused, require, trusted_approval
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from candidate_policy import REPOSITORY, SHA, SHA256, Refused, require, trusted_approval


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def read(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 4 * 1024 * 1024,
            "held record missing, linked or oversized")
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def files(root, prefix):
    directory = root / prefix
    require(directory.is_dir() and not directory.is_symlink(), "compliance directory missing")
    result = {}
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "compliance link refused")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path)
    require(bool(result), "empty compliance directory")
    return result


def validate(root, architecture):
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_REF") == "refs/heads/master"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "untrusted attestation workflow")
    approval = trusted_approval(architecture)
    authorization = read(root / "authorization.json")
    require(authorization.get("repository") == REPOSITORY
            and authorization.get("architecture") == architecture
            and authorization.get("version") == "0.5.0"
            and authorization.get("trusted_sha") == os.environ.get("GITHUB_SHA")
            and SHA.fullmatch(authorization.get("trusted_sha", "")) is not None
            and str(authorization.get("run_id")) == os.environ.get("GITHUB_RUN_ID")
            and type(authorization.get("run_attempt")) is int
            and authorization["run_attempt"] == 1, "held authorization producer mismatch")
    require(SHA.fullmatch(authorization.get("source_sha", "")) is not None
            and SHA.fullmatch(authorization.get("source_tree", "")) is not None
            and SHA256.fullmatch(authorization.get("input_digest", "")) is not None,
            "held source identity malformed")
    require(authorization.get("legal_approval_sha256") == hashlib.sha256(
        json.dumps(approval, sort_keys=True).encode()).hexdigest(), "trusted legal approval changed")
    legal = files(root, "legal")
    approved_legal = {name.removeprefix("payload/"): value
                      for name, value in approval["legal_hashes"].items()
                      if name.startswith("payload/legal/")}
    require(legal == approved_legal and "legal/TERMS.txt" in legal,
            "held legal bytes do not match reviewed approval")
    sbom = files(root, "sbom")
    require(len(sbom) == 1 and next(iter(sbom.values())) == approval["sbom_sha256"],
            "held SBOM bytes do not match reviewed approval")
    setup = root / f"Vadgr-0.5.0-windows-{architecture}-setup.exe"
    require(setup.is_file() and not setup.is_symlink() and setup.stat().st_size > 0,
            "held setup missing or invalid")
    expected = {"schema": 1, "product": "vadgr", "version": "0.5.0", "release_sequence": 500,
                "tag": "v0.5.0", "source_commit": authorization["source_sha"],
                "terms_version": "1.0", "terms_sha256": legal["legal/TERMS.txt"],
                "legal_hashes": legal, "sbom_hashes": sbom,
                "cua_version": authorization["cua_version"], "python_version": authorization["python_version"],
                "artifacts": [{"name": setup.name,
                    "target": "windows-" + {"x64": "x86_64", "arm64": "aarch64"}[architecture],
                    "kind": "burn", "size": setup.stat().st_size, "sha256": digest(setup),
                    "native_signature": "authenticode"}]}
    manifest = read(root / "release-manifest.json")
    # Comparing canonical JSON, not Python equality, rejects true as integer 1.
    require(json.dumps(manifest, sort_keys=True) == json.dumps(expected, sort_keys=True),
            "held release manifest differs from approved signed candidate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--architecture", choices=("x64", "arm64"), required=True)
    args = parser.parse_args()
    try:
        validate(args.directory, args.architecture)
    except (Refused, KeyError, TypeError, ValueError, OSError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    print("Held manifest and reviewed compliance bytes verified; native verification must follow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
