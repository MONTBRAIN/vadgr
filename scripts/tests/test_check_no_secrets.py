"""Tests for the credential gate, and for the Windows control it could not run."""

import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "check_no_secrets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_no_secrets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check():
    return load_module()


def test_windows_acl_check_receives_its_target(check, monkeypatch, tmp_path):
    """The target must reach PowerShell, which a trailing -Command argument never did.

    This is the regression for a gate that refused every file on Windows: $args
    is empty under -Command, so the check read no path and always failed closed.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=placeholder-not-a-credential\n")
    recorded = {}

    def fake_run(argv, **kwargs):
        recorded["argv"] = list(argv)
        recorded["env"] = kwargs.get("env") or {}
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(check.os, "name", "nt")
    monkeypatch.setattr(check.subprocess, "run", fake_run)

    check.load_local_secrets(env_file)

    assert recorded["env"][check.WINDOWS_ACL_TARGET_VAR] == str(env_file)
    # The path as a trailing token is the defect itself: PowerShell appends it to
    # the command text rather than binding it, so it must not be there.
    assert str(env_file) not in recorded["argv"]


def test_windows_acl_script_reads_the_environment(check):
    assert "$env:VADGR_ACL_TARGET" in check.WINDOWS_ACL_CHECK
    assert "$args" not in check.WINDOWS_ACL_CHECK


def run_acl_check(check, path):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", check.WINDOWS_ACL_CHECK],
        env={**os.environ, check.WINDOWS_ACL_TARGET_VAR: str(path)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


@pytest.mark.skipif(os.name != "nt", reason="the DACL control only exists on Windows")
def test_owner_only_file_is_accepted_and_a_broad_ace_is_refused(check, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=placeholder-not-a-credential\n")
    account = os.environ["USERDOMAIN"] + "\\" + os.environ["USERNAME"]

    subprocess.run(
        ["icacls", str(env_file), "/inheritance:r", "/grant:r", account + ":(F)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    assert run_acl_check(check, env_file) == 0

    # S-1-5-11 is Authenticated Users, one of the three broad SIDs the gate names.
    subprocess.run(
        ["icacls", str(env_file), "/grant", "*S-1-5-11:(R)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    assert run_acl_check(check, env_file) != 0


@pytest.mark.skipif(os.name != "nt", reason="the DACL control only exists on Windows")
def test_missing_target_fails_closed(check):
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", check.WINDOWS_ACL_CHECK],
        env={k: v for k, v in os.environ.items() if k != check.WINDOWS_ACL_TARGET_VAR},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert result.returncode == 1
