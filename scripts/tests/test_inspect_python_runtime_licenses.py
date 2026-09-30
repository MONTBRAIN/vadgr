"""Native runtime license metadata must bind exact pinned install bytes."""

import io
import tarfile

import pytest

from scripts import inspect_python_runtime_licenses as inspection
from scripts.validate_package_inputs import PackageInputError


def members(entries, prefix='python/'):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, value in entries:
            info = tarfile.TarInfo(name)
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))
    stream.seek(0)
    with tarfile.open(fileobj=stream) as archive:
        return inspection.inspect_members(archive, prefix, retain=True)


def test_extra_full_build_members_do_not_change_exact_install_subset():
    installed, _ = members([('python/lib/python.so', b'exact')])
    produced, _ = members([('python/install/lib/python.so', b'exact'),
                           ('python/install/tests/fixture', b'not shipped')], 'python/install/')
    assert inspection.compare(installed, produced)['extra_producer_members'] == 1


@pytest.mark.parametrize('difference', ['sha256', 'mode', 'size', 'target'])
def test_changed_install_member_is_rejected(difference):
    record = {'kind': 'file', 'sha256': 'a' * 64, 'mode': 0o755, 'size': 9}
    changed = dict(record, **{difference: 'different'})
    with pytest.raises(PackageInputError, match='bytes differ'):
        inspection.compare({'python': record}, {'python': changed})


def test_missing_or_empty_install_is_rejected():
    for install, full in [({}, {}), ({'python': {}}, {})]:
        with pytest.raises(PackageInputError):
            inspection.compare(install, full)


def test_producer_notices_are_retained_verbatim_and_separate_from_install():
    files, retained = members([('python/PYTHON.json', b'{}'),
                              ('python/licenses/LICENSE.bdb.txt', b'exact\r\nterms'),
                              ('python/install/python', b'binary')], 'python/install/')
    assert set(files) == {'python'}
    assert retained['python/licenses/LICENSE.bdb.txt'] == b'exact\r\nterms'


@pytest.mark.parametrize('names', [('../LICENSE',), ('python/a', 'python/a')])
def test_unsafe_or_duplicate_archive_paths_are_rejected(names):
    with pytest.raises(PackageInputError):
        members([(name, b'x') for name in names])
