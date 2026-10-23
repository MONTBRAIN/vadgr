"""AppImage generation must not fetch an untracked runtime implicitly."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import verify_appimage_runtime as runtime
from scripts.validate_package_inputs import PackageInputError


ROOT = Path(__file__).resolve().parents[2]


def test_linux_builder_requires_pinned_explicit_runtime():
    builder = (ROOT / 'packaging/linux/build.sh').read_text()
    assert 'verify_appimage_runtime.py' in builder
    assert '--runtime-file "$runtime"' in builder
    assert builder.index('verify_appimage_runtime.py') < builder.index('cargo build')


def test_candidate_fetches_immutable_runtime_asset():
    builder = (ROOT / 'scripts/candidate/build-native.sh').read_text()
    assert 'packaging/linux/runtime.json' in builder
    assert 'type2-runtime/releases/assets/$runtime_id' in builder
    assert 'APPIMAGE_RUNTIME="$runtime"' in builder


def test_runtime_digest_and_architecture_are_checked(tmp_path, monkeypatch):
    binary = tmp_path / 'runtime'
    binary.write_bytes(b'fixture')
    pins = tmp_path / 'pins.json'
    pins.write_text(json.dumps({'targets': {'x86_64': {
        'size': 7, 'sha256': hashlib.sha256(b'fixture').hexdigest()}}}))
    calls = []
    monkeypatch.setattr(runtime, 'verify_binary', lambda *args: calls.append(args))
    runtime.verify(binary, pins, 'x86_64')
    assert calls == [(binary, 'linux-x86_64')]
    binary.write_bytes(b'changed')
    with pytest.raises(PackageInputError, match='digest differs'):
        runtime.verify(binary, pins, 'x86_64')
    assert len(calls) == 1


def test_wrong_size_is_rejected_before_binary_inspection(tmp_path):
    binary = tmp_path / 'runtime'
    binary.write_bytes(b'fixture')
    pins = tmp_path / 'pins.json'
    pins.write_text(json.dumps({'targets': {'x86_64': {'size': 8, 'sha256': 'a' * 64}}}))
    with pytest.raises(PackageInputError, match='size differs'):
        runtime.verify(binary, pins, 'x86_64')
