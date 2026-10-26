#!/usr/bin/env python
"""Where along and across a trace does PypeIt's extraction reject pixels? (S4b investigation)

Usage:
    conda run -n pypeit14b python scripts/mosfire/extract_mask_map.py SPEC1D SPEC2D [SPEC1D SPEC2D ...]

For each (spec1d, spec2d) pair of one frame, using the object's
``TRACE_SPAT``:

- the fraction of ``EXTRACT``-flagged pixels (BPMMASK bit) and the mean
  normalized residual ``(sciimg - skymodel - objmodel) * sqrt(ivarmodel)``,
  in 1-pixel bins of the spatial offset from the trace (-10..+10);
- the same fraction in 8 spectral blocks of 255 rows, and its correlation
  with the sky level (``SKYMODEL`` + ``BKG_REDUX_SKYMODEL`` on the trace):
  rejections that follow the sky point at sky-line residuals, and rejections
  in the core or wings at a profile mismatch.
"""
import sys

import numpy as np
from astropy.io import fits
from pypeit.images.imagebitmask import ImageBitMask
from pypeit.specobjs import SpecObjs

OFFSETS = np.arange(-10, 11)


def analyse(spec1d, spec2d):
    o = SpecObjs.from_fitsfile(spec1d, chk_version=False)[0]
    trace = np.asarray(o['TRACE_SPAT'], dtype=float)
    h = fits.open(spec2d)
    sci = h['DET01-SCIIMG'].data.astype(float)
    sky = h['DET01-SKYMODEL'].data.astype(float)
    bkg = h['DET01-BKG_REDUX_SKYMODEL'].data.astype(float)
    obj = h['DET01-OBJMODEL'].data.astype(float)
    ivar = h['DET01-IVARMODEL'].data.astype(float)
    bpm = h['DET01-BPMMASK'].data.astype(int)
    ext = ImageBitMask().flagged(bpm, flag='EXTRACT')
    nspec = sci.shape[0]
    rows = np.arange(nspec)
    good = np.isfinite(trace) & (trace > 15) & (trace < sci.shape[1] - 15)
    print(f'\n== {spec1d.split("/")[-1][:36]}  FWHM {o["FWHM"]:.3f}  S/N {o["S2N"]:.2f}')
    print('  offset  EXTRACT frac  mean resid*sqrt(ivar)   mean objmodel')
    for d in OFFSETS:
        cols = np.round(trace[good]).astype(int) + d
        r = rows[good]
        e = ext[r, cols]
        res = (sci[r, cols] - sky[r, cols] - obj[r, cols]) * np.sqrt(ivar[r, cols])
        ok = ~e & (ivar[r, cols] > 0)
        print(f'  {d:+4d}    {e.mean():8.3f}        {np.mean(res[ok]):+8.3f}            '
              f'{np.mean(obj[r, cols]):9.2f}')
    c = np.round(trace[good]).astype(int)
    r = rows[good]
    core = np.zeros(r.size, dtype=bool)
    for d in range(-3, 4):
        core |= ext[r, c + d]
    skyl = sky[r, c] + bkg[r, c]
    print('  spectral block   EXTRACT frac (|offset|<=3)   median sky on trace')
    for b in range(8):
        sel = (r >= b * 255) & (r < (b + 1) * 255)
        if sel.any():
            print(f'  rows {b * 255:4d}-{(b + 1) * 255 - 1:4d}        {core[sel].mean():6.3f}'
                  f'                     {np.median(skyl[sel]):9.1f}')
    hi = skyl > np.percentile(skyl, 90)
    print(f'  rows with any core rejection: {core.mean():.3f}; in the brightest-sky 10% of rows: '
          f'{core[hi].mean():.3f}; elsewhere: {core[~hi].mean():.3f}')


def main(args):
    if len(args) < 2 or len(args) % 2:
        print(__doc__)
        return 2
    for i in range(0, len(args), 2):
        analyse(args[i], args[i + 1])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
