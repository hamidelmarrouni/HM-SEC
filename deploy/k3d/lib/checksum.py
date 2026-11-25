#!/usr/bin/env python3
"""Verify a release asset against a unique SHA256 entry, including _dist paths."""
import hashlib
from pathlib import Path
import re
import sys


def digest_file(asset):
    hasher = hashlib.sha256()
    with asset.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_raw(asset, checksum):
    expected = checksum.read_text().strip().lower()
    if not re.fullmatch('[a-f0-9]{64}', expected):
        raise ValueError('Release checksum is malformed.')
    digest = digest_file(asset)
    if digest != expected: raise ValueError('Release asset checksum does not match.')
    return digest


def verify_asset(asset, checksums):
    records = [line.split() for line in checksums.read_text().splitlines()]
    matches = [r[0].lower() for r in records if len(r)==2 and Path(r[1].lstrip('*')).name==asset.name]
    if len(matches)!=1 or not re.fullmatch('[a-f0-9]{64}', matches[0]):
        raise ValueError('Release checksum is missing, ambiguous or malformed.')
    digest = digest_file(asset)
    if digest != matches[0]: raise ValueError('Release asset checksum does not match.')
    return digest


if __name__ == '__main__':
    try:
        if sys.argv[1]=='--raw': verify_raw(Path(sys.argv[2]), Path(sys.argv[3]))
        else: verify_asset(Path(sys.argv[1]), Path(sys.argv[2]))
    except ValueError as error:
        raise SystemExit(str(error)+' Installation refused.')
