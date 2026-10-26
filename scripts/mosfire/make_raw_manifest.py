#!/usr/bin/env python
"""Write ``raw/manifest.ecsv`` for one MOSFIRE night under ``$KECK_ETCS_DATA``.

Usage:
    conda run -n pypeit14b python scripts/mosfire/make_raw_manifest.py DATE [--pypeit FILE]

e.g. ``make_raw_manifest.py 20220409 --pypeit
<dev-suite>/pypeit_files/keck_mosfire_j2_long.pypeit``.

One row per ``*.fits`` in ``night_dir('mosfire', DATE, 'raw')`` with columns
``koaid, file, frametype, target, slit, sampmode, numreads, exptime,
airmass, sha256`` (plus ``size`` and ``mjd``).

- ``frametype`` comes from the ``data`` block of the given PypeIt file (the
  frame types PypeIt actually used); without ``--pypeit`` it is ``-``.
- ``koaid`` is the header ``KOAID`` if present; otherwise it is derived as
  ``MF.<DATE-OBS>.<UT seconds, truncated>`` (the KOA pattern), and
  ``meta.koaid_derived`` lists those rows. The dev-suite frames keep their
  original ``mYYMMDD_NNNN`` names and carry no ``KOAID`` card.
- ``target`` is ``TARGNAME``, ``slit`` is ``MASKNAME``, ``exptime`` is
  ``TRUITIME`` (s).
"""
import argparse
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

from keck_etcs import paths

SCRIPT = 'scripts/mosfire/make_raw_manifest.py'


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def pypeit_frametypes(pypeit_file):
    """Map filename -> frametype from the ``data read`` block of a PypeIt file."""
    types, cols, inside = {}, None, False
    for line in Path(pypeit_file).read_text().splitlines():
        s = line.strip()
        if s == 'data read':
            inside = True
            continue
        if s == 'data end':
            break
        if not inside or not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if cols is None:
            cols = cells
            continue
        row = dict(zip(cols, cells))
        types[row['filename']] = row['frametype']
    return types


def koaid(hdr):
    if hdr.get('KOAID'):
        return str(hdr['KOAID']).replace('.fits', ''), False
    h, m, s = (float(x) for x in str(hdr['UTC']).split(':'))
    secs = int(h * 3600 + m * 60 + s)
    return f"MF.{str(hdr['DATE-OBS']).replace('-', '')}.{secs:05d}", True


def main(date, pypeit=None):
    raw = paths.night_dir('mosfire', date, 'raw')
    files = sorted(raw.glob('*.fits'))
    if not files:
        print(f'No FITS files in {raw}')
        return 1
    types = pypeit_frametypes(pypeit) if pypeit else {}
    rows, derived = [], []
    for f in files:
        hdr = fits.getheader(f)
        kid, was_derived = koaid(hdr)
        if was_derived:
            derived.append(f.name)
        rows.append({
            'koaid': kid, 'file': f.name, 'frametype': types.get(f.name, '-'),
            'target': str(hdr.get('TARGNAME', '-')), 'slit': str(hdr.get('MASKNAME', '-')),
            'sampmode': int(hdr['SAMPMODE']), 'numreads': int(hdr['NUMREADS']),
            'exptime': float(hdr['TRUITIME']), 'airmass': float(hdr['AIRMASS']),
            'mjd': float(hdr['MJD-OBS']), 'size': f.stat().st_size, 'sha256': sha256sum(f),
        })
    tbl = Table(rows=rows)
    tbl['exptime'].unit = 's'
    tbl['exptime'].format = '.5f'
    tbl['airmass'].format = '.5f'
    tbl['mjd'].format = '.8f'
    tbl.meta.update({
        'instrument': 'keck_mosfire', 'night': str(date),
        's3_prefix': paths.s3_prefix('mosfire', date, 'raw'),
        'frametype_source': str(pypeit) if pypeit else None,
        'koaid_derived': derived,
        'koaid_rule': 'header KOAID, else MF.<DATE-OBS>.<int UT seconds>',
        'exptime_card': 'TRUITIME', 'target_card': 'TARGNAME', 'slit_card': 'MASKNAME',
        'script': SCRIPT,
        'created': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    })
    out = raw / 'manifest.ecsv'
    tbl.write(out, format='ascii.ecsv', overwrite=True)
    tbl[['koaid', 'file', 'frametype', 'target', 'slit', 'sampmode', 'numreads',
         'exptime', 'airmass']].pprint(max_lines=-1, max_width=-1)
    print(f'\nWrote {out} ({len(tbl)} rows; {len(derived)} KOA IDs derived from DATE-OBS/UTC)')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('date', help='Night, YYYYMMDD')
    parser.add_argument('--pypeit', help='PypeIt file whose data block gives the frame types')
    sys.exit(main(**vars(parser.parse_args())))
