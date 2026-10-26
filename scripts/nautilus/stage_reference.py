#!/usr/bin/env python
"""Stage a locally reduced night as the reference for the Nautilus gates (S4b).

Usage:
    python scripts/nautilus/stage_reference.py DATE [--push]

Copies (not links) the products of ``$KECK_ETCS_DATA/mosfire/DATE`` that
``nautilus/gates.py --reference`` and later checks need into
``$KECK_ETCS_DATA/mosfire/DATE/reference/``, keeping the night's layout:
``run_manifest.json``, ``pypeit_pin_check.json``, ``run.log``,
``redux/*.pypeit``, ``redux/Science/spec1d_*.fits``,
``redux/Calibrations/WaveCalib_*.fits``, ``sens/sens_*.fits`` and the
``sens/*_vs_calspec.png`` / ``*_inspect.json`` QA. They are copies because a
later ``s3_sync.py pull`` of the night overwrites ``redux/`` and ``sens/``
with the pod's products. A ``reference/MANIFEST.txt`` lists every file
with its sha256.

``--push`` then runs ``s3_sync.py push mosfire/DATE/reference``.
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from keck_etcs import paths

REPO = Path(__file__).resolve().parents[2]
PATTERNS = ('run_manifest.json', 'pypeit_pin_check.json', 'run.log', 'redux/*.pypeit',
            'redux/Science/spec1d_*.fits', 'redux/Calibrations/WaveCalib_*.fits',
            'sens/sens_*.fits', 'sens/*_vs_calspec.png', 'sens/*_inspect.json')


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def main(date, push=False):
    night = paths.night_dir('mosfire', date)
    ref = night / 'reference'
    if ref.exists():
        shutil.rmtree(ref)
    lines = []
    for pat in PATTERNS:
        for src in sorted(night.glob(pat)):
            dst = ref / src.relative_to(night)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src.resolve(), dst)
            lines.append(f'{sha256sum(dst)}  {dst.relative_to(ref)}')
    if not (ref / 'run_manifest.json').exists():
        print(f'no run_manifest.json in {night}')
        return 1
    (ref / 'MANIFEST.txt').write_text('\n'.join(lines) + '\n')
    print(f'staged {len(lines)} files in {ref}')
    for line in lines:
        print(f'  {line}')
    if push:
        return subprocess.run([sys.executable, str(REPO / 'scripts' / 'nautilus' / 's3_sync.py'),
                               'push', paths.s3_prefix('mosfire', date) + '/reference']).returncode
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date', help='Night, YYYYMMDD')
    p.add_argument('--push', action='store_true', help='Push the reference to the bucket')
    sys.exit(main(**vars(p.parse_args())))
