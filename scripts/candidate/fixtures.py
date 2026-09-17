#!/usr/bin/env python3
"""Prepare isolated, credential-free inputs; never invoke the candidate tools."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--trusted-sha', required=True)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=False)
    record = {'repository': 'MONTBRAIN/vadgr', 'trusted_sha': args.trusted_sha,
              'run_id': 1, 'run_attempt': 1, 'files': {}}
    (args.root / 'authorization.json').write_text(json.dumps(record), encoding='utf-8')
    fixtures = {
        'traversal': [('../outside.txt', b'fixture')],
        'reserved': [('payload/lib/CON.txt', b'fixture')],
        'case': [('payload/lib/a.txt', b'a'), ('payload/lib/A.txt', b'A')],
    }
    for name, members in fixtures.items():
        with zipfile.ZipFile(args.root / f'{name}.zip', 'x') as archive:
            for path, value in members:
                archive.writestr(path, value)
    with zipfile.ZipFile(args.root / 'symlink.zip', 'x') as archive:
        link = zipfile.ZipInfo('payload/lib/link')
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        archive.writestr(link, '../outside.txt')
    value = (args.root / 'authorization.json').read_bytes()
    for name in ('record', 'extra'):
        with zipfile.ZipFile(args.root / f'{name}.zip', 'x') as archive:
            archive.writestr('authorization.json', value)
            if name == 'extra':
                archive.writestr('unexpected.json', b'{}')
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(args.root.iterdir())}
    (args.root / 'fixture-hashes.json').write_text(json.dumps(hashes, sort_keys=True), encoding='utf-8')
    print('Created isolated fixtures; no product command executed.')


if __name__ == '__main__':
    main()
