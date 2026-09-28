"""Secret-free checks start from the trusted checked-in workflow and tools."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_native_matrix_pins_supported_python_before_trusted_tools():
    workflow = (ROOT / '.github/workflows/candidate.yml').read_text()
    native = workflow.split('\n  build-native:', 1)[1]
    setup = 'uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065'
    assert setup in native
    assert "python-version: '3.12'" in native
    assert native.index(setup) < native.index('python scripts/candidate_policy.py preflight')


def test_signer_has_no_source_checkout_or_build_execution():
    workflow = (ROOT / '.github/workflows/candidate.yml').read_text()
    signer = workflow.split('\n  sign-windows:', 1)[1].split('\n  attest:', 1)[0]
    assert 'environment: candidate-windows' in signer
    assert 'needs: [prepare-authorization, authorize-signing, claim-signing, attest-windows-runtime]' in signer
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
    assert script.index('Reserve-Attempt $relative $inputHash') < script.index("Invoke-Wrapper 'sign'")
    assert 'candidate_claims.py' in script
    assert 'refs/heads/master' in script
    assert 'refs/tags/v' not in script


def test_feature_data_is_read_only_before_protected_authorization():
    workflow = (ROOT / '.github/workflows/candidate.yml').read_text()
    for name, next_name in (("prepare-helper-inputs", "bind-helper-inputs"),
                            ("bind-helper-inputs", "claim-probe")):
        job = workflow.split(f'\n  {name}:', 1)[1].split(f'\n  {next_name}:', 1)[0]
        assert 'ref: ${{ inputs.source_sha }}' in job
        assert '--source-root source_checkout' in job
        assert 'secrets.' not in job
        assert 'contents: write' not in job
        assert 'python source_checkout/' not in job
    approval = workflow.split('\n  authorize-signing:', 1)[1].split('\n  claim-signing:', 1)[0]
    assert 'environment: candidate-authorize' in approval
    assert 'candidate_claims.py approve' in approval
    assert 'source_checkout' not in approval


def test_windows_candidate_tests_exact_checkout_then_builds_materialized_inputs():
    workflow = (ROOT / '.github/workflows/candidate.yml').read_text()
    script = (ROOT / 'scripts/candidate/build-windows.ps1').read_text()
    calls = [line for line in workflow.splitlines() if 'build-windows.ps1' in line]
    assert len(calls) == 2
    for call in calls:
        assert '-SourceDirectory source' in call
        assert '-SourceTestDirectory source_checkout' in call
        assert '-SourceRecord preflight.json' in call
    assert 'verify-test-source --source-root $sourceTestRoot --source-record $sourceRecordPath' in script
    test_phase = script.split('Push-Location $sourceTestRoot\ntry {\n', 1)[1].split('} finally {', 1)[0]
    build_phase = script.split('Push-Location $sourceRoot\ntry {\n', 1)[1]
    assert '& cargo test --locked --all-targets --features native-gui --target $target' in test_phase
    assert '--skip' not in test_phase and '--exclude' not in test_phase
    assert '& cargo build --locked --release' in build_phase
    assert '& cargo test' not in build_phase
    assert "$env:CARGO_TARGET_DIR = Join-Path $sourceTestRoot 'target'" in script
    assert "$env:CARGO_TARGET_DIR = Join-Path $sourceRoot 'target'" in script
    assert script.count("throw 'The result-only runbook must be absent from the materialized build.'") == 2


@pytest.mark.parametrize('architecture,profile', [('x64', 'windows-x86_64'), ('arm64', 'windows-aarch64')])
@pytest.mark.parametrize('inherited', [None, '', 'synthetic-inherited-selection'])
def test_windows_candidate_source_test_environment_is_absent_in_child_process(
        tmp_path, architecture, profile, inherited):
    shell = shutil.which('pwsh') or shutil.which('powershell.exe')
    if not shell:
        pytest.skip('PowerShell is unavailable')
    script = (ROOT / 'scripts/candidate/build-windows.ps1').read_text()
    clearing = script.split('Push-Location $sourceTestRoot\ntry {\n', 1)[1].split('    & cargo test', 1)[0]
    selection = script.split('Push-Location $sourceRoot\ntry {\n', 1)[1].split('    & cargo build', 1)[0]
    names = ('VADGR_RELEASE_PROFILE', 'VADGR_RELEASE_PAYLOAD_BUILD', 'VADGR_BUILD_WHEELHOUSE')
    child = 'import json,os; print(json.dumps({name: os.environ.get(name) for name in ' + repr(names) + '}))'

    def quote(value):
        return "'" + value.replace("'", "''") + "'"

    invoke = f'& {quote(sys.executable)} -c {quote(child)}\nif ($LASTEXITCODE -ne 0) {{ throw \'Child probe failed.\' }}\n'
    probe = tmp_path / 'candidate-environment-probe.ps1'
    release_profile = "$releaseProfile = '" + profile + "'\n"
    probe.write_text("$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version Latest\n"
                     + release_profile + clearing + invoke + selection + invoke, encoding='utf-8')
    environment = {name: value for name, value in os.environ.items() if name.upper() not in names}
    if inherited is not None:
        environment.update({name: inherited for name in names})
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(probe)], env=environment, cwd=tmp_path,
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    observations = [json.loads(line) for line in result.stdout.splitlines()]
    assert observations == [dict.fromkeys(names), {
        'VADGR_RELEASE_PROFILE': profile, 'VADGR_RELEASE_PAYLOAD_BUILD': '1',
        'VADGR_BUILD_WHEELHOUSE': None}]
