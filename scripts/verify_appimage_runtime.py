#!/usr/bin/env python3
"""Verify the explicit AppImage runtime before a package builder can consume it."""

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from scripts.distribution_matrix import verify_binary
    from scripts.validate_package_inputs import require
else:
    from distribution_matrix import verify_binary
    from validate_package_inputs import require


def verify(runtime, pins, architecture):
    require(architecture in ('x86_64', 'aarch64'), 'unsupported AppImage architecture')
    row = json.loads(pins.read_bytes())['targets'][architecture]
    require(runtime.is_file() and not runtime.is_symlink(), 'AppImage runtime must be a regular file')
    require(runtime.stat().st_size == row['size'], 'AppImage runtime size differs')
    with runtime.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(actual == row['sha256'], 'AppImage runtime digest differs')
    verify_binary(runtime, 'linux-' + architecture)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--pins', type=Path, required=True)
    parser.add_argument('--architecture', required=True)
    args = parser.parse_args()
    verify(args.runtime, args.pins, args.architecture)
    print('Exact AppImage runtime bytes and architecture verified.')


if __name__ == '__main__':
    main()
