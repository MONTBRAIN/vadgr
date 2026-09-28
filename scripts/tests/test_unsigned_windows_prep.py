"""Unsigned preparation is evidence for review, never candidate approval."""

import json
import os
from pathlib import Path
import struct
import shutil
import subprocess
import sys

import pytest

from scripts import unsigned_windows_prep as prep
from scripts import candidate_policy as gate


ROOT = Path(__file__).resolve().parents[2]


def pe(machine=0x8664):
    data = bytearray(256)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, machine)
    struct.pack_into("<H", data, 88, 0x20b)
    return bytes(data)


def test_workflow_has_only_read_access_and_two_native_builds():
    workflow = (ROOT / ".github/workflows/unsigned-windows-preparation.yml").read_text()
    for prohibited in ("secrets.", "environment:", "id-token:", "attestations:",
                       "contents: write", "actions: write", "pull_request_target", "workflow_call:"):
        assert prohibited not in workflow
    assert "runner: windows-latest" in workflow
    assert "runner: windows-11-arm" in workflow
    assert "github.ref == 'refs/heads/master'" in workflow
    assert "github.run_attempt == 1" in workflow
    assert "persist-credentials: false" in workflow
    assert "GH_TOKEN: ''" in workflow and "GITHUB_TOKEN: ''" in workflow
    assert "\n  observe:" in workflow
    observer = workflow.split("\n  observe:", 1)[1]
    assert "cargo " not in observer and "__payload-setup" not in observer
    assert "unsigned_windows_prep.py observe" in observer
    assert "unapproved-windows-preparation" in workflow


def test_source_paths_reject_windows_aliases_before_materialization():
    for names in (("Cargo.toml", "cargo.toml"), ("aux.txt",), ("a:b",),
                  ("a", "a/b"), ("a/../outside",), ("a\\outside",)):
        with pytest.raises((gate.Refused, prep.PackageInputError)):
            prep.validate_paths([( "100644", "blob", "a" * 40, name) for name in names])


def test_workflow_identity_refuses_other_workflows_and_attempts(monkeypatch):
    env = {"GITHUB_REPOSITORY": gate.REPOSITORY, "GITHUB_REF": "refs/heads/master",
           "GITHUB_WORKFLOW_REF": gate.REPOSITORY + "/.github/workflows/unsigned-windows-preparation.yml@refs/heads/master",
           "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    prep.workflow_identity()
    for key, bad in (("GITHUB_REF", "refs/heads/feature/x"), ("GITHUB_RUN_ATTEMPT", "2"),
                     ("GITHUB_WORKFLOW_REF", "other"), ("GITHUB_SHA", "HEAD")):
        monkeypatch.setenv(key, bad)
        with pytest.raises(gate.Refused):
            prep.workflow_identity()
        monkeypatch.setenv(key, env[key])


def test_terms_are_exact_source_data_and_never_approval(tmp_path):
    source = tmp_path / "source"
    legal = source / "packaging/legal"
    legal.mkdir(parents=True)
    exact = b"Terms\r\n**Version 1.0**\r\nProposed terms.\r\n"
    (legal / "TERMS.txt").write_bytes(exact)
    selected = prep.terms_input(source)
    assert selected["sha256"] == prep.sha256_bytes(exact)
    assert selected["status"] == "unapproved"
    assert selected["version"] == "1.0"
    (legal / "TERMS.txt").write_text("Terms without a version")
    assert prep.terms_input(source)["status"] == "unavailable"
    (legal / "TERMS.txt").unlink()
    assert prep.terms_input(source)["status"] == "unavailable"


def test_inventory_measures_real_bytes_and_native_architecture(tmp_path):
    (tmp_path / "vadgr.exe").write_bytes(pe())
    (tmp_path / "notice.txt").write_bytes(b"exact notice")
    result = prep.file_inventory(tmp_path, "windows-x86_64")
    assert result["vadgr.exe"]["sha256"] == prep.sha256_bytes(pe())
    assert result["vadgr.exe"]["architecture"] == "x86_64"
    assert result["notice.txt"] == {"sha256": prep.sha256_bytes(b"exact notice"), "size": 12}
    with pytest.raises(gate.Refused, match="architecture"):
        prep.file_inventory(tmp_path, "windows-aarch64")


def test_changed_installed_inventory_cannot_be_observed(tmp_path):
    payload = tmp_path / "payload"
    cua = payload / "lib/cua"
    cua.mkdir(parents=True)
    (cua / "installed-inventory.json").write_text("{}")
    (cua / "payload.json").write_text(json.dumps({"installed_inventory_sha256": "0" * 64}))
    with pytest.raises(gate.Refused, match="inventory"):
        prep.verify_installed_inventory(payload)


def test_build_has_no_compliance_or_packaging_fallback():
    script = (ROOT / "scripts/candidate/prepare-unsigned-windows.ps1").read_text()
    assert "VADGR_RELEASE_PAYLOAD_BUILD = '1'" in script
    assert "VADGR_RELEASE_PROFILE = $profile" in script
    assert "@('VADGR_RELEASE_PROFILE', 'VADGR_RELEASE_PAYLOAD_BUILD', 'VADGR_BUILD_WHEELHOUSE')" in script
    assert 'Remove-Item -LiteralPath "Env:$name"' in script
    assert "Unsigned source test environment was not cleared." in script
    assert script.index('Remove-Item -LiteralPath "Env:$name"') < script.index("& cargo test")
    assert script.index("--verify $wheelhouse") < script.index("& cargo rustc")
    assert "RuntimeInformation]::OSArchitecture" in script
    assert "VADGR_TERMS_SHA256 = $terms.sha256" in script
    for forbidden in ("package-windows.ps1", "package-input-review.json", "ES_PASSWORD =", "signtool"):
        assert forbidden not in script


@pytest.mark.parametrize("architecture,profile", [("x64", "windows-x86_64"), ("arm64", "windows-aarch64")])
@pytest.mark.parametrize("inherited", [None, "", "synthetic-inherited-selection"])
def test_source_test_environment_is_absent_in_child_process(tmp_path, architecture, profile, inherited):
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not shell:
        pytest.skip("PowerShell is unavailable")
    script = (ROOT / "scripts/candidate/prepare-unsigned-windows.ps1").read_text()
    clearing = script.split("Push-Location $sourceTestRoot\ntry {\n", 1)[1].split("    & cargo test", 1)[0]
    selection = script.split("Push-Location $sourceRoot\ntry {\n", 1)[1].split("    foreach ($name in @('vadgr', 'vadgr-app'))", 1)[0]
    profile_assignment = next(line for line in script.splitlines() if line.startswith("$profile = "))
    names = ("VADGR_RELEASE_PROFILE", "VADGR_RELEASE_PAYLOAD_BUILD", "VADGR_BUILD_WHEELHOUSE")
    child = "import json,os; print(json.dumps({name: os.environ.get(name) for name in " + repr(names) + "}))"

    def quote(value):
        return "'" + value.replace("'", "''") + "'"

    invoke = f"& {quote(sys.executable)} -c {quote(child)}\nif ($LASTEXITCODE -ne 0) {{ throw 'Child probe failed.' }}\n"
    probe = tmp_path / "environment-probe.ps1"
    probe.write_text("$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version Latest\n"
                     + f"$Architecture = '{architecture}'\n" + profile_assignment + "\n"
                     + clearing + invoke + selection + invoke, encoding="utf-8")
    environment = {name: value for name, value in os.environ.items() if name.upper() not in names}
    if inherited is not None:
        environment.update({name: inherited for name in names})
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                             "-File", str(probe)], env=environment, cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    observations = [json.loads(line) for line in result.stdout.splitlines()]
    assert observations == [dict.fromkeys(names), {
        "VADGR_RELEASE_PROFILE": profile, "VADGR_RELEASE_PAYLOAD_BUILD": "1", "VADGR_BUILD_WHEELHOUSE": None}]


def test_outer_executable_must_be_unsigned():
    prep.require_unsigned_pe(pe())
    signed = bytearray(pe())
    struct.pack_into("<II", signed, 88 + 144, 256, 512)
    with pytest.raises(gate.Refused, match="certificate table"):
        prep.require_unsigned_pe(bytes(signed))


@pytest.fixture
def admission(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    files = {"Cargo.toml": b'[package]\nname="synthetic"\nversion="0.5.0"\n',
             "CHANGELOG.md": b"## [0.5.0] - 2026-09-26\n",
             gate.EXCLUDED: b"Results only\n",
             "build.rs": b'compile_error!("must never execute during admission");\n'}
    files.update({name: (ROOT / name).read_bytes() for name in gate.TRUSTED_WORKFLOWS})
    for name, data in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    def git(*args):
        return subprocess.run(["git", *args], cwd=source, check=True, capture_output=True).stdout.decode().strip()
    git("init")
    git("-c", "core.autocrlf=false", "add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Synthetic fixture")
    sha, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
    identity = {"workflow": prep.WORKFLOW, "trusted_sha": "a" * 40, "run_id": 123, "run_attempt": 1}
    monkeypatch.setattr(prep, "workflow_identity", lambda: identity)
    context = "rust (windows-latest)"
    rules = [{"type": "required_status_checks", "parameters": {
        "required_status_checks": [{"context": context, "integration_id": 15368}]}}]
    check = {"id": 42, "name": context, "app": {"id": 15368}, "status": "completed",
             "conclusion": "success", "head_sha": sha, "started_at": "2026-09-26T00:00:00Z",
             "details_url": "https://github.com/MONTBRAIN/vadgr/actions/runs/321/job/42"}
    api = {
        "": {"full_name": gate.REPOSITORY, "fork": False, "default_branch": "master"},
        f"git/ref/heads/{prep.BRANCH}": {"ref": f"refs/heads/{prep.BRANCH}", "object": {"type": "commit", "sha": sha}},
        f"git/commits/{sha}": {"sha": sha, "tree": {"sha": tree}},
        f"commits/{sha}/status?per_page=100": {"sha": sha, "statuses": []},
        "actions/workflows/ci.yml": {"path": ".github/workflows/ci.yml", "state": "active", "id": 77},
        "actions/runs/321": {"workflow_id": 77, "path": ".github/workflows/ci.yml", "head_sha": sha,
            "head_branch": prep.BRANCH, "event": "push", "run_attempt": 1, "status": "completed", "conclusion": "success",
            "repository": {"full_name": gate.REPOSITORY}, "head_repository": {"full_name": gate.REPOSITORY}},
        "actions/jobs/42": {"id": 42, "run_id": 321, "head_sha": sha, "name": context, "conclusion": "success",
            "check_run_url": f"https://api.github.com/repos/{gate.REPOSITORY}/check-runs/42"}}
    monkeypatch.setattr(gate, "github", lambda endpoint: api[endpoint])
    def pages(endpoint, key=None):
        if endpoint.startswith("pulls?"):
            return []
        if endpoint == "rules/branches/master?per_page=100":
            return rules
        if endpoint == "actions/runs/321/attempts/1/jobs?filter=all&per_page=100":
            assert key == "jobs"
            return [api["actions/jobs/42"]]
        assert endpoint == f"commits/{sha}/check-runs?filter=all&per_page=100"
        return [check]
    monkeypatch.setattr(gate, "pages", pages)
    return source, sha, api, check


def test_admission_accepts_exact_source_without_package_approval_and_never_executes_it(admission, tmp_path):
    source, sha, _, _ = admission
    record, rows = prep.admit(source, prep.BRANCH, sha)
    assert record["status"] == "unapproved" and record["candidate_approval"] is False
    assert record["publishable"] is False
    assert not (source / "packaging/inputs").exists()
    assert record["required_checks"][0]["workflow_run_id"] == 321
    materialized = tmp_path / "materialized"
    gate.materialize(source, sha, rows, materialized)
    assert not (materialized / gate.EXCLUDED).exists()
    assert (materialized / "build.rs").read_bytes() == (source / "build.rs").read_bytes()
    snapshot = tmp_path / "snapshot"
    prep.source_snapshot(source, sha, rows, snapshot)
    inventory = json.loads((snapshot / "source-inventory.json").read_text())
    assert inventory["source_sha"] == sha and gate.EXCLUDED not in inventory["files"]
    assert inventory["files"]["build.rs"]["sha256"] == prep.sha256_bytes((source / "build.rs").read_bytes())


def test_source_tests_keep_exact_runbook_outside_materialized_build(admission, tmp_path):
    source, sha, _, _ = admission
    record, rows = prep.admit(source, prep.BRANCH, sha)
    materialized = tmp_path / "materialized"
    gate.materialize(source, sha, rows, materialized)
    prep.verify_test_source(source, record)
    assert (source / gate.EXCLUDED).read_bytes() == b"Results only\n"
    assert not (materialized / gate.EXCLUDED).exists()


@pytest.mark.parametrize("defect", ["source_sha", "source_tree", "input_digest", "dirty", "missing-runbook"])
def test_source_test_checkout_must_still_match_admitted_source(admission, defect):
    source, sha, _, _ = admission
    record, _ = prep.admit(source, prep.BRANCH, sha)
    if defect in ("source_sha", "source_tree", "input_digest"):
        record[defect] = "b" * len(record[defect])
    elif defect == "dirty":
        (source / "build.rs").write_text("changed after admission")
    else:
        (source / gate.EXCLUDED).unlink()
    with pytest.raises(gate.Refused):
        prep.verify_test_source(source, record)


def test_workflow_tests_exact_checkout_then_builds_only_materialized_inputs():
    script = (ROOT / "scripts/candidate/prepare-unsigned-windows.ps1").read_text()
    workflow = (ROOT / prep.WORKFLOW).read_text()
    assert "-SourceTestDirectory source_checkout" in workflow
    assert "verify-test-source --source-root $sourceTestRoot --source-record $sourceRecordPath" in script
    test_phase = script.split("Push-Location $sourceTestRoot\ntry {\n", 1)[1].split("} finally {", 1)[0]
    build_phase = script.split("Push-Location $sourceRoot\ntry {\n", 1)[1]
    assert "& cargo test --locked --all-targets --features native-gui --target $target" in test_phase
    assert "--skip" not in test_phase and "--exclude" not in test_phase
    assert "& cargo rustc --locked --release" in build_phase
    assert '"link-arg=/MAP:$mapPath"' in build_phase
    assert '"link-arg=/MAP:$baMapPath"' in build_phase
    assert "windows_runtime_evidence.py') capture" in build_phase
    assert "& cargo test" not in build_phase
    assert "$env:CARGO_TARGET_DIR = Join-Path $sourceTestRoot 'target'" in script
    assert "$env:CARGO_TARGET_DIR = Join-Path $sourceRoot 'target'" in script
    assert script.count("throw 'The result-only runbook must be absent from the materialized build.'") == 2


@pytest.mark.parametrize("outcome", ["success", "failed-test", "unexpected-runbook"])
def test_source_and_build_phases_use_separate_directories_in_child_process(tmp_path, outcome):
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not shell:
        pytest.skip("PowerShell is unavailable")
    source_tests, build = tmp_path / "source-tests", tmp_path / "build"
    runbook = source_tests / gate.EXCLUDED
    runbook.parent.mkdir(parents=True)
    runbook.write_bytes(b"exact admitted runbook")
    build.mkdir()
    script = (ROOT / "scripts/candidate/prepare-unsigned-windows.ps1").read_text()
    phases = script[script.index("Push-Location $sourceTestRoot\n"):script.index("    $binary =")]
    phases += "} finally { Pop-Location }\n"
    observer = tmp_path / "observe-phase.py"
    observer.write_text("import json,os,pathlib,sys\n"
                        + f"runbook = pathlib.Path({gate.EXCLUDED!r})\n"
                        + "print(json.dumps({'cwd': os.getcwd(), 'target': os.environ['CARGO_TARGET_DIR'], "
                          "'runbook': runbook.read_text() if runbook.exists() else None, 'args': sys.argv[1:]}))\n",
                        encoding="utf-8")

    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    pollution = ""
    if outcome == "unexpected-runbook":
        pollution = (f"[IO.Directory]::CreateDirectory({quote((build / gate.EXCLUDED).parent)}) | Out-Null\n"
                     f"[IO.File]::WriteAllText({quote(build / gate.EXCLUDED)}, 'unexpected')\n")
    probe = tmp_path / "phase-probe.ps1"
    probe.write_text("$ErrorActionPreference = 'Stop'\nSet-StrictMode -Version Latest\n"
                     + f"$sourceTestRoot = {quote(source_tests)}\n$sourceRoot = {quote(build)}\n"
                     + "$target = 'x86_64-pc-windows-msvc'\n$profile = 'windows-x86_64'\n"
                     + f"$linkMaps = {quote(tmp_path / 'link-maps')}\n"
                     + "$env:CARGO_TARGET_DIR = Join-Path $sourceTestRoot 'target'\n"
                     + f"function cargo {{ & {quote(sys.executable)} {quote(observer)} @args\n"
                     + pollution + f"$global:LASTEXITCODE = {1 if outcome == 'failed-test' else 0}\n}}\n"
                     + phases, encoding="utf-8")
    result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                             "-File", str(probe)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    observations = [json.loads(line) for line in result.stdout.splitlines()]
    assert observations[0] == {"cwd": str(source_tests), "target": str(source_tests / "target"),
                               "runbook": "exact admitted runbook", "args": ["test", "--locked", "--all-targets",
                               "--features", "native-gui", "--target", "x86_64-pc-windows-msvc"]}
    if outcome == "success":
        assert result.returncode == 0, result.stderr
        assert len(observations) == 3
        for observation, name in zip(observations[1:], ("vadgr", "vadgr-app")):
            assert observation["cwd"] == str(build)
            assert observation["target"] == str(build / "target")
            assert observation["runbook"] is None and observation["args"][0] == "rustc"
            assert f"link-arg=/MAP:{tmp_path / 'link-maps' / (name + '.map')}" in observation["args"]
    else:
        assert result.returncode != 0 and len(observations) == 1
        expected = "source tests failed" if outcome == "failed-test" else "runbook must be absent"
        assert expected in result.stderr


@pytest.mark.parametrize("defect", ["moved", "fork", "failure", "wrong-workflow", "dirty", "wrong-branch"])
def test_admission_refuses_source_and_ci_defects(admission, defect):
    source, sha, api, check = admission
    branch = prep.BRANCH
    if defect == "moved":
        api[f"git/ref/heads/{branch}"]["object"]["sha"] = "b" * 40
    elif defect == "fork":
        api[""]["fork"] = True
    elif defect == "failure":
        check["conclusion"] = "failure"
    elif defect == "wrong-workflow":
        api["actions/runs/321"]["path"] = ".github/workflows/other.yml"
    elif defect == "dirty":
        (source / "untracked").write_text("extra")
    else:
        branch = "feature/unreviewed"
    with pytest.raises(gate.Refused):
        prep.admit(source, branch, sha)


def test_installed_inventory_detects_changed_missing_and_extra_bytes(tmp_path):
    root = tmp_path / "lib/cua"
    root.mkdir(parents=True)
    (root / "runtime.bin").write_bytes(b"exact")
    raw = prep.canonical_json({"schema": 1, "target": "synthetic", "files": {
        "runtime.bin": {"size": 5, "sha256": prep.sha256_bytes(b"exact")}}})
    (root / "installed-inventory.json").write_bytes(raw)
    (root / "payload.json").write_bytes(prep.canonical_json({
        "target": "synthetic", "installed_inventory_sha256": prep.sha256_bytes(raw)}))
    prep.verify_installed_inventory(tmp_path)
    (root / "runtime.bin").write_bytes(b"other")
    with pytest.raises(gate.Refused, match="bytes differ"):
        prep.verify_installed_inventory(tmp_path)
    (root / "runtime.bin").unlink()
    with pytest.raises(gate.Refused, match="bytes differ"):
        prep.verify_installed_inventory(tmp_path)
    (root / "runtime.bin").write_bytes(b"exact")
    (root / "extra").write_bytes(b"")
    with pytest.raises(gate.Refused, match="bytes differ"):
        prep.verify_installed_inventory(tmp_path)


@pytest.mark.parametrize("architecture,runner", [("x64", "windows-latest"), ("arm64", "windows-11-arm")])
def test_producer_is_exact_same_run_artifact_and_native_job(monkeypatch, architecture, runner):
    source = {"run_id": 123, "trusted_sha": "a" * 40}
    artifact = {"name": f"unapproved-windows-preparation-raw-{architecture}", "expired": False,
                "id": 9, "digest": "sha256:" + "b" * 64, "workflow_run": {"id": 123, "head_sha": "a" * 40}}
    job = {"name": f"build-unsigned-{architecture}", "conclusion": "success", "id": 42,
           "head_sha": "a" * 40, "labels": [runner]}
    monkeypatch.setattr(gate, "pages", lambda endpoint, key: [artifact] if key == "artifacts" else [job])
    record = prep.producer_record(architecture, source)
    assert record["artifact_id"] == 9 and record["job_id"] == 42
    job["labels"] = ["ubuntu-latest"]
    with pytest.raises(gate.Refused, match="native build"):
        prep.producer_record(architecture, source)
    job["labels"] = [runner]
    artifact["workflow_run"]["id"] = 456
    with pytest.raises(gate.Refused, match="producer"):
        prep.producer_record(architecture, source)


def test_cargo_notices_retain_exact_supplied_text_without_license_conclusions(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "Cargo.toml").write_text('[package]\nname="fixture"\n')
    exact = b"Exact license\r\n"
    (source / "LICENSE").write_bytes(exact)
    metadata = tmp_path / "metadata.json"
    metadata.write_bytes(prep.canonical_json({"packages": [{"id": "fixture", "name": "fixture", "version": "0.1.0",
        "source": None, "license": "MIT", "license_file": None, "manifest_path": str(source / "Cargo.toml")}], "resolve": None}))
    output = tmp_path / "notices"
    prep.cargo_notices(metadata, source, tmp_path / "cargo", output)
    record = json.loads((output / "cargo-components.json").read_text())
    assert record["status"] == "unapproved" and record["publishable"] is False
    package = record["packages"][0]
    assert package["license_declared"] == "MIT"
    assert "license_concluded" not in package
    assert (output / package["directory"] / "LICENSE").read_bytes() == exact


def test_public_command_refuses_untrusted_workflow_before_creating_output(tmp_path):
    env = {**os.environ, "GITHUB_REF": "refs/heads/feature/untrusted"}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/unsigned_windows_prep.py"),
        "admit", "--source-root", str(tmp_path), "--branch", prep.BRANCH, "--source-sha", "b" * 40,
        "--out", str(tmp_path / "record.json"), "--materialize", str(tmp_path / "build")],
        env=env, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 1
    assert "trusted default-branch workflow" in result.stderr
    assert not (tmp_path / "record.json").exists() and not (tmp_path / "build").exists()


def test_native_build_refuses_dummy_credential_before_touching_source(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not shell:
        pytest.skip("native PowerShell is unavailable")
    dummy = "synthetic-preparation-credential"
    result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(ROOT / "scripts/candidate/prepare-unsigned-windows.ps1"), "-Architecture", "x64",
        "-SourceDirectory", str(tmp_path / "absent"), "-SourceTestDirectory", str(tmp_path / "tests"),
        "-OutputDirectory", str(tmp_path / "output"),
        "-WheelhouseDirectory", str(tmp_path / "wheels"), "-SourceRecord", str(tmp_path / "record.json")],
        env={**os.environ, "GH_TOKEN": dummy}, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0
    assert "must have no signing or identity credential" in result.stdout + result.stderr
    assert dummy not in result.stdout + result.stderr
    assert not (tmp_path / "output").exists()


def test_fresh_observer_retains_hidden_bytes_and_exact_hashes_as_unapproved(admission, tmp_path, monkeypatch):
    source, sha, _, _ = admission
    record, _ = prep.admit(source, prep.BRANCH, sha)
    raw = tmp_path / "raw"
    cua = raw / "payload/lib/cua"
    cua.mkdir(parents=True)
    (cua / ".hidden").write_bytes(b"exact hidden runtime file")
    inventory = prep.canonical_json({"schema": 1, "target": "x86_64-pc-windows-msvc", "files": {
        ".hidden": {"size": 25, "sha256": prep.sha256_bytes(b"exact hidden runtime file")}}})
    (cua / "installed-inventory.json").write_bytes(inventory)
    (cua / "payload.json").write_bytes(prep.canonical_json({"schema": 3,
        "target": "x86_64-pc-windows-msvc", "release_profile": "windows-x86_64",
        "installed_inventory_sha256": prep.sha256_bytes(inventory)}))
    for name in ("vadgr.exe", "vadgr-app.exe"):
        (raw / "payload" / name).write_bytes(pe())
    for name in ("cargo-metadata.json", "cargo-notices/cargo-components.json", "rustc-version.txt", "cargo-version.txt"):
        path = raw / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic build observation")
    (raw / "preparation-source.json").write_bytes(prep.canonical_json(record))
    (raw / "build-observation.json").write_bytes(prep.canonical_json({
        "terms": prep.terms_input(source), "architecture": "x64", "native_architecture": "X64"}))
    checked = []
    monkeypatch.setattr(prep.cua_wheelhouse, "verify_materialized", lambda *args: checked.append(args))
    monkeypatch.setattr(prep.distribution_matrix, "verify_payload", lambda *args: None)
    runtime_checked = []
    monkeypatch.setattr(prep.windows_runtime_evidence, "validate", lambda *args: runtime_checked.append(args))
    monkeypatch.setattr(prep, "producer_record", lambda *args: {"artifact_id": 9})
    output = tmp_path / "observations"
    report = prep.observe(source, record, raw, "x64", output)
    assert runtime_checked == [(raw, "x64")]
    assert checked[0][-1] == "windows-x86_64"
    assert report["status"] == "unapproved" and report["candidate_approval"] is False
    assert report["publishable"] is False
    assert report["executable_hashes"]["payload/vadgr.exe"] == prep.sha256_bytes(pe())
    assert (output / "unsigned-inputs/payload/lib/cua/.hidden").read_bytes() == b"exact hidden runtime file"
    assert (output / "UNAPPROVED-NONPUBLISHABLE.txt").is_file()
    assert "source-inputs.zip" in report["source_files"]
    changed = {**record, "source_sha": "c" * 40}
    with pytest.raises(gate.Refused, match="source admission"):
        prep.observe(source, changed, raw, "x64", tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
