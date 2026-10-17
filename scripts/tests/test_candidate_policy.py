"""Adversarial, offline checks for the trusted candidate source gate."""

import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import candidate_policy as gate


class SizedOutput:
    def __init__(self, size):
        self.size = size

    def __len__(self):
        return self.size

    def decode(self, _encoding):
        return "metadata"


class PolicyTests(unittest.TestCase):
    def test_binary_source_blob_has_separate_bounded_limit(self):
        source_blob = SizedOutput(gate.METADATA_LIMIT + 1)
        result = SimpleNamespace(returncode=0, stdout=source_blob)
        with patch.object(gate.subprocess, "run", return_value=result):
            self.assertIs(gate.run(["git", "show"], binary=True), source_blob)
            with self.assertRaises(gate.Refused):
                gate.run(["gh", "api"])

        oversized = SimpleNamespace(returncode=0, stdout=SizedOutput(gate.SOURCE_BLOB_LIMIT + 1))
        with patch.object(gate.subprocess, "run", return_value=oversized):
            with self.assertRaises(gate.Refused):
                gate.run(["git", "show"], binary=True)

    def test_sealed_inventory_ignores_only_runbook(self):
        rows = [("100644", "blob", "a" * 40, "Cargo.toml"),
                ("100644", "blob", "b" * 40, "E2E/0.5.0/e2e.md")]
        first = gate.input_digest(rows)
        rows[1] = ("100644", "blob", "c" * 40, "E2E/0.5.0/e2e.md")
        self.assertEqual(first, gate.input_digest(rows))
        rows[0] = ("100644", "blob", "d" * 40, "Cargo.toml")
        self.assertNotEqual(first, gate.input_digest(rows))
        with self.assertRaises(gate.Refused):
            gate.input_digest([("160000", "commit", "a" * 40, "vendor")])

    def test_required_check_rejects_newer_failure_and_issuer_mismatch(self):
        rules = [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "build", "integration_id": 15368}]}}]
        old = {"id": 1, "name": "build", "app": {"id": 15368},
               "status": "completed", "conclusion": "success", "head_sha": "a" * 40,
               "started_at": "2026-09-01T00:00:00Z"}
        bad = {**old, "id": 2, "conclusion": "failure",
               "started_at": "2026-09-02T00:00:00Z"}
        gate.require_checks(rules, [old], [], "a" * 40)
        with self.assertRaises(gate.Refused):
            gate.require_checks(rules, [old, bad], [], "a" * 40)
        with self.assertRaises(gate.Refused):
            gate.require_checks(rules, [{**old, "app": {"id": 12}}],
                                [{"id": 2, "context": "build", "state": "success"}], "a" * 40)

    def test_unbound_context_rejects_newer_legacy_failure(self):
        rules = [{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "build"}]}}]
        success = {"id": 1, "name": "build", "app": {"id": 15368},
                   "status": "completed", "conclusion": "success", "head_sha": "a" * 40,
                   "started_at": "2026-09-01T00:00:00Z"}
        failed = {"id": 2, "context": "build", "state": "failure",
                  "created_at": "2026-09-02T00:00:00Z"}
        with self.assertRaises(gate.Refused):
            gate.require_checks(rules, [success], [failed], "a" * 40)

    def test_zero_pr_allowed_but_wrong_pr_refused(self):
        sha = "a" * 40
        gate.require_pull_requests([], "feature/0.5.0-distribution", sha)
        bad = {"state": "open", "number": 9, "head": {"sha": sha, "ref": "other",
               "repo": {"full_name": gate.REPOSITORY, "fork": False}},
               "base": {"ref": "master", "repo": {"full_name": gate.REPOSITORY, "fork": False}}}
        with self.assertRaises(gate.Refused):
            gate.require_pull_requests([bad], "feature/0.5.0-distribution", sha)

    def test_candidate_requires_exact_merged_pr_and_protected_master(self):
        sha = "a" * 40
        repo = {"full_name": gate.REPOSITORY, "fork": False}
        pull = {"state": "closed", "number": 9, "merged_at": "2026-09-29T00:00:00Z",
                "merge_commit_sha": sha, "head": {"repo": repo},
                "base": {"ref": "master", "repo": repo}}
        self.assertEqual(gate.require_merged_pull_requests([pull], sha), 9)
        with self.assertRaises(gate.Refused):
            gate.require_merged_pull_requests([], sha)
        with self.assertRaises(gate.Refused):
            gate.require_merged_pull_requests([{**pull, "merge_commit_sha": "b" * 40}], sha)
        rules = [{"type": "deletion"}, {"type": "non_fast_forward"},
                 {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
                 {"type": "required_status_checks", "parameters": {
                     "required_status_checks": [{"context": "build", "integration_id": 15368}]}}]
        gate.require_master_protection(rules)
        with self.assertRaises(gate.Refused):
            gate.require_master_protection([rule for rule in rules if rule["type"] != "pull_request"])

    def test_unconfigured_public_root_and_unreviewed_terms_refused(self):
        with self.assertRaises(gate.Refused):
            gate.require_release_inputs("UNCONFIGURED\n", "# Terms\nStatus: draft", False, False)

    def test_required_checks_are_bound_to_trusted_workflow_and_actual_job(self):
        sha = "a" * 40
        branch = "feature/0.5.0-distribution"
        check = {"id": 42, "name": "rust (ubuntu-latest)", "details_url":
                 "https://github.com/MONTBRAIN/vadgr/actions/runs/123/job/42"}
        row = {"context": check["name"], "integration_id": 15368, "check_id": 42}
        workflow = {"path": ".github/workflows/ci.yml", "state": "active", "id": 77}
        run = {"workflow_id": 77, "path": workflow["path"], "head_sha": sha,
               "head_branch": branch, "event": "push", "run_attempt": 1,
               "status": "completed", "conclusion": "success",
               "repository": {"full_name": gate.REPOSITORY},
               "head_repository": {"full_name": gate.REPOSITORY}}
        job = {"id": 42, "run_id": 123, "head_sha": sha, "name": row["context"],
               "conclusion": "success", "check_run_url":
               f"https://api.github.com/repos/{gate.REPOSITORY}/check-runs/42"}
        with (patch.object(gate, "github", side_effect=[workflow, run]),
              patch.object(gate, "pages", return_value=[job]) as pages):
            selected = gate.require_trusted_check_runs([row], [check], sha, branch, event="push")
        pages.assert_called_once_with(
            "actions/runs/123/attempts/1/jobs?filter=all&per_page=100", "jobs")
        self.assertEqual(selected[0]["workflow_run_id"], 123)
        second_check = {**check, "id": 43, "name": "installer (windows-latest)",
                        "details_url":
                        "https://github.com/MONTBRAIN/vadgr/actions/runs/123/job/43"}
        second_row = {"context": second_check["name"], "integration_id": 15368,
                      "check_id": 43}
        second_job = {**job, "id": 43, "name": second_row["context"],
                      "check_run_url":
                      f"https://api.github.com/repos/{gate.REPOSITORY}/check-runs/43"}
        with (patch.object(gate, "github", side_effect=[workflow, run]),
              patch.object(gate, "pages", return_value=[job, second_job]) as pages):
            selected = gate.require_trusted_check_runs(
                [row, second_row], [check, second_check], sha, branch)
        pages.assert_called_once()
        self.assertEqual([item["check_id"] for item in selected], [42, 43])
        with (patch.object(gate, "github", side_effect=[workflow, {**run, "path":
                                                                 ".github/workflows/evil.yml"}]),
              self.assertRaises(gate.Refused)):
            gate.require_trusted_check_runs([row], [check], sha, branch)
        with (patch.object(gate, "github", side_effect=[workflow, run]),
              patch.object(gate, "pages", return_value=[{**job, "run_id": 124}]),
              self.assertRaises(gate.Refused)):
            gate.require_trusted_check_runs([row], [check], sha, branch)
        with (patch.object(gate, "github", side_effect=[workflow, run]),
              patch.object(gate, "pages", return_value=[job, job]),
              self.assertRaises(gate.Refused)):
            gate.require_trusted_check_runs([row], [check], sha, branch)
        with self.assertRaises(gate.Refused):
            gate.require_trusted_check_runs([{**row, "integration_id": None}], [check], sha, branch)
        with (patch.object(gate, "github", side_effect=[workflow, {**run, "event": "pull_request"}]),
              self.assertRaises(gate.Refused)):
            gate.require_trusted_check_runs([row], [check], sha, branch, event="push")

    def test_feature_ci_workflow_cannot_redefine_trusted_checks(self):
        rows = [("100644", "blob", "a" * 40, name) for name in gate.TRUSTED_WORKFLOWS]
        with patch.object(gate, "git", return_value=b"modified on feature"):
            with self.assertRaises(gate.Refused):
                gate.require_trusted_workflows(gate.Path("/unused"), "a" * 40, rows)


if __name__ == "__main__":
    unittest.main()
