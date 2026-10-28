#!/usr/bin/env python
"""Fit the K-band thermal continuum of one reduced night: the between-line sky excess over the Gemini model (design 9.5, D60; plan S23d, S25).

Usage:
    python scripts/mosfire/fit_thermal_continuum.py DATE [--band K] [--pwv 1.6] [--window 21500 24000]
        [--frames FILE ...] [--json OUT.json]

For every on-sky frame of the night's reduction (``run_manifest.json`` of
``mosfire/DATE/<band>/``; standards and science alike) the sky spectrum is
measured from the **raw** frame, not from the A-B spec2d (whose sky is
subtracted): PypeIt's raw-image processing (gain applied, no flat;
``keck_etcs.calib.monitor.process_raw``), divided by the pixel flat and the
exposure time, the median over the slit's central spatial rows with the
frame's extracted objects masked (+-3 FWHM), on the flat's wavelength image.
That is the sky in e-/s per pixel, which is turned into a surface
brightness above the telescope,

    SB(lam) = e_rate / (A_tel * T_sys(lam) * w_slit * p * dlam) * 10      [ph/s/arcsec^2/nm/m^2]

with the Keck effective area (72.37 m^2), the band's end-to-end throughput
``T_sys`` (the instrument module's filter-free curve for the night's era
times the filter curve; **provisional** XTcalc 2012 for K until the K
standards are reduced, which the output records), the slit width times the
plate scale and the local dispersion. The Gemini model at the frame's
airmass and ``--pwv`` (1.6 mm by default; MOSFIRE's telluric fit gives no
PWV in K, 9.3), smoothed to the slit's LSF, is the model sky. Both are
reduced to their **10th percentile in 100 A bins** over ``--window``
(2.15-2.40 um by default: redward of the CO2 bands, where the model's
between-line level is the thermal floor), and the excess is fitted as

    excess(lam) = eps_eff * P_ph(lam, T_tube)

with ``T_tube`` the night's median ``TUBETEMP`` (D60, Q65; the tube is the
proxy for the mirrors and dome) and ``P_ph`` the photon Planck radiance
(``keck_etcs.core.sky.planck_photons`` if present, else the local copy).
``eps_eff`` per bin, its median per frame and the night's median are
reported, with the same quantity at the design's 275 K for comparison with
9.2 (eps 0.12-0.15). Written to ``<night>/thermal/thermal_<DATE>.ecsv``
(per bin) and ``.json`` (per frame and night, with the provenance). The K
doc (S25) re-runs this on every K night for the per-night ``eps_eff``
monitor metric (9.6) and the ETC default.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

from keck_etcs import paths
from keck_etcs.calib import monitor as mo
from keck_etcs.calib.harvest import EFF_APERTURE
from keck_etcs.core import atmosphere
from keck_etcs.instruments.mosfire import MOSFIRE, PLATESCALE

T_DESIGN_K = 275.0
BIN_A = 100.0
PERCENTILE = 10.0


def planck_photons(wave_A, T):
    """Grey-body (emissivity 1) photon radiance [photons/s/arcsec^2/nm/m^2] at wavelength [A], temperature [K]."""
    h, c, k = 6.62607015e-34, 2.99792458e8, 1.380649e-23
    lam = np.asarray(wave_A, float) * 1e-10
    b = 2 * c / lam ** 4 / np.expm1(h * c / (lam * k * T))      # photons/s/m^2/sr/m
    return b * (np.pi / 180 / 3600) ** 2 * 1e-9


def binned_floor(wave, value, lo, hi, step=BIN_A, pct=PERCENTILE):
    """``(centres, floor)``: the ``pct`` percentile of ``value`` in ``step``-wide bins over lo-hi (NaN when < 10 samples)."""
    edges = np.arange(lo, hi + step, step)
    cen, out = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        s = (wave >= a) & (wave < b) & np.isfinite(value)
        cen.append(0.5 * (a + b))
        out.append(float(np.percentile(value[s], pct)) if s.sum() >= 10 else np.nan)
    return np.array(cen), np.array(out)


def main(date, band='K', pwv=1.6, window=(21500.0, 24000.0), frames=None, json_out=None):
    night = paths.night_dir('mosfire', date, band=band)
    raw_dir = paths.night_dir('mosfire', date, 'raw', band=band)
    m = json.loads((night / 'run_manifest.json').read_text())
    band = m.get('band') or m.get('filter') or band
    cal = night / 'redux' / 'Calibrations'
    from pypeit.flatfield import FlatImages
    from pypeit.specobjs import SpecObjs
    flat = FlatImages.from_file(str(sorted(cal.glob('Flat_*.fits'))[0]), chk_version=False)
    norm, waveimg = np.asarray(flat.pixelflat_norm, float), np.asarray(flat.pixelflat_waveimg, float)
    central = mo.central_rows_mask(sorted(cal.glob('Slits_*.fits.gz'))[0], norm.shape).any(axis=0)
    # the band's end-to-end throughput for the night's era (filter-free curve x filter), provisional or not
    era, era_w = MOSFIRE.era_for_date(f'{date[:4]}-{date[4:6]}-{date[6:]}')
    group = MOSFIRE.group_of(band)
    th = MOSFIRE.throughput_for_window(era, window[0] - 500, window[1] + 500, group=group)
    fc = MOSFIRE.filter_curve(band)
    tsys = lambda w: (np.interp(w, th['wave_A'], th['thru'], left=np.nan, right=np.nan)
                      * np.interp(w, fc['wave_A'], fc['transmission'], left=0.0, right=0.0))
    g = MOSFIRE.sky_grid()
    sel_g = (g['wave_A'] >= window[0] - 300) & (g['wave_A'] <= window[1] + 300)
    gw = g['wave_A'][sel_g]
    sci = night / 'redux' / 'Science'
    onsky = [f for f in m['frames'] if ('science' in f['frametype']) or ('standard' in f['frametype'])]
    if frames:
        onsky = [f for f in onsky if f['filename'] in set(frames)]
    per_frame, rows = [], []
    tubes = []
    for f in onsky:
        hdr = fits.getheader(raw_dir / f['filename'])
        texp, airmass = float(hdr['TRUITIME']), float(hdr['AIRMASS'])
        tube = hdr.get('TUBETEMP')
        tubes.append(None if tube is None else float(tube))
        width, _ = mo.slit_from_decker(f['decker'])
        img, _ = mo.process_raw(raw_dir / f['filename'], frame='scienceframe')
        img = np.where(norm > 0, img / texp / np.where(norm > 0, norm, 1.0), np.nan)
        mask = central.copy()
        for s1 in sorted(sci.glob(f'spec1d_{Path(f["filename"]).stem}-*.fits')):
            for so in SpecObjs.from_fitsfile(str(s1), chk_version=False):
                cc, fw = float(so['SPAT_PIXPOS']), float(so['FWHM'] or 5.0)
                mask[max(int(cc - 3 * fw), 0):int(cc + 3 * fw) + 1] = False
        cols = np.flatnonzero(mask)
        sky_e = np.nanmedian(img[:, cols], axis=1)                       # e-/s per pixel per spectral row
        wave = np.nanmedian(waveimg[:, cols], axis=1)
        disp = np.abs(np.gradient(wave))
        ok = np.isfinite(sky_e) & (wave > 0) & (disp > 0)
        sb = np.full(wave.size, np.nan)
        sb[ok] = sky_e[ok] / (EFF_APERTURE * tsys(wave[ok]) * width * PLATESCALE * disp[ok]) * 10.0
        # the model at the frame's airmass and PWV, smoothed to the slit's LSF
        sky_g, _ = atmosphere.interp_grid(g['skybg'][:, sel_g], g['airmass'], g['pwv_mm'], airmass, pwv)
        fwhm_pix, _ = MOSFIRE.lsf_fwhm_pix(width, band)
        from scipy.ndimage import gaussian_filter1d
        step_g = float(np.median(np.diff(gw)))
        model = np.interp(wave, gw, gaussian_filter1d(sky_g, fwhm_pix * float(np.median(disp[ok])) / 2.3548 / step_g))
        cen, meas_floor = binned_floor(wave, sb, *window)
        _, model_floor = binned_floor(wave, np.where(ok, model, np.nan), *window)
        excess = meas_floor - model_floor
        t_tube = (float(tube) + 273.15) if tube is not None else T_DESIGN_K
        eps = excess / planck_photons(cen, t_tube)
        eps275 = excess / planck_photons(cen, T_DESIGN_K)
        good = np.isfinite(eps)
        rec = {'frame': f['filename'], 'frametype': f['frametype'], 'target': f['target'], 'exptime_s': texp,
               'airmass': airmass, 'slit_width_arcsec': width, 'tube_temp_C': tube, 'T_K': t_tube,
               'n_bins': int(good.sum()), 'eps_eff_median': float(np.nanmedian(eps)) if good.any() else None,
               'eps_eff_275K_median': float(np.nanmedian(eps275)) if good.any() else None,
               'measured_floor_median': float(np.nanmedian(meas_floor)), 'model_floor_median': float(np.nanmedian(model_floor)),
               'ratio_measured_over_model_median': float(np.nanmedian(meas_floor / model_floor))}
        per_frame.append(rec)
        for c, mf, gf, ex, e, e2 in zip(cen, meas_floor, model_floor, excess, eps, eps275):
            rows.append({'frame': f['filename'], 'wave_A': float(c), 'measured': mf, 'model': gf, 'excess': ex,
                         'eps_eff': e, 'eps_eff_275K': e2, 'tsys': float(tsys(c))})
        print(f"{f['filename']} {f['target']:14s} {width:.1f}\" X={airmass:.3f} tube {tube} C: floor measured "
              f"{rec['measured_floor_median']:.2f} model {rec['model_floor_median']:.2f} (x{rec['ratio_measured_over_model_median']:.1f}); "
              f"eps_eff {rec['eps_eff_median']:.3f} at {t_tube:.1f} K ({rec['eps_eff_275K_median']:.3f} at 275 K) over {good.sum()} bins")
    if not per_frame:
        print('no on-sky frames')
        return 1
    t = Table(rows=rows)
    for c in ('measured', 'model', 'excess', 'eps_eff', 'eps_eff_275K', 'tsys'):
        t[c].format = '.5g'
    tube_med = float(np.nanmedian([x for x in tubes if x is not None])) if any(x is not None for x in tubes) else None
    night_eps = float(np.nanmedian([r['eps_eff_median'] for r in per_frame if r['eps_eff_median'] is not None]))
    night_eps275 = float(np.nanmedian([r['eps_eff_275K_median'] for r in per_frame if r['eps_eff_275K_median'] is not None]))
    # the per-bin night median: the thermal term's wavelength dependence
    per_bin = []
    for c in sorted(set(t['wave_A'])):
        s = t[t['wave_A'] == c]
        per_bin.append({'wave_A': float(c), 'excess_median': float(np.nanmedian(s['excess'])),
                        'eps_eff_median': float(np.nanmedian(s['eps_eff']))})
    summary = {'night': date, 'band': band, 'era': era.name, 'n_frames': len(per_frame), 'pwv_mm_assumed': pwv,
               'window_A': list(window), 'bin_A': BIN_A, 'percentile': PERCENTILE,
               'tube_temp_C_median': tube_med, 'T_K': None if tube_med is None else tube_med + 273.15,
               'eps_eff_night_median': night_eps, 'eps_eff_275K_night_median': night_eps275,
               'per_bin': per_bin, 'frames': per_frame,
               'throughput': {'file': th['file'], 'calib_version': th['calib_version'], 'provisional': th['provisional'],
                              'note': 'T_sys = filter-free curve x filter curve; provisional = XTcalc 2012 placeholder'},
               'method': __doc__.split('\n\n')[1].replace('\n', ' '),
               'created': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               'script': 'scripts/mosfire/fit_thermal_continuum.py'}
    out = night / 'thermal'
    out.mkdir(exist_ok=True)
    t.meta = {k: v for k, v in summary.items() if k not in ('per_bin', 'frames')}
    t.write(out / f'thermal_{date}.ecsv', format='ascii.ecsv', overwrite=True)
    (out / f'thermal_{date}.json').write_text(json.dumps(summary, indent=1, default=str) + '\n')
    if json_out:
        Path(json_out).write_text(json.dumps(summary, indent=1, default=str) + '\n')
    print(f'night {date} {band}: {len(per_frame)} frame(s), TUBETEMP median {tube_med} C -> eps_eff {night_eps:.3f} '
          f'(at 275 K: {night_eps275:.3f}); throughput {th["file"]} ({"PROVISIONAL" if th["provisional"] else th["calib_version"]})')
    print('per bin (night median): ' + ', '.join(f"{b['wave_A']:.0f}: {b['eps_eff_median']:.3f}" for b in per_bin))
    print(f'wrote {out / f"thermal_{date}.ecsv"} and .json')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date')
    p.add_argument('--band', default='K')
    p.add_argument('--pwv', type=float, default=1.6, help='PWV [mm] of the Gemini model (default 1.6)')
    p.add_argument('--window', type=float, nargs=2, default=(21500.0, 24000.0), metavar=('LO', 'HI'))
    p.add_argument('--frames', nargs='+', help='only these raw frames')
    p.add_argument('--json', dest='json_out')
    a = p.parse_args()
    sys.exit(main(a.date, a.band, a.pwv, tuple(a.window), a.frames, a.json_out))
