"""Candidate approval generation binds exact reviewed bytes."""

import hashlib
import json

import pytest

from scripts import finalize_candidate_approval as finalize
from scripts.validate_package_inputs import PackageInputError


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_target_binds_all_legal_files_and_signing_sources(tmp_path):
    package = tmp_path / "packaging/inputs/windows-x86_64"
    files = {
        "README-OFFLINE.txt": write(package / "README-OFFLINE.txt", b"offline"),
        "legal/TERMS.rtf": write(package / "legal/TERMS.rtf", b"terms"),
        "legal/LICENSE.txt": write(package / "legal/LICENSE.txt", b"license"),
        "sbom/vadgr-0.5.0.spdx.json": write(package / "sbom/vadgr-0.5.0.spdx.json", b"sbom"),
    }
    inventory_hash = write(package / "package-input-inventory.json", b"inventory")
    review = {"status": "approved", "version": "0.5.0", "terms_version": "1.0",
              "target": "x86_64-pc-windows-msvc", "files": files,
              "inventory_sha256": inventory_hash}
    write(package / "package-input-review.json", json.dumps(review).encode())
    helper = tmp_path / "packaging/cua/helper-signing"
    for suffix in (".json", "-outer.json", "-outer-review.json", "-predecessors.json"):
        write(helper / ("x86_64" + suffix), suffix.encode())
    write(tmp_path / "scripts/generate_legal_bundle.py", b"generator")
    result = finalize.target(tmp_path, "x86_64")
    assert result["legal_hashes"]["TERMS.rtf"] == files["legal/TERMS.rtf"]
    assert result["legal_hashes"]["payload/legal/LICENSE.txt"] == files["legal/LICENSE.txt"]
    assert "payload/sbom/vadgr-0.5.0.spdx.json" not in result["legal_hashes"]
    (package / "legal/LICENSE.txt").write_bytes(b"changed")
    with pytest.raises(PackageInputError):
        finalize.target(tmp_path, "x86_64")
