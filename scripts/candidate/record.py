"""Extract one bounded trusted JSON record without extracting archive paths."""
import argparse
import json
from pathlib import Path
import zipfile


def extract(archive: Path, name: str, output: Path) -> None:
    if name not in {"preflight.json", "authorization.json", "qualification.json", "claim.json"}:
        raise ValueError("unknown record")
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) != 1 or entries[0].filename != name:
            raise ValueError("record artifact must contain exactly its declared record")
        entry = entries[0]
        if entry.file_size > 16 * 1024 * 1024 or entry.flag_bits & 1:
            raise ValueError("record is oversized or encrypted")
        body = bundle.read(entry)
    if not isinstance(json.loads(body), dict):
        raise ValueError("record must be an object")
    with output.open("xb") as destination:
        destination.write(body)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    extract(arguments.archive, arguments.name, arguments.out)
    print("Trusted record extracted; no archive paths materialized.")
