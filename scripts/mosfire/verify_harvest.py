#!/usr/bin/env python
"""Verify the harvested per-standard table and curves (plan step S6).

Usage:
    conda run -n pypeit14b python scripts/mosfire/verify_harvest.py
        [--reharvest SENS.fits RUN_MANIFEST.json [--raw DIR]]

For every row of ``keck_etcs/data/mosfire/throughput/standards.ecsv``:

1. every column is filled, except columns masked by construction
   (``zp_1300`` when the curve ends before 1.30 um);
2. ``thru_raw`` of the stored curve equals
   ``zeropoint_to_throughput(wave, zeropoint, 72.3674 m^2)`` recomputed from
   the stored zero point, to 1e-6 relative (before filter division);
3. ``pypeit_version`` ends with the pin's short SHA (``nautilus/pypeit_pin.txt``);
4. the curve's ``meta['row']`` equals the table row (the curve file belongs
   to the row).

With ``--reharvest``, the given sens file is harvested again in memory, and
every numeric column must match the table row to 1e-6 relative. That is the
"local harvest reproduces the in-pod row" check once a pod has harvested.
Exit status 1 if any check fails.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

from keck_etcs.calib import harvest as hv

REPO = Path(__file__).resolve().parents[2]
TABLE = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'throughput' / 'standards.ecsv'
PIN = (REPO / 'nautilus' / 'pypeit_pin.txt').read_text().split()[0]
TOL = 1e-6


def value(r, c):
    return None if np.ma.is_masked(r[c]) else r[c]


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float, np.integer, np.floating)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(b)))
    return str(a) == str(b)


def main(reharvest=None, raw=None):
    t = Table.read(TABLE, format='ascii.ecsv')
    ok = True
    for r in t:
        key = (r['standard'], r['date'], r['koa_id'])
        curve = Table.read(TABLE.parent / str(r['thru_curve_file']), format='ascii.ecsv')
        blank = [c for c in hv.ROW_COLUMNS if value(r, c) in (None, '')]
        expected = [c for c, w in hv.ZP_WAVES.items() if w > curve['wave'][-1] or w < curve['wave'][0]]
        missing = [c for c in blank if c not in expected]
        print(f'{key}: image {r["image"]}')
        print(f'  1. columns filled: {"PASS" if not missing else "FAIL " + str(missing)}'
              f' (masked by construction: {expected or "none"})')
        ok &= not missing
        recomputed = hv.zeropoint_to_throughput(curve['wave'], curve['zeropoint'])
        rel = np.max(np.abs(recomputed / np.asarray(curve['thru_raw']) - 1))
        print(f'  2. thru_raw from zeropoint: max rel diff {rel:.2e} {"PASS" if rel < TOL else "FAIL"}')
        ok &= rel < TOL
        short = str(r['pypeit_version']).split('+g')[-1]
        v_ok = PIN.startswith(short)
        print(f'  3. pypeit_version {r["pypeit_version"]} vs pin {PIN[:9]}: {"PASS" if v_ok else "FAIL"}')
        ok &= v_ok
        meta_ok = all(close(curve.meta['row'][c], value(r, c)) for c in hv.ROW_COLUMNS)
        print(f'  4. curve meta row == table row: {"PASS" if meta_ok else "FAIL"}')
        ok &= meta_ok
    if reharvest:
        row, _ = hv.harvest(reharvest[0], reharvest[1], raw_dir=raw)
        key = (row['standard'], row['date'], row['koa_id'])
        match = [r for r in t if (r['standard'], r['date'], r['koa_id']) == key]
        if not match:
            print(f'  5. re-harvest: no table row {key}: FAIL')
            return 1
        bad = [c for c in hv.ROW_COLUMNS if c != 'thru_curve_file' and not close(row[c], value(match[0], c))]
        print(f'  5. re-harvest of {Path(reharvest[0]).name} vs table row: '
              f'{"PASS" if not bad else "FAIL " + str(bad)}')
        ok &= not bad
    print('VERIFY: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--reharvest', nargs=2, metavar=('SENS', 'RUN_MANIFEST'))
    p.add_argument('--raw', help='raw directory for --reharvest')
    a = p.parse_args()
    sys.exit(main(a.reharvest, a.raw))
