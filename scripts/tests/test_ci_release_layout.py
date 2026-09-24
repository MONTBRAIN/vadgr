"""Execute the workflow's release selector using isolated package metadata."""

import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
LAYOUT_GUARD = "Require a successful reviewed layout"


def job(name):
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"(?m)^  {re.escape(name)}:\n", text)
    assert match, f"Missing job: {name}"
    return re.split(r"(?m)^  [a-z][a-z-]*:\n", text[match.end():], maxsplit=1)[0]


def steps(name):
    return re.findall(r"(?ms)^      - name: (.*?)\n(.*?)(?=^      - |\Z)", job(name))


def step(job_name, step_name):
    matches = [body for name, body in steps(job_name) if name == step_name]
    assert len(matches) == 1, f"Missing or repeated step: {step_name}"
    return matches[0]


def selected_steps(job_name, layout, runner, image):
    selected = set()
    for name, body in steps(job_name):
        condition = re.search(r"(?m)^        if: (.*)$", body)
        if condition:
            expression = condition[1].replace("needs.release-layout.outputs.layout", repr(layout))
            expression = expression.replace("runner.os", repr(runner)).replace("matrix.os", repr(image))
            expression = expression.replace("&&", "and").replace("||", "or")
            if not eval(expression, {"__builtins__": {}}, {}):
                continue
        selected.add(name)
    return selected


def select_layout(tmp_path, metadata):
    (tmp_path / "Cargo.toml").write_text(metadata, encoding="utf-8")
    output = tmp_path / "job-output"
    body = step("release-layout", "Select the reviewed release layout")
    lines = []
    for line in body.split("        run: |\n", 1)[1].splitlines():
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line)
    script = textwrap.dedent("\n".join(lines)).strip()
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True, timeout=15,
    )
    return result, output.read_text(encoding="utf-8") if output.exists() else ""


@pytest.mark.parametrize("version,layout", [("0.4.12", "legacy"), ("0.5.0", "distribution")])
def test_exact_reviewed_versions_select_their_layout(tmp_path, version, layout):
    result, output = select_layout(tmp_path, f'[package]\nname = "vadgr-daemon"\nversion = "{version}"\n')
    assert result.returncode == 0, result.stderr
    assert output == f"layout={layout}\n"
    assert result.stdout.strip() == f"Reviewed CI layout: {layout}"


@pytest.mark.parametrize("metadata", [
    '[package]\nname = "vadgr-daemon"\nversion = "0.4.11"\n',
    '[package]\nname = "vadgr-daemon"\nversion = "0.4.13"\n',
    '[package]\nname = "vadgr-daemon"\nversion = "0.5.1"\n',
    '[package]\nname = "vadgr-daemon"\nversion = "0.5.0-rc.1"\n',
    '[package]\nname = "another-product"\nversion = "0.5.0"\n',
    '[package]\nname = "vadgr-daemon"\n',
    'invalid toml',
])
def test_unknown_or_invalid_package_cannot_select_a_layout(tmp_path, metadata):
    result, output = select_layout(tmp_path, metadata)
    assert result.returncode != 0
    assert output == ""
    assert "Reviewed CI layout:" not in result.stdout


@pytest.mark.parametrize("layout", ["legacy", "distribution"])
@pytest.mark.parametrize("runner,image,legacy,distribution", [
    ("Linux", "ubuntu-latest", "Install on Linux, in a container with nothing in it",
     "Keep native Linux on the graphical package boundary"),
    ("macOS", "macos-latest", "Install on macOS, where the runner already has a toolchain",
     "Keep macOS on the signed package boundary"),
    ("Windows", "windows-latest", "Install on Windows, through the PowerShell half",
     "Install on Windows, through the PowerShell half"),
])
def test_each_installer_runs_only_its_version_and_platform(layout, runner, image, legacy, distribution):
    assert selected_steps("installer", layout, runner, image) == {
        LAYOUT_GUARD, legacy if layout == "legacy" else distribution}


@pytest.mark.parametrize("layout,expected", [
    ("legacy", "Run the real source installer inside a clean WSL distribution"),
    ("distribution", "Prove an unconfigured WSL candidate fails before mutation"),
])
def test_wsl_runs_exactly_the_required_version_probe(layout, expected):
    assert selected_steps("wsl-clean-install", layout, "Windows", "windows-latest") == {
        LAYOUT_GUARD, expected}


@pytest.mark.parametrize("layout", ["legacy", "distribution"])
@pytest.mark.parametrize("runner,image", [("Linux", "ubuntu-24.04"), ("macOS", "macos-latest"),
                                          ("macOS", "macos-15"), ("Windows", "windows-latest")])
def test_clean_install_selects_one_build_and_one_matching_assembly(layout, runner, image):
    selected = selected_steps("clean-install", layout, runner, image)
    builds = {name for name in selected if name.startswith("Build ")}
    assemblies = {name for name in selected if name.startswith("Assemble ")}
    assert len(builds) == len(assemblies) == 1
    if runner == "macOS" and layout == "distribution":
        assert builds == {"Build the macOS CLI and responsible-process host"}
        assert assemblies == {"Assemble the macOS app without Python tools"}
    elif runner != "Windows":
        assert builds == {"Build the release binaries"}
        assert assemblies == {"Assemble the complete clean install on Unix without Python tools"}
    else:
        assert assemblies == {"Assemble the complete clean install on Windows without Python tools"}


def test_layout_failure_fails_required_jobs_instead_of_skipping_them():
    for name in ("installer", "wsl-clean-install", "clean-install"):
        assert "    needs: release-layout\n" in job(name)
        assert "    if: ${{ always() }}\n" in job(name)
        assert job(name).split("    steps:\n", 1)[1].startswith(f"      - name: {LAYOUT_GUARD}\n")
        guard = step(name, LAYOUT_GUARD)
        assert "if:" not in guard and "continue-on-error:" not in guard
        assert "RELEASE_LAYOUT_RESULT: ${{ needs.release-layout.result }}" in guard
        assert "RELEASE_LAYOUT: ${{ needs.release-layout.outputs.layout }}" in guard
    assert "os: [ubuntu-latest, windows-latest, macos-latest]" in job("rust")
    assert "os: [ubuntu-latest, windows-latest, macos-latest]" in job("installer")
    assert "os: [ubuntu-24.04, windows-latest, macos-latest, macos-15]" in job("clean-install")


@pytest.mark.parametrize("job_name", ["installer", "wsl-clean-install", "clean-install"])
@pytest.mark.parametrize("result,layout,accepted", [
    ("success", "legacy", True),
    ("success", "distribution", True),
    ("failure", "legacy", False),
    ("failure", "distribution", False),
    ("skipped", "legacy", False),
    ("cancelled", "distribution", False),
    ("", "legacy", False),
    ("success", "", False),
    ("success", "unknown", False),
])
def test_required_job_guard_rejects_failed_or_missing_layout(tmp_path, job_name, result, layout, accepted):
    body = step(job_name, LAYOUT_GUARD)
    assert "        shell: python\n" in body
    script = textwrap.dedent(body.split("        run: |\n", 1)[1]).strip()
    probe = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path,
        env={**os.environ, "RELEASE_LAYOUT_RESULT": result, "RELEASE_LAYOUT": layout},
        capture_output=True, text=True, timeout=15,
    )
    assert (probe.returncode == 0) == accepted, probe.stdout + probe.stderr
    if accepted:
        assert probe.stdout.strip() == "Reviewed layout prerequisite passed."
    else:
        assert "The reviewed release layout did not succeed." in probe.stderr


def test_both_workflows_keep_actions_pinned_and_cannot_use_signing_credentials():
    for name in ("ci.yml", "secret-scan.yml"):
        text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        for action in re.findall(r"(?m)^\s*- uses:\s*(\S+)", text):
            assert re.fullmatch(r"[\w/-]+@[a-f0-9]{40}", action), action
        assert not re.search(r"\$\{\{\s*secrets\.", text)
        assert not re.search(r"(?m)^\s+environment:", text)


def test_macos_probe_uses_the_executable_recorded_by_either_layout():
    legacy = step("clean-install", "Assemble the complete clean install on Unix without Python tools")
    distribution = step("clean-install", "Assemble the macOS app without Python tools")
    probe = step("clean-install", "What it links, and the user's steps with the toolchain out of reach")
    assert 'CLEAN_INSTALL_EXECUTABLE=$install_root/bin/vadgr' in legacy
    assert 'CLEAN_INSTALL_EXECUTABLE=$app/Contents/MacOS/vadgr' in distribution
    assert 'exe="$CLEAN_INSTALL_EXECUTABLE"' in probe


def test_linux_relocation_is_distribution_only():
    text = job("clean-install")
    assert ('container_root="$CLEAN_INSTALL_ROOT"\n'
            '          if [ "${{ needs.release-layout.outputs.layout }}" = distribution ]; then\n'
            '            container_root="/opt/vadgr"\n'
            '          fi') in text
    assert 'dst=$container_root,readonly' in text
    assert '"$container_root/bin/vadgr" serve' in text
