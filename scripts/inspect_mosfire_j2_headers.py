#!/usr/bin/env python
"""Inspect the raw MOSFIRE J2_long FITS headers for ETC / sensfunc-relevant cards.

Usage:
    conda run -n pypeit14 python scripts/inspect_mosfire_j2_headers.py [RAW_DIR]

Prints a per-frame table of the header cards that matter for an exposure-time
calculator or a sensitivity function (readout mode, number of reads, gain,
exposure time, airmass, slit, seeing / guider values), then dumps the full
header of one science frame and one standard frame so nothing is missed.
"""
import glob
import os
import sys

from astropy.io import fits

DEFAULT_RAW = ('/Users/xavier/Projects/PypeIt/PypeIt-development-suite/'
               'RAW_DATA/keck_mosfire/J2_long')

# Cards we care about.  Anything missing prints as '-'.
CARDS = ['FRAMENUM', 'OBJECT', 'TARGNAME', 'MASKNAME', 'OBSMODE', 'FILTER',
         'TRUITIME', 'ITIME', 'COADDS', 'READMODE', 'SAMPMODE', 'NUMREADS',
         'GAIN', 'SYSGAIN', 'RN', 'AIRMASS', 'MJD-OBS', 'UTC', 'PSCALE',
         'PATTERN', 'FRAMEID', 'YOFFSET', 'XOFFSET', 'GRATMODE', 'MGTNAME',
         'FLATSPEC', 'PWSTATA7', 'PWSTATA8', 'EL', 'ROTPPOSN', 'PA',
         'DOMEPOSN', 'DOMESTAT', 'WXOUTHUM', 'WXOUTTMP', 'WXPRESS', 'TUBETEMP',
         'GUIDFWHM', 'GUIDER', 'CURRINST', 'INSTFLIP']

SEEING_HINTS = ('FWHM', 'SEEING', 'GUID', 'DIMM', 'MASS', 'HUMID', 'PWV',
                'WATER', 'TEMP', 'READ', 'SAMP', 'GAIN', 'NOISE', 'COADD',
                'ITIME', 'RESET', 'SLIT', 'MASK', 'DECKER', 'CSU')


def main(raw_dir):
    files = sorted(glob.glob(os.path.join(raw_dir, '*.fits')))
    print(f'{len(files)} files in {raw_dir}\n')

    # Table of the chosen cards
    hdrs = {}
    for f in files:
        with fits.open(f) as hdul:
            hdrs[os.path.basename(f)] = hdul[0].header
            if f == files[0]:
                print('HDU layout of first file:')
                hdul.info()
                print()

    present = [c for c in CARDS if any(c in h for h in hdrs.values())]
    missing = [c for c in CARDS if c not in present]
    print('Requested cards absent from all headers:', ', '.join(missing), '\n')

    # Print in blocks so it is readable
    for block in (present[:10], present[10:20], present[20:30], present[30:]):
        if not block:
            continue
        print('file'.ljust(18) + ''.join(c.ljust(15) for c in block))
        for name, h in hdrs.items():
            row = name.ljust(18)
            for c in block:
                v = h.get(c, '-')
                if isinstance(v, float):
                    v = f'{v:.4g}'
                row += str(v)[:14].ljust(15)
            print(row)
        print()

    # Any card whose name hints at seeing / detector / slit, from one frame
    sci = hdrs['m220409_0036.fits']
    print('Cards in the science frame whose names hint at seeing, detector or slit:')
    for k in sci:
        if any(s in k.upper() for s in SEEING_HINTS):
            print(f'  {k:10s} = {sci[k]!r:40.40}  / {sci.comments[k]}')
    print()

    # Full header dumps of one science and one standard frame
    for name in ('m220409_0036.fits', 'm220409_0218.fits'):
        print('=' * 78)
        print('FULL HEADER:', name)
        print('=' * 78)
        print(repr(hdrs[name]))
        print()


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RAW)
