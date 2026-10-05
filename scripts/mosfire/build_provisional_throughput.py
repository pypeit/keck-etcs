#!/usr/bin/env python
"""Build the provisional MOSFIRE J throughput from XTcalc (plan step S9; replaced by S10).

Usage:
    conda run -n pypeit14b python scripts/mosfire/build_provisional_throughput.py

Until part 4 (S10) writes ``mosfire_thru_<era>.ecsv`` from our own standards,
``keck_etcs.etc.compute`` uses this curve, labelled
``calib_version = provisional-xtcalc-2012`` and flagged ``provisional`` in
``index.yaml`` and in every output's ``warnings``. It must be replaced
before any release.

Source: XTcalc v2.3 ``MosfireSpecEff/Jeff.sm.dat``, the J-band efficiency
from the May 2012 commissioning standards, instrument plus detector through
the J filter, without the telescope. Steps:

1. end-to-end: ``Jeff x 0.89^2`` (two Keck mirrors, XTcalc's reflectance in J);
2. divide out the J filter (``keck_etcs/data/mosfire/filters/mosfire_J.ecsv``)
   to get the filter-free curve the ETC multiplies by any band's filter
   (design 5.3.4), but only over 11700-13400 A: the ``.sm`` curve is
   smoothed and its cut-on does not line up with the Keck J curve, so the
   ratio collapses at the filter edges (it is still falling at 11605 A,
   where F_J first reaches 0.85);
3. a 51-sample (64 A) running median inside that range; held constant at
   the edge values outside it (an assumption for J2 below 11700 A and for
   J above 13400 A);
4. resampled to the common 1 A grid of design 4.5 over 11000-14000 A, with
   the S10 column layout ``wave, thru_median, thru_mad, n_std`` (``thru_mad``
   = 0, ``n_std`` = 0).

XTcalc's wavelengths are taken as vacuum, as for its sky grids (design N5;
``build_gemini_sky_grid.py`` found a +0.009 A median offset from PypeIt's
vacuum OH list).
"""
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table
from scipy.ndimage import median_filter

import keck_etcs
from keck_etcs import paths
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'throughput' / 'mosfire_thru_provisional-xtcalc-2012.ecsv'
INDEX = REPO / 'keck_etcs' / 'data' / 'index.yaml'
CALIB_VERSION = 'provisional-xtcalc-2012'
MIRROR = 0.89
VALID_A = (11700.0, 13400.0)
SMOOTH = 51
GRID = np.arange(11000.0, 14000.0 + 0.5, 1.0)


def main():
    src = paths.data_root() / 'external' / 'xtcalc' / 'XTcalc_dir' / 'MosfireSpecEff' / 'Jeff.sm.dat'
    w, eff = np.loadtxt(src, unpack=True)
    f = MOSFIRE.filter_curve('J')
    fj = np.interp(w, f['wave_A'], f['transmission'], left=0.0, right=0.0)
    inside = (w >= VALID_A[0]) & (w <= VALID_A[1])
    lo, hi = w[inside][0], w[inside][-1]
    ratio = median_filter(eff[inside] * MIRROR ** 2 / fj[inside], size=SMOOTH, mode='nearest')
    thru = np.interp(GRID, w[inside], ratio)          # constant beyond [lo, hi]
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    t = Table([GRID, thru, np.zeros_like(GRID), np.zeros(GRID.size, int)],
              names=('wave', 'thru_median', 'thru_mad', 'n_std'))
    t['wave'].unit = 'Angstrom'
    t['thru_median'].format = '.5f'
    t.meta = {
        'description': 'PROVISIONAL filter-free MOSFIRE J-grating throughput (telescope + instrument + detector) '
                       'from XTcalc 2012; replaced by the S10 per-era curves',
        'instrument': 'keck_mosfire', 'band': 'J, J2 (filter-free)', 'era': 'all (provisional)',
        'provisional': True,
        'source': 'XTcalc v2.3 MosfireSpecEff/Jeff.sm.dat (May 2012 commissioning standards)',
        'source_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
        'mirror_reflectance': MIRROR, 'filter_divided': 'mosfire/filters/mosfire_J.ecsv',
        'valid_range_A': [round(float(lo), 1), round(float(hi), 1)],
        'outside_valid_range': 'held constant at the edge value',
        'smoothing': f'{SMOOTH}-sample running median on the XTcalc grid (1.255 A/sample)',
        'waveref': 'vacuum (XTcalc, as its sky grids; design N5)',
        'standards': [], 'pypeit_version': 'n/a', 'calib_version': CALIB_VERSION,
        'keck_etcs_version': keck_etcs.__version__, 'created': now,
        'script': 'scripts/mosfire/build_provisional_throughput.py',
        'image': 'n/a', 'image_digest': 'n/a', 'pypeit_git_sha': 'n/a', 'keck_etcs_git_sha': 'n/a',
        'job_name': 'n/a', 's3_prefix': 'n/a',
    }
    t.write(OUT, format='ascii.ecsv', overwrite=True)
    index = yaml.safe_load(INDEX.read_text()) or {}
    index.setdefault('files', {})[str(OUT.relative_to(REPO / 'keck_etcs' / 'data'))] = {
        'calib_version': CALIB_VERSION, 'created': now, 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
        'script': 'scripts/mosfire/build_provisional_throughput.py', 'provisional': True, 'pypeit_version': 'n/a',
        'provenance': 'PROVISIONAL: XTcalc 2012 Jeff.sm.dat x 0.89^2 / Keck J filter (11700-13400 A, constant '
                      'outside); to be replaced by the S10 per-era curves before any release'}
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))
    for lam in (11200, 11700, 12000, 12500, 13000, 13400):
        print(f'{lam} A: thru {np.interp(lam, GRID, thru):.4f}')
    sel = (GRID >= 11170) & (GRID <= 12460)
    print(f'valid {lo:.1f}-{hi:.1f} A; median J2 window {np.median(thru[sel]):.4f}; '
          f'median J window {np.median(thru[(GRID >= 11535) & (GRID <= 13523)]):.4f}')
    print(f'wrote {OUT.relative_to(REPO)}; index.yaml updated')
    return 0


if __name__ == '__main__':
    sys.exit(main())
