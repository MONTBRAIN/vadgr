"""Tests for the branch-point gate.

The ancestry lookup is injected, so the logic is tested without a network, a
GitHub token or a repository shaped for the occasion.
"""

import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from check_branch_point import inherited  # noqa: E402


def ancestry_of(pairs):
    """A stub: `pairs` are the (candidate, head) couples that are ancestors."""
    return lambda candidate, head: (candidate, head) in pairs


class TestItCatchesTheRealShape:
    def test_a_branch_cut_from_an_open_pull_request(self):
        others = [{"number": 190, "title": "0.4.8: the CLI in Rust", "head": "featsha"}]
        problems = inherited("mysha", others, ancestry_of({("featsha", "mysha")}))
        assert len(problems) == 1
        assert "#190" in problems[0]

    def test_it_names_every_one_it_inherited(self):
        others = [
            {"number": 1, "title": "a", "head": "x"},
            {"number": 2, "title": "b", "head": "y"},
        ]
        problems = inherited("mine", others, ancestry_of({("x", "mine"), ("y", "mine")}))
        assert len(problems) == 2


class TestItLeavesCorrectWorkAlone:
    def test_a_branch_cut_from_the_default_branch(self):
        others = [{"number": 190, "title": "a feature", "head": "featsha"}]
        assert inherited("mysha", others, ancestry_of(set())) == []

    def test_the_only_open_pull_request_is_this_one(self):
        assert inherited("mysha", [], ancestry_of(set())) == []

    def test_a_pull_request_whose_head_is_this_head(self):
        """The same branch pushed twice is not an inheritance."""
        others = [{"number": 5, "title": "same", "head": "mysha"}]
        assert inherited("mysha", others, ancestry_of({("mysha", "mysha")})) == []

    def test_a_head_that_cannot_be_resolved_is_skipped(self):
        """A branch deleted mid-run is not evidence of anything."""
        others = [{"number": 7, "title": "gone", "head": None}]
        assert inherited("mysha", others, ancestry_of(set())) == []


class TestTheScriptRuns:
    def test_it_reports_on_this_repository(self):
        script = pathlib.Path(__file__).resolve().parents[1] / "check_branch_point.py"
        result = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True,
            cwd=script.parents[1],
        )
        assert result.returncode in (0, 1), result.stdout
        assert "BRANCH POINT CHECK" in result.stdout or "CUT FROM" in result.stdout
