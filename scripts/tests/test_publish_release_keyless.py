"""The public release gate must reject a manifest before it trusts any fields."""

from pathlib import Path

import pytest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/publish-release.yml"


def check_policy(text: str) -> None:
    verification = text.index("gh attestation verify assets/release-manifest.json")
    manifest_parse = text.index("row=json.load(open('assets/release-manifest.json'")
    assert verification < manifest_parse
    assert "--bundle assets/release-manifest.json.bundle.jsonl" in text
    assert "--custom-trusted-root packaging/release-trusted-root.jsonl" in text
    assert "--signer-workflow MONTBRAIN/vadgr/.github/workflows/candidate.yml" in text
    assert "--source-ref refs/heads/master --deny-self-hosted-runners" in text
    assert "--manifest assets/release-manifest.json --bundle assets/release-manifest.json.bundle.jsonl" in text
    assert "release-manifest.json.minisig" not in text
    assert "      - name: Verify the keyless manifest bundle before trusting artifact metadata\n        env:\n          GH_TOKEN: ${{ github.token }}" in text
    assert "id-token: write" not in text


def test_publish_gate_checks_keyless_policy_before_reading_untrusted_manifest():
    check_policy(WORKFLOW.read_text())


def test_publish_rechecks_tag_release_identity_and_exact_asset_bytes_after_approval():
    workflow = WORKFLOW.read_text()
    protected_job = workflow[workflow.index("  publish:\n"):]
    assert "environment: release-publish" in protected_job
    assert "git verify-tag --raw" in protected_job
    assert "EXPECTED_RELEASE_ID: ${{ needs.verify-draft.outputs.release_id }}" in protected_job
    assert "EXPECTED_ASSET_IDS: ${{ needs.verify-draft.outputs.asset_ids }}" in protected_job
    assert "test \"$current_ids\" = \"$EXPECTED_ASSET_IDS\"" in protected_job
    assert "cmp --silent \"$expected\"" in protected_job
    assert protected_job.index("cmp --silent") < protected_job.index("gh release edit")


@pytest.mark.parametrize("old,new", [
    ("--bundle assets/release-manifest.json.bundle.jsonl", "--bundle untrusted.json"),
    ("--custom-trusted-root packaging/release-trusted-root.jsonl", "--custom-trusted-root asset.jsonl"),
    ("--signer-workflow MONTBRAIN/vadgr/.github/workflows/candidate.yml", "--owner MONTBRAIN"),
    ("--source-ref refs/heads/master --deny-self-hosted-runners", "--source-ref refs/heads/feature"),
])
def test_policy_guard_fails_when_removed(old: str, new: str):
    text = WORKFLOW.read_text()
    assert old in text
    with pytest.raises((AssertionError, ValueError)):
        check_policy(text.replace(old, new))
