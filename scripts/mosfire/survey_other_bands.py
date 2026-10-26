#!/usr/bin/env python
"""Survey of what the Y, H and K bands need from the MOSFIRE ETC (design, "Other bands" prompt #1).

Prints, per spectroscopic band, the numbers quoted in section 9 of
``docs/keck_mosfire_design.md``:

1. the wavelength footprint and dispersion of PypeIt's stitched OH templates
   (``keck_mosfire_OH_<band>.fits``) and, where a dev-suite reduction exists
   locally, the footprint of the centred long slit from its ``WaveCalib``;
2. the shipped filter half-power bands, the ETC window they imply and its
   size in pixels, and the AB-Vega offsets;
3. the Gemini sky grid inside each window: continuum between lines, median,
   brightest line, and the atmospheric transmission;
4. the May 2012 MOSFIRE sky spectra that ship with Keck's XTcalc
   (``MosfireSkySpec/<band>sky.eps.msdc.dat``, e-/s/pix per spatial pixel,
   0.7" slit) against the Gemini model converted to the same units with
   XTcalc's own efficiency curve: the ratio of the between-line continuum in
   200 A bins. In K this measures the thermal emission of the telescope and
   dome that the Gemini model does not contain;
5. a grey-body estimate of that thermal emission for comparison (printed
   with items 3 and 4);
6. XTcalc's 2012 efficiency curves per band (``MosfireSpecEff``) times the
   mirror reflectivity its README gives;
7. the time for the brightest sky line of each band to reach the 1 percent
   non-linearity limit through a 0.7" slit (printed with item 3);
8. PypeIt's 2MASS filter curves (``TMASS-J/H/K``) and the OH / lamp line
   lists per band;
9. with ``--koa``, a KOA TAP count of public long-slit spectroscopy frames
   per filter (``koa_mosfire``), and of frames whose target name looks like
   a HIP/HD star or a CALSPEC white dwarf.

Usage:
    conda run -n pypeit14b python scripts/mosfire/survey_other_bands.py [--koa]

Needs PypeIt (templates, filters), ``$KECK_ETCS_DATA/external/xtcalc`` for
items 4 and 6, and the dev suite's ``REDUX_OUT/keck_mosfire`` for item 1.
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from keck_etcs.instruments.mosfire import MOSFIRE, AREA_M2, PLATESCALE, NONLINEAR_ADU  # noqa: E402
from keck_etcs.instruments.base import DATA_DIR  # noqa: E402
from keck_etcs.core import atmosphere  # noqa: E402

BANDS = ('Y', 'J', 'J2', 'H', 'K')
ORDER = {'Y': 6, 'J': 5, 'J2': 5, 'J3': 5, 'H': 4, 'K': 3}
# XTcalc README (MosfireSpecEff): mirror reflectivity per surface that reproduces the end-to-end throughput
KMREF = {'Y': 0.85, 'J': 0.89, 'J2': 0.89, 'H': 0.94, 'K': 0.95}
# Keck MOSFIRE web page, "wavelength coverage for a slit at the centre of the field" (um)
WEB_COVERAGE = {'Y': (0.972, 1.125), 'J': (1.153, 1.352), 'H': (1.468, 1.804), 'K': (1.954, 2.397)}
GAIN = 2.15
DEVSUITE = Path(os.environ.get('PYPEIT_DEV', Path.home() / 'Projects/PypeIt/PypeIt-development-suite'))
XTDIR = Path(os.environ.get('KECK_ETCS_DATA', Path.home() / 'Projects/PypeIt/keck-etcs-data')) / 'external/xtcalc/XTcalc_dir'
REDUX = {'Y': 'Y_long', 'J2': 'J2_long', 'H': 'longslit_3x0.7_H', 'K': 'K_long'}
PLANCK_T = 275.0   # K, telescope and dome


def hdr(s):
    print(f'\n=== {s}')


def section(fn):
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:          # keep going; the survey is informational
            print(f'  [{fn.__name__} failed: {exc!r}]')
    return wrapped


@section
def templates():
    hdr('1a. PypeIt OH templates (stitched across CSU positions, N2): footprint and dispersion')
    from pypeit import dataPaths
    out = {}
    for band in ('Y', 'J', 'J2', 'H', 'K'):
        name = f'keck_mosfire_OH_{band}.fits'
        path = dataPaths.reid_arxiv.get_file_path(name)
        with fits.open(path) as h:
            wave = None
            for x in h:
                if getattr(x, 'columns', None) is not None and 'wave' in x.columns.names:
                    wave = np.asarray(x.data['wave'], float)
                    break
            if wave is None:
                wave = np.asarray(h[0].data, float).ravel()
        wave = wave[wave > 0]
        disp = float(np.median(np.diff(wave)))
        out[band] = (wave.min(), wave.max(), disp, wave.size)
        print(f'  {band:3s} {wave.min():9.1f}-{wave.max():9.1f} A  {wave.size:5d} px  {disp:.4f} A/px  '
              f'(x m/5 of J: {disp * ORDER[band] / 5:.4f})')
    return out


@section
def devsuite_footprints():
    hdr('1b. Centred long-slit footprint from local dev-suite WaveCalib files (pixel 0 and 2047)')
    from pypeit.wavecalib import WaveCalib
    out = {}
    for band, setup in REDUX.items():
        cal = DEVSUITE / 'REDUX_OUT/keck_mosfire' / setup / 'Calibrations'
        files = sorted(cal.glob('WaveCalib_*_DET01.fits')) if cal.exists() else []
        if not files:
            print(f'  {band:3s} {setup}: no WaveCalib locally (reduce it first)')
            continue
        wc = WaveCalib.from_file(files[0])
        for wf in wc.wv_fits:
            if wf.wave_soln is None:
                continue
            w = np.asarray(wf.wave_soln, float)
            good = w > 0
            w0, w1 = w[good][0], w[good][-1]
            d = (w1 - w0) / (good.sum() - 1)
            out[band] = (w0, w1, d)
            print(f'  {band:3s} {setup:18s} {files[0].name}: slit {wf.spat_id}: {w0:9.1f}-{w1:9.1f} A, '
                  f'{good.sum()} px, {d:.4f} A/px')
            break
    return out


@section
def filters():
    hdr('2. Shipped filter curves: half-power band, AB-Vega, window if detector-limited')
    out = {}
    for band in ('Y', 'J', 'J2', 'J3', 'H', 'K'):
        f = DATA_DIR / 'mosfire/filters' / f'mosfire_{band}.ecsv'
        if not f.exists():
            print(f'  {band:3s} no filter file')
            continue
        t = Table.read(f, format='ascii.ecsv')
        lo, hi = (float(x) for x in t.meta['half_power_A'])
        abv = float(t.meta['ab_minus_vega'])
        disp = 1.2922 * 5 / ORDER[band]
        npix_filter = (hi - lo) / disp
        web = WEB_COVERAGE.get(band)
        s = f'  {band:3s} half-power {lo:8.1f}-{hi:8.1f} A ({hi - lo:6.0f} A, {npix_filter:5.0f} px at {disp:.3f} A/px)' \
            f'  AB-Vega {abv:.3f}'
        if web:
            s += f'  web coverage {web[0] * 1e4:.0f}-{web[1] * 1e4:.0f} A ({(web[1] - web[0]) * 1e4 / disp:.0f} px)'
        if npix_filter > 2048:
            s += f'  DETECTOR-LIMITED: {npix_filter - 2048:.0f} px ({(npix_filter - 2048) * disp:.0f} A) of the filter band fall off'
        print(s)
        out[band] = (lo, hi, abv, disp)
    return out


def planck_photons(wave_A, T):
    """Grey-body (emissivity 1) photon radiance [photons/s/arcsec^2/nm/m^2]."""
    h, c, k = 6.62607015e-34, 2.99792458e8, 1.380649e-23
    lam = wave_A * 1e-10
    b = 2 * c / lam ** 4 / np.expm1(h * c / (lam * k * T))      # photons/s/m^2/sr/m
    sr_per_arcsec2 = (np.pi / 180 / 3600) ** 2
    return b * sr_per_arcsec2 * 1e-9


@section
def gemini(filt):
    hdr('3. Gemini grid inside each window (airmass 1.5, PWV 1.6 mm): sky [ph/s/arcsec^2/nm/m^2], transmission')
    g = MOSFIRE.sky_grid()
    out = {}
    for band in ('Y', 'J', 'H', 'K'):
        if band not in filt:
            continue
        lo, hi, _, disp = filt[band]
        if band in WEB_COVERAGE:
            lo, hi = max(lo, WEB_COVERAGE[band][0] * 1e4), min(hi, WEB_COVERAGE[band][1] * 1e4)
        sel = (g['wave_A'] >= lo) & (g['wave_A'] <= hi)
        sky, _ = atmosphere.interp_grid(g['skybg'][:, sel], g['airmass'], g['pwv_mm'], 1.5, 1.6)
        trans, _ = atmosphere.interp_grid(g['trans'][:, sel], g['airmass'], g['pwv_mm'], 1.5, 1.6)
        w = g['wave_A'][sel]
        # between-line continuum: 10th percentile in 100 A bins, then median over the band
        edges = np.arange(lo, hi + 100, 100.0)
        cont = [np.percentile(sky[(w >= a) & (w < b)], 10) for a, b in zip(edges[:-1], edges[1:]) if ((w >= a) & (w < b)).sum() > 10]
        imax = int(np.argmax(sky))
        # brightest line, integrated over +-1.5 A (the grid is 0.5 A; an OH line fills 1-2 samples), through a
        # 0.7" slit at T_sys 0.25 into one spatial pixel; spread over the 0.7" LSF (2.6 px, Gaussian peak 0.94/2.6)
        near = np.abs(w - w[imax]) <= 1.5
        line_ph = np.sum(sky[near]) * 0.05                      # ph/s/arcsec^2/m^2, integrated
        peak_e = line_ph * AREA_M2 * 0.25 * 0.7 * PLATESCALE * 0.94 / 2.6
        t_sat = NONLINEAR_ADU * GAIN / peak_e
        thermal = planck_photons(np.array([0.5 * (lo + hi), hi]), PLANCK_T)
        print(f'  {band:3s} {lo:7.0f}-{hi:7.0f} A: continuum (10th pct) median {np.median(cont):8.1f}, '
              f'band median {np.median(sky):8.1f}, brightest line {sky[imax]:9.1f} at {w[imax]:.0f} A; '
              f'trans median {np.median(trans):.3f}, frac < 0.8: {np.mean(trans < 0.8):.2f}')
        print(f'        continuum per 100 A bin: min {np.min(cont):.1f}, max {np.max(cont):.1f}; '
              f'brightest line ~{peak_e:.0f} e-/s/pix (0.7", T_sys 0.25) -> 26k ADU in {t_sat:.0f} s; '
              f'grey body {PLANCK_T:.0f} K eps=1 at band centre {thermal[0]:.2g}, at red edge {thermal[1]:.2g}')
        out[band] = {'cont': cont, 'edges': edges}
    return out


def _read_two_col(path):
    rows = []
    with open(path) as f:
        for line in f:
            s = line.split()
            if len(s) >= 2:
                try:
                    rows.append((float(s[0]), float(s[1])))
                except ValueError:
                    continue
    a = np.array(rows)
    return a[:, 0], a[:, 1]


@section
def xtcalc_sky(filt):
    hdr('4. XTcalc May-2012 measured MOSFIRE sky (MosfireSkySpec/<band>sky_cal_pA.sav, erg/s/cm^2/A per spatial '
        'row of a 0.7" slit) converted to ph/s/arcsec^2/nm/m^2, against the Gemini model (airmass 1.0, PWV 1.6): '
        'between-line continuum (10th percentile) per 200 A bin where the transmission is > 0.95; the model is '
        'smoothed to the 0.7" LSF (2.7 px) first')
    from scipy.io import readsav
    g = MOSFIRE.sky_grid()
    hc = 1.98645e-8     # erg A
    for band in ('Y', 'J', 'H', 'K'):
        f = XTDIR / 'MosfireSkySpec' / f'{band}sky_cal_pA.sav'
        if not f.exists():
            print(f'  {band}: missing {f}')
            continue
        d = readsav(str(f))
        sw, sf = np.asarray(d['lam'], float), np.asarray(d['mksky'], float)
        meas = sf / (hc / sw) * 1e4 * 10.0 / (0.7 * PLATESCALE)       # ph/s/arcsec^2/nm/m^2
        sel = (g['wave_A'] >= sw.min() - 5) & (g['wave_A'] <= sw.max() + 5)
        sky, _ = atmosphere.interp_grid(g['skybg'][:, sel], g['airmass'], g['pwv_mm'], 1.0, 1.6)
        trans, _ = atmosphere.interp_grid(g['trans'][:, sel], g['airmass'], g['pwv_mm'], 1.0, 1.6)
        gw = g['wave_A'][sel]
        # smooth the model to MOSFIRE's 0.7" resolution (2.7 px) before comparing between-line levels
        from scipy.ndimage import gaussian_filter1d
        disp = float(np.median(np.diff(sw)))
        sky_s = gaussian_filter1d(sky, 2.7 * disp / 2.3548 / 0.5)
        gem = np.interp(sw, gw, sky_s)
        tr = np.interp(sw, gw, trans)
        edges = np.arange(np.floor(sw.min() / 200) * 200, sw.max() + 200, 200.0)
        print(f'  {band}: measured {sw.min():.0f}-{sw.max():.0f} A, {sw.size} px, {np.median(np.diff(sw)):.3f} A/px')
        print('      bin(A)       meas_cont   gem_cont   ratio     meas_med/gem_med  (ph/s/arcsec^2/nm/m^2)')
        for a, b in zip(edges[:-1], edges[1:]):
            m = (sw >= a) & (sw < b) & (sf > 0) & (tr > 0.95)
            if m.sum() < 20:
                continue
            mc, gc = np.percentile(meas[m], 10), np.percentile(gem[m], 10)
            mm, gm = np.median(meas[m]), np.median(gem[m])
            print(f'      {a:6.0f}-{b:6.0f} {mc:10.2f} {gc:10.2f} {mc / gc if gc > 0 else np.nan:7.2f}     {mm / gm if gm > 0 else np.nan:7.2f}')
        if band == 'K':
            for eps in (0.05, 0.1, 0.2):
                th = planck_photons(np.array([20000.0, 21500.0, 23000.0, 24000.0]), PLANCK_T) * eps
                print(f'      grey body {PLANCK_T:.0f} K, eps {eps}: at 2.00/2.15/2.30/2.40 um = '
                      + ' / '.join(f'{x:.2f}' for x in th))


@section
def xtcalc_eff():
    hdr('6. XTcalc 2012 efficiency curves x mirror reflectivity^2 (end-to-end, no atmosphere)')
    for band in ('Y', 'J', 'H', 'K'):
        e = XTDIR / 'MosfireSpecEff' / f'{band}eff.sm.dat'
        if not e.exists():
            print(f'  {band}: missing')
            continue
        w, t = _read_two_col(e)
        if w.max() < 100:
            w = w * 1e4
        tt = np.clip(t, 0, None) * KMREF[band] ** 2
        inb = tt > 0.5 * tt.max()
        print(f'  {band}: {w.min():.0f}-{w.max():.0f} A; peak {tt.max():.3f} at {w[np.argmax(tt)]:.0f} A; '
              f'median over the half-max range ({w[inb].min():.0f}-{w[inb].max():.0f} A) {np.median(tt[inb]):.3f}; '
              f'KMRef {KMREF[band]}')


@section
def tmass_and_lines():
    hdr('8. PypeIt 2MASS filter curves and line lists')
    from pypeit import dataPaths
    with fits.open(dataPaths.filters.get_file_path('filtercurves.fits')) as h:
        for name in ('TMASS-J', 'TMASS-H', 'TMASS-K'):
            d = h[name].data
            lam = np.asarray(d['lam'], float)
            tr = np.asarray(d['Rlam'], float)
            use = tr > 0.5 * tr.max()
            print(f'  {name}: {lam.min():.0f}-{lam.max():.0f} A, half-max {lam[use].min():.0f}-{lam[use].max():.0f} A, '
                  f'{lam.size} points')
    for name in ('OH_MOSFIRE_Y', 'OH_MOSFIRE_J', 'OH_MOSFIRE_H', 'OH_MOSFIRE_K', 'OH_R24000',
                 'Ne_IR_MOSFIRE', 'Ar_IR_MOSFIRE'):
        p = dataPaths.linelist.get_file_path(f'{name}_lines.dat')
        t = Table.read(p, format='ascii.fixed_width', delimiter='|')
        w = np.asarray(t['wave'], float)
        print(f'  {name:16s}: {w.min():.0f}-{w.max():.0f} A, {w.size} lines; '
              + ', '.join(f'{b} {((w >= lo) & (w <= hi)).sum()}'
                          for b, (lo, hi) in (('Y', (9718, 11243)), ('J', (11530, 13520)), ('H', (14661, 18076)),
                                              ('K', (19215, 24046)))))


@section
def koa():
    hdr('9. KOA TAP: public spectroscopy frames per filter (long-slit masks), and star-like target names')
    import requests
    url = 'https://koa.ipac.caltech.edu/TAP/sync'

    def q(adql):
        r = requests.post(url, data={'REQUEST': 'doQuery', 'LANG': 'ADQL', 'FORMAT': 'csv', 'QUERY': adql},
                          timeout=600)
        r.raise_for_status()
        return Table.read(r.text, format='ascii.csv')

    base = "gratmode = 'spectroscopy' AND (maskname LIKE 'LONGSLIT%' OR maskname LIKE 'long2pos%')"
    t = q(f"SELECT filter, COUNT(*) AS n FROM koa_mosfire WHERE {base} GROUP BY filter ORDER BY filter")
    print('  long-slit and long2pos frames per filter:')
    for r in t:
        print(f'    {str(r["filter"]):4s} {int(r["n"]):7d}')
    star = ("(targname LIKE 'HIP%' OR targname LIKE 'HD%' OR targname LIKE 'GD%' OR targname LIKE 'Feige%' "
            "OR targname LIKE 'G191%' OR targname LIKE 'LDS%' OR targname LIKE 'BD+%')")
    t = q(f"SELECT filter, COUNT(*) AS n, COUNT(DISTINCT date_obs) AS nights FROM koa_mosfire WHERE {base} AND {star} "
          f"GROUP BY filter ORDER BY filter")
    print('  of these, HIP/HD/GD/Feige/G191/LDS/BD targets (frames, distinct nights):')
    for r in t:
        print(f'    {str(r["filter"]):4s} {int(r["n"]):7d} {int(r["nights"]):5d}')
    t = q(f"SELECT filter, COUNT(*) AS n, COUNT(DISTINCT date_obs) AS nights FROM koa_mosfire WHERE "
          f"gratmode = 'spectroscopy' AND maskname LIKE 'long2pos_specphot%' AND {star} GROUP BY filter ORDER BY filter")
    print('  long2pos_specphot star frames (the wide-slit throughput sample):')
    for r in t:
        print(f'    {str(r["filter"]):4s} {int(r["n"]):7d} {int(r["nights"]):5d}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--koa', action='store_true', help='also query KOA TAP (network)')
    args = ap.parse_args()
    templates()
    devsuite_footprints()
    filt = filters() or {}
    gemini(filt)
    xtcalc_sky(filt)
    xtcalc_eff()
    tmass_and_lines()
    if args.koa:
        koa()


if __name__ == '__main__':
    main()
