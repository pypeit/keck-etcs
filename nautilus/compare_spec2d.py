#!/usr/bin/env python
"""Compare two spec2d files of the same frame stage by stage (S4b diagnosis).

Usage:
    python nautilus/compare_spec2d.py SPEC2D_A SPEC2D_B [--det DET01] [--spat LO HI]

For each image HDU (``SCIIMG``, ``IVARRAW``, ``SKYMODEL``,
``BKG_REDUX_SKYMODEL``, ``OBJMODEL``, ``IVARMODEL``, ``TILTS``, ``WAVEIMG``,
``BPMMASK``) prints the number of differing pixels, the maximum and median
absolute difference, and the A-B sum inside a spatial window (default the
whole frame; e.g. ``--spat 780 810`` around a trace). It also prints the slit
edges and the scalar HDUs. The first stage that differs is where the two
reductions diverged: ``SCIIMG``/``IVARRAW`` is image processing (bias,
flat, A-B), ``SKYMODEL`` is global sky, ``OBJMODEL`` is local sky and
extraction.
"""
import argparse
import sys

import numpy as np
from astropy.io import fits

IMAGES = ('SCIIMG', 'IVARRAW', 'SKYMODEL', 'BKG_REDUX_SKYMODEL', 'OBJMODEL', 'IVARMODEL',
          'TILTS', 'WAVEIMG', 'BPMMASK')


def main(a, b, det='DET01', spat=None):
    ha, hb = fits.open(a), fits.open(b)
    print(f'A = {a}\nB = {b}')
    for name in IMAGES:
        key = f'{det}-{name}'
        if key not in ha or key not in hb:
            print(f'{name:20s} missing in {"A" if key not in ha else "B"}')
            continue
        da = np.asarray(ha[key].data, dtype=float)
        db = np.asarray(hb[key].data, dtype=float)
        d = da - db
        if spat is not None:
            dwin = d[:, spat[0]:spat[1]]
            win = f', window sum A-B {np.nansum(dwin):+.4g} (A {np.nansum(da[:, spat[0]:spat[1]]):.4g})'
        else:
            win = ''
        nz = np.count_nonzero(d)
        print(f'{name:20s} differing pixels {nz:8d} / {d.size}, max |d| {np.nanmax(np.abs(d)):.4g}, '
              f'median |d| (differing) {np.nanmedian(np.abs(d[d != 0])) if nz else 0:.4g}{win}')
    for name in ('SCALEIMG', 'MED_CHIS', 'STD_CHIS'):
        key = f'{det}-{name}'
        if key in ha and key in hb:
            print(f'{name:20s} A {np.ravel(ha[key].data)} B {np.ravel(hb[key].data)}')
    sa, sb = ha[f'{det}-SLITS'].data, hb[f'{det}-SLITS'].data
    for col in sa.columns.names:
        va, vb = np.asarray(sa[col]), np.asarray(sb[col])
        if va.dtype.kind in 'fi' and va.shape == vb.shape:
            print(f'SLITS {col:16s} max |A-B| {np.nanmax(np.abs(va - vb)) if va.size else 0:.4g}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('a')
    p.add_argument('b')
    p.add_argument('--det', default='DET01')
    p.add_argument('--spat', nargs=2, type=int, metavar=('LO', 'HI'))
    x = p.parse_args()
    sys.exit(main(x.a, x.b, x.det, x.spat))
