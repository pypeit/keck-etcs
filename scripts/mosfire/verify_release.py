#!/usr/bin/env python
"""Checks of a MOSFIRE calibration release (plan S16 "Verify"; per band group since S23b, D49).

Usage:
    conda run -n pypeit14b python scripts/mosfire/verify_release.py

0. **Names and registration.** Every throughput product in ``index.yaml``
   is ``mosfire/throughput/mosfire_thru_<group>_<era tag | provisional>.ecsv``
   for a band group of the instrument module and carries ``bands``; no
   file of the pre-S23b form ``mosfire_thru_<era tag>.ecsv`` is registered
   (an unregistered file on disk, e.g. an old name not yet removed with
   ``git rm``, is printed as a warning).
   A group with a measured era file is *released*; a group with only its
   ``provisional-*`` placeholder is listed and skipped by the checks below.
1. ``compute`` with ``throughput.date`` in each era, for every band of
   every released group, returns that era's curve: ``meta.era`` is the era,
   the file used is ``Instrument.throughput_file(era, group)``, and
   ``meta.calib_version`` is the release.
2. The 2012-04..2016-09 era median of each released group against XTcalc's
   2012 curve (``$KECK_ETCS_DATA/external/xtcalc/XTcalc_dir/MosfireSpecEff/<group>eff.sm.dat``
   x KMRef^2, as ``compare_xtcalc.py`` and ``build_provisional_throughput.py``),
   after the aperture correction: XTcalc's efficiency is defined for 75 m^2
   and ours for the effective 72.37 m^2 (``harvest.EFF_APERTURE``), so
   XTcalc's equivalent is ``eff x 75 / 72.37``. XTcalc's efficiency includes
   the order-sorting filter, so our filter-free curve is multiplied by the
   group's first filter before the ratio (corrected 2026-10-09; the first
   release log's +3.6 percent compared a filter-free curve with a filtered
   one). Reported in 250 A bins and as the median ratio over the overlap;
   the target is agreement at about 10 percent.
3. ``zp_mid`` (the zero point at the band's middle node) against airmass,
   within each filter, over the rows that entered an era curve (residuals
   after era medians): no correlation beyond 2 sigma.
4. Every row that entered an era curve has a non-empty ``image_digest`` and
   ``pypeit_git_sha``; the distinct (image, digest, PypeIt sha) triplets are
   printed for ``CHANGES.md``.

Read-only. Exit 1 when a check fails.
"""
import re
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table

from keck_etcs import etc, paths
from keck_etcs.calib import trend
from keck_etcs.calib.harvest import EFF_APERTURE
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

RELEASE = 'mosfire-2026.10'
DATES = {'2012-04..2016-09': '2014-06-01', '2017-02..2025-02': '2020-01-01', '2025-04..': '2025-08-01'}
XT_AREA = 75.0
KMREF = {'Y': 0.85, 'J': 0.89, 'H': 0.94, 'K': 0.95}      # XTcalc's Keck mirror reflectivity per surface, per band
THRU_PREFIX = 'mosfire/throughput/mosfire_thru_'


def released_groups():
    groups = sorted({b.group_name for b in MOSFIRE.bands.values()})
    measured = [g for g in groups if any(MOSFIRE._throughput_exists(e, g) for e in MOSFIRE.eras)]
    return groups, measured


def main():
    bad = []
    groups, measured = released_groups()
    print('0. throughput products registered in index.yaml')
    index = yaml.safe_load((DATA_DIR / 'index.yaml').read_text())['files']
    pat = re.compile(r'mosfire_thru_(?P<group>[A-Za-z0-9]+)_(?P<tag>[0-9]{4}-(?:[0-9]{4}|on)|provisional)\.ecsv$')
    for key, entry in sorted(index.items()):
        if not key.startswith(THRU_PREFIX) or key.endswith('standards.ecsv'):
            continue
        m = pat.search(key)
        ok = m is not None and m.group('group') in groups and isinstance(entry.get('bands'), list) \
            and set(entry['bands']) == set(MOSFIRE.group_bands(m.group('group'))) and (DATA_DIR / key).exists()
        print(f"   {key}: {entry.get('calib_version')}, bands {entry.get('bands')} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            bad.append(f'index {key}')
    for g in groups:
        print(f"   group {g} ({', '.join(MOSFIRE.group_bands(g))}): "
              + ('released (measured era file)' if g in measured else 'provisional placeholder only; skipped'))
    stray = sorted(f.name for f in (DATA_DIR / 'mosfire' / 'throughput').glob('mosfire_thru_*.ecsv')
                   if f'mosfire/throughput/{f.name}' not in index)
    if stray:
        print(f'   WARN: throughput files on disk that index.yaml does not register (git rm them): {stray}')

    print('1. compute per era, band and released group')
    for g in measured:
        for era in MOSFIRE.eras:
            for band in MOSFIRE.group_bands(g):
                out = etc.compute({'band': band, 'throughput': {'date': DATES[era.name]}})
                m = out['meta']
                th = MOSFIRE.throughput(era, g)
                ok = (m['era'] == era.name and m['calib_version'] == RELEASE
                      and th['file'] == MOSFIRE.throughput_file(era, g) and not th['provisional'])
                print(f"   {DATES[era.name]} {band:2s}: meta.era {m['era']}, calib_version {m['calib_version']}, "
                      f"file {th['file']} -> {'OK' if ok else 'FAIL'}")
                if not ok:
                    bad.append(f'compute {era.name} {band}')

    print('2. 2012-04..2016-09 x filter against XTcalc 2012 (x 75 / 72.37 m^2)')
    for g in measured:
        era0 = MOSFIRE.eras[0]
        if not MOSFIRE._throughput_exists(era0, g):
            print(f'   group {g}: no {era0.name} file; skipped')
            continue
        t = Table.read(DATA_DIR / MOSFIRE.throughput_file(era0, g), format='ascii.ecsv')
        xf = paths.data_root() / 'external' / 'xtcalc' / 'XTcalc_dir' / 'MosfireSpecEff' / f'{g}eff.sm.dat'
        if not xf.exists():
            print(f'   XTcalc file not found: {xf}')
            bad.append(f'xtcalc file {g}')
            continue
        xw, xe = np.loadtxt(xf, unpack=True)
        xeq = np.clip(xe, 0, None) * KMREF[g] ** 2 * XT_AREA / EFF_APERTURE
        w, th = np.asarray(t['wave'], float), np.asarray(t['thru_median'], float)
        band0 = MOSFIRE.group_bands(g)[0]
        fc = MOSFIRE.filter_curve(band0)
        th = th * np.interp(w, fc['wave_A'], fc['transmission'], left=0.0, right=0.0)      # XTcalc's efficiency includes the filter
        xi = np.interp(w, xw, xeq, left=np.nan, right=np.nan)
        ok = np.isfinite(xi) & (xi > 0) & np.isfinite(th)
        print(f'   group {g} (x {band0} filter, KMRef {KMREF[g]}):')
        for lo in np.arange(np.floor(w[ok].min() / 250) * 250, w[ok].max(), 250):
            s = ok & (w >= lo) & (w < lo + 250)
            if s.sum() > 50:
                print(f'   {lo:6.0f}-{lo + 250:6.0f} A: ours {np.median(th[s]):.4f}, XTcalc {np.median(xi[s]):.4f}, '
                      f'ratio {np.median(th[s] / xi[s]):.3f}')
        r = float(np.median(th[ok] / xi[ok]))
        print(f'   overlap {w[ok].min():.0f}-{w[ok].max():.0f} A: median ratio ours/XTcalc {r:.3f} '
              f'({100 * (r - 1):+.1f} %) -> {"within 10 %" if abs(r - 1) <= 0.10 else "beyond 10 %, discuss"}')

    print('3. zp_mid against airmass (rows in era curves, residuals after era medians)')
    rows = Table.read(DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    used = np.array(['excluded' not in str(f) for f in rows['flag']])
    eras = [getattr(trend.era_of(str(d), MOSFIRE.eras), 'name', 'none') for d in rows['date']]
    for band in sorted({str(b) for b in rows['filter']}):
        s = used & (np.asarray(rows['filter']) == band)
        node = str(rows['zp_nodes_A'][s][0]).split('/')[1] if s.any() else '?'
        c = trend.correlation(np.asarray(rows['airmass'], float)[s], np.asarray(rows['zp_mid'], float)[s],
                              by_era=np.asarray(eras)[s])
        ok = not (c['sigma'] > 2)
        print(f"   {band} (zp_mid at {node} A): n={c['n']} r={c['r']:+.3f} -> {c['sigma']:.2f} sigma "
              f"{'OK' if ok else 'FAIL (> 2 sigma)'}")
        if not ok:
            bad.append(f'zp-airmass {band}')

    print('4. provenance of the rows in the era curves')
    triplets = set()
    for g in measured:
        for era in MOSFIRE.eras:
            if not MOSFIRE._throughput_exists(era, g):
                continue
            et = Table.read(DATA_DIR / MOSFIRE.throughput_file(era, g), format='ascii.ecsv')
            for s in et.meta['standards']:
                r = [x for x in rows if str(x['standard']) == s['standard'] and str(x['date']) == s['date']][0]
                if not str(r['image_digest']).startswith('sha256:') or len(str(r['pypeit_git_sha'])) != 40:
                    bad.append(f"provenance {s['standard']} {s['date']}")
                triplets.add((str(r['image']), str(r['image_digest']), str(r['pypeit_git_sha'])))
            print(f"   group {g}, {era.name}: {len(et.meta['standards'])} standards, excluded {et.meta['excluded']}")
    for tr in sorted(triplets):
        print(f'   {tr[0]} | {tr[1]} | PypeIt {tr[2]}')
    print('ALL CHECKS PASS' if not bad else f'FAILED: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
