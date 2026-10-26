#!/usr/bin/env python
"""Estimate how large the Gemini Maunakea sky grid becomes if we keep only the
MOSFIRE wavelength range, at native or degraded sampling.

Usage:
    conda run -n pypeit14 python scripts/size_gemini_sky_subset.py XTCALC_DIR

The 24 IDL save files in ``XTCALC_DIR/Mauna_Kea_sky`` (12 sky-background
``mk_skybg_zm_WW_AA_ph`` and 12 transmission ``mktrans_zm_WW_AA``) cover
0.9-5.6 um at 0.02 nm.  MOSFIRE's Y-K coverage is about 0.95-2.45 um.  This
script cuts each grid to that range, writes nothing permanent (it builds the
arrays in memory), and reports the byte size of a float32 FITS-style cube for
several resamplings, so we can decide how to store the grid in the package.
"""
import glob
import os
import sys

import numpy as np
from scipy.io import readsav

WMIN, WMAX = 950.0, 2450.0     # nm, MOSFIRE Y through K
J_MIN, J_MAX = 1100.0, 1400.0  # nm, J + J2 + J3 footprint


def load(path):
    s = readsav(path)
    keys = [k for k in s.keys() if k != 'comment']
    wkey = 'lam' if 'lam' in keys else 'tran_lam'
    vkey = [k for k in keys if k != wkey][0]
    w = np.asarray(s[wkey], dtype=float)
    if w.max() < 100:          # transmission files are in micron
        w = w * 1000.0
    return w, np.asarray(s[vkey], dtype=float)


def main(xtdir):
    files = sorted(glob.glob(os.path.join(xtdir, 'Mauna_Kea_sky', '*.sav')))
    print(f'{len(files)} files')
    total_native = 0
    sizes = {}
    for f in files:
        w, v = load(f)
        total_native += os.path.getsize(f)
        for label, (lo, hi), step in (('YJHK native 0.02 nm', (WMIN, WMAX), None),
                                      ('YJHK 0.1 nm', (WMIN, WMAX), 0.1),
                                      ('J-only native 0.02 nm', (J_MIN, J_MAX), None),
                                      ('J-only 0.05 nm', (J_MIN, J_MAX), 0.05)):
            sel = (w >= lo) & (w <= hi)
            n = sel.sum()
            if step is not None:
                n = int(round((hi - lo) / step))
            sizes[label] = sizes.get(label, 0) + n * 4   # float32 values
    print(f'native IDL save files on disk: {total_native/1e6:.1f} MB')
    print('float32 storage (values only; one shared wavelength axis adds <1 MB):')
    for label, nbytes in sizes.items():
        print(f'  {label:26s} {nbytes/1e6:6.1f} MB for all 24 grids')
    # Resolution check: MOSFIRE J is ~1.3 A/pix = 0.13 nm, R ~ 3300 at 0.7"
    # so a 0.1 nm grid (R ~ 12000 at 1.2 um) still oversamples the instrument.
    print('\nMOSFIRE J dispersion is 0.13 nm/pix and the 0.7" slit gives ~0.36 nm '
          'FWHM, so 0.1 nm sampling oversamples the line spread function ~3.5x.')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
