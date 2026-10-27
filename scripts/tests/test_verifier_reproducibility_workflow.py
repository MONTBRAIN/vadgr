"""The verifier hash pin comes from two byte-identical secret-free builds."""

from pathlib import Path
import re


WORKFLOW = (Path(__file__).resolve().parents[2] / ".github/workflows/verifier-reproducibility.yml").read_text()


def test_compiled_payload_input_changes_trigger_new_verifier_builds():
    for path in ("build.rs", "packaging/cua/locks/**", "packaging/cua/native-wheel-manifest.json"):
        assert f"      - {path}" in WORKFLOW


def test_reproducible_verifier_matrix_is_secret_free_and_hosted():
    assert "runner: ubuntu-22.04-arm" in WORKFLOW
    assert "runner: ubuntu-22.04\n" in WORKFLOW
    assert "cmp --silent out/verifier-one out/verifier-two" in WORKFLOW
    assert "--locked --release --features release-verifier" in WORKFLOW
    assert "sha256sum \"out/vadgr-release-verify-$ARCHITECTURE\"" in WORKFLOW
    assert "id-token: write" not in WORKFLOW
    assert "secrets." not in WORKFLOW
    assert "contents: write" not in WORKFLOW
    assert "persist-credentials: false" in WORKFLOW


def test_installer_pins_match_reproduced_final_inventory_schema():
    # Run 35953535470 built source 8097fbff7d466e405c41ed4240725988832fc5c2
    # twice per native target. Artifact IDs: x64 10789851385, ARM64 10789722794.
    # These are hashes of the downloaded executable bytes, not their ZIP files.
    expected = {
        "X86_64": "80f437caf3c06b1ec1fdbf38cb6b7d1ee5b5ac61d8f298e384c0e6550519627e",
        "AARCH64": "70ea64be2134a617cef67a6f34df9c38e07630e3022fae6dc13bbffe4973ab3e",
    }
    installer = (Path(__file__).resolve().parents[2] / "install.sh").read_text()
    actual = dict(re.findall(r"^VERIFIER_SHA_(X86_64|AARCH64)=([0-9a-f]{64})$", installer, re.M))
    assert actual == expected
