#!/usr/bin/env python
"""Does PypeIt's object trace follow the object? (S4b investigation)

Usage:
    conda run -n pypeit14b python scripts/mosfire/trace_vs_centroid.py SPEC1D SPEC2D [SPEC1D SPEC2D ...]
        [--block 51]

For each frame: in blocks of ``--block`` spectral rows, median-collapse the
sky-subtracted image ``SCIIMG - SKYMODEL`` (no object model, no extraction
mask) and measure the object's centroid within +-6 px of PypeIt's
``TRACE_SPAT``. The centroid is iterated twice, weighted by the positive
flux. Prints trace - centroid per block, its median, its rms, and the
largest offset.

A trace that is off the object by a pixel or more, over part of the
spectrum, makes a profile centred on the trace misfit the data. The local
sky / extraction fit then rejects the core or wing pixels as outliers
(``EXTRACT``).
"""
import argparse
import sys

import numpy as np
from astropy.io import fits
from pypeit.specobjs import SpecObjs


def centroid(prof, x0, half=6, niter=2):
    x = np.arange(prof.size)
    c = x0
    for _ in range(niter):
        sel = (x >= np.round(c) - half) & (x <= np.round(c) + half)
        w = np.clip(prof[sel], 0, None)
        if w.sum() <= 0:
            return np.nan
        c = float(np.sum(x[sel] * w) / w.sum())
    return c


def analyse(spec1d, spec2d, block):
    o = SpecObjs.from_fitsfile(spec1d, chk_version=False)[0]
    trace = np.asarray(o['TRACE_SPAT'], dtype=float)
    h = fits.open(spec2d)
    img = h['DET01-SCIIMG'].data.astype(float) - h['DET01-SKYMODEL'].data.astype(float)
    nspec = img.shape[0]
    rows = []
    for lo in range(0, nspec - block + 1, block):
        sl = slice(lo, lo + block)
        t = np.median(trace[sl])
        x0 = int(round(t))
        cut = img[sl, x0 - 15:x0 + 16]
        prof = np.nanmedian(cut, axis=0)
        c = centroid(prof, t - (x0 - 15))
        rows.append((lo, t, c + (x0 - 15) if np.isfinite(c) else np.nan, np.nanmax(prof)))
    rows = np.array(rows)
    d = rows[:, 1] - rows[:, 2]
    ok = np.isfinite(d) & (rows[:, 3] > 5)
    print(f'\n== {spec1d.split("/")[-1][:36]}  FWHM {o["FWHM"]:.3f}')
    print('  rows        trace    centroid   trace-centroid   peak')
    for r, dd in zip(rows, d):
        flag = '  <--' if np.isfinite(dd) and abs(dd) > 0.75 else ''
        print(f'  {int(r[0]):4d}-{int(r[0]) + block - 1:4d}  {r[1]:8.2f}  {r[2]:8.2f}     {dd:+7.2f}      '
              f'{r[3]:7.1f}{flag}')
    print(f'  median {np.median(d[ok]):+.3f}  rms {np.std(d[ok]):.3f}  max |d| {np.max(np.abs(d[ok])):.2f} px'
          f'  ({np.sum(np.abs(d[ok]) > 0.75)} of {ok.sum()} blocks off by > 0.75 px)')


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('files', nargs='+')
    p.add_argument('--block', type=int, default=51)
    a = p.parse_args()
    if len(a.files) % 2:
        p.error('give SPEC1D SPEC2D pairs')
    for i in range(0, len(a.files), 2):
        analyse(a.files[i], a.files[i + 1], a.block)
    return 0


if __name__ == '__main__':
    sys.exit(main())
