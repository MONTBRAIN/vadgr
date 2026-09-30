"""Synthetic path-package identities cannot bypass source or grant checks."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rust_path_patches as patches
import validate_package_inputs as package

REPO = Path(__file__).resolve().parents[2]


def fixture(root):
    registry = {"schema": 1, "patches": []}
    cargo = '[package]\nname="vadgr"\nversion="0.5.0"\n[patch.crates-io]\n'
    lock = 'version = 4\n'
    for name, (version, checksum) in patches.BASES.items():
        directory = f"vendor/{name}-{version}"
        cargo += f'{name} = {{ path = "{directory}" }}\n'
        lock += f'[[package]]\nname="{name}"\nversion="{version}"\n'
        crate = root / directory
        crate.mkdir(parents=True)
        (crate / "Cargo.toml").write_text(f'[package]\nname="{name}"\nversion="{version}"\nlicense="MIT OR Apache-2.0"\n')
        (crate / "PATCHES.md").write_text("Synthetic test source, not a redistribution approval.\n")
        (crate / "lib.rs").write_text("pub fn example() {}\n")
        upstream = REPO / 'packaging/inputs/linux-x86_64/legal/NOTICES/cargo-accesskit-atspi-common-0.18.1'
        for filename in patches.LICENSE_HASHES:
            match = next(upstream.glob('*-' + filename))
            (crate / filename).write_bytes(match.read_bytes())
        rows = []
        for path in sorted(crate.iterdir()):
            path.chmod(0o644)
            raw = path.read_bytes()
            rows.append({"path": path.name, "mode": 0o644, "bytes": len(raw), "sha256": patches.digest(raw)})
        manifest = f"packaging/rust-patches/{name}-{version}.json"
        raw = patches.canonical({"schema": 1, "name": name, "version": version, "files": rows})
        output = root / manifest; output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(raw)
        registry["patches"].append({"name": name, "version": version, "path": directory,
            "manifest": manifest, "manifest_sha256": patches.digest(raw),
            "upstream_archive_sha256": checksum,
            "upstream_archive_url": f"https://static.crates.io/crates/{name}/{name}-{version}.crate"})
    (root / "Cargo.toml").write_text(cargo)
    (root / "Cargo.lock").write_text(lock)
    (root / patches.REGISTRY).write_bytes(patches.canonical(registry))
    return registry


def test_complete_registered_patches_and_crlf(tmp_path):
    fixture(tmp_path)
    assert set(patches.load(tmp_path)) == set(patches.BASES)
    path = tmp_path / 'vendor/accesskit_unix-0.21.1/lib.rs'
    path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    assert len(patches.load(tmp_path)) == 2


@pytest.mark.parametrize('change', ['changed', 'extra', 'missing', 'mode', 'license', 'registry', 'lock'])
def test_unbound_changes_fail(tmp_path, change):
    registry = fixture(tmp_path)
    crate = tmp_path / 'vendor/accesskit_unix-0.21.1'
    if change == 'changed': (crate / 'lib.rs').write_text('changed\n')
    elif change == 'extra': (crate / 'extra').write_text('extra\n')
    elif change == 'missing': (crate / 'lib.rs').unlink()
    elif change == 'mode':
        if patches.os.name == 'nt': pytest.skip('POSIX executable mode')
        (crate / 'lib.rs').chmod(0o755)
    elif change == 'license': (crate / 'LICENSE-MIT').write_text('changed grant\n')
    elif change == 'registry':
        registry['patches'][0]['upstream_archive_sha256'] = '0' * 64
        (tmp_path / patches.REGISTRY).write_bytes(patches.canonical(registry))
    elif change == 'lock':
        path = tmp_path / 'Cargo.lock'
        path.write_text(path.read_text() + 'checksum="' + '0' * 64 + '"\n')
    with pytest.raises((ValueError, OSError)): patches.load(tmp_path)


def test_unknown_override_and_missing_binding_fail(tmp_path):
    fixture(tmp_path)
    path = tmp_path / 'Cargo.toml'
    path.write_text(path.read_text() + 'unknown = { path = "vendor/unknown" }\n')
    with pytest.raises(ValueError, match='unregistered'): patches.load(tmp_path)


def test_unknown_local_metadata_and_wrong_path_fail(tmp_path):
    fixture(tmp_path); bound = patches.load(tmp_path)
    row = {'name': 'accesskit_unix', 'version': '0.21.1', 'source': None,
           'manifest_path': str(tmp_path / 'vendor/accesskit_unix-0.21.1/Cargo.toml')}
    assert patches.component(tmp_path, row, bound)['name'] == row['name']
    with pytest.raises(ValueError): patches.component(tmp_path, {**row, 'name': 'unknown'}, bound)
    with pytest.raises(ValueError): patches.component(tmp_path, {**row, 'manifest_path': str(tmp_path / 'elsewhere')}, bound)


def test_uncommitted_or_wrong_manifest_location_refused(tmp_path, monkeypatch):
    fixture(tmp_path); item = patches.load(tmp_path)['accesskit_unix']
    monkeypatch.setattr(patches.subprocess, 'check_output', lambda *a, **k: b'wrong')
    url = 'https://raw.githubusercontent.com/MONTBRAIN/vadgr/' + 'a' * 40 + '/' + item['manifest']
    with pytest.raises(ValueError, match='URL bytes'): patches.verify_location(tmp_path, item, url)
    with pytest.raises(ValueError, match='location'): patches.verify_location(tmp_path, item, 'https://example.com/source')


def test_symlinked_source_refused(tmp_path):
    fixture(tmp_path)
    path = tmp_path / 'vendor/accesskit_unix-0.21.1/lib.rs'
    other = tmp_path / 'outside.rs'; other.write_bytes(path.read_bytes()); path.unlink()
    try: path.symlink_to(other)
    except OSError: pytest.skip('symlink privilege unavailable')
    with pytest.raises(ValueError, match='linked'): patches.load(tmp_path)


def inventory(root):
    bound = patches.load(root)
    return {'target': 'x86_64-unknown-linux-gnu',
        'source_inputs': {n: patches.digest(patches.read(root, n)) for n in patches.SOURCE_INPUTS},
        'components': [{'name': name, 'version': row['version'], 'kind': 'cargo',
                        'sha256': row['manifest_sha256'],
                        'download_location': 'https://raw.githubusercontent.com/MONTBRAIN/vadgr/' + 'a' * 40 + '/' + row['manifest'],
                        'license_declared': 'MIT OR Apache-2.0',
                        'license_concluded': patches.CONCLUSIONS[name]} for name, row in bound.items()]}


@pytest.mark.parametrize('change', ['missing-binding', 'stale-registry', 'old-archive', 'grant', 'windows-leak', 'mutable-url'])
def test_package_patch_binding_rejects_stale_inventory(tmp_path, monkeypatch, change):
    fixture(tmp_path); value = inventory(tmp_path)
    monkeypatch.setattr(patches, 'verify_location', lambda *args: None)
    package.validate_patched_sources(tmp_path, value)
    if change == 'missing-binding': value['source_inputs'].pop(patches.REGISTRY)
    elif change == 'stale-registry': value['source_inputs'][patches.REGISTRY] = '0' * 64
    elif change == 'old-archive': value['components'][0]['sha256'] = next(iter(patches.BASES.values()))[1]
    elif change == 'grant': value['components'][0]['license_concluded'] = 'MIT'
    elif change == 'windows-leak': value['target'] = 'x86_64-pc-windows-msvc'
    elif change == 'mutable-url': value['components'][0]['download_location'] = 'https://example.com/main/source'
    with pytest.raises(package.PackageInputError): package.validate_patched_sources(tmp_path, value)


def test_windows_binding_does_not_promote_linux_crates(tmp_path):
    fixture(tmp_path); value = inventory(tmp_path)
    value.update(target='x86_64-pc-windows-msvc', components=[])
    package.validate_patched_sources(tmp_path, value)


@pytest.mark.parametrize('architecture', ['x86_64', 'aarch64'])
def test_wsl_profile_omits_gui_patches_but_rejects_leakage(tmp_path, architecture):
    fixture(tmp_path); value = inventory(tmp_path)
    value['target'] = architecture + '-unknown-linux-gnu'
    value['source_inputs'].update({n: '0' * 64 for n in package.profile_source_inputs('wsl-' + architecture)})
    leaked = value['components']
    value['components'] = []
    package.validate_patched_sources(tmp_path, value)
    value['components'] = leaked
    with pytest.raises(package.PackageInputError):
        package.validate_patched_sources(tmp_path, value)


@pytest.mark.parametrize('checkout', ['source-only', 'shallow'])
def test_current_source_validation_does_not_require_historical_git_objects(tmp_path, monkeypatch, checkout):
    fixture(tmp_path); value = inventory(tmp_path)
    if checkout == 'shallow':
        (tmp_path / '.git').mkdir()
        (tmp_path / '.git/shallow').write_text('fixture without historical objects\n')
    def unavailable(*args, **kwargs):
        raise patches.subprocess.CalledProcessError(128, ['git', 'show'])
    monkeypatch.setattr(patches.subprocess, 'check_output', unavailable)
    package.validate_patched_sources(tmp_path, value)
    patch = patches.load(tmp_path)['accesskit_atspi_common']
    with pytest.raises(ValueError, match='commit unavailable'):
        patches.verify_location(tmp_path, patch, value['components'][0]['download_location'])
    source = tmp_path / 'vendor/accesskit_unix-0.21.1/lib.rs'
    source.write_text('changed after inventory binding\n')
    with pytest.raises(package.PackageInputError, match='source binding'):
        package.validate_patched_sources(tmp_path, value)


def test_profile_inputs_accept_only_complete_patch_binding():
    base = package.profile_source_inputs('linux-x86_64')
    assert package.profile_from_inputs(base | patches.SOURCE_INPUTS, 'x86_64-unknown-linux-gnu') == 'linux-x86_64'
    assert package.profile_from_inputs(base | {patches.REGISTRY}, 'x86_64-unknown-linux-gnu') is None


def test_collector_keeps_registered_local_dependencies_and_rejects_unknown(tmp_path, monkeypatch):
    import collect_legal_sources as collect
    fixture(tmp_path)
    rows = [{'id': 'root', 'name': 'vadgr', 'version': '0.5.0', 'source': None}]
    for name, (version, _) in patches.BASES.items():
        rows.append({'id': name, 'name': name, 'version': version, 'source': None,
                     'license': 'MIT OR Apache-2.0',
                     'manifest_path': str(tmp_path / f'vendor/{name}-{version}/Cargo.toml')})
    metadata = {'packages': rows, 'resolve': {'root': 'root', 'nodes': [
        {'id': 'root', 'deps': [{'pkg': r['id'], 'dep_kinds': [{'kind': None}]} for r in rows[1:]]},
        *[{'id': r['id'], 'deps': []} for r in rows[1:]]]}}
    monkeypatch.setattr(collect.subprocess, 'check_output', lambda *a, **k: patches.canonical(metadata))
    monkeypatch.setattr(patches, 'location', lambda *a: 'https://example.com/exact-manifest')
    result = collect.cargo_components(tmp_path, tmp_path / 'collected', tmp_path / 'cache', 'x86_64-unknown-linux-gnu')
    assert {r['name'] for r in result} == set(patches.BASES)
    assert all(r['source_kind'] == 'reviewed-path-patch' for r in result)
    assert all(any(s['upstream_path'] == 'patched-source-manifest.json' for s in r['source_files']) for r in result)
    rows[1]['name'] = 'unknown'
    with pytest.raises(ValueError, match='unbound local'):
        collect.cargo_components(tmp_path, tmp_path / 'rejected', tmp_path / 'cache', 'x86_64-unknown-linux-gnu')
