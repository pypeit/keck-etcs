#!/usr/bin/env python
"""Numbers and figures for docs/XTcalc_bug.md: XTcalc's magnitude-mode band-median indexing bug.

Usage:
    conda run -n pypeit14b python scripts/mosfire/xtcalc_bug_report.py [--figdir docs/figures]

Uses the Python port of XTcalc (v2.0, Keck XTcalc.tar) in ``compare_xtcalc.py`` (checked
against the real program: the WMKO GUI gave S/N 4.4 for the J test case,
the port 4.437; the manual's K line example 9.1, the port 8.85). For
magnitude mode it evaluates, per spectral pixel, XTcalc's signal, sky,
noise, S/N and exposure time, then takes the median two ways:

- *as coded*: over ``filt_index = NONzero_index`` (indices on the full
  3072-pixel grid) applied to the band-cut arrays, with IDL's clipping of
  out-of-range subscripts to the last element;
- *intended*: over the band pixels with non-zero sky.

Prints the tables quoted in the report and writes two PNG figures.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_xtcalc as cx  # noqa: E402

BANDS = ('Y', 'J', 'H', 'K')
MAGS = np.arange(17.0, 23.01, 0.5)
CASE = {'slit': 0.7, 'theta': 0.7, 'nreads': 16, 'nexp': 4, 'time': 480.0}
BLUE, ORANGE, AQUA, YELLOW = '#2a78d6', '#eb6834', '#1baf7a', '#eda100'   # dataviz reference slots 1-4
INK, MUTED, SURFACE = '#0b0b0b', '#6b6a63', '#fcfcfb'


def mag_mode(band, mag, slit=0.7, theta=0.7, nreads=16, nexp=4, time=480.0, target_sn=None):
    """XTcalc magnitude mode (flat f_nu), per pixel; the median taken as coded and as intended."""
    inp = cx.xtcalc_inputs(band, slit)
    disp, w = inp['disp'], inp['grid_um']
    bk = inp['bk'] * inp['tp'] * slit * theta * (cx.AT_CM2 * 1e-4) * (disp / 10.0)
    sig = 10.0 ** (-0.4 * (mag + cx.FNU_AB)) / cx.H_ERG_S * cx.AT_CM2 / w * inp['tran'] * inp['tp'] * (disp / 1e4)
    npx = theta / cx.PIX
    dither = 2.0 if nexp > 1 else 1.0
    rn2 = cx.DET_RN ** 2 / nreads * npx * nexp
    # XTcalc's linearly extrapolated H throughput is negative at 1.454-1.460 um (37 px), which makes the
    # variance negative there for bright sources; those pixels lie outside both index sets
    with np.errstate(invalid='ignore'):
        noise = np.sqrt(sig * time + dither * ((bk + cx.DARK * npx) * time + rn2))
    sn = sig * time / noise
    coded = cx.quirk_index(inp)
    intended = np.flatnonzero(inp['bk'] > 0)
    out = {'band': band, 'mag': mag, 'wave_um': w, 'sn': sn, 'sig': sig, 'bk': bk, 'n_band': inp['n_band'],
           'n_index': inp['nonzero_full'].size, 'n_clipped': int(np.sum(inp['nonzero_full'] >= inp['n_band'])),
           'sn_coded': float(np.median(sn[coded])), 'sn_intended': float(np.median(sn[intended])),
           'sn_edge': float(sn[-1]), 'idx_coded': coded, 'idx_intended': intended}
    out['percentile_coded'] = float(100.0 * np.mean(sn[intended] <= out['sn_coded']))
    # the other summaries that use sn_index in magnitude mode (XTcalc.pro lines 754, 757)
    epp = noise ** 2 / npx / nexp
    out['tp_coded'], out['tp_intended'] = float(np.mean(inp['tp'][coded])), float(np.mean(inp['tp'][intended]))
    out['max_epp_coded'], out['max_epp_intended'] = float(np.nanmax(epp[coded])), float(np.nanmax(epp[intended]))
    out['max_epp_band'] = float(np.nanmax(epp))
    if target_sn is not None:
        qa = -sig ** 2 / target_sn ** 2
        qb = dither * bk + dither * cx.DARK * npx + sig
        qc = dither * cx.DET_RN ** 2 / nreads * npx * nexp
        t = (-qb - np.sqrt(qb ** 2 - 4 * qa * qc)) / (2 * qa)
        out['t_coded'] = float(np.median(t[coded]))
        out['t_intended'] = float(np.median(t[intended]))
    return out


def figure_spectrum(r, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    w = r['wave_um']
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={'width_ratios': [2.2, 1]}, facecolor=SURFACE)
    for a in ax:
        a.set_facecolor(SURFACE)
        for s in ('top', 'right'):
            a.spines[s].set_visible(False)
        a.tick_params(colors=MUTED)
    ax[0].plot(w, r['sn'], color=MUTED, lw=0.6)
    ax[0].axhline(r['sn_intended'], color=BLUE, lw=2)
    ax[0].axhline(r['sn_coded'], color=ORANGE, lw=2)
    ax[0].plot(w[-1], r['sn_edge'], 'o', ms=8, color=ORANGE, mec=SURFACE, mew=2)
    ax[0].text(w[0], r['sn_intended'] * 1.04, f"median over the band: {r['sn_intended']:.2f}", color=INK, fontsize=9)
    ax[0].text(w[0], r['sn_coded'] * 0.86, f"XTcalc reports: {r['sn_coded']:.2f}", color=INK, fontsize=9)
    ax[0].annotate(f"last band pixel, S/N {r['sn_edge']:.2f}\n(repeated {r['n_clipped']}x)", (w[-1], r['sn_edge']),
                   xytext=(-150, 40), textcoords='offset points', fontsize=9, color=INK,
                   arrowprops={'arrowstyle': '-', 'color': MUTED, 'lw': 0.8})
    ax[0].set_xlabel('wavelength (um)', color=INK)
    ax[0].set_ylabel('S/N per spectral pixel', color=INK)
    ax[0].set_title(f"XTcalc J, {r['mag']:.0f} AB flat f_nu, 0.7\" slit, 4 x 120 s, 16 reads", fontsize=10, color=INK,
                    loc='left')
    s = np.sort(r['sn'][r['idx_intended']])
    ax[1].plot(s, np.arange(1, s.size + 1) / s.size, color=MUTED, lw=1.5)
    ax[1].axvline(r['sn_intended'], color=BLUE, lw=2)
    ax[1].axvline(r['sn_coded'], color=ORANGE, lw=2)
    ax[1].text(r['sn_coded'], 0.93, f" {r['percentile_coded']:.0f}th\n percentile", color=INK, fontsize=9)
    ax[1].text(r['sn_intended'], 0.52, ' 50th', color=INK, fontsize=9)
    ax[1].set_xlabel('S/N per spectral pixel', color=INK)
    ax[1].set_ylabel(f"fraction of the {s.size} band pixels", color=INK)
    ax[1].set_title('distribution over the band', fontsize=10, color=INK, loc='left')
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def figure_ratio(rows, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.5, 4.2), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED)
    ax.axhline(1.0, color=MUTED, lw=0.8)
    for band, col in zip(BANDS, (BLUE, ORANGE, AQUA, YELLOW)):
        rr = [r for r in rows if r['band'] == band]
        m = [r['mag'] for r in rr]
        y = [r['sn_coded'] / r['sn_intended'] for r in rr]
        ax.plot(m, y, color=col, lw=2, marker='o', ms=4, label=band)
        ax.text(m[-1] + 0.12, y[-1], band, color=INK, va='center', fontsize=10)
    ax.set_xlabel('source magnitude (AB, flat f_nu)', color=INK)
    ax.set_ylabel('reported S/N / band-median S/N', color=INK)
    ax.set_title('XTcalc magnitude mode: reported over intended S/N\n0.7" slit, theta 0.7", 4 x 120 s, 16 reads',
                 fontsize=10, color=INK, loc='left')
    ax.set_ylim(0, 1.1)
    ax.legend(frameon=False, ncol=4, loc='lower left')
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main(figdir):
    figdir = Path(figdir)
    figdir.mkdir(parents=True, exist_ok=True)
    j = mag_mode('J', 20.0, **CASE, target_sn=10.0)
    print(f"J = 20 AB test case: band {j['n_band']} px ({j['wave_um'][0]:.4f}-{j['wave_um'][-1]:.4f} um); "
          f"filt_index has {j['n_index']} entries, {j['n_clipped']} beyond the band "
          f"({j['n_clipped'] / j['n_index']:.1%}) -> clipped to the last pixel")
    print(f"  S/N as coded {j['sn_coded']:.3f} (WMKO GUI: 4.4); intended {j['sn_intended']:.3f}; ratio "
          f"{j['sn_coded'] / j['sn_intended']:.3f}; reported value = {j['percentile_coded']:.1f}th percentile; "
          f"last pixel {j['sn_edge']:.3f} at {j['wave_um'][-1]:.4f} um")
    print(f"  exposure time for S/N 10 per pixel: as coded {j['t_coded']:.0f} s, intended {j['t_intended']:.0f} s, "
          f"ratio {j['t_coded'] / j['t_intended']:.2f}")
    print(f"  mean throughput: as coded {j['tp_coded']:.4f}, intended {j['tp_intended']:.4f}")
    for band in BANDS:
        for m in (17.0, 20.0):
            r = mag_mode(band, m, **CASE)
            print(f"  {band} {m:.0f} AB: max e- per pixel per exposure as coded {r['max_epp_coded']:.0f}, over the "
                  f"intended pixels {r['max_epp_intended']:.0f}, over the whole band {r['max_epp_band']:.0f}; "
                  f"mean throughput {r['tp_coded']:.3f} vs {r['tp_intended']:.3f}")
    figure_spectrum(j, figdir / 'xtcalc_bug_J20.png')
    rows = []
    print('\nband  n_band  n_index  clipped   ratio reported/intended S/N at AB 17 / 19 / 21 / 23   '
          't(S/N=10) ratio at 20')
    for band in BANDS:
        rr = [mag_mode(band, m, **CASE) for m in MAGS]
        rows += rr
        t = mag_mode(band, 20.0, **CASE, target_sn=10.0)
        rat = {r['mag']: r['sn_coded'] / r['sn_intended'] for r in rr}
        print(f"{band:4s}  {rr[0]['n_band']:6d}  {rr[0]['n_index']:7d}  {rr[0]['n_clipped']:7d}   "
              f"{rat[17.0]:.3f} / {rat[19.0]:.3f} / {rat[21.0]:.3f} / {rat[23.0]:.3f}"
              f"{'':20s}{t['t_coded'] / t['t_intended']:.2f}")
    figure_ratio(rows, figdir / 'xtcalc_bug_ratio.png')
    print(f'\nfigures: {figdir}/xtcalc_bug_J20.png, {figdir}/xtcalc_bug_ratio.png')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--figdir', default=str(Path(__file__).resolve().parents[2] / 'docs' / 'figures'))
    sys.exit(main(p.parse_args().figdir))
