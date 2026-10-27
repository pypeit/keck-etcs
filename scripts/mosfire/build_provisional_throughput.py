#!/usr/bin/env python
"""Placeholder filter-free throughput curves for the band groups without a reduced standard (plan S23a).

Usage:
    conda run -n pypeit14b python scripts/mosfire/build_provisional_throughput.py [--bands Y H K]

For each band group, XTcalc's 2012 end-to-end efficiency
(``$KECK_ETCS_DATA/external/xtcalc/XTcalc_dir/MosfireSpecEff/<band>eff.sm.dat``,
C. Steidel; it excludes the two Keck mirrors) is multiplied by the mirror
reflectivity squared that XTcalc uses (``KMREF``), the shipped filter curve
is divided out, and the result over the filter's half-power band is written
on the 1 A grid as
``keck_etcs/data/mosfire/throughput/mosfire_thru_<group>_provisional.ecsv``
with the columns of an era product (``wave, thru_median, thru_mad, n_std``;
MAD NaN, ``n_std`` 0) and ``calib_version = provisional-xtcalc-2012``,
registered in ``index.yaml``. ``keck_etcs.instruments.base.Instrument.throughput``
uses such a file only when no era of the group has a measured curve, with a
``PROVISIONAL`` warning (design D1: XTcalc curves are cross-checks, not
calibration; this placeholder lets ``compute()`` run for Y, H and K before
parts H, K and Y deliver the measured products, as the J ETC ran on
``provisional-xtcalc-2012`` before S10).
"""
import argparse
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table

import keck_etcs
from keck_etcs import paths
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

CALIB_VERSION = 'provisional-xtcalc-2012'
SCRIPT = 'scripts/mosfire/build_provisional_throughput.py'
KMREF = {'Y': 0.85, 'J': 0.89, 'H': 0.94, 'K': 0.95}
"""Keck mirror reflectivity per surface in XTcalc's MOSFIRE calculation (XTcalc_dir/MOSFIRE_XTcalc.pdf)."""
XTDIR = paths.data_root() / 'external' / 'xtcalc' / 'XTcalc_dir'
INDEX = DATA_DIR / 'index.yaml'


def sha256sum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_eff(path):
    """``(wave_A, efficiency)`` of an XTcalc ``*eff.sm.dat`` file (two columns; um or A)."""
    a = np.loadtxt(path)
    w, e = a[:, 0].astype(float), a[:, 1].astype(float)
    if w.max() < 100:
        w = w * 1e4
    o = np.argsort(w)
    return w[o], e[o]


def build(group):
    band = MOSFIRE.bands[group]
    src = XTDIR / 'MosfireSpecEff' / f'{group}eff.sm.dat'
    w, e = read_eff(src)
    end_to_end = np.clip(e, 0, None) * KMREF[group] ** 2
    filt = MOSFIRE.filter_curve(group)
    lo, hi = (float(x) for x in filt['meta']['half_power_A'])
    grid = np.arange(np.ceil(max(lo, w.min())), np.floor(min(hi, w.max())) + 0.5, 1.0)
    ft = np.interp(grid, filt['wave_A'], filt['transmission'])
    thru = np.interp(grid, w, end_to_end) / ft
    t = Table([grid, thru, np.full(grid.size, np.nan), np.zeros(grid.size, int)],
              names=('wave', 'thru_median', 'thru_mad', 'n_std'))
    t['wave'].unit = 'Angstrom'
    t['thru_median'].format = t['thru_mad'].format = '.6f'
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    t.meta = {
        'description': f'PROVISIONAL MOSFIRE filter-free throughput of the {group} band group: XTcalc 2012 '
                       f'efficiency x KMRef^2 with the shipped {group} filter divided out, over the filter '
                       f'half-power band. A placeholder until the group has reduced standards (plan S23a); '
                       f'not a calibration (design D1).',
        'instrument': 'keck_mosfire', 'band': f'{group} grating, filter-free', 'band_group': group,
        'era': None, 'standards': [], 'excluded': [], 'n_standards': 0,
        'filter_handling': ['XTcalc end-to-end efficiency divided by the shipped filter curve'],
        'valid_range_A': [float(grid[0]), float(grid[-1])],
        'band_median_era': round(float(np.median(thru)), 5),
        'source_file': f'external/xtcalc/XTcalc_dir/MosfireSpecEff/{src.name}', 'source_sha256': sha256sum(src),
        'kmref_per_surface': KMREF[group], 'filter_file': band.filter_file,
        'filter_sha256': sha256sum(DATA_DIR / band.filter_file),
        'pypeit_versions': ['none (XTcalc 2012)'], 'images': [], 'image_digests': [], 'pypeit_git_shas': [],
        'keck_etcs_git_shas': [],
        'bands': list(MOSFIRE.group_bands(group)),
        'calib_version': CALIB_VERSION, 'keck_etcs_version': keck_etcs.__version__, 'created': now,
        'script': SCRIPT,
    }
    rel = MOSFIRE.throughput_provisional_file(group)
    t.write(DATA_DIR / rel, format='ascii.ecsv', overwrite=True)
    entry = {'calib_version': CALIB_VERSION, 'bands': list(MOSFIRE.group_bands(group)), 'created': now,
             'sha256': sha256sum(DATA_DIR / rel), 'script': SCRIPT,
             'pypeit_version': 'none', 'waveref': 'vacuum',
             'provenance': f'PROVISIONAL placeholder: XTcalc 2012 {src.name} (sha256 {sha256sum(src)[:12]}) x '
                           f'{KMREF[group]}^2, divided by {band.filter_file}; no standard reduced in {group} yet'}
    print(f'{group}: {grid[0]:.0f}-{grid[-1]:.0f} A, median filter-free throughput {np.median(thru):.3f} '
          f'(end-to-end median {np.median(np.interp(grid, w, end_to_end)):.3f}) -> {rel}')
    return rel, entry


def write_index(entries):
    index = yaml.safe_load(INDEX.read_text()) or {}
    index.setdefault('files', {}).update(entries)
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--bands', nargs='+', default=['Y', 'H', 'K'])
    args = ap.parse_args(argv)
    entries = {}
    for group in args.bands:
        rel, entry = build(group)
        entries[rel] = entry
    write_index(entries)
    print(f'index.yaml updated ({len(entries)} entr(ies))')
    return 0


if __name__ == '__main__':
    sys.exit(main())
