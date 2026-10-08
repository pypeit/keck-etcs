#!/usr/bin/env python
"""Checks of a MOSFIRE calibration release (plan S16 "Verify").

Usage:
    conda run -n pypeit14b python scripts/mosfire/verify_release.py

1. ``compute`` with ``throughput.date`` in each era (bands J and J2) returns
   that era's curve: ``meta.era`` is the era, the throughput file is the
   era's, and ``meta.calib_version`` is the release.
2. The 2012-04..2016-09 era median against XTcalc's 2012 curve
   (``$KECK_ETCS_DATA/external/xtcalc/XTcalc_dir/MosfireSpecEff/Jeff.sm.dat``
   x KMRef^2 = 0.89, as ``compare_xtcalc.py``), after the aperture
   correction: XTcalc's efficiency is defined for 75 m^2 and ours for the
   effective 72.37 m^2 (``harvest.EFF_APERTURE``), so XTcalc's
   equivalent is ``eff x 75 / 72.37``. Reported in 250 A bins and as the
   median ratio over the overlap; the target is agreement at about 10
   percent.
3. ``zp_1250`` against airmass, within each filter, over the rows that
   entered an era curve (residuals after era medians): no correlation
   beyond 2 sigma.
4. Every row that entered an era curve has a non-empty ``image_digest`` and
   ``pypeit_git_sha``; the distinct (image, digest, PypeIt sha) triplets are
   printed for ``CHANGES.md``.

Read-only. Exit 1 when a check fails.
"""
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

from keck_etcs import etc, paths
from keck_etcs.calib import trend
from keck_etcs.calib.harvest import EFF_APERTURE
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

RELEASE = 'mosfire-J-2026.10'
DATES = {'2012-04..2016-09': '2014-06-01', '2017-02..2025-02': '2020-01-01', '2025-04..': '2025-08-01'}
XT_AREA = 75.0
KMREF = 0.89


def main():
    bad = []
    print('1. compute per era')
    for era in MOSFIRE.eras:
        for band in ('J', 'J2'):
            out = etc.compute({'band': band, 'throughput': {'date': DATES[era.name]}})
            m = out['meta']
            ok = m['era'] == era.name and m['calib_version'] == RELEASE
            print(f"   {DATES[era.name]} {band:2s}: meta.era {m['era']}, calib_version {m['calib_version']}"
                  f" -> {'OK' if ok else 'FAIL'}")
            if not ok:
                bad.append(f'compute {era.name} {band}')

    print('2. 2012-04..2016-09 against XTcalc 2012 (x 75 / 72.37 m^2)')
    t = Table.read(DATA_DIR / MOSFIRE.throughput_file(MOSFIRE.eras[0]), format='ascii.ecsv')
    xf = paths.data_root() / 'external' / 'xtcalc' / 'XTcalc_dir' / 'MosfireSpecEff' / 'Jeff.sm.dat'
    if not xf.exists():
        print(f'   XTcalc file not found: {xf}')
        bad.append('xtcalc file')
    else:
        xw, xe = np.loadtxt(xf, unpack=True)
        xeq = np.clip(xe, 0, None) * KMREF ** 2 * XT_AREA / EFF_APERTURE
        w, th = np.asarray(t['wave'], float), np.asarray(t['thru_median'], float)
        xi = np.interp(w, xw, xeq, left=np.nan, right=np.nan)
        ok = np.isfinite(xi) & (xi > 0) & np.isfinite(th)
        for lo in np.arange(np.floor(w[ok].min() / 250) * 250, w[ok].max(), 250):
            s = ok & (w >= lo) & (w < lo + 250)
            if s.sum() > 50:
                print(f'   {lo:6.0f}-{lo + 250:6.0f} A: ours {np.median(th[s]):.4f}, XTcalc {np.median(xi[s]):.4f}, '
                      f'ratio {np.median(th[s] / xi[s]):.3f}')
        r = float(np.median(th[ok] / xi[ok]))
        print(f'   overlap {w[ok].min():.0f}-{w[ok].max():.0f} A: median ratio ours/XTcalc {r:.3f} '
              f'({100 * (r - 1):+.1f} %) -> {"within 10 %" if abs(r - 1) <= 0.10 else "beyond 10 %, discuss"}')

    print('3. zp_1250 against airmass (rows in era curves, residuals after era medians)')
    rows = Table.read(DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    used = np.array(['excluded' not in str(f) for f in rows['flag']])
    eras = [getattr(trend.era_of(str(d), MOSFIRE.eras), 'name', 'none') for d in rows['date']]
    for band in sorted({str(b) for b in rows['filter']}):
        s = used & (np.asarray(rows['filter']) == band)
        c = trend.correlation(np.asarray(rows['airmass'], float)[s], np.asarray(rows['zp_1250'], float)[s],
                              by_era=np.asarray(eras)[s])
        ok = not (c['sigma'] > 2)
        print(f"   {band}: n={c['n']} r={c['r']:+.3f} -> {c['sigma']:.2f} sigma {'OK' if ok else 'FAIL (> 2 sigma)'}")
        if not ok:
            bad.append(f'zp-airmass {band}')

    print('4. provenance of the rows in the era curves')
    triplets = set()
    for era in MOSFIRE.eras:
        et = Table.read(DATA_DIR / MOSFIRE.throughput_file(era), format='ascii.ecsv')
        for s in et.meta['standards']:
            r = [x for x in rows if str(x['standard']) == s['standard'] and str(x['date']) == s['date']][0]
            if not str(r['image_digest']).startswith('sha256:') or len(str(r['pypeit_git_sha'])) != 40:
                bad.append(f"provenance {s['standard']} {s['date']}")
            triplets.add((str(r['image']), str(r['image_digest']), str(r['pypeit_git_sha'])))
        print(f"   {era.name}: {len(et.meta['standards'])} standards, excluded {et.meta['excluded']}")
    for tr in sorted(triplets):
        print(f'   {tr[0]} | {tr[1]} | PypeIt {tr[2]}')
    print('ALL CHECKS PASS' if not bad else f'FAILED: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
