#!/usr/bin/env python
"""Inspect one PypeIt MOSFIRE J sensitivity function, or compare two.

Usage:
    conda run -n pypeit14b python scripts/mosfire/inspect_sensfunc.py SENS.fits [SENS2.fits]
        [--plot] [--json OUT.json]

For each ``SensFunc`` file prints:

- the standard, algorithm, airmass and exposure time;
- the fitted telluric parameters. With PypeIt's PCA telluric grid
  (``TellPCA_*``) the fit has no PWV or airmass parameter: it fits
  ``tell_npca`` PCA coefficients, the resolution R, a shift and a stretch at
  the *header* airmass. So the script also estimates PWV by matching the
  fitted telluric transmission over 1.117-1.260 um to the Gemini ATRAN grid
  (``keck_etcs/data/sky/gemini_mk_sky_grid.fits``). The grid is interpolated
  linearly in airmass and in log PWV (design N4) to the header airmass,
  smoothed to the fitted R and resampled to PypeIt's wavelengths. PWV is
  searched over 0.5-10 mm; outside the grid's 1-5 mm the interpolation
  extrapolates in log PWV, which is flagged;
- the zero point (AB mag for 1 photon/s/A) at 1.20, 1.25 and 1.30 um, and the
  implied end-to-end throughput
  (``pypeit.core.flux_calib.zeropoint_to_throughput``, Keck effective
  aperture 72.3674 m^2, decision N1) there and its median over
  1.117-1.260 um;
- checks: zero point finite over 1.117-1.260 um; median throughput within
  0.15-0.45 (XTcalc 2012: 0.28); telluric residual near 1.13 um (median of
  fluxed standard / CALSPEC model - 1 over 1.125-1.140 um) below 5 percent;
- the red-edge table: the median residual in 5 nm bins from 1.22 um to the
  end of the fluxed standard, to judge whether 1.260 um is the clean red edge.

With two files it also prints their zero-point ratio statistics over
1.117-1.260 um, the ratio being the throughput ratio 10**(0.4 (ZP1 - ZP2)).
It is used to compare the local and in-pod sensfuncs, or two frames.

``--plot`` writes ``<sens stem>_vs_calspec.png`` next to each file: the fluxed
standard against the CALSPEC model and, in a second panel on the same
wavelength axis, their ratio. Exit status 1 if a check fails.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

from pypeit.core.flux_calib import zeropoint_to_throughput
from pypeit.sensfunc import SensFunc

REPO = Path(__file__).resolve().parents[2]
EFF_APERTURE = 72.3674           # m^2, Keck (decision N1)
JWIN = (11170.0, 12600.0)        # A, the J2 analysis window (1.117-1.260 um)
ZP_WAVES = (12000.0, 12500.0, 13000.0)
THRU_RANGE = (0.15, 0.45)
TELL_WINDOW = (11250.0, 11400.0)  # A, telluric check near 1.13 um
TELL_TOL = 0.05


def load(path):
    sf = SensFunc.from_file(str(path), chk_version=False)
    wave = np.asarray(sf.wave).ravel()
    zp = np.asarray(sf.zeropoint).ravel()
    return sf, wave, zp


def good_zp(wave, zp):
    return (wave > 0) & np.isfinite(zp) & (zp > 0)


def interp_zp(wave, zp, w):
    g = good_zp(wave, zp)
    if not g.any() or w < wave[g].min() or w > wave[g].max():
        return None
    return float(np.interp(w, wave[g], zp[g]))


def estimate_pwv(sf):
    """PWV from the fitted telluric model (keck_etcs.calib.harvest.estimate_pwv)."""
    from keck_etcs.calib.harvest import estimate_pwv as _estimate
    m = sf.telluric.model
    res = float(m['TELL_RESLN'][0])
    out = _estimate(np.asarray(m['WAVE'][0], float), np.asarray(m['TELLURIC'][0], float), res,
                    float(sf.airmass), window=JWIN)
    out.update({'airmass': float(sf.airmass), 'resolution': res})
    return out


def fluxed(sf):
    s = sf.sens
    w = np.asarray(s['SENS_FLUXED_STD_WAVE'][0], float)
    f = np.asarray(s['SENS_FLUXED_STD_FLAM'][0], float)
    ivar = np.asarray(s['SENS_FLUXED_STD_FLAM_IVAR'][0], float)
    mask = np.asarray(s['SENS_FLUXED_STD_MASK'][0], bool)
    model = np.asarray(s['SENS_STD_MODEL_FLAM'][0], float)
    # tweak_standard zeroes the spectrum outside the J2 window: exclude those pixels
    good = mask & (w > 0) & np.isfinite(f) & (f != 0) & np.isfinite(model) & (model > 0)
    return w, f, ivar, model, good


def binned_resid(w, ratio, good, lo, hi):
    sel = good & (w >= lo) & (w < hi)
    if sel.sum() < 5:
        return None, int(sel.sum())
    return float(np.median(ratio[sel]) - 1), int(sel.sum())


def inspect(path):
    sf, wave, zp = load(path)
    out = {'file': str(path), 'std_name': sf.std_name, 'std_cal': sf.std_cal,
           'algorithm': sf.algorithm, 'airmass': float(sf.airmass), 'exptime': float(sf.exptime)}
    m = sf.telluric.model if sf.telluric is not None else None
    if m is not None:
        out['telluric'] = {'grid': sf.telluric.telgrid, 'teltype': sf.telluric.teltype,
                           'pca_coeffs': [float(x) for x in np.asarray(m['TELL_PARAM'][0])],
                           'resolution': float(m['TELL_RESLN'][0]),
                           'shift_pix': float(m['TELL_SHIFT'][0]),
                           'stretch': float(m['TELL_STRETCH'][0]),
                           'chi2': float(m['CHI2'][0]), 'success': bool(m['SUCCESS'][0]),
                           'niter': int(m['NITER'][0])}
        out['pwv_estimate'] = estimate_pwv(sf)

    g = good_zp(wave, zp)
    thru = np.full_like(zp, np.nan)
    thru[g] = zeropoint_to_throughput(wave[g], zp[g], EFF_APERTURE)
    out['zeropoint'] = {}
    for w in ZP_WAVES:
        z = interp_zp(wave, zp, w)
        t = None if z is None else float(zeropoint_to_throughput(np.array([w]), np.array([z]),
                                                                 EFF_APERTURE)[0])
        out['zeropoint'][f'{w / 1e4:.2f}um'] = {'zp': z, 'throughput': t}
    inj = (wave >= JWIN[0]) & (wave <= JWIN[1])
    out['zp_finite_in_window'] = bool(inj.any() and np.all(g[inj]))
    out['zp_range_A'] = [float(wave[g].min()), float(wave[g].max())] if g.any() else None
    out['thru_median_window'] = float(np.nanmedian(thru[inj & g])) if (inj & g).any() else None

    fw, ff, fivar, fmodel, fgood = fluxed(sf)
    ratio = np.where(fgood, ff / np.where(fmodel > 0, fmodel, 1), np.nan)
    out['tell_resid_1.13'], n = binned_resid(fw, ratio, fgood, *TELL_WINDOW)
    out['red_edge'] = []
    last = fw[fgood].max() if fgood.any() else JWIN[1]
    for lo in np.arange(12200.0, last, 50.0):
        r, n = binned_resid(fw, ratio, fgood, lo, lo + 50)
        if n:
            out['red_edge'].append({'lo_A': float(lo), 'hi_A': float(lo + 50), 'resid': r, 'n': n})
    out['fluxed_range_A'] = [float(fw[fgood].min()), float(fw[fgood].max())] if fgood.any() else None

    thru_ok = out['thru_median_window'] is not None and \
        THRU_RANGE[0] <= out['thru_median_window'] <= THRU_RANGE[1]
    tell_ok = out['tell_resid_1.13'] is not None and abs(out['tell_resid_1.13']) < TELL_TOL
    out['checks'] = {'zp_finite': out['zp_finite_in_window'], 'thru_in_range': bool(thru_ok),
                     'tell_resid_1.13_ok': bool(tell_ok)}
    return out, (sf, wave, zp, fw, ff, fivar, fmodel, fgood)


def compare(a, b):
    (_, wa, za), (_, wb, zb) = a, b
    ga, gb = good_zp(wa, za), good_zp(wb, zb)
    sel = ga & (wa >= JWIN[0]) & (wa <= JWIN[1]) & (wa >= wb[gb].min()) & (wa <= wb[gb].max())
    zb_i = np.interp(wa[sel], wb[gb], zb[gb])
    dzp = za[sel] - zb_i
    ratio = 10 ** (0.4 * dzp)
    return {'n': int(sel.sum()), 'median_ratio': float(np.median(ratio)),
            'mean_ratio': float(np.mean(ratio)), 'std_ratio': float(np.std(ratio)),
            'p05': float(np.percentile(ratio, 5)), 'p95': float(np.percentile(ratio, 95)),
            'max_abs_dev': float(np.max(np.abs(ratio - 1))),
            'median_dzp_mag': float(np.median(dzp))}


def plot(path, data):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    sf, wave, zp, fw, ff, fivar, fmodel, fgood = data
    blue, orange, ink, muted, grid = '#2a78d6', '#eb6834', '#1f1f1e', '#6b6a64', '#e4e3dc'
    sel = fgood & (fw > 11000) & (fw < 13200)
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(8, 6), height_ratios=[2, 1],
                                   facecolor='#fcfcfb')
    # PypeIt FLAM is already in units of 1e-17 erg/s/cm^2/A
    ax1.plot(fw[sel] / 1e4, ff[sel], color=blue, lw=1.0, label='Fluxed standard (PypeIt)')
    ax1.plot(fw[sel] / 1e4, fmodel[sel], color=orange, lw=2.0,
             label=f'CALSPEC model ({sf.std_cal})')
    ax1.set_ylabel(r'$F_\lambda$ ($10^{-17}$ erg s$^{-1}$ cm$^{-2}$ $\AA^{-1}$)', color=ink)
    ax1.legend(frameon=False, fontsize=9, loc='upper right')
    ratio = ff[sel] / fmodel[sel]
    ax2.plot(fw[sel] / 1e4, ratio, color=blue, lw=0.6, alpha=0.5, label='per pixel')
    # 5 nm medians
    edges = np.arange(fw[sel].min(), fw[sel].max() + 50, 50.0)
    idx = np.digitize(fw[sel], edges)
    med = [(edges[i - 1] + 25, np.median(ratio[idx == i])) for i in np.unique(idx)
           if (idx == i).sum() >= 5]
    if med:
        mx, my = np.array(med).T
        ax2.plot(mx / 1e4, my, color=ink, lw=2.0, marker='o', ms=4, label='5 nm median')
    ax2.axhspan(0.95, 1.05, color=grid, zorder=0, label='±5%')
    ax2.axhline(1.0, color=muted, lw=0.8)
    ax2.set_ylim(0.7, 1.3)
    ax2.set_ylabel('Fluxed / model', color=ink)
    ax2.set_xlabel(r'Vacuum wavelength ($\mu$m)', color=ink)
    ax2.legend(frameon=False, fontsize=8, loc='lower left', ncol=3)
    for ax in (ax1, ax2):
        for x in (JWIN[0] / 1e4, 1.260):
            ax.axvline(x, color=muted, lw=0.8, ls='--')
        ax.axvspan(TELL_WINDOW[0] / 1e4, TELL_WINDOW[1] / 1e4, color=grid, alpha=0.6, zorder=0)
        ax.set_facecolor('#fcfcfb')
        ax.grid(color=grid, lw=0.5)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        ax.tick_params(colors=muted)
    ax1.set_title(f'{sf.std_name}, {Path(path).stem}: J2 window 1.117-1.260 um (dashed), '
                  f'1.125-1.140 um telluric check (shaded)', fontsize=9, color=ink)
    fig.tight_layout()
    out = Path(path).with_name(Path(path).stem + '_vs_calspec.png')
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def report(o):
    print(f"\n== {Path(o['file']).name}")
    print(f"standard {o['std_name']} ({o['std_cal']}), algorithm {o['algorithm']}, "
          f"airmass {o['airmass']:.4f}, exptime {o['exptime']:.2f} s")
    t = o.get('telluric')
    if t:
        print(f"telluric: {t['grid']} ({t['teltype']}), success {t['success']}, niter {t['niter']}, "
              f"chi2 {t['chi2']:.1f}")
        print(f"  PCA coeffs {np.round(t['pca_coeffs'], 3).tolist()}, R {t['resolution']:.0f}, "
              f"shift {t['shift_pix']:+.3f} pix, stretch {t['stretch']:.5f}")
        p = o['pwv_estimate']
        print(f"  PWV (Gemini ATRAN match at the header airmass {p['airmass']:.3f}): "
              f"{p['pwv_mm']:.2f} mm (rms {p['rms_resid']:.4f}"
              f"{', extrapolated beyond the 1-5 mm grid' if p['extrapolated'] else ''}"
              f"{', AT SEARCH EDGE' if p['at_search_edge'] else ''}); airmass is not fitted")
    print(f"zero point finite over its fitted range {o['zp_range_A']} A")
    for k, v in o['zeropoint'].items():
        if v['zp'] is None:
            print(f"  {k}: outside the fitted range")
        else:
            print(f"  {k}: ZP {v['zp']:.3f} mag, throughput {v['throughput']:.4f}")
    print(f"median throughput 1.117-1.260 um: {o['thru_median_window']:.4f}")
    print(f"telluric residual 1.125-1.140 um: {100 * o['tell_resid_1.13']:+.2f} %")
    print(f"red edge (median fluxed/model - 1 per 5 nm; fluxed standard covers {o['fluxed_range_A']} A):")
    for r in o['red_edge']:
        val = '   n/a' if r['resid'] is None else f"{100 * r['resid']:+6.2f} %"
        print(f"  {r['lo_A'] / 1e4:.3f}-{r['hi_A'] / 1e4:.3f} um: {val} (n={r['n']})")
    c = o['checks']
    print(f"checks: ZP finite {'PASS' if c['zp_finite'] else 'FAIL'}; throughput in "
          f"{THRU_RANGE} {'PASS' if c['thru_in_range'] else 'FAIL'}; |telluric residual| < 5% "
          f"{'PASS' if c['tell_resid_1.13_ok'] else 'FAIL'}")


def main(files, do_plot=False, json_out=None):
    results, raw = [], []
    for f in files:
        o, data = inspect(f)
        results.append(o)
        raw.append(data)
        report(o)
        if do_plot:
            print(f'plot: {plot(f, data)}')
    summary = {'files': results}
    if len(files) == 2:
        c = compare(raw[0][:3], raw[1][:3])
        summary['comparison'] = c
        print(f"\n== zero-point ratio {Path(files[0]).name} / {Path(files[1]).name}, "
              f"1.117-1.260 um ({c['n']} pts):")
        print(f"  median {c['median_ratio']:.4f}, mean {c['mean_ratio']:.4f}, std {c['std_ratio']:.4f}, "
              f"5-95% {c['p05']:.4f}-{c['p95']:.4f}, max |dev| {c['max_abs_dev']:.4f}, "
              f"median dZP {c['median_dzp_mag']:+.4f} mag")
    if json_out:
        Path(json_out).write_text(json.dumps(summary, indent=2) + '\n')
    ok = all(all(o['checks'].values()) for o in results)
    return 0 if ok else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('files', nargs='+', help='One or two SensFunc files')
    parser.add_argument('--plot', dest='do_plot', action='store_true',
                        help='Write <stem>_vs_calspec.png next to each file')
    parser.add_argument('--json', dest='json_out', help='Write the results as JSON')
    a = parser.parse_args()
    if len(a.files) > 2:
        parser.error('give one or two files')
    sys.exit(main(**vars(a)))
