"""Credential lifetime and boundary checks without a real signing identity."""

import base64
import ctypes
import importlib.util
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "macos_signing_credentials.py"


@pytest.fixture
def signing():
    spec = importlib.util.spec_from_file_location("macos_signing_credentials", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner(tmp_path):
    return {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_REPOSITORY": "MONTBRAIN/vadgr",
        "GITHUB_EVENT_NAME": "push",
        "RUNNER_TEMP": str(tmp_path),
        "PATH": os.defpath,
        "MACOS_APPLICATION_SHA1": "A" * 40,
        "MACOS_INSTALLER_SHA1": "B" * 40,
        "MACOS_APPLICATION_P12_BASE64": base64.b64encode(b"application-fixture").decode(),
        "MACOS_APPLICATION_P12_PASSWORD": "application-fixture-password",
        "MACOS_INSTALLER_P12_BASE64": base64.b64encode(b"installer-fixture").decode(),
        "MACOS_INSTALLER_P12_PASSWORD": "installer-fixture-password",
        "MACOS_NOTARY_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----\n",  # secret-scan: allow-test-fixture
        "MACOS_NOTARY_KEY_ID": "TESTKEY123",
        "MACOS_NOTARY_ISSUER_ID": "00000000-0000-0000-0000-000000000001",
    }


class FakeSecurity:
    def __init__(self, fail=None):
        self.events = []
        self.fail = fail

    def snapshot(self):
        self.events.append("snapshot")
        return "original-search-and-default"

    def create(self, path, password):
        self.events.append("create")
        assert password and isinstance(password, bytes)
        self.path = path
        path.write_bytes(b"synthetic-keychain")
        return "temporary-keychain"

    def restrict_search(self, keychain):
        self.events.append("restrict")

    def import_identity(self, keychain, payload, password, keychain_password):
        self.events.append("import")
        if self.fail == "import":
            raise RuntimeError("sensitive backend detail")
        assert password.endswith("fixture-password")
        assert keychain_password
        return ("A" if payload == b"application-fixture" else "B") * 40

    def restore(self, snapshot):
        self.events.append("restore")
        assert snapshot == "original-search-and-default"
        if self.fail == "restore":
            raise RuntimeError("restore failed")

    def delete(self, keychain):
        self.events.append("delete")

    def close(self):
        self.events.append("close")


def test_platform_and_host_guard_precede_native_api(signing, runner, monkeypatch):
    monkeypatch.setattr(signing.sys, "platform", "linux")
    with pytest.raises(signing.SigningError, match="GitHub-hosted macOS"):
        signing.require_runner(runner)
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    for name, value in (("GITHUB_ACTIONS", "false"), ("RUNNER_ENVIRONMENT", "self-hosted"),
                        ("GITHUB_REPOSITORY", "someone/fork"), ("GITHUB_EVENT_NAME", "pull_request_target")):
        with pytest.raises(signing.SigningError):
            signing.require_runner({**runner, name: value})


def test_credentials_exist_only_during_command(signing, runner, monkeypatch):
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    backend = FakeSecurity()
    root = None
    with signing.Credentials(runner, backend) as child:
        root = Path(child["VADGR_NOTARY_KEY_FILE"]).parent
        assert root.stat().st_mode & 0o777 == 0o700
        assert Path(child["VADGR_NOTARY_KEY_FILE"]).stat().st_mode & 0o777 == 0o600
        assert child["APPLICATION_IDENTITY"] == "A" * 40
        assert child["INSTALLER_IDENTITY"] == "B" * 40
        assert not any(name in child for name in signing.SECRET_NAMES)
        assert "fixture-password" not in repr(child)
    assert not root.exists()
    assert backend.events[-3:] == ["restore", "delete", "close"]


@pytest.mark.parametrize("failure", ["import", "fingerprint", "command"])
def test_partial_failure_restores_and_removes_files(signing, runner, monkeypatch, failure):
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    backend = FakeSecurity(fail="import" if failure == "import" else None)
    if failure == "fingerprint":
        runner["MACOS_APPLICATION_SHA1"] = "C" * 40
    with pytest.raises((signing.SigningError, RuntimeError)):
        with signing.Credentials(runner, backend):
            raise RuntimeError("command failed")
    assert not list(Path(runner["RUNNER_TEMP"]).iterdir())
    assert backend.events[-3:] == ["restore", "delete", "close"]


def test_restore_failure_does_not_skip_key_deletion(signing, runner, monkeypatch):
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    backend = FakeSecurity(fail="restore")
    with pytest.raises(signing.SigningError, match="cleanup"):
        with signing.Credentials(runner, backend):
            pass
    assert "delete" in backend.events
    assert not list(Path(runner["RUNNER_TEMP"]).iterdir())


def test_bad_inputs_fail_before_keychain_creation(signing, runner, monkeypatch):
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    for name, value in (("MACOS_APPLICATION_P12_BASE64", "%%%"),
                        ("MACOS_INSTALLER_SHA1", ""), ("MACOS_NOTARY_KEY_ID", "bad\nvalue")):
        backend = FakeSecurity()
        with pytest.raises(signing.SigningError):
            with signing.Credentials({**runner, name: value}, backend):
                pass
        assert "create" not in backend.events


def test_child_argv_never_contains_credentials(signing, runner, monkeypatch):
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    backend = FakeSecurity()
    recorded = {}

    def popen(argv, **kwargs):
        recorded.update(argv=argv, **kwargs)
        from types import SimpleNamespace
        return SimpleNamespace(pid=47290, wait=lambda timeout=None: 7)

    def absent_group(*args):
        raise ProcessLookupError()

    monkeypatch.setattr(signing.subprocess, "Popen", popen)
    monkeypatch.setattr(signing.os, "killpg", absent_group)
    assert signing.run_command(["/bin/sh", "sign-package.sh"], runner, backend) == 7
    assert recorded["argv"] == ["/bin/sh", "sign-package.sh"]
    assert recorded["start_new_session"] is True
    for name in signing.SECRET_NAMES:
        assert name not in recorded["env"]
    assert not list(Path(runner["RUNNER_TEMP"]).iterdir())


def test_cli_error_does_not_print_environment_or_traceback(runner):
    process = subprocess.run([sys.executable, str(SCRIPT), "--", "/usr/bin/true"],
                             env={**runner, "RUNNER_ENVIRONMENT": "self-hosted"},
                             capture_output=True, text=True)
    assert process.returncode == 1
    assert "Traceback" not in process.stderr
    assert "fixture-password" not in process.stdout + process.stderr
    assert "GitHub-hosted macOS" in process.stderr


def test_a_secret_in_explicit_command_arguments_is_refused(signing, runner, monkeypatch):
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    backend = FakeSecurity()
    with pytest.raises(signing.SigningError, match="command argument"):
        signing.run_command(["tool", runner["MACOS_APPLICATION_P12_PASSWORD"]], runner, backend)
    assert not backend.events


def test_native_import_parameter_abi_matches_macos_64_bit(signing):
    assert ctypes.sizeof(signing.ImportParameters) == 56
    assert signing.ImportParameters.passphrase.offset == 8
    assert signing.ImportParameters.accessRef.offset == 32
    assert signing.ImportParameters.keyAttributes.offset == 48
    assert ctypes.sizeof(signing.KeychainSettings) == 12


def test_partition_acl_uses_native_password_buffer(signing, monkeypatch):
    calls = []
    strings = []
    backend = object.__new__(signing.NativeSecurity)
    backend.refs = []
    backend.copied = lambda *args: 100
    backend.retain_result = lambda value: value
    backend.values = lambda array: [200]
    backend.string = lambda value: strings.append(value) or 300

    class PointerType:
        def __new__(cls):
            return ctypes.c_void_p()

        @staticmethod
        def in_dll(_library, _name):
            return ctypes.c_void_p(400)

    class Security:
        @staticmethod
        def SecAccessCopyMatchingACLList(*args):
            return 500

        @staticmethod
        def SecACLCopyContents(*args):
            return 0

        @staticmethod
        def SecACLSetContents(*args):
            calls.append(("acl", args))
            return 0

        @staticmethod
        def SecKeychainItemSetAccessWithPassword(*args):
            calls.append(("password", args))
            return 0

    backend.sec = Security()
    # Substitute only this module's ctypes namespace; do not alter global ctypes.
    from types import SimpleNamespace
    monkeypatch.setattr(signing, "C", SimpleNamespace(c_void_p=PointerType,
                                                     c_uint32=ctypes.c_uint32,
                                                     byref=ctypes.byref))
    backend.set_partitions(42, b"synthetic-keychain-password")
    assert plistlib.loads(bytes.fromhex(strings[0])) == {"Partitions": ["apple-tool:", "apple:"]}
    assert calls[-1] == ("password", (42, 100, 27, b"synthetic-keychain-password"))


def test_missing_partition_acl_fails_closed(signing, monkeypatch):
    backend = object.__new__(signing.NativeSecurity)
    backend.copied = lambda *args: 100
    backend.retain_result = lambda value: value
    backend.values = lambda array: []
    from types import SimpleNamespace
    backend.sec = SimpleNamespace(SecAccessCopyMatchingACLList=lambda *args: 200)
    pointer = SimpleNamespace(in_dll=lambda *args: SimpleNamespace(value=300))
    monkeypatch.setattr(signing, "C", SimpleNamespace(c_void_p=pointer))
    with pytest.raises(signing.SigningError, match="no partition ACL"):
        backend.set_partitions(42, b"synthetic-password")


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, RuntimeError])
def test_interrupted_child_group_stops_before_credentials_are_removed(
        signing, runner, monkeypatch, interruption):
    monkeypatch.setattr(signing.sys, "platform", "darwin")
    backend = FakeSecurity()
    group = {"alive": True}
    recorded = {}

    class Process:
        pid = 47291
        calls = 0

        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise interruption("interrupted")
            backend.events.append("reaped")
            return -signal.SIGTERM

        def poll(self):
            return None

    def popen(argv, **kwargs):
        recorded.update(kwargs)
        return Process()

    def killpg(pid, number):
        assert pid == Process.pid
        if not group["alive"]:
            raise ProcessLookupError()
        if number == signal.SIGTERM:
            backend.events.append("stopped-group")
            group["alive"] = False

    def old_run(*args, **kwargs):
        raise interruption("interrupted")

    monkeypatch.setattr(signing.subprocess, "run", old_run)
    monkeypatch.setattr(signing.subprocess, "Popen", popen)
    monkeypatch.setattr(signing.os, "killpg", killpg)
    with pytest.raises(interruption):
        signing.run_command(["/bin/sh", "sign-package.sh"], runner, backend)
    assert "stopped-group" in backend.events
    assert recorded["start_new_session"] is True
    assert backend.events.index("stopped-group") < backend.events.index("delete")
    assert backend.events.index("reaped") < backend.events.index("delete")


def test_unresponsive_descendants_are_killed_after_the_grace_period(signing, monkeypatch):
    calls = []
    ticks = iter([0.0, 6.0])
    from types import SimpleNamespace
    process = SimpleNamespace(pid=47292, poll=lambda: 0,
                              wait=lambda timeout: calls.append(("wait", timeout)))
    monkeypatch.setattr(signing.os, "killpg", lambda pid, number: calls.append((pid, number)))
    clock = SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda seconds: None)
    monkeypatch.setattr(signing, "time", clock, raising=False)
    signing.stop_owned_group(process)
    assert calls == [(47292, signal.SIGTERM), (47292, signal.SIGKILL), ("wait", 5)]
