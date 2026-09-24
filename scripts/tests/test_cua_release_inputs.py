"""Synthetic release-input fixtures; none authorize real wheel output."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import cua_release_inputs as release
from scripts.validate_package_inputs import PackageInputError


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class ReleaseInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.trusted = self.root / "trusted"
        self.payload = self.root / "payload"
        self.target = "aarch64-pc-windows-msvc"
        self.lock = b"cryptography==50.0.1 --hash=sha256:" + b"1" * 64 + b"\n"
        self.manifest = {"schema": 1, "repository": "MONTBRAIN/vadgr",
                         "repository_id": 1, "workflow": ".github/workflows/native-wheels.yml",
                         "workflow_id": 2, "producer_sha": "a" * 40,
                         "input_commit": "a" * 40, "run_id": 3, "run_attempt": 1,
                         "inputs": {"synthetic": True},
                         "input_sha256": sha(encoded({"synthetic": True})), "wheels": []}
        for index, target in enumerate(("windows-aarch64", "macos-x86_64"), 1):
            self.manifest["wheels"].append({"target": target,
                "sha256": str(index) * 64, "size": 17, "artifact_id": index + 10,
                "artifact_digest": "sha256:" + str(index + 2) * 64,
                "job_id": index + 20, "image_version": "synthetic-image",
                "filename": ("cryptography-50.0.1-cp311-abi3-win_arm64.whl" if index == 1
                             else "cryptography-50.0.1-cp311-abi3-macosx_13_0_x86_64.whl"),
                "test_report_sha256": "3" * 64, "build_report_sha256": "4" * 64,
                "build_sbom_sha256": "5" * 64})
        for root in (self.source, self.trusted):
            self.write(root, release.MANIFEST, encoded(self.manifest))
            self.write(root, release.BUNDLE, b'{"synthetic":true}\n')
            self.write(root, release.lock_path(self.target), self.lock)
        self.binding = {"target": self.target,
                        "wheel_manifest_sha256": sha(encoded(self.manifest)),
                        "requirements_sha256": sha(self.lock)}

    def write(self, root, name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    def runtime(self):
        self.write(self.payload, "python/python.exe", b"synthetic executable")
        files = {"python/python.exe": {"size": 20, "sha256": sha(b"synthetic executable")}}
        inventory = encoded({"schema": 1, "target": self.target, "files": files})
        self.write(self.payload, release.INVENTORY, inventory)
        manifest = {"schema": 2, **self.binding,
                    "installed_inventory_sha256": sha(inventory),
                    "cua_version": "0.7.8", "python_version": "3.12.14",
                    "python_build": "20260825", "python_archive_sha256": "6" * 64,
                    "uv_archive_sha256": "7" * 64}
        self.write(self.payload, "payload.json", encoded(manifest))
        return manifest

    def test_reviewed_source_inputs_bind_exact_default_branch_bytes(self):
        result = release.reviewed_inputs(self.source, self.trusted, self.target)
        self.assertEqual(result, self.binding)
        for name in (release.MANIFEST, release.BUNDLE, release.lock_path(self.target)):
            previous = (self.source / name).read_bytes()
            self.write(self.source, name, previous + b" ")
            with self.subTest(name=name), self.assertRaises(PackageInputError):
                release.reviewed_inputs(self.source, self.trusted, self.target)
            self.write(self.source, name, previous)

    def test_missing_review_is_not_a_development_fallback(self):
        (self.trusted / release.MANIFEST).unlink()
        with self.assertRaises(PackageInputError):
            release.reviewed_inputs(self.source, self.trusted, self.target)

    def test_target_lock_rejects_multiple_hashes_options_duplicates_and_wrong_custom_hash(self):
        for bad in (self.lock + self.lock, self.lock + b"--extra-index-url https://example.invalid\n",
                    self.lock.rstrip() + b" --hash=sha256:" + b"2" * 64 + b"\n",
                    self.lock.replace(b"1" * 64, b"2" * 64)):
            with self.subTest(lock=bad):
                for root in (self.source, self.trusted):
                    self.write(root, release.lock_path(self.target), bad)
                with self.assertRaises(PackageInputError):
                    release.reviewed_inputs(self.source, self.trusted, self.target)

    def test_schema_two_binds_inventory_and_complete_file_set(self):
        self.runtime()
        result = release.validate_payload(self.payload, self.binding)
        self.assertIn("installed_inventory_sha256", result)
        self.write(self.payload, "unrecorded.dll", b"extra")
        with self.assertRaises(PackageInputError):
            release.validate_payload(self.payload, self.binding)

    def test_schema_one_wrong_target_and_changed_pin_are_refused(self):
        manifest = self.runtime()
        for key, value in (("schema", 1), ("target", "x86_64-pc-windows-msvc"),
                           ("requirements_sha256", "e" * 64),
                           ("wheel_manifest_sha256", "e" * 64),
                           ("installed_inventory_sha256", "e" * 64)):
            self.write(self.payload, "payload.json", encoded({**manifest, key: value}))
            with self.subTest(key=key), self.assertRaises(PackageInputError):
                release.validate_payload(self.payload, self.binding)

    def test_changed_missing_and_duplicate_inventory_files_are_refused(self):
        self.runtime()
        self.write(self.payload, "python/python.exe", b"modified executable!")
        with self.assertRaises(PackageInputError):
            release.validate_payload(self.payload, self.binding)
        (self.payload / "python/python.exe").unlink()
        with self.assertRaises(PackageInputError):
            release.validate_payload(self.payload, self.binding)

    def test_duplicate_json_and_unsafe_paths_are_refused(self):
        manifest = self.runtime()
        for content in (b'{"schema":1,"schema":1}',
                        encoded({"schema": 1, "target": self.target, "files": {
                            "../escape": {"size": 0, "sha256": sha(b"")}}})):
            self.write(self.payload, release.INVENTORY, content)
            self.write(self.payload, "payload.json", encoded({**manifest,
                       "installed_inventory_sha256": sha(content)}))
            with self.assertRaises(PackageInputError):
                release.validate_payload(self.payload, self.binding)

    def test_origin_resolves_real_run_jobs_and_artifacts_independently(self):
        run = {"id": 3, "head_sha": "a" * 40, "head_branch": "master",
               "event": "workflow_dispatch", "run_attempt": 1, "status": "completed",
               "conclusion": "success", "path": self.manifest["workflow"], "workflow_id": 2,
               "repository": {"full_name": "MONTBRAIN/vadgr", "id": 1}}
        replies = [run]
        for row in self.manifest["wheels"]:
            windows = row["target"] == "windows-aarch64"
            replies.extend([{"id": row["job_id"], "run_id": 3, "head_sha": "a" * 40,
                             "conclusion": "success", "status": "completed", "runner_group_name": "GitHub Actions",
                             "name": "build-windows" if windows else "build-macos",
                             "labels": ["windows-11-arm" if windows else "macos-15-intel"]},
                            {"id": row["artifact_id"], "expired": False,
                             "name": "native-wheel-" + row["target"],
                             "digest": row["artifact_digest"], "workflow_run": {
                                 "id": 3, "head_sha": "a" * 40, "head_branch": "master"}}])
        with patch.object(release, "github", side_effect=copy.deepcopy(replies)), \
             patch.object(release, "verify_attestation") as verify:
            release.verify_origin(self.trusted)
            verify.assert_called_once()
        for key, value in (("conclusion", "failure"), ("run_attempt", 2),
                           ("head_branch", "feature/evil"), ("head_sha", "b" * 40)):
            bad = copy.deepcopy(replies)
            bad[0][key] = value
            with self.subTest(key=key), patch.object(release, "github", side_effect=bad), \
                 patch.object(release, "verify_attestation"), self.assertRaises(PackageInputError):
                release.verify_origin(self.trusted)

    def test_attestation_command_enforces_exact_issuer_workflow_source_and_hosted_runner(self):
        from types import SimpleNamespace

        with patch.object(release, "read_owned", return_value=b"synthetic root"), \
             patch.object(release, "TRUSTED_ROOT_SHA256", sha(b"synthetic root")), \
             patch.object(release.subprocess, "run", return_value=SimpleNamespace(
                 returncode=0, stdout=b'[{"synthetic":true}]')) as command:
            release.verify_attestation(self.trusted, self.manifest)
        arguments = command.call_args.args[0]
        for flag, value in (("--signer-digest", "a" * 40), ("--source-digest", "a" * 40),
                            ("--source-ref", "refs/heads/master"),
                            ("--cert-oidc-issuer", "https://token.actions.githubusercontent.com")):
            self.assertEqual(arguments[arguments.index(flag) + 1], value)
        self.assertIn("--deny-self-hosted-runners", arguments)
        self.assertIn("--custom-trusted-root", arguments)

    def test_runtime_link_cannot_escape_inventory_root(self):
        self.runtime()
        executable = self.payload / "python/python.exe"
        outside = self.root / "outside.exe"
        outside.write_bytes(executable.read_bytes())
        executable.unlink()
        try:
            executable.symlink_to(outside)
        except OSError as error:
            if getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows symlink creation privilege absent")
            raise
        with self.assertRaises(PackageInputError):
            release.validate_payload(self.payload, self.binding)


if __name__ == "__main__":
    unittest.main()
