"""The exact certificate policy must also be a valid verifier invocation."""

from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from scripts import cua_release_inputs as release
from scripts.validate_package_inputs import PackageInputError, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
IDENTITY = "https://github.com/MONTBRAIN/vadgr/.github/workflows/native-wheels.yml@refs/heads/master"


def arguments(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(release, "read_owned", lambda *args: b"test root")
    monkeypatch.setattr(release, "TRUSTED_ROOT_SHA256", sha256_bytes(b"test root"))

    def run(args, **kwargs):
        captured.append(args)
        return SimpleNamespace(returncode=0, stdout=b"[{}]")

    monkeypatch.setattr(release.subprocess, "run", run)
    release.verify_attestation(tmp_path, {"producer_sha": SHA, "input_commit": SHA})
    return captured[0]


def test_exact_certificate_policy_uses_one_identity_selector(tmp_path, monkeypatch):
    args = arguments(tmp_path, monkeypatch)
    exclusive = {"--cert-identity", "--cert-identity-regex", "--signer-repo", "--signer-workflow"}
    assert exclusive.intersection(args) == {"--cert-identity"}
    for flag, value in {
        "--cert-identity": IDENTITY, "--repo": "MONTBRAIN/vadgr",
        "--cert-oidc-issuer": "https://token.actions.githubusercontent.com",
        "--signer-digest": SHA, "--source-digest": SHA, "--source-ref": "refs/heads/master",
        "--custom-trusted-root": str(tmp_path / release.TRUSTED_ROOT),
        "--bundle": str(tmp_path / release.BUNDLE), "--format": "json",
    }.items():
        assert args[args.index(flag) + 1] == value
    assert "--deny-self-hosted-runners" in args


def test_installed_gh_accepts_identity_flags_before_reading_missing_root(tmp_path, monkeypatch):
    executable = shutil.which("gh")
    if not executable:
        pytest.skip("GitHub CLI is not installed; exact selector policy is checked separately")
    actual_run = subprocess.run
    args = arguments(tmp_path, monkeypatch)
    args[0] = executable
    result = actual_run(args, cwd=tmp_path, capture_output=True, timeout=20, check=False)
    assert result.returncode != 0
    assert b"none of the others can be" not in result.stderr
    assert b"release-trusted-root.jsonl" in result.stderr


def test_committed_trust_root_survives_windows_checkout():
    assert sha256_bytes((ROOT / release.TRUSTED_ROOT).read_bytes()) == release.TRUSTED_ROOT_SHA256
    assert f"{release.TRUSTED_ROOT} text eol=lf" in (ROOT / ".gitattributes").read_text().splitlines()


@pytest.mark.parametrize("failure", ["certificate identity", "issuer", "source ref", "source digest", "signer digest"])
def test_verifier_identity_failure_cannot_be_overridden_by_json_output(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(release, "read_owned", lambda *args: b"test root")
    monkeypatch.setattr(release, "TRUSTED_ROOT_SHA256", sha256_bytes(b"test root"))
    monkeypatch.setattr(release.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout=b"[{}]", stderr=f"verification failed: {failure}".encode()))
    with pytest.raises(PackageInputError, match="attestation verification failed"):
        release.verify_attestation(tmp_path, {"producer_sha": SHA, "input_commit": SHA})
