#!/usr/bin/env python
"""One-off: migrate ``standards.ecsv`` from the J column names to the band-neutral ones (plan S23b, design D49).

Usage:
    conda run -n pypeit14b python scripts/mosfire/migrate_standards_table.py [--calib-version mosfire-2026.10]

Release ``mosfire-J-2026.10`` harvested every row with the J-only metrics
``zp_1200``, ``zp_1250``, ``zp_1300`` (zero point at 12000/12500/13000 A for
every row, J2 included) and ``thru_median_1117_1260``,
``thru_median_1117_1250`` (medians of ``thru_raw``, filter included). Since
S23a ``keck_etcs.calib.harvest`` writes ``zp_lo``, ``zp_mid``, ``zp_hi`` at
the band's own nodes (J 12000/12500/13000, J2 11500/12000/12500 A;
``zp_nodes_A``) and ``thru_median_common``, the median of the filter-free
``thru`` over the group's common window (``common_window_A``, 11900-12450 A).

The harvest files synced under ``$KECK_ETCS_DATA`` are the in-pod outputs
with the old columns, and a local re-harvest would not reproduce every row
(the raw frames behind ``excluded_nonlinear`` are not all local), so this
script recomputes the four metrics **from the committed curves** with the
harvest's own functions (``harvest.zp_at`` on the curve's ``zeropoint``,
``harvest.median_in`` on ``thru``; both are what ``harvest.harvest`` calls)
and copies every other column unchanged. For J rows ``zp_lo/mid/hi`` must
equal the old ``zp_1200/1250/1300`` exactly, and for J2 rows ``zp_mid`` and
``zp_hi`` the old ``zp_1200`` and ``zp_1250``; the script checks that and
prints the old and new values per row.

It also:

- rewrites each curve's ``meta['row']`` with the new columns (the
  ``flag`` stays the harvest-time one, without the ``excluded_3mad`` that
  ``combine_throughput.py`` adds to the table) and adds ``band_group``;
  the curve data are untouched (asserted);
- stamps the table and its ``index.yaml`` entry with ``--calib-version``;
- drops the ``index.yaml`` entries of the old era files
  ``mosfire/throughput/mosfire_thru_<tag>.ecsv`` (renamed
  ``mosfire_thru_J_<tag>.ecsv`` by ``combine_throughput.py``) and prints the
  ``git rm`` lines for the user, who runs git.

Idempotent: a table that already has ``zp_nodes_A`` is left alone.
"""
import argparse
import datetime
import hashlib
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table

from keck_etcs.calib import harvest as hv
from keck_etcs.calib import trend
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
THRU = DATA_DIR / 'mosfire' / 'throughput'
TABLE = THRU / 'standards.ecsv'
INDEX = DATA_DIR / 'index.yaml'
SCRIPT = 'scripts/mosfire/migrate_standards_table.py'
OLD_ZP = ('zp_1200', 'zp_1250', 'zp_1300')
OLD_NODES = (12000.0, 12500.0, 13000.0)
OLD_MEDIANS = ('thru_median_1117_1260', 'thru_median_1117_1250')
OLD_ERA_PATTERN = 'mosfire/throughput/mosfire_thru_{tag}.ecsv'


def value(r, c):
    if c not in r.colnames or np.ma.is_masked(r[c]):
        return None
    v = r[c]
    return v.item() if hasattr(v, 'item') else v


def same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= 1e-12 * max(1.0, abs(float(b)))


def data_lines(path):
    return [ln for ln in Path(path).read_text().splitlines() if not ln.startswith('#')]


def write_index(index):
    head = ''.join(ln for ln in INDEX.read_text().splitlines(keepends=True) if ln.startswith('#'))
    INDEX.write_text(head + yaml.safe_dump(index, sort_keys=False, width=100))


def main(calib_version):
    t = Table.read(TABLE, format='ascii.ecsv')
    if 'zp_nodes_A' in t.colnames:
        print(f'{TABLE.relative_to(REPO)} already has the band-neutral columns; nothing to do')
        return 0
    missing = [c for c in OLD_ZP + OLD_MEDIANS if c not in t.colnames]
    if missing:
        print(f'table lacks the old columns {missing}; not a mosfire-J-2026.10 table')
        return 1
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    rows, bad = [], []
    print(f'{"standard":10s} {"date":10s} {"filt":4s} | old zp_1200 zp_1250 zp_1300 thru_1117_1260 | '
          'new zp_lo zp_mid zp_hi (nodes) thru_common (window) | checks')
    for r in t:
        band = MOSFIRE.bands[str(r['filter'])]
        cpath = THRU / str(r['thru_curve_file'])
        curve = Table.read(cpath, format='ascii.ecsv')
        new = {c: value(r, c) for c in hv.ROW_COLUMNS if c in t.colnames}
        zp = {k: hv.zp_at(curve, w) for k, w in zip(hv.ZP_KEYS, band.zp_nodes_A)}
        nofilter = 'nofilter' in str(r['flag']) or np.all(np.ma.getmaskarray(curve['thru']))
        tmc = None if nofilter else hv.median_in(curve, *band.common_window_A, col='thru')
        new.update(zp)
        new['thru_median_common'] = tmc
        new['zp_nodes_A'] = hv.zp_nodes_str(band.zp_nodes_A)
        new['common_window_A'] = hv.window_str(band.common_window_A)
        rows.append(new)
        # the old values at the same nodes must come back exactly (same function on the same curve)
        checks = []
        for k, w in zip(hv.ZP_KEYS, band.zp_nodes_A):
            if w in OLD_NODES:
                old = value(r, OLD_ZP[OLD_NODES.index(w)])
                checks.append(same(zp[k], old))
        tc = trend.curve_common_median(curve['wave'], curve['thru'], band.common_window_A)
        checks.append(same(tmc, None if np.isnan(tc) else tc))
        ok = all(checks)
        if not ok:
            bad.append((str(r['standard']), str(r['date'])))
        fmt = lambda v: '   -  ' if v is None else f'{float(v):6.3f}'
        print(f"{str(r['standard']):10s} {str(r['date']):10s} {str(r['filter']):4s} | "
              f"{fmt(value(r, 'zp_1200'))} {fmt(value(r, 'zp_1250'))} {fmt(value(r, 'zp_1300'))} "
              f"{fmt(value(r, 'thru_median_1117_1260'))} | {fmt(zp['zp_lo'])} {fmt(zp['zp_mid'])} "
              f"{fmt(zp['zp_hi'])} ({new['zp_nodes_A']}) {fmt(tmc)} ({new['common_window_A']}) | "
              f"{'PASS' if ok else 'FAIL'}")
        # the curve's meta row: new columns, harvest-time flag, band group; data lines untouched
        before = data_lines(cpath)
        meta_row = dict(new)
        meta_row['flag'] = curve.meta.get('row', {}).get('flag', new['flag'])
        curve.meta['row'] = {k: meta_row[k] for k in hv.ROW_COLUMNS}
        keys = list(curve.meta.keys())
        if 'band_group' not in keys:
            # keep the harvest's key order: band_group right after band
            items = list(curve.meta.items())
            i = next(j for j, (k, _) in enumerate(items) if k == 'band') + 1
            items.insert(i, ('band_group', band.group_name))
            curve.meta.clear()
            curve.meta.update(items)
        curve.meta['row_columns_migrated'] = f'{now} ({SCRIPT}, S23b)'
        curve.write(cpath, format='ascii.ecsv', overwrite=True)
        assert data_lines(cpath) == before, f'curve data changed: {cpath}'
    if bad:
        print(f'FAIL: recomputed metrics differ from the old columns for {bad}; table not written')
        return 1

    out = hv.row_table(rows)
    out.sort(['date', 'standard'])
    out.meta.update({
        'description': 'MOSFIRE per-standard zero points and throughput (design 4.4); '
                       'one row per standard per night; curves in standards/',
        'calib_version': calib_version,
        'row_created': dict(t.meta.get('row_created', {})),
        'merged': t.meta.get('merged'),
        'migrated': now,
        'migration': 'S23b (design D49, 9.3): zp_1200/1250/1300 and thru_median_1117_1260/1250 replaced by '
                     'zp_lo/zp_mid/zp_hi at the band nodes (zp_nodes_A) and thru_median_common over the group '
                     'common window (common_window_A), recomputed from the committed curves with '
                     'keck_etcs.calib.harvest; every other column unchanged',
        'script': SCRIPT, 'eff_aperture_m2': hv.EFF_APERTURE})
    out.write(TABLE, format='ascii.ecsv', overwrite=True)
    print(f'{len(out)} row(s) written to {TABLE.relative_to(REPO)} with columns {list(hv.ROW_COLUMNS)}')

    index = yaml.safe_load(INDEX.read_text()) or {}
    files = index.setdefault('files', {})
    files['mosfire/throughput/standards.ecsv'] = {
        'calib_version': calib_version, 'created': now,
        'sha256': hashlib.sha256(TABLE.read_bytes()).hexdigest(),
        'script': 'scripts/mosfire/harvest_sens.py --merge; ' + SCRIPT,
        'provenance': f'{len(out)} per-standard rows harvested from PypeIt IR sensfuncs (keck_etcs.calib.harvest); '
                      f'curves in mosfire/throughput/standards/; metric columns migrated to zp_lo/mid/hi and '
                      f'thru_median_common (S23b)'}
    removed = []
    for era in MOSFIRE.eras:
        old = OLD_ERA_PATTERN.format(tag=era.tag)
        if old in files:
            del files[old]
            removed.append(old)
    write_index(index)
    print(f'index.yaml: standards.ecsv entry updated; {len(removed)} old era-file entr(ies) dropped')
    if removed:
        print('The old J era files are replaced by mosfire_thru_J_<tag>.ecsv (combine_throughput.py). '
              'Git is yours; after the combine step run:')
        for old in removed:
            print(f'    git rm keck_etcs/data/{old}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--calib-version', default='mosfire-2026.10')
    a = p.parse_args()
    sys.exit(main(a.calib_version))
