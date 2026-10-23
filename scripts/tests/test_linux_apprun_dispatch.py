"""Exercise the shipped shell dispatcher with an inert executable, not a GUI."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux AppRun contract')


@pytest.fixture
def dispatch(tmp_path):
    appdir = tmp_path / 'mounted AppDir'
    binary = appdir / 'usr/bin/vadgr'
    binary.parent.mkdir(parents=True)
    calls = tmp_path / 'calls.jsonl'
    binary.write_text(f'#!{sys.executable}\n' + '''import json, os, pathlib, sys
root = os.environ.get('VADGR_INSTALL_ROOT')
receipt = pathlib.Path(root) / 'install-receipt.json' if root else pathlib.Path(__file__).parent / 'install-receipt.json'
record = {'argv': sys.argv[1:], 'install_root': root,
          'appdir': os.environ.get('VADGR_APPDIR'),
          'receipt': json.loads(receipt.read_text()) if receipt.exists() else None}
with open(os.environ['TEST_CALLS'], 'a') as stream:
    stream.write(json.dumps(record) + '\\n')
sys.exit(int(os.environ.get('TEST_EXIT', '0')))
''')
    binary.chmod(0o755)
    apprun = appdir / 'AppRun'
    shutil.copyfile(ROOT / 'packaging/linux/AppRun', apprun)
    install = tmp_path / 'installed release'
    install.mkdir()
    vehicle = install / 'Vadgr.AppImage'
    vehicle.write_bytes(b'inert vehicle fixture')
    (install / 'install-receipt.json').write_text(json.dumps({'fixture': 'installed'}))
    (binary.parent / 'install-receipt.json').write_text(json.dumps({'fixture': 'wrong-mounted-root'}))
    bindir = tmp_path / 'public bin'
    bindir.mkdir()
    shim = bindir / 'vadgr'
    shim.symlink_to(vehicle)

    def run(args, *, public=True, extra=None):
        if calls.exists():
            calls.unlink()
        env = {'PATH': os.defpath, 'APPDIR': str(appdir),
               'APPIMAGE': str(shim if public else vehicle),
               'ARGV0': str(shim if public else vehicle), 'TEST_CALLS': str(calls)}
        if 'HOME' in os.environ:
            env['HOME'] = os.environ['HOME']
        env.update(extra or {})
        result = subprocess.run(['/bin/sh', str(apprun), *args], env=env,
                                cwd=tmp_path, capture_output=True, text=True, timeout=10)
        records = [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        return result, records

    return run, install, appdir, vehicle


@pytest.mark.parametrize('args', [[], ['update', '--check'], ['--version'],
                                 ['machine', 'set', 'a name', '', '*', '--literal']])
def test_installed_shim_preserves_cli_arguments_and_selects_installed_receipt(dispatch, args):
    run, install, appdir, _ = dispatch
    result, calls = run(args)
    assert result.returncode == 0, result.stderr
    assert calls == [{'argv': args, 'install_root': str(install),
                      'appdir': str(appdir), 'receipt': {'fixture': 'installed'}}]


def test_installed_shim_overrides_stale_install_root_and_preserves_exit(dispatch):
    run, install, _, _ = dispatch
    result, calls = run(['update', '--check'], extra={'VADGR_INSTALL_ROOT': '/stale', 'TEST_EXIT': '23'})
    assert result.returncode == 23
    assert calls[0]['install_root'] == str(install)
    assert calls[0]['receipt'] == {'fixture': 'installed'}


def test_direct_vehicle_without_arguments_still_opens_installer(dispatch):
    run, _, _, vehicle = dispatch
    result, calls = run([], public=False)
    assert result.returncode == 0
    assert calls[0]['argv'] == ['--installer', '--vehicle', str(vehicle)]
    assert calls[0]['install_root'] is None


@pytest.mark.parametrize('args', [['update', '--check'], ['status'], ['--daemon']])
def test_direct_vehicle_named_commands_keep_installed_root(dispatch, args):
    run, install, _, _ = dispatch
    result, calls = run(args, public=False)
    assert result.returncode == 0
    assert calls[0]['argv'] == args
    assert calls[0]['install_root'] == str(install)


def test_direct_console_starts_daemon_then_console(dispatch):
    run, install, _, _ = dispatch
    result, calls = run(['--console'], public=False)
    assert result.returncode == 0
    assert [c['argv'] for c in calls] == [['start'], ['--console']]
    assert all(c['install_root'] == str(install) for c in calls)


@pytest.mark.parametrize('key', ['APPDIR', 'APPIMAGE'])
def test_missing_runtime_context_refuses_before_dispatch(dispatch, key):
    run, _, _, _ = dispatch
    result, calls = run(['update', '--check'], extra={key: ''})
    assert result.returncode == 1
    assert 'AppImage runtime' in result.stderr
    assert calls == []
