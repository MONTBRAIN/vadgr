"""A newer workstation libc must not silently raise the package baseline."""

import inspect
from pathlib import Path

import pytest

from scripts import prepare_unsigned_linux as preparation
from scripts.validate_package_inputs import PackageInputError


ROOT = Path(__file__).resolve().parents[2]


def test_packaging_checks_the_registered_linux_abi():
    assert 'require_release_abi' in inspect.getsource(preparation.package)


def test_newer_glibc_requirements_are_not_release_equivalent(monkeypatch, tmp_path):
    monkeypatch.setattr(preparation.subprocess, 'check_output',
                        lambda *args, **kwargs: 'Name: GLIBC_2.34\nName: GLIBC_2.43\n')
    with pytest.raises(PackageInputError, match='registered Linux producer baseline'):
        preparation.require_release_abi(tmp_path / 'binary')


def test_numeric_abi_comparison_and_supported_relocations(monkeypatch, tmp_path):
    monkeypatch.setattr(preparation.subprocess, 'check_output',
                        lambda *args, **kwargs: 'Name: GLIBC_2.9\nName: GLIBC_2.39\nName: GLIBC_ABI_DT_RELR\n')
    assert preparation.require_release_abi(tmp_path / 'binary')['maximum_glibc'] == '2.39'


def test_unsigned_linux_workflow_uses_native_registered_runner_and_no_signing():
    workflow = (ROOT / '.github/workflows/unsigned-linux-preparation.yml').read_text()
    assert 'runs-on: ubuntu-24.04' in workflow
    assert 'persist-credentials: false' in workflow
    assert 'toolchain: 1.97.1' in workflow
    assert 'prepare_unsigned_linux.py prepare' in workflow
    assert 'prepare_unsigned_linux.py package' in workflow
    assert 'unsigned-linux-x86_64-development-' in workflow
    assert 'id-token: write' not in workflow
    assert 'secrets.' not in workflow
    assert 'environment:' not in workflow
