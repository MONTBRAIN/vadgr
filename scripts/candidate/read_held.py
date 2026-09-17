"""Read a held file set without trusting ZIP paths or a build-produced manifest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from candidate_artifacts import MAX_COMPRESSED, MAX_EXPANDED, MAX_FILES, safe_name


def extract(archive: Path, output: Path) -> None:
    if output.exists() or archive.stat().st_size > MAX_COMPRESSED:
        raise ValueError("held extraction boundary refused")
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > MAX_FILES or sum(entry.file_size for entry in entries) > MAX_EXPANDED:
            raise ValueError("held artifact exceeds limits")
        names = set()
        folded = set()
        for entry in entries:
            kind = (entry.external_attr >> 16) & 0o170000
            if not safe_name(entry.filename) or kind not in (0, 0o100000, 0o040000) or entry.flag_bits & 1:
                raise ValueError("held artifact contains unsafe member")
            normalized = entry.filename.rstrip("/").casefold()
            if normalized in folded:
                raise ValueError("held artifact contains duplicate member")
            folded.add(normalized)
            if not entry.is_dir():
                names.add(entry.filename)
        for required in ("candidate-manifest.json", "authorization.json", "release-manifest.json"):
            if required not in names or bundle.getinfo(required).file_size > 16 * 1024 * 1024:
                raise ValueError("held record missing or too large")
        candidate = json.loads(bundle.read("candidate-manifest.json"))
        authorization = json.loads(bundle.read("authorization.json"))
        if candidate["status"] != "held-unpublished" or candidate["trusted_tooling_commit"] != os.environ.get("GITHUB_SHA"):
            raise ValueError("held tooling identity mismatch")
        for field in ("run_id", "run_attempt", "candidate_id", "input_digest"):
            if candidate[field] != authorization[field]:
                raise ValueError("held authorization mismatch")
        if str(candidate["run_id"]) != os.environ.get("GITHUB_RUN_ID") or candidate["run_attempt"] != 1:
            raise ValueError("held run mismatch")
        if candidate["source_commit"] != authorization["source_sha"] or candidate["source_tree"] != authorization["source_tree"]:
            raise ValueError("held source mismatch")
        expected = {row["name"]: row for row in candidate["artifacts"]}
        if len(expected) != len(candidate["artifacts"]) or names != set(expected) | {"candidate-manifest.json"}:
            raise ValueError("held file set mismatch")
        for name, row in expected.items():
            data = bundle.read(name)
            if len(data) != row["size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError("held file identity mismatch")
        output.mkdir()
        for name in sorted(names):
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(bundle.read(name))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    extract(args.archive, args.out)
    print("Held archive identities verified. No artifact executed.")
