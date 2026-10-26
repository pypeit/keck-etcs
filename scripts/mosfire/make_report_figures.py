#!/usr/bin/env python
"""Figures for the MOSFIRE report (``reports/Keck_MOSFIRE_report_20261009.md``).

Usage:
    conda run -n pypeit14b python scripts/mosfire/make_report_figures.py [--outdir reports/figures]

Writes into ``--outdir``:

- ``mosfire_era_throughput.png``: the filter-free era curves of the
  calibration release (``thru_median`` with the ``thru_mad`` band), XTcalc's
  2012 curve on our aperture (``Jeff.sm.dat`` x 0.89^2 x 75 / 72.37, which
  includes the order-sorting filter, divided by the J filter inside its
  half-power band), the J
  and J2 half-power bands; below, every standard's harvested filter-free
  curve (``thru``, before the combine cuts), coloured by era, open for
  excluded rows;
- ``mosfire_xtcalc_comparison.png``: median S/N per pixel against J (AB) for
  the 0.7" and 1.0" slits, from ``compare_xtcalc.py``'s table in
  ``$KECK_ETCS_DATA/external/xtcalc/comparison_2026.10/`` (XTcalc as coded,
  XTcalc's true band median, keck_etcs), and the ratio;
- ``mosfire_etc_example.png``: ``compute`` for a J = 20 AB point source
  (defaults: 0.7" slit and seeing, 4 x 120 s ABBA MCDS-16, airmass 1.2,
  PWV 1.6 mm), with S/N per pixel and the sky and source electrons; and the
  per-frame exposure time for S/N 5 per resolution element in 8 frames
  against magnitude, J and J2;
- ``mosfire_j0841_validation.png``: a copy of ``validate_j0841.py``'s figure
  (``$KECK_ETCS_DATA/mosfire/20220409/validation/validation_j0841.png``,
  the release re-run of 2026-10-09).
"""
import argparse
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from astropy.table import Table

from keck_etcs import etc, paths
from keck_etcs.calib.harvest import EFF_APERTURE
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
ERA_COLORS = {'2012-04..2016-09': 'tab:blue', '2017-02..2025-02': 'tab:green', '2025-04..': 'tab:red'}


def era_of(date):
    for e in MOSFIRE.eras:
        if str(date) >= e.start and (e.end is None or str(date) < e.end):
            return e.name
    return None


def half_power(band):
    f = Table.read(DATA_DIR / MOSFIRE.bands[band].filter_file, format='ascii.ecsv')
    w, t = np.asarray(f['wave_A'], float), np.asarray(f['transmission'], float)
    above = w[t >= 0.5 * t.max()]
    return above.min(), above.max()


def fig_era(out):
    fig, (a, b) = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
    for era in MOSFIRE.eras:
        t = Table.read(DATA_DIR / MOSFIRE.throughput_file(era), format='ascii.ecsv')
        w, m, d = (np.asarray(t[c], float) for c in ('wave', 'thru_median', 'thru_mad'))
        c = ERA_COLORS[era.name]
        a.plot(w, m, color=c, lw=1.2, label=f"{era.name} ({len(t.meta['standards'])} std)")
        ok = np.isfinite(d)
        a.fill_between(w[ok], (m - d)[ok], (m + d)[ok], color=c, alpha=0.2, lw=0)
    xf = paths.data_root() / 'external' / 'xtcalc' / 'XTcalc_dir' / 'MosfireSpecEff' / 'Jeff.sm.dat'
    if xf.exists():
        # XTcalc's efficiency includes the order-sorting filter: divide the J filter out inside its half-power band
        xw, xe = np.loadtxt(xf, unpack=True)
        fc = MOSFIRE.filter_curve('J')
        fj = np.interp(xw, fc['wave_A'], fc['transmission'], left=0.0, right=0.0)
        inside = fj >= 0.5 * fc['transmission'].max()
        xff = np.where(inside, np.clip(xe, 0, None) * 0.89 ** 2 * 75.0 / EFF_APERTURE / np.where(inside, fj, 1), np.nan)
        a.plot(xw, xff, 'k--', lw=1, label='XTcalc 2012 / J filter (x 0.89$^2$ x 75/72.37)')
    for band, y in (('J', 0.05), ('J2', 0.03)):
        lo, hi = half_power(band)
        a.annotate('', xy=(lo, y), xytext=(hi, y), arrowprops=dict(arrowstyle='<->', color='gray'))
        a.text(0.5 * (lo + hi), y + 0.005, f'{band} half-power', ha='center', fontsize=8, color='gray')
    a.axvspan(11900, 12450, color='gold', alpha=0.15, lw=0, label='common window 11900-12450 A')
    a.set_ylabel('filter-free throughput')
    a.set_ylim(0, 0.42)
    a.legend(fontsize=8, loc='lower center', ncol=2)
    a.set_title('MOSFIRE J/J2 system throughput (telescope + spectrograph + detector), mosfire-J-2026.10',
                fontsize=10)

    rows = Table.read(DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    for r in rows:
        f = DATA_DIR / 'mosfire' / 'throughput' / 'standards' / Path(str(r['thru_curve_file'])).name
        if not f.exists():
            continue
        c = Table.read(f, format='ascii.ecsv')
        w = np.asarray(c['wave'], float)
        th = np.ma.filled(np.ma.asarray(c['thru'], float), np.nan)
        excl = 'excluded' in str(r['flag'])
        b.plot(w, th, color=ERA_COLORS.get(era_of(r['date']), 'gray'), lw=0.6,
               ls=':' if excl else '-', alpha=0.5 if excl else 0.9)
    for name, c in ERA_COLORS.items():
        b.plot([], [], color=c, label=name)
    b.plot([], [], color='gray', ls=':', label='excluded (nonlinear or 3 MAD)')
    b.set_ylim(0, 0.42)
    b.set_xlim(11000, 13600)
    b.set_xlabel('vacuum wavelength (A)')
    b.set_ylabel('per-standard throughput')
    b.legend(fontsize=8, loc='lower center', ncol=2)
    b.set_title('20 standard-star nights, filter divided out (before the combine cuts of design 4.5)', fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def fig_xtcalc(out):
    f = paths.data_root() / 'external' / 'xtcalc' / 'comparison_2026.10' / 'xtcalc_comparison.ecsv'
    t = Table.read(f, format='ascii.ecsv')
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    for j, slit in enumerate((0.7, 1.0)):
        s = np.isclose(t['slit_arcsec'], slit)
        m = np.asarray(t['mag_ab'][s], float)
        a, r = axes[0, j], axes[1, j]
        a.semilogy(m, t['snr_xtcalc'][s], 'o-', label='XTcalc as coded')
        a.semilogy(m, t['snr_xtcalc_plain_median'][s], 's--', label='XTcalc, true band median')
        a.semilogy(m, t['snr_keck_etcs'][s], 'D-', label='keck_etcs (mosfire-J-2026.10)')
        a.set_title(f'J, {slit}" slit, 0.7" seeing, 4 x 120 s ABBA MCDS-16', fontsize=10)
        a.set_ylabel('median S/N per pixel')
        a.grid(alpha=0.3)
        r.plot(m, t['ratio_ours_over_xtcalc'][s], 'D-', color='tab:green', label='keck_etcs / XTcalc as coded')
        r.plot(m, np.asarray(t['snr_keck_etcs'][s]) / np.asarray(t['snr_xtcalc_plain_median'][s]), 's--',
               color='tab:orange', label='keck_etcs / XTcalc true median')
        r.axhline(1, color='k', lw=0.5)
        r.set_xlabel('J (AB)')
        r.set_ylabel('ratio')
        r.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=8)
    axes[1, 0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def fig_example(out):
    o = etc.compute({'band': 'J', 'source': {'mag': 20.0}})
    w = np.asarray(o['wave_A'])
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={'width_ratios': [3, 2]})
    a.plot(w, o['snr_pixel'], color='k', lw=0.6, label='S/N per pixel')
    a.axhline(o['summary']['snr_pixel_median'], color='tab:orange',
              label=f"band median {o['summary']['snr_pixel_median']:.2f}")
    a.set_xlabel('vacuum wavelength (A)')
    a.set_ylabel('S/N per pixel (4 frames)')
    a2 = a.twinx()
    a2.semilogy(w, o['sky_e'], color='tab:blue', lw=0.4, alpha=0.6, label='sky e-')
    a2.semilogy(w, o['signal_e'], color='tab:red', lw=0.8, alpha=0.8, label='source e-')
    a2.set_ylabel('electrons per pixel in the aperture (4 frames)')
    h1, l1 = a.get_legend_handles_labels()
    h2, l2 = a2.get_legend_handles_labels()
    a.legend(h1 + h2, l1 + l2, fontsize=8, loc='upper left')
    a.set_title(f"J = 20 AB point source, 0.7\" slit and seeing, 4 x 120 s ABBA, era {o['meta']['era']}",
                fontsize=10)
    mags = np.arange(18.0, 23.01, 0.5)
    for band, c in (('J', 'tab:green'), ('J2', 'tab:purple')):
        ts = [etc.compute({'band': band, 'source': {'mag': float(m)}, 'n_frames': 8, 'target_snr': 5,
                           'snr_reference': 'resel'})['summary']['exptime_s'] for m in mags]
        b.semilogy(mags, ts, 'o-', color=c, label=band)
    b.axhline(1.455, color='gray', ls=':', lw=0.8)
    b.axhline(3600, color='gray', ls=':', lw=0.8)
    b.set_xlabel('magnitude (AB)')
    b.set_ylabel('exposure per frame (s)')
    b.set_title('S/N 5 per resolution element (band median), 8 frames', fontsize=10)
    b.legend(fontsize=8)
    b.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--outdir', default=str(REPO / 'reports' / 'figures'))
    args = p.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    fig_era(out / 'mosfire_era_throughput.png')
    fig_xtcalc(out / 'mosfire_xtcalc_comparison.png')
    fig_example(out / 'mosfire_etc_example.png')
    src = paths.data_root() / 'mosfire' / '20220409' / 'validation' / 'validation_j0841.png'
    shutil.copy2(src, out / 'mosfire_j0841_validation.png')
    for f in sorted(out.glob('*.png')):
        print(f'wrote {f.relative_to(REPO) if f.is_relative_to(REPO) else f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
