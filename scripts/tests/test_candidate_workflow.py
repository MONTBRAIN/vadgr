"""Secret-free checks start from the trusted checked-in workflow and tools."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_pre_pr_ci_only_adds_named_candidate_source_branch():
    workflow = (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'branches: [master, feature/0.5.0-distribution]' in workflow
    assert 'secrets.' not in workflow
    assert not re.search(r'^\s+environment:', workflow, re.MULTILINE)


def test_all_required_secret_gate_runners_are_emitted():
    workflow = (ROOT / '.github/workflows/secret-scan.yml').read_text()
    gates = workflow.split('\n  gate-tests:', 1)[1]
    assert 'os: [ubuntu-latest, windows-latest, macos-15]' in gates


def test_dispatch_is_default_branch_only_and_one_shot():
    workflow = (ROOT / '.github/workflows/candidate.yml').read_text()
    assert 'workflow_dispatch:' in workflow
    assert 'pull_request_target' not in workflow
    assert 'workflow_call:' not in workflow
    assert "github.ref == 'refs/heads/master'" in workflow
    assert "github.run_attempt == 1" in workflow
    assert 'cancel-in-progress: false' in workflow
    for action in re.findall(r'^\s*- uses:\s*(\S+)', workflow, re.MULTILINE):
        assert re.fullmatch(r'[\w/-]+@[a-f0-9]{40}', action), action


def test_signer_has_no_source_checkout_or_build_execution():
    workflow = (ROOT / '.github/workflows/candidate.yml').read_text()
    signer = workflow.split('\n  sign-windows:', 1)[1].split('\n  attest:', 1)[0]
    assert 'environment: candidate-windows' in signer
    assert 'needs: [prepare-authorization, authorize-signing, claim-signing]' in signer
    assert 'ref: ${{ github.sha }}' in signer
    assert 'cargo ' not in signer
    assert 'source_sha' not in signer
    assert 'contents: write' not in signer
    assert 'id-token: write' not in signer
    assert 'candidate_claims.py verify' in signer


def test_trusted_packager_never_compiles_or_executes_payload():
    script = (ROOT / 'scripts/candidate/package-windows.ps1').read_text()
    assert 'cargo' not in script
    assert 'Start-Process' not in script
    assert 'BAFunctionsPath=$ba' in script
    assert 'VadgrMsi.wixproj' in script
    assert 'VadgrBundle.wixproj' in script
    assert 'ImportDirectoryBuildProps=false' in script
    assert 'ImportDirectoryBuildTargets=false' in script


def test_quota_reserves_before_vendor_request():
    script = (ROOT / 'scripts/signing/release.ps1').read_text()
    assert script.index('Reserve-Attempt $inputFile') < script.index("Invoke-Wrapper 'sign'")
    assert 'candidate_claims.py' in script
    assert 'refs/heads/master' in script
    assert 'refs/tags/v' not in script
