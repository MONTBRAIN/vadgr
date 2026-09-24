"""CI preparation must not downgrade incomplete reviewed inputs to development."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import prepare_cua_build as prepare
from scripts.validate_package_inputs import PackageInputError


TARGET = "x86_64-pc-windows-msvc"


def test_development_requires_explicit_permission_and_no_reviewed_inputs(tmp_path):
    with pytest.raises(PackageInputError):
        prepare.prepare(tmp_path, tmp_path, TARGET, tmp_path / "wheels", False)
    assert prepare.prepare(tmp_path, tmp_path, TARGET, tmp_path / "wheels", True) == {}


@pytest.mark.parametrize("name", ["packaging/cua/native-wheel-manifest.json",
                                 "packaging/cua/native-wheel-manifest.json.bundle.jsonl",
                                 "packaging/cua/locks/other-target.lock"])
def test_partial_inputs_never_select_development(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fixture")
    with patch.object(prepare.wheels, "materialize", side_effect=PackageInputError("missing reviewed input")) as call:
        with pytest.raises(PackageInputError):
            prepare.prepare(tmp_path, tmp_path, TARGET, tmp_path / "wheels", True)
        call.assert_called_once()


def test_reviewed_mode_materializes_before_emitting_release_environment(tmp_path):
    with patch.object(prepare.wheels, "materialize") as call:
        result = prepare.prepare(tmp_path, tmp_path, TARGET, tmp_path / "wheels", False)
        call.assert_called_once_with(tmp_path, tmp_path, TARGET, tmp_path / "wheels")
    assert result["VADGR_RELEASE_PAYLOAD_BUILD"] == "1"
    assert result["VADGR_BUILD_WHEELHOUSE"] == str(tmp_path / "wheels")


def test_clean_install_prepares_before_compile_and_passes_wheelhouse():
    root = Path(__file__).resolve().parents[2]
    text = (root / ".github/workflows/ci.yml").read_text().split("\n  clean-install:", 1)[1]
    assert text.index("prepare_cua_build.py") < text.index("cargo build")
    assert "--allow-development" in text
    assert "--trusted .trusted-cua" in text
    assert "VADGR_BUILD_WHEELHOUSE" in text and text.count("--wheelhouse") >= 3
    macos = (root / ".github/workflows/signed-candidate-macos.yml").read_text()
    assert macos.index("prepare_cua_build.py") < macos.index("cargo build")
    assert "--allow-development" not in macos
