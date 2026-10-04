#!/usr/bin/env python
"""Is a frame's sky dominated by OH lines or by continuum (e.g. twilight)? (S6b diagnosis)

Usage:
    conda run -n pypeit14b python scripts/mosfire/oh_continuum_check.py DATE [--band J2]

For every on-sky frame of the night: the Sun's altitude at mid-exposure
(Maunakea), and the measured sky in the J2 window with the least OH emission
in the Gemini model (a 40 A window chosen automatically, Gemini ``TRANS`` >
0.9). The measurement is in e-/s/arcsec^2/A over the slit's central rows,
with objects masked, flat-fielded, as in ``monitor.line_fluxes``; the Gemini
prediction for the same window, through the night's throughput, is shown
beside it. A frame whose low-OH window is far above the model, and rising
with solar altitude, has a continuum (twilight) problem, not a
slit-normalisation problem.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, get_sun
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
import astropy.units as u

from keck_etcs import paths
from keck_etcs.calib import monitor as mo, monitor_configs as mc
from keck_etcs.calib.harvest import EFF_APERTURE, SKYGRID

KECK = EarthLocation(lat=19.8263 * u.deg, lon=-155.4747 * u.deg, height=4145 * u.m)
WIN = 40.0   # A


def low_oh_window(lo, hi):
    with fits.open(SKYGRID) as h:
        wave = h['WAVE'].data.astype(float) * 10.0
        sky = h['SKYBG'].data[3].astype(float)      # airmass 1.0, PWV 1.6
        trans = h['TRANS'].data[3].astype(float)
    best = None
    for c in np.arange(lo + 100, hi - 100, 5.0):
        sel = np.abs(wave - c) <= WIN / 2
        if trans[sel].mean() < 0.9:
            continue
        v = sky[sel].sum()
        if best is None or v < best[1]:
            best = (c, v)
    return best[0]


def main(date, band='J2'):
    results = {}
    night = paths.night_dir('mosfire', date)
    m = json.loads((night / 'run_manifest.json').read_text())
    cfg = mc.get_config('keck_mosfire')
    cal = night / 'redux' / 'Calibrations'
    from pypeit.flatfield import FlatImages
    from pypeit.specobjs import SpecObjs
    flat = FlatImages.from_file(str(sorted(cal.glob('Flat_*.fits'))[0]), chk_version=False)
    norm, waveimg = np.asarray(flat.pixelflat_norm, float), np.asarray(flat.pixelflat_waveimg, float)
    central = mo.central_rows_mask(sorted(cal.glob('Slits_*.fits.gz'))[0], norm.shape).any(axis=0)
    lo, hi = cfg['band_windows'][band]
    c = low_oh_window(lo, hi)
    hrow = sorted((night / 'harvest').glob('*_row.ecsv'))
    curve = Table.read(str(hrow[0]).replace('_row.ecsv', '.ecsv'), format='ascii.ecsv') if hrow else None
    t_c = float(np.interp(c, curve['wave'], curve['thru_raw'])) if curve is not None else np.nan
    print(f'low-OH window: {c - WIN / 2:.0f}-{c + WIN / 2:.0f} A; throughput there {t_c:.3f}')
    sci = night / 'redux' / 'Science'
    for f in m['frames']:
        if not (('science' in f['frametype']) or ('standard' in f['frametype'])):
            continue
        hdr = fits.getheader(night / 'raw' / f['filename'])
        texp = float(hdr['TRUITIME'])
        t_mid = Time(float(hdr['MJD-OBS']) + 0.5 * texp / 86400.0, format='mjd')
        sun = get_sun(t_mid).transform_to(AltAz(obstime=t_mid, location=KECK)).alt.deg
        img, _ = mo.process_raw(night / 'raw' / f['filename'], frame='scienceframe')
        img = np.where(norm > 0, img / texp / np.where(norm > 0, norm, 1.0), np.nan)
        mask = central.copy()
        s1 = sorted(sci.glob(f'spec1d_{Path(f["filename"]).stem}-*.fits'))
        for so in (SpecObjs.from_fitsfile(str(s1[0]), chk_version=False) if s1 else []):
            cc, fw = float(so['SPAT_PIXPOS']), float(so['FWHM'] or 5.0)
            mask[max(int(cc - 3 * fw), 0):int(cc + 3 * fw) + 1] = False
        width, _ = mo.slit_from_decker(f['decker'])
        vals = []
        for j in np.where(mask)[0]:
            sel = np.abs(waveimg[:, j] - c) <= WIN / 2
            if sel.sum() > 5:
                dl = np.median(np.abs(np.diff(waveimg[sel, j])))
                vals.append(np.sum(img[sel, j]) / (WIN / dl))     # e-/s per pixel-row per spectral pixel
        per_pix = float(np.median(vals))
        disp = float(np.median(np.abs(np.diff(waveimg[:, central], axis=0))))
        meas = per_pix / disp / (cfg['platescale'] * width)       # e-/s/arcsec^2/A
        with fits.open(SKYGRID) as h:
            wave = h['WAVE'].data.astype(float) * 10.0
            sky = h['SKYBG'].data[3].astype(float) / 10.0         # ph/s/arcsec^2/A/m^2, X=1.0 PWV 1.6
        pred = float(np.mean(sky[np.abs(wave - c) <= WIN / 2])) * t_c * EFF_APERTURE
        print(f"{f['filename']} {f['target']:16s} slit {width:.0f}\" UT {t_mid.isot[11:19]} sun alt {sun:6.1f} deg: "
              f"low-OH sky {meas:7.3f} e-/s/arcsec^2/A (Gemini X=1 {pred:6.3f}; ratio {meas / pred:6.1f})")
        results[f['filename']] = (meas, width, float(hdr['AIRMASS']))

    # Continuum-corrected fixed windows: subtract each frame's low-OH level x window width
    mon = night / 'harvest' / f'{date}_monitor.ecsv'
    if mon.exists():
        t = Table.read(mon, format='ascii.ecsv')
        win = t[t['metric'] == 'line_flux_window']
        disp = float(np.median(np.abs(np.diff(waveimg[:, central], axis=0))))
        width_a = 2 * 1.5 * mo.sky_line_fwhm_A(mo.WINDOW_SLIT, disp)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from verify_monitor import van_rhijn
        print(f'continuum-corrected OH in the fixed windows (window {width_a:.1f} A), zenith-normalised:')
        corr = {}
        for fn, (cont, width, am) in results.items():
            sub = win[win['frame'] == fn]
            oh = float(np.sum(sub['value'])) - len(sub) * cont * width_a
            corr[fn] = (oh / float(van_rhijn(am)), width)
            print(f'  {fn} {width:.0f}": total {float(np.sum(sub["value"])):8.1f}, continuum {len(sub) * cont * width_a:8.1f}, '
                  f'OH {corr[fn][0]:8.1f} e-/s/arcsec^2')
        n1 = np.median([v for v, w in corr.values() if w <= 1.0])
        n5 = np.median([v for v, w in corr.values() if w > 1.0])
        print(f'  5"/1" ratio after continuum correction: {n5 / n1:.3f}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date')
    p.add_argument('--band', default='J2')
    a = p.parse_args()
    sys.exit(main(a.date, a.band))
