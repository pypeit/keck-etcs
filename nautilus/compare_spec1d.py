#!/usr/bin/env python
"""Compare two reductions of one night frame by frame (spec1d level; S4b diagnosis).

Usage:
    python nautilus/compare_spec1d.py NIGHT_DIR_A NIGHT_DIR_B [--window LO HI] [--within]

For every ``redux/Science/spec1d_*.fits`` present in both night directories
(e.g. a pod's products pulled into a scratch data root, and the local
reference), prints per object: trace position, FWHM, S2N, and the median
ratio A/B of ``OPT_COUNTS`` and ``BOX_COUNTS`` over the window (default
1.17-1.24 um). If ``BOX_COUNTS`` agree while ``OPT_COUNTS`` do not, the
photons are the same and the difference is in the extraction profile
(FWHM / profile fit), not in calibration or sky subtraction.

``--within`` also prints, for each directory, every frame's median OPT and
BOX counts relative to the median over the frames of the same target. Frames
of one star taken minutes apart should agree, which shows which reduction
of a frame is the outlier.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from pypeit.specobjs import SpecObjs


def ratio(a, b, ext, window):
    wa, ca = a[f'{ext}_WAVE'], a[f'{ext}_COUNTS']
    wb, cb = b[f'{ext}_WAVE'], b[f'{ext}_COUNTS']
    if ca is None or cb is None:
        return float('nan')
    sel = (wa > window[0]) & (wa < window[1])
    return float(np.median(ca[sel]) / np.median(np.interp(wa[sel], wb, cb)))


def within(d, window):
    rows = []
    for f in sorted(Path(d, 'redux', 'Science').glob('spec1d_*.fits')):
        o = SpecObjs.from_fitsfile(str(f), chk_version=False)[0]
        sel = (o['OPT_WAVE'] > window[0]) & (o['OPT_WAVE'] < window[1])
        target = f.name.split('-', 1)[1].rsplit('_MOSFIRE', 1)[0]
        rows.append((f.name[7:20], target, float(np.median(o['OPT_COUNTS'][sel])),
                     float(np.median(o['BOX_COUNTS'][sel]))))
    print(f'-- {d}: counts / median of the same target')
    for t in sorted({r[1] for r in rows}):
        sub = [r for r in rows if r[1] == t]
        mo, mb = np.median([r[2] for r in sub]), np.median([r[3] for r in sub])
        for r in sub:
            print(f'   {r[0]:13s} {t:16s} OPT {r[2] / mo:7.4f}  BOX {r[3] / mb:7.4f}')


def main(a_dir, b_dir, window=(11700.0, 12400.0), within_target=False):
    a_files = {p.name: p for p in sorted(Path(a_dir, 'redux', 'Science').glob('spec1d_*.fits'))}
    b_files = {p.name: p for p in sorted(Path(b_dir, 'redux', 'Science').glob('spec1d_*.fits'))}
    common = sorted(set(a_files) & set(b_files))
    if not common:
        print('no spec1d files in common')
        return 1
    print(f'A = {a_dir}\nB = {b_dir}')
    print(f'{"frame":13s} {"spatA":>8s} {"spatB":>8s} {"fwhmA":>6s} {"fwhmB":>6s} {"s2nA":>6s} {"s2nB":>6s} '
          f'{"OPT A/B":>8s} {"BOX A/B":>8s}')
    for name in common:
        a = SpecObjs.from_fitsfile(str(a_files[name]), chk_version=False)
        b = SpecObjs.from_fitsfile(str(b_files[name]), chk_version=False)
        for oa, ob in zip(a, b):
            print(f'{name[7:20]:13s} {oa["SPAT_PIXPOS"]:8.2f} {ob["SPAT_PIXPOS"]:8.2f} {oa["FWHM"]:6.3f} '
                  f'{ob["FWHM"]:6.3f} {oa["S2N"]:6.2f} {ob["S2N"]:6.2f} '
                  f'{ratio(oa, ob, "OPT", window):8.5f} {ratio(oa, ob, "BOX", window):8.5f}')
    if within_target:
        within(a_dir, window)
        within(b_dir, window)
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('a_dir')
    p.add_argument('b_dir')
    p.add_argument('--window', nargs=2, type=float, default=(11700.0, 12400.0), metavar=('LO', 'HI'))
    p.add_argument('--within', action='store_true', help='Also compare frames of a target within each run')
    a = p.parse_args()
    sys.exit(main(a.a_dir, a.b_dir, tuple(a.window), a.within))
