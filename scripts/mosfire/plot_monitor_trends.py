#!/usr/bin/env python
"""Calibration-monitor trends: per-era 3-MAD flags and four figures (design 4.6, 4.9, D47; plan S16).

Usage:
    conda run -n pypeit14b python scripts/mosfire/plot_monitor_trends.py [--no-write] [--figdir docs/figures]

1. Flags: ``keck_etcs.calib.trend.monitor_flags`` over
   ``keck_etcs/data/mosfire/monitor/calib_monitor.ecsv``: for every metric
   group (metric, line or node, filter) and era, nights whose median is more
   than 3 MAD from the era's median of night medians get ``trend_3mad`` in
   ``flag`` (flagged, never excluded; D47). The table is rewritten and its
   ``index.yaml`` sha256 updated (``--no-write``: report only).
2. Figures in ``docs/figures/``:
   - ``mosfire_monitor_fwhm.png``: the standards' spatial FWHM
     (``fwhm_scalar_arcsec``, night medians) against date;
   - ``mosfire_monitor_flat_rate.png``: the dome-flat rate
     (``flat_rate_per_arcsec``) at each node against date, era boundaries
     dashed, each night labelled with its lamp power ``FPOWER``;
   - ``mosfire_monitor_lsf.png``: OH line FWHM at 12500 A (``line_fwhm_pix``)
     against slit width, with the current D25 model
     (``max(slit / LSF_SLOPE, LSF_FLOOR_PIX)``) and a refit
     ``sqrt((slit / s)^2 + f^2)``;
   - ``mosfire_monitor_sky_scale.png``: the OH flux above the atmosphere over
     the Gemini model (``line_flux_above`` / its ``err``, the per-frame sum
     over the monitor lines; an empirical ``sky_scale``, D14) against date
     and airmass.
3. Prints the per-group era statistics that flagged a night, the D25 refit,
   the ``sky_scale`` distribution, and the correlation of the dome-flat
   rate at 12000 and 12500 A with ``zp_1250`` (``standards.ecsv``).

Proposals that follow from these (D25 constants, the default ``sky_scale``)
are printed, never applied.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table

from keck_etcs.calib import trend
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import LSF_FLOOR_PIX, LSF_SLOPE, MOSFIRE

REPO = Path(__file__).resolve().parents[2]
MONITOR = DATA_DIR / 'mosfire' / 'monitor' / 'calib_monitor.ecsv'
STANDARDS = DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv'
INDEX = DATA_DIR / 'index.yaml'


def night_date(n):
    n = str(n)
    return f'{n[:4]}-{n[4:6]}-{n[6:8]}'


def night_medians(t, metric, **match):
    """{night: median value} of one metric (rows matching ``match``, finite values)."""
    s = t[t['metric'] == metric]
    for k, v in match.items():
        s = s[[str(x) == str(v) for x in s[k]]]
    out = {}
    for r in s:
        v = r['value']
        if np.ma.is_masked(v) or not np.isfinite(float(v)):
            continue
        out.setdefault(str(r['night']), []).append(float(v))
    return {n: float(np.median(v)) for n, v in sorted(out.items())}


def update_index(path):
    rel = str(path.relative_to(DATA_DIR))
    text = INDEX.read_text()
    index = yaml.safe_load(text)
    index['files'][rel]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    header = ''.join(ln + '\n' for ln in text.splitlines() if ln.startswith('#'))
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))


def era_lines(ax, eras):
    for e in eras:
        ax.axvline(trend.decimal_year(e.start), color='0.6', lw=0.8, ls='--')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--no-write', action='store_true')
    ap.add_argument('--figdir', default=str(REPO / 'docs' / 'figures'))
    a = ap.parse_args(argv)
    eras = MOSFIRE.eras
    t = Table.read(MONITOR, format='ascii.ecsv')

    # 1. flags
    new, summary = trend.monitor_flags(t, eras)
    old = [str(f) for f in t['flag']]
    changed = sum(o != n for o, n in zip(old, new))
    flagged = [s for s in summary if s['flagged']]
    print(f'monitor: {len(t)} rows; {len(summary)} (group, era) sets with >= {trend.MIN_NIGHTS} nights; '
          f'{len(flagged)} with flagged nights; {sum(f.count(trend.MONITOR_FLAG) > 0 for f in new)} rows '
          f'carry {trend.MONITOR_FLAG} ({changed} changed)')
    for s in flagged:
        print(f"  {s['group']} {s['era']}: {s['n_nights']} nights, median {s['median']:.4g}, MAD {s['mad']:.3g}"
              f" -> flagged {s['flagged']}")
    if not a.no_write and changed:
        t['flag'] = new
        t.write(MONITOR, format='ascii.ecsv', overwrite=True)
        update_index(MONITOR)
        print(f'wrote {MONITOR.relative_to(REPO)} and its index.yaml sha256')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figdir = Path(a.figdir)
    figdir.mkdir(parents=True, exist_ok=True)

    # 2a. FWHM against date
    fw = night_medians(t, 'fwhm_scalar_arcsec')
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.plot([trend.decimal_year(night_date(n)) for n in fw], list(fw.values()), 'o')
    era_lines(ax, eras)
    ax.set_xlabel('year')
    ax.set_ylabel('standard FWHM [arcsec]\n(night median)')
    fig.tight_layout()
    fig.savefig(figdir / 'mosfire_monitor_fwhm.png', dpi=120)
    plt.close(fig)
    print(f'FWHM: {len(fw)} nights, median {np.median(list(fw.values())):.2f}" '
          f'(range {min(fw.values()):.2f}-{max(fw.values()):.2f}")')

    # 2b. dome-flat rate per node
    fr = t[t['metric'] == 'flat_rate_per_arcsec']
    nodes = sorted({float(w) for w in fr['wave_A'] if not np.ma.is_masked(w)})
    power = {}
    for r in t[t['metric'] == 'flat_rate']:
        try:
            power[str(r['night'])] = json.loads(str(r['cards'])).get('FPOWER')
        except (ValueError, TypeError):
            pass
    fig, ax = plt.subplots(figsize=(8, 4))
    for node in nodes:
        nm = night_medians(t, 'flat_rate_per_arcsec', wave_A=node)
        if nm:
            ax.plot([trend.decimal_year(night_date(n)) for n in nm], list(nm.values()), 'o-', ms=4,
                    label=f'{node:.0f} A')
    for n in {str(x) for x in fr['night']}:
        nm = night_medians(t, 'flat_rate_per_arcsec', wave_A=12000.0)
        if n in nm:
            ax.annotate(f'FPOWER {power.get(n)}', (trend.decimal_year(night_date(n)), nm[n]), fontsize=7,
                        xytext=(3, 3), textcoords='offset points')
    era_lines(ax, eras)
    ax.set_xlabel('year')
    ax.set_ylabel('dome-flat rate [e-/s/pix/arcsec]')
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    fig.savefig(figdir / 'mosfire_monitor_flat_rate.png', dpi=120)
    plt.close(fig)

    # 2c. line FWHM against slit width; D25 refit
    lw = t[t['metric'] == 'line_fwhm_pix']
    sw = np.array([float(x) for x in lw['slit_width']])
    fp = np.array([float(x) for x in lw['value']])
    widths = np.unique(sw)
    fit = None
    if widths.size >= 2:
        # FWHM^2 = (slit / s)^2 + f^2, linear in (slit^2, 1)
        A = np.vstack([sw ** 2, np.ones_like(sw)]).T
        (c1, c0), *_ = np.linalg.lstsq(A, fp ** 2, rcond=None)
        if c1 > 0 and c0 > 0:
            fit = (1 / np.sqrt(c1), np.sqrt(c0))
    xs = np.linspace(0.3, 1.2, 100)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(sw, fp, 'o', label='OH lines at 12500 A (night medians)')
    ax.plot(xs, np.maximum(xs / LSF_SLOPE, LSF_FLOOR_PIX), '-', label=f'D25 now: max(slit/{LSF_SLOPE}, {LSF_FLOOR_PIX})')
    if fit:
        ax.plot(xs, np.sqrt((xs / fit[0]) ** 2 + fit[1] ** 2), '--',
                label=f'refit: sqrt((slit/{fit[0]:.3f})^2 + {fit[1]:.2f}^2)')
    ax.set_xlabel('slit width [arcsec]')
    ax.set_ylabel('line FWHM [pix]')
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(figdir / 'mosfire_monitor_lsf.png', dpi=120)
    plt.close(fig)
    print('D25: line FWHM at 12500 A per night: ' + ', '.join(f'{n} {w:.1f}": {v:.3f} pix'
                                                               for n, w, v in zip(lw['night'], sw, fp)))
    for w in widths:
        meas = float(np.median(fp[sw == w]))
        print(f'   {w:.1f}": measured {meas:.3f} pix, D25 now {max(w / LSF_SLOPE, LSF_FLOOR_PIX):.3f} '
              f'({100 * (max(w / LSF_SLOPE, LSF_FLOOR_PIX) / meas - 1):+.1f} %)'
              + (f', refit {np.hypot(w / fit[0], fit[1]):.3f}' if fit else ''))
    if fit:
        print(f'   PROPOSAL (not applied): D25 as FWHM = sqrt((slit / {fit[0]:.3f})^2 + {fit[1]:.2f}^2) pix, '
              f'from {len(fp)} nights at {len(widths)} slit widths (the floor is set by the 0.7" point)')

    # 2d. OH flux / Gemini (empirical sky_scale)
    ab = t[(t['metric'] == 'line_flux_above') & ([str(x).endswith('_sum') for x in t['line_id']])]
    # science-slit frames only (< 3"): on the 5" standard slit the fixed windows mix blended lines and
    # the ratio scatters 0.5-1.9 between nights
    ok = np.array([not np.ma.is_masked(r['err']) and float(r['err']) > 0 and not np.ma.is_masked(r['slit_width'])
                   and float(r['slit_width']) < 3.0 for r in ab])
    ab = ab[ok]
    ratio = np.array([float(r['value']) / float(r['err']) for r in ab])
    yr = np.array([trend.decimal_year(night_date(n)) for n in ab['night']])
    am = np.array([float(x) for x in ab['airmass']])
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.5), sharey=True)
    axs[0].plot(yr, ratio, '.', alpha=0.6)
    era_lines(axs[0], eras)
    axs[0].set_xlabel('year')
    axs[0].set_ylabel('OH flux / Gemini model')
    axs[1].plot(am, ratio, '.', alpha=0.6)
    axs[1].set_xlabel('airmass')
    for ax in axs:
        ax.axhline(1.0, color='0.6', lw=0.8)
    fig.tight_layout()
    fig.savefig(figdir / 'mosfire_monitor_sky_scale.png', dpi=120)
    plt.close(fig)
    per_night = {}
    for n, r in zip(ab['night'], ratio):
        per_night.setdefault(str(n), []).append(r)
    nmed = {n: float(np.median(v)) for n, v in per_night.items()}
    c = trend.correlation(am, ratio)
    print(f'sky_scale (OH lines): {len(ratio)} frames on {len(nmed)} nights; per night '
          + ', '.join(f'{n} {v:.3f}' for n, v in sorted(nmed.items()))
          + f'; median of nights {np.median(list(nmed.values())):.3f}, frames {np.median(ratio):.3f} '
            f'(16-84 % {np.percentile(ratio, 16):.3f}-{np.percentile(ratio, 84):.3f}); '
            f'vs airmass r={c["r"]:+.2f} ({c["sigma"]:.1f} sigma)')
    vals = np.array(list(nmed.values()))
    print(f'   PROPOSAL (not applied): D14 sky_scale for OH lines {np.median(vals):.2f} (median of {len(vals)} '
          f'nights; night to night {vals.min():.2f}-{vals.max():.2f}, as OH varies); the continuum between lines is '
          'not measured by this monitor '
          '(S11: x1.14-1.33), so SKY_SCALE_DEFAULT stays 1.0 unless lines and continuum get separate scales')

    # 3. dome-flat rate vs zp_1250 (same night)
    st = Table.read(STANDARDS, format='ascii.ecsv')
    zp = {str(r['s3_prefix']).rstrip('/').split('/')[-1]: (float(r['zp_1250']), str(r['filter'])) for r in st}
    for node in (12000.0, 12500.0):
        nm = night_medians(t, 'flat_rate_per_arcsec', wave_A=node)
        common = [n for n in nm if n in zp]
        if not common:
            continue
        for band in sorted({zp[n][1] for n in common}):
            ns = [n for n in common if zp[n][1] == band]
            c = trend.correlation([nm[n] for n in ns], [zp[n][0] for n in ns])
            print(f'flat rate at {node:.0f} A vs zp_1250 ({band}): nights {ns}, FPOWER '
                  f'{[power.get(n) for n in ns]} -> n={c["n"]} r={c["r"]:+.2f} ({c["sigma"]:.1f} sigma)')
    print(f'figures in {figdir.relative_to(REPO) if figdir.is_relative_to(REPO) else figdir}: '
          'mosfire_monitor_{fwhm,flat_rate,lsf,sky_scale}.png')
    return 0


if __name__ == '__main__':
    sys.exit(main())
