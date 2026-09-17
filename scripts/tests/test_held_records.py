"""Held archive fixtures are synthetic records with no signed executables."""
import hashlib
import json
import zipfile

import pytest

from scripts.candidate.read_held import extract
from scripts.candidate.record import extract as extract_record


def test_single_record_extracts_exact_bytes_and_refuses_extra_member(tmp_path):
    archive = tmp_path / "record.zip"
    data = b'{"fixture":true}\n'
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("authorization.json", data)
    output = tmp_path / "authorization.json"
    extract_record(archive, "authorization.json", output)
    assert output.read_bytes() == data
    with zipfile.ZipFile(archive, "a") as stream:
        stream.writestr("extra.json", b"{}")
    with pytest.raises(ValueError, match="exactly"):
        extract_record(archive, "authorization.json", tmp_path / "extra")
    assert not (tmp_path / "extra").exists()


def test_held_records_bind_source_run_and_every_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ID", "12")
    authorization = {"run_id": 12, "run_attempt": 1, "candidate_id": "v0.5.0-rc-1",
                     "input_digest": "b" * 64, "source_sha": "c" * 40, "source_tree": "d" * 40}
    files = {"authorization.json": json.dumps(authorization).encode(), "release-manifest.json": b"{}"}
    candidate = {**authorization, "status": "held-unpublished", "trusted_tooling_commit": "a" * 40,
                 "source_commit": authorization["source_sha"],
                 "artifacts": [{"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                               for name, data in files.items()]}
    files["candidate-manifest.json"] = json.dumps(candidate).encode()
    archive = tmp_path / "held.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        for name, data in files.items():
            stream.writestr(name, data)
    extract(archive, tmp_path / "accepted")
    assert (tmp_path / "accepted/authorization.json").read_bytes() == files["authorization.json"]
    monkeypatch.setenv("GITHUB_RUN_ID", "13")
    with pytest.raises(ValueError, match="run mismatch"):
        extract(archive, tmp_path / "refused")
    assert not (tmp_path / "refused").exists()
