"""Keep production credentials behind the protected macOS candidate job."""

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/signed-candidate-macos.yml"


def validate_workflow(text):
    assert "branches: [feature/0.5.0-distribution]" in text
    assert not re.search(r"^\s+(pull_request|pull_request_target|workflow_run|issue_comment):", text, re.M)
    assert "permissions:\n  contents: read\n" in text
    assert "cancel-in-progress: false" in text
    assert "startsWith(github.event.head_commit.message, 'candidate: macos ')" in text
    assert "if: >-\n      github.event_name ==" in text
    assert "persist-credentials: false" in text
    actions = re.findall(r"^\s+- (?:id: [^\n]+\n\s+)?uses: ([^\n #]+)", text, re.M)
    assert actions
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in actions)
    before, signer = text.split("\n  sign:\n", 1)
    assert "${{ secrets." not in before
    assert "environment: release-macos" in signer
    assert "needs: [validate, build]" in signer
    assert "--self-check validate-macos-candidate" in signer
    assert "Revalidate current source after environment approval" in signer
    assert signer.index("Revalidate current source after environment approval") < signer.index("Download exact same-run artifact")
    assert "--self-check validate-macos-candidate" in before
    assert "test -s packaging/release-trusted-root.jsonl" in before
    source_validation = before.split("\n  build:\n", 1)[0]
    for arch, target in (("arm64", "aarch64-apple-darwin"), ("x86_64", "x86_64-apple-darwin")):
        assert ("python3 scripts/validate_package_inputs.py --source-only --source-root . "
                f"--root packaging/inputs/macos-{arch} --version 0.5.0 --target {target}") in source_validation
    assert "--source-only" not in signer
    assert "assert state['head_sha'] == os.environ['GITHUB_SHA']" in signer
    assert "str(state['run_attempt']) == attempt" in signer
    assert "assert artifact['digest'].removeprefix('sha256:') == expected" in signer
    assert "assert hashlib.sha256(data).hexdigest() == expected" in signer
    assert "assert set(archive.namelist()) == allowed" in signer
    assert "python3 scripts/macos_signing_credentials.py --" in signer
    assert "--metadata unsigned/unsigned-provenance.json" in signer
    assert "held/provenance.json" in signer
    assert "retention-days: 90" in signer
    assert not re.search(r"contents: write|gh release|--overwrite|set -x|printenv|env dump", text)


def test_workflow_has_protected_source_digest_and_credential_boundaries():
    validate_workflow(WORKFLOW.read_text())


@pytest.mark.parametrize("old,new", [
    ("branches: [feature/0.5.0-distribution]", "branches: ['**']"),
    ("  workflow_dispatch:", "  pull_request_target:"),
    ("  contents: read", "  contents: write"),
    ("environment: release-macos", "environment: ordinary-ci"),
    ("needs: [validate, build]", "needs: build"),
    ("Revalidate current source after environment approval", "Skip current source validation"),
    ("startsWith(github.event.head_commit.message, 'candidate: macos ')", "true"),
    ("if: >-\n      github.event_name ==", "if: github.event_name =="),
    ("--self-check validate-macos-candidate", "--self-check unused"),
    ("--root packaging/inputs/macos-arm64", "--root packaging/inputs/macos-x86_64"),
    ("--target x86_64-apple-darwin", "--target aarch64-apple-darwin"),
    ("--source-only --source-root .", "--source-only --source-root other"),
    ("assert state['head_sha'] == os.environ['GITHUB_SHA']", "assert True"),
    ("str(state['run_attempt']) == attempt", "True"),
    ("assert hashlib.sha256(data).hexdigest() == expected", "assert True"),
    ("assert set(archive.namelist()) == allowed", "assert True"),
    ("python3 scripts/macos_signing_credentials.py --", "python3 direct_sign.py --"),
    ("retention-days: 90", "retention-days: 1"),
    ("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "actions/checkout@v4"),
])
def test_boundary_regressions_go_red_without_each_guard(old, new):
    text = WORKFLOW.read_text()
    assert old in text
    with pytest.raises(AssertionError):
        validate_workflow(text.replace(old, new))


def test_build_cannot_receive_signing_secrets():
    text = WORKFLOW.read_text()
    with pytest.raises(AssertionError):
        validate_workflow(text.replace("  build:\n", "  build:\n    secret: ${{ secrets.MACOS_APPLICATION_P12_PASSWORD }}\n"))


def test_legacy_tag_workflow_stops_before_checkout_or_signing():
    text = (ROOT / ".github/workflows/release.yml").read_text()
    first_job = text.split("  validate-tag:\n", 1)[1].split("\n  build:\n", 1)[0]
    assert first_job.index("exit 2") < first_job.index("uses: actions/checkout@")
    assert "legacy rebuild-and-sign path is disabled" in first_job


def validate_gate_matrix(text):
    assert "os: [ubuntu-latest, windows-latest, macos-15]" in text
    assert "environment: release-macos" not in text
    assert "${{ secrets.MACOS_" not in text


def test_native_macos_gate_runs_without_production_signing_secrets():
    validate_gate_matrix((ROOT / ".github/workflows/secret-scan.yml").read_text())


def test_missing_native_macos_gate_goes_red():
    text = (ROOT / ".github/workflows/secret-scan.yml").read_text()
    with pytest.raises(AssertionError):
        validate_gate_matrix(text.replace(", macos-15]", "]"))


def validate_package_builder(text):
    assert 'inputs="$repo/packaging/inputs/macos-$arch"' in text
    command = ('python3 "$repo/scripts/validate_package_inputs.py" --root "$inputs" '
               '--source-root "$repo" --version "$version" --target "$rust_target"')
    assert command in text
    assert '--payload-manifest "$repo/dist/payload/lib/cua/payload.json"' in text
    assert "--source-only" not in text
    assert text.index(command) < text.index("cargo build")
    for name in ("package-input-review.json", "package-input-inventory.json", "README-OFFLINE.txt"):
        assert f'cp -- "$inputs/{name}" "$app/Contents/Resources/{name}"' in text
    for directory in ("legal", "sbom"):
        assert f'cp -R -- "$inputs/{directory}/." "$app/Contents/Resources/{directory}/"' in text
    assert '"$repo/packaging/legal' not in text
    assert '"$repo/packaging/sbom' not in text


def test_builder_verifies_actual_target_payload_and_copies_review_metadata():
    validate_package_builder((ROOT / "packaging/macos/build.sh").read_text())


@pytest.mark.parametrize("old,new", [
    ('inputs="$repo/packaging/inputs/macos-$arch"', 'inputs="$repo/packaging"'),
    ('--payload-manifest "$repo/dist/payload/lib/cua/payload.json"', '--source-only'),
    ('--target "$rust_target"', '--target all'),
    ('cp -- "$inputs/package-input-review.json"', 'true #'),
    ('cp -- "$inputs/package-input-inventory.json"', 'true #'),
])
def test_builder_rejects_missing_target_review_boundary(old, new):
    text = (ROOT / "packaging/macos/build.sh").read_text()
    assert old in text
    with pytest.raises(AssertionError):
        validate_package_builder(text.replace(old, new))
