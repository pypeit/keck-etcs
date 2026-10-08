#!/usr/bin/env python
"""MOSFIRE throughput trend: zero point and filter-free throughput against date (design 4.6; plan S16).

Usage:
    conda run -n pypeit14b python scripts/mosfire/plot_throughput_trend.py [--png docs/figures/mosfire_throughput_trend.png]

Reads ``keck_etcs/data/mosfire/throughput/standards.ecsv`` and the curves it
points to. For every row, ``thru_common`` (``keck_etcs.calib.trend``: the
median filter-free throughput over the common window, comparable across J
and J2) is computed from its curve. Prints, per era of
``keck_etcs.instruments.mosfire``:

- the median, MAD and slope (percent per year, with its error) of
  ``thru_common`` over the rows that can enter an era curve (not
  ``excluded``), and of ``zp_1250`` per filter (it includes the filter, and
  J2's red cut-off falls at 1.25 um, so filters are not mixed);
- the correlation of ``thru_common`` with airmass, PWV (``pwv_fit``) and
  slit width, on residuals after each era's median is removed (a residual
  airmass trend would mean an incomplete telluric division).

Plots ``zp_1250`` (J and J2 separately) and ``thru_common`` against date,
with the era boundaries, the excluded rows marked as open symbols.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

from keck_etcs.calib import trend
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
THRU = DATA_DIR / 'mosfire' / 'throughput'


def load():
    rows = Table.read(THRU / 'standards.ecsv', format='ascii.ecsv')
    common = []
    for r in rows:
        c = Table.read(THRU / str(r['thru_curve_file']), format='ascii.ecsv')
        common.append(trend.curve_common_median(c['wave'], c['thru']))
    rows['thru_common'] = common
    return rows


def fmt(s):
    if not s['n']:
        return f"{s['era']:17s} n=0"
    slope = ('-' if s['slope_pct_yr'] is None else f"{s['slope_pct_yr']:+.2f} +- {s['slope_err']:.2f} %/yr")
    return (f"{s['era']:17s} n={s['n']:2d} median {s['median']:.4f} MAD {s['mad']:.4f} "
            f"({s['mad_pct']:.1f} %) slope {slope}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--png', default=str(REPO / 'docs' / 'figures' / 'mosfire_throughput_trend.png'))
    a = ap.parse_args(argv)
    rows = load()
    use = np.array(['excluded' not in str(f) for f in rows['flag']])
    eras = MOSFIRE.eras
    print(f'{len(rows)} rows, {int(use.sum())} usable (not excluded); common window {trend.COMMON_WINDOW} A')
    print('thru_common (filter-free), usable rows:')
    for s in trend.era_stats(list(rows['date'][use]), list(rows['thru_common'][use]), eras):
        print('  ' + fmt(s))
    for band in sorted({str(b) for b in rows['filter']}):
        sel = use & (np.asarray(rows['filter']) == band)
        print(f'zp_1250, filter {band}, usable rows (median in mag; MAD and slope of the flux 10^(0.4 zp)):')
        zp = np.asarray(rows['zp_1250'], float)[sel]
        for s in trend.era_stats(list(rows['date'][sel]), list(10 ** (0.4 * (zp - 19.0))), eras):
            if s['n']:
                s['median'] = 19.0 + 2.5 * np.log10(s['median'])
                s['mad'] = 2.5 * np.log10(1 + s['mad_pct'] / 100.0)
            print('  ' + fmt(s).replace('MAD ', 'MAD [mag] '))
    era_lab = [getattr(trend.era_of(d, eras), 'name', 'none') for d in rows['date']]
    y = np.asarray(rows['thru_common'], float)
    print('correlation of thru_common residuals (era medians removed), usable rows:')
    for col in ('airmass', 'pwv_fit', 'slit_width'):
        x = np.ma.filled(np.ma.asarray(rows[col], float), np.nan)
        c = trend.correlation(x[use], y[use], by_era=np.asarray(era_lab)[use])
        print(f"  {col:10s} n={c['n']:2d} r={c['r']:+.3f} p={c['p']:.3f} -> {c['sigma']:.2f} sigma"
              + ('  ** > 2 sigma' if c['sigma'] > 2 else ''))
    # zp_1250 against airmass within one filter (the release check of plan S16)
    for band in sorted({str(b) for b in rows['filter']}):
        sel = use & (np.asarray(rows['filter']) == band)
        c = trend.correlation(np.asarray(rows['airmass'], float)[sel], np.asarray(rows['zp_1250'], float)[sel],
                              by_era=np.asarray(era_lab)[sel])
        print(f"  zp_1250 vs airmass, {band}: n={c['n']} r={c['r']:+.3f} -> {c['sigma']:.2f} sigma")

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    yr = np.array([trend.decimal_year(d) for d in rows['date']])
    fig, axs = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True)
    marks = {'J': ('o', 'C0'), 'J2': ('s', 'C1')}
    for band, (m, col) in marks.items():
        sel = np.asarray(rows['filter']) == band
        for u, face in ((use, col), (~use, 'none')):
            s = sel & u
            if s.any():
                axs[0].plot(yr[s], rows['zp_1250'][s], m, mfc=face, mec=col, ls='',
                            label=f'{band}' + ('' if face != 'none' else ' (excluded)'))
                axs[1].plot(yr[s], rows['thru_common'][s], m, mfc=face, mec=col, ls='')
    for era in eras:
        for ax in axs:
            ax.axvline(trend.decimal_year(era.start), color='0.6', lw=0.8, ls='--')
        sel = use & np.array([trend.in_era(d, era) for d in rows['date']])
        if sel.any():
            med = float(np.median(rows['thru_common'][sel]))
            x1 = trend.decimal_year(era.end) if era.end else yr.max() + 0.3
            axs[1].hlines(med, trend.decimal_year(era.start), x1, color='k', lw=1)
            axs[1].text(trend.decimal_year(era.start) + 0.05, med + 0.004, f'{era.name}: {med:.3f}', fontsize=7)
    axs[0].set_ylabel('zp_1250 [mag] (filter included)')
    axs[0].invert_yaxis()
    axs[0].legend(fontsize=8, ncol=2)
    axs[1].set_ylabel(f'filter-free throughput\n{trend.COMMON_WINDOW[0]:.0f}-{trend.COMMON_WINDOW[1]:.0f} A')
    axs[1].set_xlabel('year')
    fig.suptitle('Keck/MOSFIRE J throughput from standard stars (era boundaries dashed)', fontsize=10)
    fig.tight_layout()
    Path(a.png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.png, dpi=120)
    print(f'wrote {Path(a.png).relative_to(REPO) if Path(a.png).is_relative_to(REPO) else a.png}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
