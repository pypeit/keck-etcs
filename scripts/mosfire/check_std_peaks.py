#!/usr/bin/env python
"""Peak raw counts of the standard star in the frames a sensfunc used (plan S15a verification).

Usage:
    conda run -n pypeit14b python scripts/mosfire/check_std_peaks.py DATE [DATE ...] [--limit 26000]

For each night under ``$KECK_ETCS_DATA/mosfire/<DATE>``, reads
``run_manifest.json``, takes the standard objects the sensfunc used
(``specphot_use`` on long2pos_specphot nights, otherwise every standard
object) and, in each object's raw frame (``raw/``), the 99.9th percentile
and the maximum of the raw counts (ADU per coadd) in a 15-pixel band around
the object's spatial position over the central 80 percent of the spectrum.
Frames above ``--limit`` (the 26k ADU linearity limit of the calibration
monitor, design 4.9.4 rule 3) are flagged: a nonlinear standard gives a
zero point that is too faint. The raw frames must be local (``s3_sync.py
pull mosfire/<DATE>/raw``). Read-only.
"""
import argparse
import json
import sys

import numpy as np
from astropy.io import fits

from keck_etcs import paths


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('dates', nargs='+')
    ap.add_argument('--limit', type=float, default=26000.)
    a = ap.parse_args(argv)
    for date in a.dates:
        night = paths.night_dir('mosfire', date)
        m = json.loads((night / 'run_manifest.json').read_text())
        objs = [o for o in m['objects'] if 'standard' in o['frametype'] and o.get('sign') == 'positive']
        if m.get('specphot'):
            objs = [o for o in objs if o.get('specphot_use')]
        for o in objs:
            raw = night / 'raw' / o['frame']
            if not raw.exists():
                print(f'{date} {o["frame"]}: raw frame not local')
                continue
            d = fits.getdata(raw).astype(float)
            h = fits.getheader(raw)
            n = d.shape[1]
            s = int(round(o['spat_pixpos']))
            band = d[max(0, s - 7):s + 8, int(0.1 * n):int(0.9 * n)]   # rows = spatial, columns = spectral
            p999, pmax = np.percentile(band, 99.9), band.max()
            print(f"{date} {o['frame']} {o['target']:10s} exptime {h.get('TRUITIME')} s SAMPMODE {h.get('SAMPMODE')} "
                  f"spat {s}: p99.9 {p999:7.0f}  max {pmax:7.0f} ADU"
                  + ('  ABOVE LINEARITY LIMIT' if p999 > a.limit else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
