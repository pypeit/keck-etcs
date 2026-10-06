#!/usr/bin/env python
"""Check the raw frames on S3 against each night's raw/manifest.ecsv (KOA prompts 2-3).

Usage:
    conda run -n pypeit14b python scripts/koa/verify_raw_on_s3.py nautilus/manifests/nights_batch1.csv [...]

For every night of the given manifests: pulls ``mosfire/<night>/raw/manifest.ecsv``
from the bucket into a scratch directory, lists the bucket objects under
``mosfire/<night>/raw/`` (``s3_sync.py ls``), and reports the frames per type,
the total size, and any frame whose bucket size differs from the manifest or
is missing. Every night must have a standard and dome flats; a night whose
manifest row has ``spec2d = 1`` (validation, KOA prompt 3) must also have
``science`` frames. Exit 1 on any problem. Read-only on the bucket.
"""
import csv
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from astropy.table import Table

REPO = Path(__file__).resolve().parents[2]
S3_SYNC = REPO / 'scripts' / 'nautilus' / 's3_sync.py'


def ls(prefix, env):
    r = subprocess.run([sys.executable, str(S3_SYNC), 'ls', prefix], capture_output=True, text=True, env=env)
    out = {}
    for ln in r.stdout.splitlines():
        p = ln.split()
        if len(p) >= 2 and p[0].isdigit() and p[1].startswith(prefix):
            out[p[1]] = int(p[0])
    return out


def main(manifests):
    import os
    rows = {}
    for m in manifests:
        for r in csv.DictReader(open(m)):
            rows.setdefault(r['night'], r)
            if r.get('spec2d') == '1':
                rows[r['night']]['spec2d'] = '1'
    bad, total = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, KECK_ETCS_DATA=tmp)
        for night, r in sorted(rows.items()):
            prefix = f'mosfire/{night}/raw'
            sizes = ls(prefix, env)
            subprocess.run([sys.executable, str(S3_SYNC), 'pull', f'mosfire/{night}', '--include', 'raw/manifest.ecsv',
                            '--force'], capture_output=True, env=env)
            mp = Path(tmp) / prefix / 'manifest.ecsv'
            if not mp.exists():
                bad.append(f'{night}: no raw/manifest.ecsv on S3')
                print(f'{night}: NO MANIFEST ({len(sizes)} objects)')
                continue
            t = Table.read(mp, format='ascii.ecsv')
            kinds = Counter(str(k) for k in t['frame_type'])
            miss = [str(f) for f, s in zip(t['file'], t['size']) if sizes.get(f'{prefix}/{f}') != int(s)]
            nbytes = int(sum(int(s) for s in t['size']))
            total += nbytes
            need = ['standard', 'dome_flat'] + (['science'] if r.get('spec2d') == '1' else [])
            lack = [k for k in need if not kinds.get(k)]
            ok = not miss and not lack
            print(f"{night} {r['standard']:10s} spec2d={r.get('spec2d', '0')}: {len(t)} frames "
                  f"({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}), {nbytes / 1e9:.2f} GB; "
                  f"bucket sizes {'match' if not miss else 'DIFFER for ' + str(miss[:3])}"
                  + (f'; MISSING {lack}' if lack else ''))
            if not ok:
                bad.append(night)
    print(f'{len(rows)} nights, {total / 1e9:.2f} GB in the manifests: ' + ('ALL OK' if not bad else f'problems: {bad}'))
    return 0 if not bad else 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
