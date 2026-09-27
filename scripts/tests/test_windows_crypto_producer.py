"""Exact upstream artifact equality must not inherit approval or mutable metadata."""

import json
from pathlib import Path

import pytest

from scripts import windows_crypto_producer as producer
from scripts.validate_package_inputs import PackageInputError


@pytest.fixture
def retained():
    root = Path(__file__).resolve().parents[2] / "packaging/inputs/windows-x86_64/producer-evidence" / producer.FOLDER
    return {path.name: path.read_bytes() for path in root.iterdir()}


def test_exact_upstream_source_and_wheel_producer_remains_unapproved(retained):
    record = producer.validate_files(retained)
    assert record["run_id"] == 32890072935
    assert record["candidate_approval"] is False and record["publishable"] is False
    assert "not a new independently verified build attestation" in record["limitation"]


@pytest.mark.parametrize("defect", ["source.zip", "wheel.zip", "workflow.yml.txt", "windows-action.yml.txt",
                                    "run-source", "job-target", "artifact-run", "artifact-digest"])
def test_upstream_binding_rejects_changed_bytes_and_scope(retained, defect):
    if defect in retained:
        retained[defect] += b"uninspected change"
    else:
        name = {"run-source": "run.json", "job-target": "job.json",
                "artifact-run": "wheel-artifact.json", "artifact-digest": "source-artifact.json"}[defect]
        value = json.loads(retained[name])
        if defect == "run-source":
            value["head_sha"] = "0" * 40
        elif defect == "job-target":
            value["name"] = "3.14 arm64 py311"
        elif defect == "artifact-run":
            value["workflow_run"]["id"] += 1
        else:
            value["digest"] = "sha256:" + "0" * 64
        retained[name] = producer.canonical_json(value)
    with pytest.raises(PackageInputError):
        producer.validate_files(retained)
