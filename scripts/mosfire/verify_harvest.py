#!/usr/bin/env python
"""Verify the harvested per-standard table and curves (plan step S6).

Usage:
    conda run -n pypeit14b python scripts/mosfire/verify_harvest.py
        [--reharvest SENS.fits RUN_MANIFEST.json [--raw DIR]]

For every row of ``keck_etcs/data/mosfire/throughput/standards.ecsv``:

1. the columns are ``harvest.ROW_COLUMNS`` and every one is filled, except
   columns masked by construction (a ``zp_*`` node outside the curve;
   ``thru_median_common`` for ``nofilter`` rows);
2. ``thru_raw`` of the stored curve equals
   ``zeropoint_to_throughput(wave, zeropoint, 72.3674 m^2)`` recomputed from
   the stored zero point, to 1e-6 relative (before filter division);
3. ``pypeit_version`` ends with the short SHA of a PypeIt pin of one of
   the images in ``nautilus/README.md`` (section 3's table); whether it is
   the current pin (``nautilus/pypeit_pin.txt``) is printed, since rows
   harvested by earlier images keep their pin (the table is not re-harvested
   when the pin moves);
4. the curve's ``meta['row']`` equals the table row (the curve file belongs
   to the row) in every column but ``flag``, whose table value may carry
   the ``excluded_3mad`` that ``combine_throughput.py`` adds after the
   harvest; the other flags must agree.

With ``--reharvest``, the given sens file is harvested again in memory
(with the night's shipped filter curve divided out, as the night job does),
and every numeric column must match the table row to 1e-6 relative. That is
the "local harvest reproduces the in-pod row" check once a pod has harvested.
Exit status 1 if any check fails.
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

from keck_etcs.calib import harvest as hv

REPO = Path(__file__).resolve().parents[2]
TABLE = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'throughput' / 'standards.ecsv'
PIN = (REPO / 'nautilus' / 'pypeit_pin.txt').read_text().split()[0]
TOL = 1e-6
COMBINE_FLAGS = ('excluded_3mad',)
"""Flags the combine step adds to the table after the harvest (not in the curve meta)."""


def image_pins():
    """``{image tag: PypeIt pin}`` from the image table of ``nautilus/README.md``."""
    pins = {}
    for line in (REPO / 'nautilus' / 'README.md').read_text().splitlines():
        m = re.match(r'\| (\d+\.\d+\.\d+) \| `([0-9a-f]{40})`', line)
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def value(r, c):
    return None if np.ma.is_masked(r[c]) else r[c]


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float, np.integer, np.floating)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(b)))
    return str(a) == str(b)


def flags(value):
    return {f for f in str(value).split(',') if f and f != 'ok'}


def main(reharvest=None, raw=None):
    t = Table.read(TABLE, format='ascii.ecsv')
    ok = True
    if list(t.colnames) != list(hv.ROW_COLUMNS):
        print(f'standards.ecsv columns differ from harvest.ROW_COLUMNS: {t.colnames}')
        return 1
    columns = list(hv.ROW_COLUMNS)
    pins = image_pins()
    for r in t:
        key = (r['standard'], r['date'], r['koa_id'])
        curve = Table.read(TABLE.parent / str(r['thru_curve_file']), format='ascii.ecsv')
        blank = [c for c in columns if value(r, c) in (None, '')]
        nodes = [float(x) for x in str(r['zp_nodes_A']).split('/')]
        expected = [c for c, w in zip(hv.ZP_KEYS, nodes) if w > curve['wave'][-1] or w < curve['wave'][0]]
        if 'nofilter' in str(r['flag']):
            expected.append('thru_median_common')
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
        images = sorted(tag for tag, pin in pins.items() if pin.startswith(short))
        v_ok = bool(images)
        which = 'current pin' if PIN.startswith(short) else f'pin of image(s) {images}' if images else 'no image has this pin'
        print(f'  3. pypeit_version {r["pypeit_version"]}: {which} -> {"PASS" if v_ok else "FAIL"}')
        ok &= v_ok
        mrow = curve.meta['row']
        meta_ok = all(close(mrow.get(c), value(r, c)) for c in columns if c != 'flag' and c in mrow)
        flag_ok = flags(r['flag']) - set(COMBINE_FLAGS) == flags(mrow.get('flag'))
        print(f'  4. curve meta row == table row (but flag): {"PASS" if meta_ok else "FAIL"}; flags agree '
              f'(table may add {COMBINE_FLAGS}): {"PASS" if flag_ok else "FAIL"}')
        ok &= meta_ok and flag_ok
    if reharvest:
        import json
        from keck_etcs.instruments.base import DATA_DIR
        band = hv.band_of(json.loads(Path(reharvest[1]).read_text()))
        filt = None
        if band is not None and (DATA_DIR / band.filter_file).exists():
            ft = Table.read(DATA_DIR / band.filter_file, format='ascii.ecsv')
            filt = (np.asarray(ft['wave_A'], float), np.asarray(ft['transmission'], float))
            print(f'  5. re-harvest divides out {band.filter_file} (the night job does the same from image 0.2.0 on)')
        row, _ = hv.harvest(reharvest[0], reharvest[1], raw_dir=raw, filter_curve=filt)
        key = (row['standard'], row['date'], row['koa_id'])
        match = [r for r in t if (r['standard'], r['date'], r['koa_id']) == key]
        if not match:
            print(f'  5. re-harvest: no table row {key}: FAIL')
            return 1
        bad = [c for c in hv.ROW_COLUMNS if c not in ('thru_curve_file', 'flag') and not close(row[c], value(match[0], c))]
        if flags(row['flag']) != flags(match[0]['flag']) - set(COMBINE_FLAGS):
            bad.append('flag')
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
