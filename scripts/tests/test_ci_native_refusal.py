"""Native refusal probes observe only isolated state, including file contents."""

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
NATIVE_STEPS = (
    "Keep native Linux on the graphical package boundary",
    "Keep macOS on the signed package boundary",
)
REFUSAL = "This installer is for WSL. Native Linux uses the graphical AppImage installer."


def native_probe(name):
    text = WORKFLOW.read_text(encoding="utf-8")
    body = text.split(f"      - name: {name}\n", 1)[1]
    body = re.split(r"\n      - ", body, maxsplit=1)[0]
    lines = []
    for line in body.split("        run: |\n", 1)[1].splitlines():
        if line.strip() and not line.startswith("          "):
            break
        lines.append(line)
    return textwrap.dedent("\n".join(lines)).strip()


def test_native_platforms_use_the_same_isolation_and_oracles():
    assert native_probe(NATIVE_STEPS[0]) == native_probe(NATIVE_STEPS[1])


@pytest.mark.parametrize("name", NATIVE_STEPS)
def test_native_probe_snapshots_isolated_paths_and_contents(name):
    script = native_probe(name)
    assert 'find "$HOME"' not in script
    assert 'find "$fixture/home" "$fixture/tmp" -mindepth 1 -print' in script
    assert 'find "$fixture/home" "$fixture/tmp" -type f -exec "${checksum[@]}" {} \\;' in script
    assert 'printf' in script and '"$fixture/home/owner-state"' in script
    for assignment in (
        'HOME="$fixture/home"', 'XDG_DATA_HOME="$fixture/home/data"',
        'XDG_STATE_HOME="$fixture/home/state"', 'XDG_CONFIG_HOME="$fixture/home/config"',
        'XDG_CACHE_HOME="$fixture/home/cache"', 'TMPDIR="$fixture/tmp"',
    ):
        assert assignment in script
    assert 'test "$before" = "$after"' in script


@pytest.mark.parametrize("name", NATIVE_STEPS)
def test_native_probe_checks_exact_refusal_and_bounded_cleanup(name):
    script = native_probe(name)
    assert 'test "$code" -eq 2' in script
    assert 'test ! -s "$fixture/stdout"' in script
    assert REFUSAL in script
    assert 'cmp -s "$fixture/expected-stderr" "$fixture/stderr"' in script
    assert 'runner_tmp=$(cd -- "${RUNNER_TEMP:?}" && pwd -P)' in script
    assert 'fixture=$(mktemp -d "$runner_tmp/vadgr-native-refusal.XXXXXXXX")' in script
    assert 'case "$fixture" in' in script
    assert '"$runner_tmp"/vadgr-native-refusal.*)' in script
    assert '[ -d "$fixture" ] && [ ! -L "$fixture" ] || return 1' in script
    assert "trap cleanup EXIT" in script
    assert script.count('rm -rf -- "$fixture"') == 1


def run_probe(tmp_path, name, installer):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "install.sh").write_text(installer, encoding="utf-8")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    runner_home = tmp_path / "runner-home"
    runner_home.mkdir()
    (runner_home / "owner-marker").write_text("preserve", encoding="utf-8")
    bash = shutil.which("bash")
    assert bash, "The native Unix workflow uses bash"
    result = subprocess.run(
        [bash, "-euo", "pipefail", "-c", native_probe(name)], cwd=checkout,
        env={**os.environ, "HOME": str(runner_home), "RUNNER_TEMP": str(runner_temp),
             "RUNNER_HOME_CONTROL": str(runner_home)},
        capture_output=True, text=True, timeout=15,
    )
    assert (runner_home / "owner-marker").read_text(encoding="utf-8") == "preserve"
    assert list(runner_temp.iterdir()) == [], "The probe must remove its fixture after every result"
    return result, runner_home


@pytest.mark.skipif(sys.platform == "win32", reason="Native Unix shell fixtures do not run through Windows or WSL")
@pytest.mark.parametrize("name", NATIVE_STEPS)
def test_native_probe_ignores_unrelated_runner_home_activity(tmp_path, name):
    installer = (
        'printf activity > "$RUNNER_HOME_CONTROL/runner-activity"\n'
        f"printf '%s\\n' '{REFUSAL}' >&2\nexit 2\n"
    )
    result, runner_home = run_probe(tmp_path, name, installer)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (runner_home / "runner-activity").read_text(encoding="utf-8") == "activity"
    assert "Native installer refused before mutation in isolated owner state." in result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="Native Unix shell fixtures do not run through Windows or WSL")
@pytest.mark.parametrize("damage", [
    'printf changed > "$HOME/owner-state"\n',
    'mkdir "$HOME/unexpected"\n',
    'printf changed > "$XDG_DATA_HOME/unexpected"\n',
    'printf changed > "$XDG_STATE_HOME/unexpected"\n',
    'printf changed > "$XDG_CONFIG_HOME/unexpected"\n',
    'printf changed > "$XDG_CACHE_HOME/unexpected"\n',
    'printf changed > "$TMPDIR/unexpected"\n',
    "printf 'unexpected stdout\\n'\n",
    "printf 'unexpected stderr\\n' >&2\n",
])
def test_native_probe_rejects_mutation_or_extra_output(tmp_path, damage):
    result, _ = run_probe(tmp_path, NATIVE_STEPS[0],
                          damage + f"printf '%s\\n' '{REFUSAL}' >&2\nexit 2\n")
    assert result.returncode != 0
    assert "Native installer refused before mutation in isolated owner state." not in result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="Native Unix shell fixtures do not run through Windows or WSL")
@pytest.mark.parametrize("installer", [
    "exit 2\n",
    "printf 'An unrelated error occurred.\\n' >&2\nexit 2\n",
    f"printf '%s\\n' '{REFUSAL}' >&2\nexit 0\n",
])
def test_native_probe_rejects_false_refusals(tmp_path, installer):
    result, _ = run_probe(tmp_path, NATIVE_STEPS[0], installer)
    assert result.returncode != 0
    assert "Native installer refused before mutation in isolated owner state." not in result.stdout
