#!/usr/bin/env python
"""Compare the extracted counts of a night's standard frames (diagnostic for S5).

Usage:
    conda run -n pypeit14b python scripts/mosfire/compare_standard_frames.py DATE [--window LO HI]

For every pair of standard spec1d files in ``<night>/redux/Science`` (from
``run_manifest.json``), prints each frame's trace position, FWHM and
exposure time, and the median ratio of their optimal and boxcar counts over
the window (default 1.17-1.24 um, inside the J2 filter's flat top). If the
two extractions give the same ratio, a zero-point difference between
per-frame sensfuncs is in the data (transparency, guiding, slit position),
not in the extraction or the sensfunc fit.
"""
import argparse
import itertools
import json
import sys

import numpy as np
from pypeit.specobjs import SpecObjs

from keck_etcs import paths


def main(date, window=(11700.0, 12400.0)):
    night = paths.night_dir('mosfire', date)
    m = json.loads((night / 'run_manifest.json').read_text())
    frames = {f['filename']: f for f in m['frames']}
    objs = [o for o in m['objects'] if 'standard' in o['frametype']]
    sobj = {}
    for o in objs:
        so = SpecObjs.from_fitsfile(str(night / 'redux' / 'Science' / o['spec1d']), chk_version=False)[0]
        sobj[o['frame']] = so
        print(f"{o['frame']}: spat {so['SPAT_PIXPOS']:.1f}, FWHM {so['FWHM']:.2f} pix, "
              f"exptime {frames[o['frame']]['exptime']} s, airmass {frames[o['frame']]['airmass']:.4f}, "
              f"S/N {so['S2N']:.1f}")
    for a, b in itertools.combinations(sorted(sobj), 2):
        print(f'{a} / {b}, {window[0] / 1e4:.3f}-{window[1] / 1e4:.3f} um:')
        for ext in ('OPT', 'BOX'):
            wa, ca = sobj[a][f'{ext}_WAVE'], sobj[a][f'{ext}_COUNTS']
            wb, cb = sobj[b][f'{ext}_WAVE'], sobj[b][f'{ext}_COUNTS']
            sel = (wa > window[0]) & (wa < window[1])
            r = np.median(ca[sel]) / np.median(np.interp(wa[sel], wb, cb))
            print(f'  {ext}_COUNTS median ratio {r:.4f}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date')
    p.add_argument('--window', nargs=2, type=float, default=(11700.0, 12400.0), metavar=('LO', 'HI'),
                   help='Wavelength window in A')
    sys.exit(main(**vars(p.parse_args())))
