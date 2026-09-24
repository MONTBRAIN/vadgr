"""A missing target closure is a refusal check, never a clean-install pass."""

from unittest.mock import patch

import pytest

from scripts import check_cua_ci_boundary as boundary
from scripts.validate_package_inputs import PackageInputError


TARGET = "aarch64-apple-darwin"


def inputs(tmp_path):
    source = tmp_path / "source"
    trusted = tmp_path / "trusted"
    for root in (source, trusted):
        path = root / "packaging/cua"
        path.mkdir(parents=True)
        (path / "native-wheel-manifest.json").write_bytes(b"exact manifest")
        (path / "native-wheel-manifest.json.bundle.jsonl").write_bytes(b"exact bundle")
    return source, trusted


def test_missing_target_verifies_refusal_without_marking_install_passed(tmp_path):
    source, trusted = inputs(tmp_path)
    with patch.object(boundary.release, "manifest"), patch.object(
            boundary.prepare, "prepare", side_effect=PackageInputError("missing input")) as call:
        mode, values = boundary.check(source, trusted, TARGET, tmp_path / "wheels")
    assert mode == "unpromoted" and values == {}
    call.assert_called_once_with(source, trusted, TARGET, tmp_path / "wheels", True)


def test_missing_target_cannot_accept_a_development_fallback(tmp_path):
    source, trusted = inputs(tmp_path)
    with patch.object(boundary.release, "manifest"), patch.object(boundary.prepare, "prepare", return_value={}):
        with pytest.raises(PackageInputError, match="did not refuse"):
            boundary.check(source, trusted, TARGET, tmp_path / "wheels")


def test_missing_target_cannot_hide_mismatched_reviewed_metadata(tmp_path):
    source, trusted = inputs(tmp_path)
    (source / boundary.release.MANIFEST).write_bytes(b"different")
    with pytest.raises(PackageInputError, match="differs"):
        boundary.check(source, trusted, TARGET, tmp_path / "wheels")


@pytest.mark.parametrize("which", ["source", "trusted"])
def test_present_target_lock_errors_remain_fatal(tmp_path, which):
    source, trusted = inputs(tmp_path)
    root = source if which == "source" else trusted
    lock = root / boundary.release.lock_path(TARGET)
    lock.parent.mkdir()
    lock.write_bytes(b"broken lock")
    with patch.object(boundary.prepare, "prepare", side_effect=PackageInputError("invalid closure")):
        with pytest.raises(PackageInputError, match="invalid closure"):
            boundary.check(source, trusted, TARGET, tmp_path / "wheels")


def test_verified_preparation_preserves_release_environment(tmp_path):
    values = {"VADGR_RELEASE_PAYLOAD_BUILD": "1", "VADGR_BUILD_WHEELHOUSE": "exact"}
    with patch.object(boundary.prepare, "prepare", return_value=values):
        assert boundary.check(tmp_path, tmp_path, TARGET, tmp_path / "wheels") == ("reviewed", values)


def test_refusal_cannot_leave_a_partial_wheelhouse(tmp_path):
    source, trusted = inputs(tmp_path)
    output = tmp_path / "wheels"

    def mutated(*args):
        output.mkdir()
        raise PackageInputError("missing input")

    with patch.object(boundary.release, "manifest"), patch.object(boundary.prepare, "prepare", side_effect=mutated):
        with pytest.raises(PackageInputError, match="mutated"):
            boundary.check(source, trusted, TARGET, output)


def test_actual_unpromoted_checkout_refuses_before_materialization(tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    if (root / boundary.release.lock_path(TARGET)).exists():
        pytest.skip("This target now has reviewed inputs")
    assert boundary.check(root, root, TARGET, tmp_path / "wheels") == ("unpromoted", {})
    assert not (tmp_path / "wheels").exists()
