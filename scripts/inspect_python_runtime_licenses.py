#!/usr/bin/env python3
"""Bind producer license metadata to the exact pinned install-only Python bytes.

This is source evidence, not a license conclusion or package approval. The full
producer archive can include libraries and build inputs absent from the payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tomllib

if __package__:
    from scripts.validate_package_inputs import canonical_json, relative_path, require
else:
    from validate_package_inputs import canonical_json, relative_path, require


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect_members(archive, prefix, retain=False):
    files, retained, seen = {}, {}, set()
    for member in archive:
        name = member.name.rstrip('/')
        relative_path(name)
        require(name not in seen, 'duplicate archive member')
        seen.add(name)
        if member.isdir():
            continue
        require(member.isfile() or member.issym(), 'unsupported archive member')
        if member.name.startswith(prefix):
            relative = member.name[len(prefix):]
            require(bool(relative), 'invalid archive root')
            if member.isfile():
                value = hashlib.file_digest(archive.extractfile(member), 'sha256').hexdigest()
                files[relative] = {'kind': 'file', 'mode': member.mode,
                                   'size': member.size, 'sha256': value}
            else:
                require(not member.linkname.startswith('/'), 'absolute archive link')
                files[relative] = {'kind': 'symlink', 'mode': member.mode,
                                   'target': member.linkname}
        elif retain and (name == 'python/PYTHON.json' or name.startswith('python/licenses/')):
            require(member.isfile() and member.size <= 8 * 1024 * 1024,
                    'invalid producer legal member')
            retained[name] = archive.extractfile(member).read()
    return files, retained


def compare(install, full):
    require(bool(install), 'empty install archive')
    require(all(full.get(name) == value for name, value in install.items()),
            'producer install bytes differ from pinned archive')
    return {'install_members': len(install), 'producer_install_members': len(full),
            'extra_producer_members': len(set(full) - set(install)),
            'install_only_is_exact_subset': True}


def inspect(install, full, pins_path, target, full_sha256, output):
    require(not output.exists() and output.parent.is_dir(), 'output must be new')
    pins = tomllib.loads(pins_path.read_text())
    require(target in pins['targets'] and target.endswith(('unknown-linux-gnu', 'apple-darwin')),
            'unsupported native target')
    require(digest(install) == pins['targets'][target]['python_sha256'], 'install digest differs')
    require(digest(full) == full_sha256, 'producer digest differs')
    with tarfile.open(install, 'r:gz') as archive:
        installed, _ = inspect_members(archive, 'python/')
    process = subprocess.Popen(['zstd', '-dc', str(full)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            produced, retained = inspect_members(archive, 'python/install/', retain=True)
        require(process.wait() == 0, 'producer decompression failed')
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()
    comparison = compare(installed, produced)
    metadata = json.loads(retained['python/PYTHON.json'])
    require(metadata['target_triple'] == target and metadata['python_version'] == pins['python'],
            'producer Python identity differs')
    report = {'schema': 1, 'status': 'source-evidence-not-approval',
              'development': True, 'publishable': False, 'legal_approval': False,
              'target': target, 'python_version': pins['python'], 'python_build': pins['python_build'],
              'install_sha256': digest(install), 'producer_sha256': full_sha256,
              **comparison, 'retained_files': {name: hashlib.sha256(raw).hexdigest()
                                              for name, raw in sorted(retained.items())},
              'limitation': 'Producer metadata is not the shipped-component scope or a redistribution approval.'}
    output.mkdir(mode=0o700)
    for name, raw in sorted(retained.items()):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
    with (output / 'observation.json').open('xb') as stream:
        stream.write(canonical_json(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'full', 'pins', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--full-sha256', required=True)
    args = parser.parse_args()
    report = inspect(args.install, args.full, args.pins, args.target, args.full_sha256, args.output)
    print(json.dumps({key: value for key, value in report.items() if key != 'retained_files'}, indent=2))


if __name__ == '__main__':
    main()
