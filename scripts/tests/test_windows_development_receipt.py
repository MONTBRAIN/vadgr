"""The producer's receipt must describe the payload exactly, or refuse.

Every case builds a complete payload and changes one thing, so a refusal names
the condition it came from. The receipt the daemon reads is the one these tests
build, so the shape they assert is the shape the Rust verifier parses.
"""

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts/windows_development_receipt.py"

PAYLOAD = {
    "vadgr.exe": b"the backend image",
    "vadgr-app.exe": b"the windowless launcher",
    "README-OFFLINE.txt": b"offline notes",
    "package-input-inventory.json": b"{}",
    "package-input-review.json": b"{}",
    "legal/TERMS.txt": b"the accepted terms",
    "sbom/vadgr.spdx.json": b"{}",
    "lib/cua/payload.json": b'{"cua_version":"0.0.0"}',
    "lib/cua/bootstrap.py": b"print()",
}


def write(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def source(tmp_path):
    """A clean Git source whose commit the receipt can name."""
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("fixture\n", encoding="utf-8")

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    git("init", "--initial-branch=master")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "fixture")
    git("add", "README.md")
    git("commit", "--no-gpg-sign", "-m", "fixture")
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    return root, commit


@pytest.fixture
def payload(tmp_path):
    root = tmp_path / "payload"
    root.mkdir()
    for relative, data in PAYLOAD.items():
        write(root, relative, data)
    write(root, "install-receipt.json", json.dumps(
        {"schema": 1, "version": "0.5.0", "package_kind": "msi"}
    ).encode())
    return root


def run(mode, payload, source=None, commit=None, extra=()):
    command = [sys.executable, "-I", str(TOOL), mode, "--payload", str(payload), *extra]
    if source is not None:
        command += ["--source-root", str(source), "--source-commit", commit,
                    "--architecture", "x86_64"]
    return subprocess.run(command, capture_output=True, text=True)


def test_a_complete_payload_produces_a_receipt(payload, source):
    root, commit = source
    result = run("write", payload, root, commit)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((payload / "development-receipt.json").read_bytes())
    assert receipt["development"] is True and receipt["publishable"] is False
    assert receipt["signing"] == "disabled" and receipt["attestation"] == "absent"
    assert receipt["platform"] == "windows" and receipt["architecture"] == "x86_64"
    assert receipt["source_commit"] == commit
    assert run("check", payload).returncode == 0


def test_the_inventory_excludes_the_records_that_authorize_it(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    receipt = json.loads((payload / "development-receipt.json").read_bytes())
    paths = [row["path"] for row in receipt["payload"]]
    assert "install-receipt.json" not in paths
    assert "development-receipt.json" not in paths
    assert sorted(paths) == paths, "the verifier requires one sorted inventory"
    assert set(paths) == set(PAYLOAD), "every other installed file is inventoried"


def test_the_install_receipt_records_the_bytes_that_were_written(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    written = (payload / "development-receipt.json").read_bytes()
    recorded = json.loads((payload / "install-receipt.json").read_bytes())
    assert recorded["development_receipt_sha256"] == hashlib.sha256(written).hexdigest()
    assert recorded["package_kind"] == "msi"


def test_every_inventoried_digest_is_the_file(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    receipt = json.loads((payload / "development-receipt.json").read_bytes())
    for row in receipt["payload"]:
        data = (payload / row["path"]).read_bytes()
        assert row["sha256"] == hashlib.sha256(data).hexdigest()
        assert row["size"] == len(data)


def test_a_changed_payload_fails_the_check(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    write(payload, "lib/cua/bootstrap.py", b"PRINT()")
    result = run("check", payload)
    assert result.returncode == 1
    assert "differs from its receipt" in result.stderr


def test_an_added_payload_file_fails_the_check(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    write(payload, "lib/cua/planted.dll", b"loaded beside it")
    result = run("check", payload)
    assert result.returncode == 1
    assert "differs from its receipt" in result.stderr


def test_a_replaced_receipt_fails_the_check(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    receipt = json.loads((payload / "development-receipt.json").read_bytes())
    receipt["publishable"] = True
    (payload / "development-receipt.json").write_bytes(json.dumps(receipt).encode())
    result = run("check", payload)
    assert result.returncode == 1
    assert "does not record this development receipt" in result.stderr


def test_a_dirty_source_is_refused(payload, source):
    root, commit = source
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    result = run("write", payload, root, commit)
    assert result.returncode == 1
    assert "must be clean" in result.stderr


def test_another_commit_is_refused(payload, source):
    root, _ = source
    result = run("write", payload, root, "0" * 40)
    assert result.returncode == 1
    assert "source commit differs" in result.stderr


def test_the_release_form_becomes_the_development_form(payload, source):
    root, commit = source
    # This is the shipped receipt's shape: a release sequence and an update
    # origin. A development installation carries neither release field, and the
    # daemon's own mode check reads exactly that, so the producer rewrites it.
    write(payload, "install-receipt.json", json.dumps({
        "schema": 1, "version": "0.5.0", "package_kind": "msi",
        "product_code": "{CEFD8482-734F-403D-B9BB-5ABD06A2A79E}",
        "release_sequence": 500, "manifest_sha256": None,
        "update_origin": "https://example.invalid/latest",
    }).encode())
    assert run("write", payload, root, commit).returncode == 0
    recorded = json.loads((payload / "install-receipt.json").read_bytes())
    assert "release_sequence" not in recorded and "manifest_sha256" not in recorded
    assert recorded["development_receipt_sha256"]
    # Everything that is not a release claim survives untouched.
    assert recorded["product_code"] == "{CEFD8482-734F-403D-B9BB-5ABD06A2A79E}"
    assert recorded["update_origin"] == "https://example.invalid/latest"
    assert run("check", payload).returncode == 0


def test_a_restored_release_claim_fails_the_check(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    recorded = json.loads((payload / "install-receipt.json").read_bytes())
    recorded["release_sequence"] = 500
    write(payload, "install-receipt.json", json.dumps(recorded).encode())
    result = run("check", payload)
    assert result.returncode == 1
    assert "no release manifest or sequence" in result.stderr


def test_a_payload_that_is_not_an_msi_installation_is_refused(payload, source):
    root, commit = source
    write(payload, "install-receipt.json", json.dumps(
        {"schema": 1, "version": "0.5.0", "package_kind": "appimage"}
    ).encode())
    result = run("write", payload, root, commit)
    assert result.returncode == 1
    assert "does not describe a Windows MSI installation" in result.stderr


def test_an_empty_payload_is_refused(tmp_path, source):
    root, commit = source
    empty = tmp_path / "empty"
    empty.mkdir()
    write(empty, "install-receipt.json", json.dumps(
        {"schema": 1, "version": "0.5.0", "package_kind": "msi"}
    ).encode())
    result = run("write", empty, root, commit)
    assert result.returncode == 1
    assert "inventories no file" in result.stderr


def test_the_receipt_is_canonical_and_rewriting_changes_nothing(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    first = (payload / "development-receipt.json").read_bytes()
    install = (payload / "install-receipt.json").read_bytes()
    assert run("write", payload, root, commit).returncode == 0
    assert (payload / "development-receipt.json").read_bytes() == first
    assert (payload / "install-receipt.json").read_bytes() == install


def rust_fields(name):
    """The field names of one struct in the verifier, in source order."""
    source = (ROOT / "src/install/development_windows.rs").read_text(encoding="utf-8")
    body = source.split(f"struct {name} {{", 1)[1].split("\n}", 1)[0]
    return [
        line.strip().rstrip(",").split(":", 1)[0].strip()
        for line in body.splitlines()
        if ":" in line and not line.strip().startswith("//")
    ]


def test_the_receipt_carries_exactly_the_fields_the_verifier_parses(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    receipt = json.loads((payload / "development-receipt.json").read_bytes())
    # The verifier refuses an unknown field, so a producer field it does not
    # parse is a refused install rather than an ignored extra.
    assert sorted(receipt) == sorted(rust_fields("Receipt"))
    assert sorted(receipt["payload"][0]) == sorted(rust_fields("Member"))


def test_the_verifier_names_no_installation_vehicle(payload, source):
    root, commit = source
    assert run("write", payload, root, commit).returncode == 0
    receipt = json.loads((payload / "development-receipt.json").read_bytes())
    # The MSI carries the receipt, so the receipt is sealed before the vehicle
    # exists, and a development install caches no vehicle to compare against.
    assert "artifact" not in receipt
    assert "artifact" not in rust_fields("Receipt")
