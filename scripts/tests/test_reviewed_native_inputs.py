"""Committed input bytes must match the reviewed, attested native outputs."""

import base64
import json
from pathlib import Path

import pytest

from scripts import cua_release_inputs as release
from scripts import validate_native_wheels as producer
from scripts.validate_package_inputs import PackageInputError, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
SHA = "4624073d81f44bf8ae88ca4fbe482d7f138095f1"
MANIFEST_SHA = "2f86c4d2c6493d32019a617c669e3c0babefc565f9da73c6182475286ad499b8"
BUNDLE_SHA = "8e8f9ec6f85662872c06b15b0e9d205fbff6a62d02fad1121b0ee00fe71f3708"
OUTPUTS = {
    "windows-aarch64": (10790957494, 107498542111,
        "907307e09afbe384e5d8c16239d111ee7070d7527797db647f891568ff35fa65",
        "900c3a689b80ca7c3f0c0846af6c1023f8c02cc4b1555f0126adb4e9789fce70", 3331485, 4651, 30),
    "macos-x86_64": (10791711091, 107498542241,
        "35773788c020b1362c1bc1a46d7d2ea7dc70862dab60fdf6459b2a09f19bde37",
        "e414d09a63dca5056ed46bcb915ecd5a27c3c08a23a540337d5f061b09c8c665", 3610568, 4654, 27),
}


def test_reviewed_json_and_locks_retain_exact_bytes_on_native_checkout():
    assert sha256_bytes((ROOT / release.TRUSTED_ROOT).read_bytes()) == release.TRUSTED_ROOT_SHA256
    attributes = (ROOT / ".gitattributes").read_text().splitlines()
    for name in (release.TRUSTED_ROOT, release.MANIFEST, release.BUNDLE):
        assert f"{name} text eol=lf" in attributes
    assert "packaging/cua/locks/*.lock text eol=lf" in attributes


def test_reviewed_manifest_retains_exact_successful_producer_identity():
    raw, manifest = release.manifest(ROOT)
    assert sha256_bytes(raw) == MANIFEST_SHA
    assert raw == producer.canonical(manifest)
    assert manifest["repository_id"] == 1158230114
    assert manifest["workflow_id"] == 365688750
    assert manifest["run_id"] == 35957405519
    assert manifest["run_attempt"] == 1
    assert manifest["producer_sha"] == manifest["input_commit"] == SHA
    assert manifest["input_sha256"] == "cf877317aa2ff7624f02c5403ef5872d6aac2eb981bb3450c61dbbf536b3bbbc"
    producer.validate_descriptor(manifest["inputs"])
    assert manifest["inputs"] == json.loads((ROOT / "packaging/cua/native-wheels-input.json").read_bytes())
    for row in manifest["wheels"]:
        artifact, job, artifact_sha, wheel_sha, size, passed, skipped = OUTPUTS[row["target"]]
        assert (row["artifact_id"], row["job_id"]) == (artifact, job)
        assert row["artifact_digest"] == "sha256:" + artifact_sha
        assert (row["sha256"], row["size"]) == (wheel_sha, size)
        assert (row["tests"]["total"], row["tests"]["passed"], row["tests"]["skipped"]) == (4681, passed, skipped)
        expected = manifest["inputs"]["targets"][row["target"]]["test_policy"]["skips"]
        assert row["tests"]["skip_cases"] == sorted(expected, key=lambda case: (case["classname"], case["name"]))


def test_reviewed_bundle_preserves_the_attested_manifest_subject():
    raw = (ROOT / release.BUNDLE).read_bytes()
    assert sha256_bytes(raw) == BUNDLE_SHA
    bundle = json.loads(raw)
    statement = json.loads(base64.b64decode(bundle["dsseEnvelope"]["payload"], validate=True))
    assert statement["subject"] == [{"name": "native-wheel-manifest.json", "digest": {"sha256": MANIFEST_SHA}}]
    assert statement["predicateType"] == "https://slsa.dev/provenance/v1"
    definition = statement["predicate"]["buildDefinition"]
    assert definition["externalParameters"]["workflow"] == {
        "ref": "refs/heads/master", "repository": "https://github.com/MONTBRAIN/vadgr",
        "path": ".github/workflows/native-wheels.yml"}
    assert definition["resolvedDependencies"][0]["digest"] == {"gitCommit": SHA}
    assert statement["predicate"]["runDetails"]["metadata"]["invocationId"] == (
        "https://github.com/MONTBRAIN/vadgr/actions/runs/35957405519/attempts/1")


def test_windows_x64_lock_selects_complete_released_runtime_without_custom_wheels():
    target = "x86_64-pc-windows-msvc"
    binding = release.reviewed_inputs(ROOT, ROOT, target)
    assert binding["requirements_sha256"] == "83bdf9d395ea701f032e30cba1537483ebfefe8cdac03f30b9eccdccb4e98292"
    selected = release.selected_lock((ROOT / release.lock_path(target)).read_bytes())
    assert len(selected) == 40
    assert selected["vadgr-computer-use"] == (
        "0.7.8", "1c905c200d0e2190bb3512ecf0c58f1b683900ad15288cef00c14a732fb10535")
    assert selected["uniseg"][0] == "0.10.1"
    assert {"pywin32", "pywinauto", "comtypes"} <= selected.keys()
    assert not {"dbus-fast", "jeepney", "python-xlib", "pyobjc-core", "bcrypt", "pytest"} & selected.keys()
    assert not {row[3] for row in OUTPUTS.values()} & {digest for _, digest in selected.values()}


@pytest.mark.parametrize("target", [*release.CUSTOM_TARGETS, "x86_64-pc-windows-msvc"])
@pytest.mark.parametrize("changed", [release.MANIFEST, release.BUNDLE, "lock"])
def test_feature_cannot_change_any_reviewed_input(tmp_path, target, changed):
    # This one-package fixture tests equality only; it is not a promoted runtime lock.
    source, trusted = tmp_path / "source", tmp_path / "trusted"
    lock = release.lock_path(target)
    digest = (OUTPUTS[release.CUSTOM_TARGETS[target]][3] if target in release.CUSTOM_TARGETS
              else release.selected_lock((ROOT / lock).read_bytes())["cryptography"][1])
    for root in (source, trusted):
        for name in (release.MANIFEST, release.BUNDLE, lock):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((f"cryptography==50.0.1 --hash=sha256:{digest}\n".encode()
                              if name == lock else (ROOT / name).read_bytes()))
    assert release.reviewed_inputs(source, trusted, target)["wheel_manifest_sha256"] == MANIFEST_SHA
    path = source / (lock if changed == "lock" else changed)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(PackageInputError, match="differs from reviewed"):
        release.reviewed_inputs(source, trusted, target)


@pytest.mark.parametrize("target", release.CUSTOM_TARGETS)
def test_unpromoted_targets_still_refuse_missing_selected_locks(target):
    assert not (ROOT / release.lock_path(target)).exists()
    with pytest.raises(PackageInputError, match="missing input"):
        release.reviewed_inputs(ROOT, ROOT, target)


@pytest.mark.parametrize("field,value", [
    ("run_attempt", 2), ("repository", "different/repository"),
    ("workflow", ".github/workflows/different.yml"), ("input_commit", "a" * 40),
    ("input_sha256", "b" * 64),
])
def test_real_manifest_rejects_changed_producer_binding(tmp_path, field, value):
    manifest = json.loads((ROOT / release.MANIFEST).read_bytes())
    manifest[field] = value
    path = tmp_path / release.MANIFEST
    path.parent.mkdir(parents=True)
    path.write_bytes(producer.canonical(manifest))
    with pytest.raises(PackageInputError):
        release.manifest(tmp_path)
