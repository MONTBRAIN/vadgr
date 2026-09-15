"""CI boundary probes use disposable inputs, never production trust placeholders."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def push_branches(text):
    block = text.split("  push:\n", 1)[1].split("  pull_request:\n", 1)[0]
    match = re.search(r"branches: \[([^\]]+)\]", block)
    assert match, "CI must declare its push branches"
    return {branch.strip() for branch in match[1].split(",")}


def wsl_step(text):
    block = text.split("  wsl-clean-install:\n", 1)[1].split("\n  clean-install:\n", 1)[0]
    return textwrap.dedent(block.split("        run: |\n", 1)[1].split("\n  #", 1)[0])


def test_normal_ci_runs_on_the_exact_candidate_source_before_a_pr():
    assert push_branches(WORKFLOW.read_text()) == {"master", "feature/0.5.0-distribution"}


def run_wsl_probe(tmp_path, arch, configured, damage=None):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "packaging").mkdir()
    source = (ROOT / "install.sh").read_text()
    value = "a" * 64 if configured else "UNCONFIGURED"
    source = re.sub(r"(?m)^(VERIFIER_SHA_(?:X86_64|AARCH64))=.*$", rf"\g<1>={value}", source)
    if damage:
        old, new = damage
        assert old in source
        source = source.replace(old, new)
    (checkout / "install.sh").write_text(source)
    key = "configured-test-public-key\n" if configured else "UNCONFIGURED\n"
    (checkout / "packaging/release-public-key.txt").write_text(key)
    home = tmp_path / "home"
    home.mkdir()
    (home / "owner-state").write_text("preserve this fixture\n")
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "uname").write_text(f"#!/bin/sh\nprintf '%s\\n' {arch}\n")
    (shims / "uname").chmod(0o755)
    environment = {
        "HOME": str(home), "TMPDIR": str(temporary),
        "PATH": str(shims) + os.pathsep + os.defpath,
    }
    sha256sum = shutil.which("sha256sum")
    assert sha256sum, "The WSL boundary probe requires sha256sum"
    (shims / "sha256sum").symlink_to(sha256sum)
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", wsl_step(WORKFLOW.read_text())],
        cwd=checkout, env=environment, capture_output=True, text=True, timeout=15,
    )
    assert (checkout / "install.sh").read_text() == source
    assert (checkout / "packaging/release-public-key.txt").read_text() == key
    assert list(home.iterdir()) == [home / "owner-state"]
    assert (home / "owner-state").read_text() == "preserve this fixture\n"
    assert not list(temporary.iterdir()), "The probe must remove only its disposable root"
    return result


@pytest.mark.skipif(sys.platform == "win32", reason="The WSL shell probe runs on Unix or inside WSL")
@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
@pytest.mark.parametrize("configured", [False, True])
def test_wsl_probe_is_independent_of_production_trust_inputs(tmp_path, arch, configured):
    result = run_wsl_probe(tmp_path, arch, configured)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Unconfigured WSL fixture refused before mutation." in result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="The WSL shell probe runs on Unix or inside WSL")
@pytest.mark.parametrize("damage", [
    ('[ "$VERIFIER_SHA" != UNCONFIGURED ]',
     'printf mutated > "$HOME/owner-state"\n[ "$VERIFIER_SHA" != UNCONFIGURED ]'),
    ('[ "$VERIFIER_SHA" != UNCONFIGURED ]',
     'mkdir "$HOME/unexpected"\n[ "$VERIFIER_SHA" != UNCONFIGURED ]'),
    ("The reviewed verifier hash is not configured.", "An unrelated error occurred."),
    ("This candidate cannot install.\" >&2; exit 2;", "This candidate cannot install.\" >&2; exit 0;"),
])
def test_wsl_probe_detects_state_mutation_and_false_refusals(tmp_path, damage):
    result = run_wsl_probe(tmp_path, "x86_64", True, damage)
    assert result.returncode != 0
    assert "Unconfigured WSL fixture refused before mutation." not in result.stdout


def test_ci_probe_requires_the_exact_refusal_and_checks_state():
    step = wsl_step(WORKFLOW.read_text())
    assert "The reviewed verifier hash is not configured. This candidate cannot install." in step
    assert 'test "$code" -eq 2' in step
    assert 'test "$before" = "$after"' in step
    assert "release-public-key.txt" not in step


def test_macos_clean_install_uses_the_native_bundle_and_real_host_build():
    text = WORKFLOW.read_text()
    assert "cargo build --locked --release --features macos-cua-host --bin vadgr --bin vadgr-cua-host" in text
    assembly = text.split("- name: Assemble the macOS app without Python tools\n", 1)[1]
    assembly = assembly.split("\n      - name:", 1)[0]
    assert "if: runner.os == 'macOS'" in assembly
    assert 'app="$RUNNER_TEMP/vadgr-clean-install/Vadgr.app"' in assembly
    assert 'install_root="$app/Contents/Resources"' in assembly
    assert 'host="$app/Contents/Library/LoginItems/Vadgr Computer Use.app/Contents"' in assembly
    assert 'packaging/macos/Vadgr-Info.plist' in assembly
    assert 'packaging/macos/CuaHost-Info.plist' in assembly
    assert assembly.index('"$host/MacOS/vadgr-cua-host"') < assembly.index('__payload-setup')
    assert '--install-root "$install_root" --payload-only' in assembly
    assert 'CLEAN_INSTALL_EXECUTABLE=$app/Contents/MacOS/vadgr' in assembly
    assert 'manifest="$install_root/lib/cua/payload.json"' in assembly
    macos_probe = text.split("- name: What it links, and the user's steps with the toolchain out of reach\n", 1)[1]
    macos_probe = macos_probe.split("\n      - name:", 1)[0]
    assert 'exe="$CLEAN_INSTALL_EXECUTABLE"' in macos_probe
    assert 'exe="$CLEAN_INSTALL_ROOT/bin/vadgr"' not in macos_probe
    assert "codesign" not in assembly
