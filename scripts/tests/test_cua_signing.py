"""Synthetic signer transitions, never real signatures or signing approval."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.candidate import cua_signing as signing
from scripts.validate_package_inputs import PackageInputError


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def transition(tmp_path):
    root = tmp_path.resolve() / "verified"
    records = tmp_path.resolve() / "records"
    binding = {"target": "x86_64-pc-windows-msvc", "requirements_sha256": "1" * 64,
               "wheel_manifest_sha256": "2" * 64}
    files = {"python/python.exe": b"synthetic unsigned PE", "data.txt": b"unchanged"}
    identity = lambda data: {"size": len(data), "sha256": sha(data)}
    inventory = signing.canonical_json({"schema": 1, "target": binding["target"],
                                       "files": {name: identity(data) for name, data in files.items()}})
    payload = signing.canonical_json({"schema": 2, **binding, "installed_inventory_sha256": sha(inventory)})
    for name, data in {**files, "installed-inventory.json": inventory, "payload.json": payload}.items():
        write(root, "payload/lib/cua/" + name, data)
    write(root, "payload/bin/vadgr.exe", b"synthetic product")
    write(root, "ba-functions.dll", b"synthetic BA")
    auth = {"cua_inputs": binding, "cua_payload": {**binding, "installed_inventory_sha256": sha(inventory)},
            "files": {path.relative_to(root).as_posix(): identity(path.read_bytes())
                      for path in root.rglob("*") if path.is_file()}}
    return root, records, auth


def sign_fixture(root, auth):
    receipt = {}
    for name, before in auth["files"].items():
        if Path(name).suffix.lower() in (".exe", ".dll", ".pyd"):
            path = root / name
            path.write_bytes(path.read_bytes() + b" synthetic signature")
            receipt[name] = {"input": copy.deepcopy(before), "output": {"size": path.stat().st_size,
                                                        "sha256": sha(path.read_bytes())}}
    return receipt


def test_reseal_preserves_inputs_and_binds_every_output(transition):
    root, records, auth = transition
    signing.snapshot(root, auth, records)
    receipt = sign_fixture(root, auth)
    result = signing.reseal(root, auth, records, receipt)
    assert result["pre_signing"] == auth["cua_payload"]
    assert result["final"]["installed_inventory_sha256"] != auth["cua_payload"]["installed_inventory_sha256"]
    assert result["final"]["wheel_manifest_sha256"] == auth["cua_inputs"]["wheel_manifest_sha256"]
    assert signing.validate_records(records, auth) == result
    signing.release.validate_payload(root / "payload/lib/cua", auth["cua_inputs"])


@pytest.mark.parametrize("mutation", ["extra", "data", "missing", "receipt", "unsigned", "input", "pins"])
def test_reseal_refuses_any_unapproved_transition_without_rewriting_metadata(transition, mutation):
    root, records, auth = transition
    signing.snapshot(root, auth, records)
    receipt = sign_fixture(root, auth)
    if mutation == "extra":
        write(root, "payload/extra.txt", b"extra")
    elif mutation == "data":
        write(root, "payload/lib/cua/data.txt", b"tampered")
    elif mutation == "missing":
        (root / "payload/lib/cua/data.txt").unlink()
    elif mutation == "receipt":
        next(iter(receipt.values()))["output"]["sha256"] = "f" * 64
    elif mutation == "unsigned":
        receipt.pop(next(iter(receipt)))
    elif mutation == "input":
        next(iter(receipt.values()))["input"]["sha256"] = "f" * 64
    else:
        auth["cua_inputs"]["requirements_sha256"] = "f" * 64
    original = (root / "payload/lib/cua/payload.json").read_bytes()
    with pytest.raises(PackageInputError):
        signing.reseal(root, auth, records, receipt)
    assert (root / "payload/lib/cua/payload.json").read_bytes() == original


def test_snapshot_requires_exact_authorized_inventory(transition):
    root, records, auth = transition
    auth["files"]["payload/bin/vadgr.exe"]["sha256"] = "f" * 64
    with pytest.raises(PackageInputError):
        signing.snapshot(root, auth, records)
    assert not records.exists()


@pytest.mark.parametrize("filename", ["pre-payload.json", "pre-inventory.json", "payload.json",
                                    "installed-inventory.json", "input-output.json"])
def test_held_records_refuse_substitution(transition, filename):
    root, records, auth = transition
    signing.snapshot(root, auth, records)
    signing.reseal(root, auth, records, sign_fixture(root, auth))
    (records / filename).write_bytes(b"{}")
    with pytest.raises(PackageInputError):
        signing.validate_records(records, auth)


def test_workflow_reseals_after_signing_before_packaging():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/candidate.yml").read_text()
    snapshot = workflow.index("cua_signing.py snapshot")
    sign = workflow.index("-PayloadRoot verified")
    reseal = workflow.index("reseal-cua.ps1")
    package = workflow.index("package-windows.ps1 -Mode msi")
    assert snapshot < sign < reseal < package
