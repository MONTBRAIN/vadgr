"""Adversarial, offline checks for the trusted candidate source gate."""

import hashlib
import unittest
from unittest.mock import patch

from scripts import candidate_policy as gate


class PolicyTests(unittest.TestCase):
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

    def test_unconfigured_public_key_and_unreviewed_terms_refused(self):
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
        with patch.object(gate, "github", side_effect=[workflow, run, job]):
            selected = gate.require_trusted_check_runs([row], [check], sha, branch)
        self.assertEqual(selected[0]["workflow_run_id"], 123)
        with patch.object(gate, "github", side_effect=[workflow, {**run, "path":
                                                               ".github/workflows/evil.yml"}]):
            with self.assertRaises(gate.Refused):
                gate.require_trusted_check_runs([row], [check], sha, branch)
        with patch.object(gate, "github", side_effect=[workflow, run, {**job, "run_id": 124}]):
            with self.assertRaises(gate.Refused):
                gate.require_trusted_check_runs([row], [check], sha, branch)
        with self.assertRaises(gate.Refused):
            gate.require_trusted_check_runs([{**row, "integration_id": None}], [check], sha, branch)

    def test_feature_ci_workflow_cannot_redefine_trusted_checks(self):
        rows = [("100644", "blob", "a" * 40, name) for name in gate.TRUSTED_WORKFLOWS]
        with patch.object(gate, "git", return_value=b"modified on feature"):
            with self.assertRaises(gate.Refused):
                gate.require_trusted_workflows(gate.Path("/unused"), "a" * 40, rows)


if __name__ == "__main__":
    unittest.main()
