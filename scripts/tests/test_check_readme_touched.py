"""Tests for the README gate.

Both halves. The second is the one that decides whether the gate survives: it
must stay silent on the hundreds of changes that ship no version, or it becomes
noise attached to every pull request.
"""

import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "check_readme_touched.py"


def repo(tmp_path):
    run = lambda *a: subprocess.run(a, cwd=tmp_path, check=True, capture_output=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "a@b.c")
    run("git", "config", "user.name", "A")
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\n')
    (tmp_path / "README.md").write_text("# x\n")
    (tmp_path / "src.rs").write_text("fn main() {}\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "base")
    return run


def check(tmp_path, event=None):
    args = [sys.executable, str(SCRIPT), "--git-range", "HEAD~1..HEAD"]
    if event is not None:
        p = tmp_path / "event.json"
        p.write_text(event)
        args += ["--event-file", str(p)]
    return subprocess.run(args, cwd=tmp_path, capture_output=True, text=True)


class TestItCatchesTheRealShape:
    def test_a_version_moved_and_no_readme_did(self, tmp_path):
        run = repo(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.2.0"\n')
        run("git", "commit", "-aqm", "bump")
        result = check(tmp_path)
        assert result.returncode == 1
        assert "NO README DID" in result.stdout


class TestItLeavesCorrectWorkAlone:
    def test_a_version_moved_and_the_readme_moved_with_it(self, tmp_path):
        run = repo(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.2.0"\n')
        (tmp_path / "README.md").write_text("# x\n\nnow does something else\n")
        run("git", "commit", "-aqm", "bump and say so")
        assert check(tmp_path).returncode == 0

    def test_a_change_that_ships_no_version(self, tmp_path):
        """The common case, and the one that decides whether the gate survives."""
        run = repo(tmp_path)
        (tmp_path / "src.rs").write_text("fn main() { }\n")
        run("git", "commit", "-aqm", "a fix")
        result = check(tmp_path)
        assert result.returncode == 0
        assert "no version change" in result.stdout

    def test_a_manifest_edited_without_touching_its_version(self, tmp_path):
        run = repo(tmp_path)
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "x"\nversion = "0.1.0"\n\n[dependencies]\nserde = "1"\n'
        )
        run("git", "commit", "-aqm", "add a dependency")
        assert check(tmp_path).returncode == 0

    def test_the_body_says_nothing_changed(self, tmp_path):
        run = repo(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.2.0"\n')
        run("git", "commit", "-aqm", "bump")
        event = '{"pull_request": {"body": "A patch.\\n\\nREADME: nothing changed\\n"}}'
        result = check(tmp_path, event)
        assert result.returncode == 0, result.stdout
        assert "nothing changed" in result.stdout

    def test_a_body_that_does_not_say_it_is_not_an_escape(self, tmp_path):
        run = repo(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.2.0"\n')
        run("git", "commit", "-aqm", "bump")
        assert check(tmp_path, '{"pull_request": {"body": "a patch"}}').returncode == 1


class TestItRefusesRatherThanPasses:
    def test_an_unavailable_range(self, tmp_path):
        repo(tmp_path)
        result = check.__wrapped__ if hasattr(check, "__wrapped__") else None
        out = subprocess.run(
            [sys.executable, str(SCRIPT), "--git-range", "deadbeef..HEAD"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert out.returncode == 2
        assert "could not run" in out.stdout
