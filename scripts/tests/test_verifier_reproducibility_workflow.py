"""The verifier hash pin comes from two byte-identical secret-free builds."""

from pathlib import Path


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
