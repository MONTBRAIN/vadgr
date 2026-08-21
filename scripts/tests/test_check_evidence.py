"""Tests for the evidence gate.

The second half of each pair is the one that decides whether the gate
survives. A gate that also fires on a correct change becomes noise attached to
every pull request, and the two failures it exists to catch both arrived inside
otherwise correct work.
"""

import pathlib
import shutil
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "check_evidence.py"


def workspace(tmp_path):
    """A docs-shaped repository with the gate installed."""
    run = lambda *a: subprocess.run(a, cwd=tmp_path, check=True, capture_output=True)
    run("git", "init", "-q")
    run("git", "config", "user.email", "a@b.c")
    run("git", "config", "user.name", "A")
    (tmp_path / "scripts").mkdir()
    shutil.copy(SCRIPT, tmp_path / "scripts" / "check_evidence.py")
    (tmp_path / "NOTES.md").write_text("# notes\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "start")
    return tmp_path


def gate(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "scripts/check_evidence.py", *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def file_a_pass(root, name, with_host=True):
    pass_dir = root / "e2e_evidence" / "vadgr-0.4.9" / name
    (pass_dir / "A").mkdir(parents=True)
    (pass_dir / "A" / "A1.txt").write_text("the first cell\n")
    if with_host:
        (pass_dir / "host.txt").write_text("vadgr head: " + "a" * 40 + "\n")
    return pass_dir


def test_evidence_beside_a_document_edit_is_refused(tmp_path):
    root = workspace(tmp_path)
    file_a_pass(root, "20260819-wsl")
    (root / "NOTES.md").write_text("# notes\n\nand a change nobody asked for\n")
    result = gate(root)
    assert result.returncode == 1
    assert "files evidence and edits" in result.stdout


def test_evidence_on_its_own_is_accepted(tmp_path):
    root = workspace(tmp_path)
    file_a_pass(root, "20260819-wsl")
    result = gate(root)
    assert result.returncode == 0, result.stdout
    assert "EVIDENCE ACCOUNTED FOR" in result.stdout


def test_a_pass_that_cannot_name_its_build_is_refused(tmp_path):
    root = workspace(tmp_path)
    file_a_pass(root, "20260819-wsl", with_host=False)
    result = gate(root)
    assert result.returncode == 1
    assert "carries no host.txt" in result.stdout


def test_a_host_record_naming_no_head_is_refused(tmp_path):
    root = workspace(tmp_path)
    pass_dir = file_a_pass(root, "20260819-wsl")
    (pass_dir / "host.txt").write_text("host: a laptop\ndate: today\n")
    result = gate(root)
    assert result.returncode == 1
    assert "names no head" in result.stdout


def test_withdrawing_a_pass_is_not_a_defect(tmp_path):
    """The repair must not trip the gate that caught the fault."""
    root = workspace(tmp_path)
    file_a_pass(root, "20260819-wsl")
    run = lambda *a: subprocess.run(a, cwd=root, check=True, capture_output=True)
    run("git", "add", "-A")
    run("git", "commit", "-qm", "file the pass")
    shutil.rmtree(root / "e2e_evidence" / "vadgr-0.4.9" / "20260819-wsl")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "withdraw it")
    result = gate(root, "--range", "HEAD~1..HEAD")
    assert result.returncode == 0, result.stdout


def test_a_change_with_no_evidence_at_all_is_silent(tmp_path):
    root = workspace(tmp_path)
    (root / "NOTES.md").write_text("# notes\n\nan ordinary edit\n")
    result = gate(root)
    assert result.returncode == 0, result.stdout


def test_a_whole_pass_filed_at_once_is_still_seen(tmp_path):
    """git collapses a new directory to one entry; the gate must not be fooled."""
    root = workspace(tmp_path)
    file_a_pass(root, "20260819-wsl", with_host=False)
    result = gate(root)
    assert "carries no host.txt" in result.stdout


def branch_with(root, *steps):
    """Cut a branch from the default and commit each step on it."""
    run = lambda *a: subprocess.run(a, cwd=root, check=True, capture_output=True)
    run("git", "branch", "-M", "master")
    run("git", "checkout", "-q", "-b", "work")
    for message, make in steps:
        make(root)
        run("git", "add", "-A")
        run("git", "commit", "-qm", message)
    return root


def test_a_branch_mixing_them_in_separate_commits_is_refused(tmp_path):
    """The hole the gate fell through: clean tree, two commits, one branch.

    Evidence went in one commit and a document in the next. Nothing was
    uncommitted, so reading the working tree saw an empty change and the gate
    printed ok while the pull request carried both.
    """
    root = workspace(tmp_path)
    branch_with(
        root,
        ("file the pass", lambda r: file_a_pass(r, "20260819-wsl")),
        ("edit a document", lambda r: (r / "NOTES.md").write_text("# notes\n\nedited\n")),
    )
    result = gate(root)
    assert result.returncode == 1, result.stdout
    assert "files evidence and edits" in result.stdout


def test_a_branch_of_evidence_alone_is_accepted(tmp_path):
    """The other half: the gate must not fire on a correct evidence branch."""
    root = workspace(tmp_path)
    branch_with(
        root,
        ("file the pass", lambda r: file_a_pass(r, "20260819-wsl")),
        ("file another group", lambda r: (
            r / "e2e_evidence" / "vadgr-0.4.9" / "20260819-wsl" / "A" / "A2.txt"
        ).write_text("the second cell\n")),
    )
    result = gate(root)
    assert result.returncode == 0, result.stdout


def test_a_branch_of_documents_alone_is_accepted(tmp_path):
    root = workspace(tmp_path)
    branch_with(
        root,
        ("edit a document", lambda r: (r / "NOTES.md").write_text("# notes\n\nedited\n")),
        ("edit it again", lambda r: (r / "NOTES.md").write_text("# notes\n\ntwice\n")),
    )
    result = gate(root)
    assert result.returncode == 0, result.stdout


def test_the_default_branch_itself_is_not_diffed_against_itself(tmp_path):
    """On master there is no branch to read, and the gate says so."""
    root = workspace(tmp_path)
    subprocess.run(["git", "branch", "-M", "master"], cwd=root, check=True, capture_output=True)
    result = gate(root)
    assert result.returncode == 0, result.stdout
    assert "on master itself" in result.stdout


def test_a_repository_with_no_default_branch_skips_the_branch_half(tmp_path):
    """It says which sources it read rather than inventing a base to diff."""
    root = workspace(tmp_path)
    subprocess.run(
        ["git", "branch", "-M", "somewhere-else"], cwd=root, check=True, capture_output=True
    )
    result = gate(root)
    assert result.returncode == 0, result.stdout
    assert "no default branch to compare against" in result.stdout


def commit_evidence(root, message):
    run = lambda *a: subprocess.run(a, cwd=root, check=True, capture_output=True)
    file_a_pass(root, "20260819-wsl")
    run("git", "add", "-A")
    run("git", "commit", "-qm", message)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()


def test_evidence_pushed_straight_to_a_branch_is_refused(tmp_path):
    """The macOS boundary, three releases running, with no diff anyone read."""
    root = workspace(tmp_path)
    head = commit_evidence(root, "e2e_evidence(vadgr-0.4.9): the macOS pass")
    result = gate(root, "--range", f"{head}~1..{head}", "--require-pull-request")
    assert result.returncode == 1, result.stdout
    assert "pushed evidence with no pull request" in result.stdout


def test_evidence_from_a_squash_merged_pull_request_is_accepted(tmp_path):
    """GitHub appends (#NN) on a squash merge, and that is the mark."""
    root = workspace(tmp_path)
    head = commit_evidence(root, "0.4.9 e2e evidence: the WSL pass (#93)")
    result = gate(root, "--range", f"{head}~1..{head}", "--require-pull-request")
    assert result.returncode == 0, result.stdout


def test_a_range_holding_no_evidence_says_nothing(tmp_path):
    root = workspace(tmp_path)
    run = lambda *a: subprocess.run(a, cwd=root, check=True, capture_output=True)
    (root / "NOTES.md").write_text("# notes\n\nan ordinary edit\n")
    run("git", "add", "-A")
    run("git", "commit", "-qm", "an ordinary edit")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    result = gate(root, "--range", f"{head}~1..{head}", "--require-pull-request")
    assert result.returncode == 0, result.stdout


def test_the_pull_request_rule_needs_a_range(tmp_path):
    """Pointed at a whole branch it fires on history nobody can fix."""
    root = workspace(tmp_path)
    result = gate(root, "--require-pull-request")
    assert result.returncode == 2, result.stdout
    assert "needs --range" in result.stdout
