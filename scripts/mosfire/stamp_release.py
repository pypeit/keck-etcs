#!/usr/bin/env python
"""Stamp a calibration release tag into every ``index.yaml`` entry (plan S16/S23b; design 5.5, D28, D49).

Usage:
    conda run -n pypeit14b python scripts/mosfire/stamp_release.py mosfire-2026.10 [--dry-run]

The build scripts register their products in ``keck_etcs/data/index.yaml``
under a development tag (``<release>-dev``). At a release every entry must
carry the release tag (``scripts/check_docs.py`` check 3), except the
``provisional-*`` placeholders of band groups without a reduced standard
(S23a), which are not part of a release. This script sets
``calib_version`` on every non-provisional entry and leaves everything
else (``sha256``, ``created``, ``provenance``) as the build scripts wrote
it; the files themselves are not touched (``compute`` reads the tag from
the index). Prints the entries changed; ``--dry-run`` only prints.

Tag format: ``mosfire-YYYY.MM`` (one tag per release for all band groups,
D49; ``mosfire-J-YYYY.MM`` before S23b).
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
INDEX = REPO / 'keck_etcs' / 'data' / 'index.yaml'
TAG = re.compile(r'^mosfire-\d{4}\.\d{2}$')


def main(tag, dry_run=False):
    if not TAG.match(tag):
        print(f'{tag!r} is not a release tag of the form mosfire-YYYY.MM')
        return 2
    text = INDEX.read_text()
    index = yaml.safe_load(text) or {}
    changed, kept = [], []
    for path, entry in index.get('files', {}).items():
        old = str(entry.get('calib_version'))
        if old.startswith('provisional'):
            kept.append((path, old))
        elif old != tag:
            entry['calib_version'] = tag
            changed.append((path, old))
    for path, old in changed:
        print(f'  {path}: {old} -> {tag}')
    for path, old in kept:
        print(f'  {path}: {old} (placeholder, kept)')
    print(f'{len(changed)} entr(ies) stamped {tag}, {len(kept)} placeholder(s) kept'
          + (' (dry run, index.yaml not written)' if dry_run else ''))
    if changed and not dry_run:
        head = ''.join(ln for ln in text.splitlines(keepends=True) if ln.startswith('#'))
        INDEX.write_text(head + yaml.safe_dump(index, sort_keys=False, width=100))
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('tag')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    sys.exit(main(a.tag, a.dry_run))
