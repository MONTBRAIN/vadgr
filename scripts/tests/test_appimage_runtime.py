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


BUILDERS = ('scripts/candidate/build-native.sh', '.github/workflows/unsigned-linux-preparation.yml')


def test_builders_use_the_tracked_runtime_bytes():
    # The upstream "continuous" release replaces its assets, so a pinned asset
    # ID stopped resolving and every Linux build failed with HTTP 404. The
    # reviewed bytes are tracked beside the pin instead of downloaded.
    for path in BUILDERS:
        builder = (ROOT / path).read_text()
        assert 'type2-runtime/releases' not in builder, path
        assert 'packaging/appimage-runtime/runtime-' in builder, path
    native = (ROOT / 'scripts/candidate/build-native.sh').read_text()
    assert 'APPIMAGE_RUNTIME="$runtime"' in native
    assert native.index('verify_appimage_runtime.py') < native.index('APPIMAGE_RUNTIME="$runtime"')


def test_tracked_runtime_matches_its_pin():
    pins = json.loads((ROOT / 'packaging/linux/runtime.json').read_bytes())['targets']
    tracked = ROOT / 'packaging/appimage-runtime/runtime-x86_64'
    assert tracked.is_file() and not tracked.is_symlink()
    data = tracked.read_bytes()
    assert len(data) == pins['x86_64']['size']
    assert hashlib.sha256(data).hexdigest() == pins['x86_64']['sha256']


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
