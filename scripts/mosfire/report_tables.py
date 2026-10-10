#!/usr/bin/env python
"""Markdown tables for the MOSFIRE report (``reports/Keck_MOSFIRE_report_20261009.md``).

Usage:
    conda run -n pypeit14b python scripts/mosfire/report_tables.py

Prints, from the committed products only (``keck_etcs/data/mosfire/``):

1. the per-standard table: date, star, class, filter, mask
   (``long2pos_specphot`` 4" bar for one-bar rows, else ``LONGSLIT-46x<w>``),
   read mode, exposure, airmass, fitted PWV (``*`` = extrapolated beyond
   the grid), ``zp_1250``,
   ``thru_common`` (median filter-free throughput over 11900-12450 A,
   ``keck_etcs.calib.trend``), era, and the row flags;
2. per era: n, median and MAD of ``thru_common`` (rows in the era curves),
   and the slope in percent per year (``trend.era_stats``);
3. the release ETC predictions: band-median S/N per pixel for a J = 20 AB
   point source with the schema defaults, per era and band.
"""
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

from keck_etcs import etc
from keck_etcs.calib import trend
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

THRU = DATA_DIR / 'mosfire' / 'throughput'
ERA_DATE = {'2012-04..2016-09': '2014-06-01', '2017-02..2025-02': '2020-01-01', '2025-04..': '2025-08-01'}


def main():
    rows = Table.read(THRU / 'standards.ecsv', format='ascii.ecsv')
    common = []
    print('| Date | Star | Class | Filter | Mask | Read | t [s] | Airmass | PWV [mm] | zp_1250 | thru_common '
          '| Era | Flag |')
    print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        c = Table.read(THRU / 'standards' / Path(str(r['thru_curve_file'])).name, format='ascii.ecsv')
        tc = trend.curve_common_median(c['wave'], c['thru'])
        common.append(tc)
        era = getattr(trend.era_of(str(r['date']), MOSFIRE.eras), 'name', '-')
        read = 'CDS' if int(r['sampmode']) == 2 else f"MCDS-{int(r['numreads'])}"
        flag = ', '.join(f for f in str(r['flag']).split(',') if f not in ('ok', 'pwv_extrapolated')) or '-'
        mask = (f"long2pos_specphot {float(r['slit_width']):g}\"" if float(r['slit_length']) <= 1
                else f"LONGSLIT-{int(r['slit_length'])}x{float(r['slit_width']):g}")
        pwv = f"{float(r['pwv_fit']):.1f}" + ('*' if 'pwv_extrapolated' in str(r['flag']) else '')
        zp = r['zp_1250']
        zp = f'{float(zp):.2f}' if not np.ma.is_masked(zp) and np.isfinite(float(zp)) else '-'
        print(f"| {r['date']} | {str(r['standard']).lstrip('*')} | {r['std_class']} | {r['filter']} | "
              f"{mask} | {read} | {float(r['exptime']):.1f} | "
              f"{float(r['airmass']):.2f} | {pwv} | {zp} | {tc:.3f} | {era} | {flag} |")
    print()
    used = np.array(['excluded' not in str(f) for f in rows['flag']])
    dates = [str(d) for d in np.asarray(rows['date'])[used]]
    vals = np.asarray(common)[used]
    print('| Era | n | thru_common median | MAD | slope [%/yr] |')
    print('|---|---|---|---|---|')
    for s in trend.era_stats(dates, vals, MOSFIRE.eras):
        slope = '-' if s['slope_pct_yr'] is None or not np.isfinite(s['slope_pct_yr']) else \
            f"{s['slope_pct_yr']:+.1f} +- {s['slope_err']:.1f}"
        mad = '-' if s['n'] < 2 else f"{100 * s['mad'] / s['median']:.1f} %"
        print(f"| {s['era']} | {s['n']} | {s['median']:.3f} | {mad} | {slope} |")
    print()
    print('| Era | J: S/N per pixel | J: per resel | J2: S/N per pixel | J2: per resel |')
    print('|---|---|---|---|---|')
    for era in MOSFIRE.eras:
        cells = []
        for band in ('J', 'J2'):
            o = etc.compute({'band': band, 'source': {'mag': 20.0}, 'throughput': {'date': ERA_DATE[era.name]}})
            cells += [f"{o['summary']['snr_pixel_median']:.2f}", f"{o['summary']['snr_resel_median']:.2f}"]
        print(f"| {era.name} | " + ' | '.join(cells) + ' |')
    return 0


if __name__ == '__main__':
    sys.exit(main())
