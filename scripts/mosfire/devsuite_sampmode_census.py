#!/usr/bin/env python
"""Readout modes of the PypeIt dev-suite MOSFIRE raw data (plan S17).

Usage:
    conda run -n pypeit14b python scripts/mosfire/devsuite_sampmode_census.py
        [--devsuite ~/Projects/PypeIt/PypeIt-development-suite]

For every setup under ``RAW_DATA/keck_mosfire`` it counts the raw frames
by (``SAMPMODE``, ``NUMREADS``) and gives the read noise the PypeIt
``ronoise`` patch (``nautilus/patches/pypeit_mosfire_ronoise.patch``)
assigns them (Keck table, ``keck_etcs.core.detector`` convention). Frames
that are not MCDS-16 are the ones whose ``ronoise`` changes from 5.8 e-,
so the setups listing them are where dev-suite reference outputs may shift.

Read-only (headers only).
"""
import argparse
import collections
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits

TABLE = {1: 21.0, 4: 10.8, 8: 7.7, 16: 5.8, 32: 4.2, 64: 3.5, 128: 3.0}


def rn(sampmode, numreads):
    if sampmode == 2:
        n = 1
    elif sampmode == 3 and numreads:
        n = int(numreads)
    else:
        return None
    k = np.array(sorted(TABLE))
    return float(np.interp(np.log2(n), np.log2(k), [TABLE[i] for i in k]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--devsuite', default='~/Projects/PypeIt/PypeIt-development-suite')
    args = p.parse_args()
    root = Path(args.devsuite).expanduser() / 'RAW_DATA' / 'keck_mosfire'
    changed = []
    for setup in sorted(d for d in root.iterdir() if d.is_dir()):
        counts = collections.Counter()
        for f in sorted(setup.glob('*.fits*')):
            h = fits.getheader(f)
            counts[(h.get('SAMPMODE'), h.get('NUMREADS'))] += 1
        modes = ', '.join(f'SAMPMODE {sm} NUMREADS {nr}: {n} (RN {rn(sm, nr)})'
                          for (sm, nr), n in sorted(counts.items(), key=lambda x: str(x[0])))
        print(f'{setup.name:28s} {sum(counts.values()):3d} frames | {modes}')
        if any(not (sm == 3 and nr == 16) for sm, nr in counts):
            changed.append(setup.name)
    print(f'\nsetups with frames not in MCDS-16 (ronoise changes): {changed}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
