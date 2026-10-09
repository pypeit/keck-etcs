#!/usr/bin/env python
"""Check PypeIt's MOSFIRE read noise against the readout mode of real frames (plan S17).

Usage:
    conda run -n pypeit14b python scripts/mosfire/check_ronoise_patch.py [--night 20220409]

    # against a scratch copy of PypeIt with nautilus/patches/pypeit_mosfire_ronoise.patch applied:
    PYTHONPATH=<scratch copy> conda run -n pypeit14b python scripts/mosfire/check_ronoise_patch.py

For every raw frame of the night it prints ``SAMPMODE``, ``NUMREADS`` and
``KeckMOSFIRESpectrograph.get_detector_par(1, hdu).ronoise``, and compares
the value with the Keck table in ``keck_etcs/data/mosfire/detector.ecsv``
(``keck_etcs.core.detector.read_noise``, linear in log2 N; CDS is N = 1).
The expected results with the patch: 21 e- for the CDS dome flats
(m220409_0017-0026) and 5.8 e- for the MCDS-16 science and standard frames.
Without the patch every frame reads 5.8 e-, and the CDS frames fail.

Prints which PypeIt was imported. Exit 0 if every frame agrees, 1 otherwise.
"""
import argparse
import sys

import numpy as np
from astropy.io import fits
from astropy.table import Table

import pypeit
from pypeit.spectrographs.util import load_spectrograph

from keck_etcs import paths
from keck_etcs.instruments.base import DATA_DIR


def expected_rn(sampmode, numreads, table):
    """The Keck-table read noise for CDS or MCDS-N, or None for other modes."""
    if sampmode == 2:
        n = 1
    elif sampmode == 3:
        n = int(numreads)
    else:
        return None
    n_tab = np.asarray(table['n_reads'], float)
    return float(np.interp(np.log2(n), np.log2(n_tab), np.asarray(table['read_noise_e'], float)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--night', default='20220409')
    args = p.parse_args()

    print(f'pypeit {pypeit.__version__} from {pypeit.__file__}')
    table = Table.read(DATA_DIR / 'mosfire' / 'detector.ecsv', format='ascii.ecsv')
    spec = load_spectrograph('keck_mosfire')
    raw = paths.data_root() / 'mosfire' / args.night / 'raw'
    bad = []
    for f in sorted(raw.glob('m*.fits')):
        with fits.open(f) as hdu:
            sm, nr = hdu[0].header.get('SAMPMODE'), hdu[0].header.get('NUMREADS')
            rn = float(spec.get_detector_par(1, hdu=hdu).ronoise[0])
        exp = expected_rn(sm, nr, table)
        ok = exp is not None and abs(rn - exp) < 1e-6
        print(f'{f.name}: SAMPMODE {sm} NUMREADS {nr:3d} -> ronoise {rn:5.2f} e- '
              f'(Keck table {exp if exp is None else round(exp, 2)}) {"OK" if ok else "MISMATCH"}')
        if not ok:
            bad.append(f.name)
    print('ALL FRAMES AGREE' if not bad else f'MISMATCH: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
