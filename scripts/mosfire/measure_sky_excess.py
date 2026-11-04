#!/usr/bin/env python
"""Measure a band's sky continuum excess over the Gemini model from our own reduced nights (design D61, 5.3.8; plan S24b).

Usage:
    conda run -n pypeit14b python scripts/mosfire/measure_sky_excess.py --band H [--nights 20141123 ...]
        [--pwv-default 1.6] [--moon-cut] [--no-write]

Between the OH lines the measured sky exceeds the Gemini model (1.05-1.5x in
J, 2.4-3.5x in H, design 8); a single ``sky_scale`` cannot fit lines and
continuum. D61 ships, per band, an **additive excess** ``E_band(lam)`` in
Gemini units (photons/s/arcsec^2/nm/m^2), added inside the ``sky_scale``
bracket of 5.3.8 by ``keck_etcs.etc.compute``.

Frames: every on-sky frame (standards and science alike) of every locally
reduced night of the band (``$KECK_ETCS_DATA/mosfire/<night>/<band>/`` with
``run_manifest.json`` and ``redux/Calibrations``; the raw frames under
``<night>/raw``, pulled from the bucket). Twilight frames (Sun above -18 deg
at mid-exposure, the monitor's rule) are excluded in every band. The Moon
(altitude, illuminated fraction and separation from the pointing, by
ephemeris as the Sun's altitude is; no header card exists) is recorded for
every frame; ``--moon-cut`` (the Y rule of D61) keeps only dark frames (Moon
below the horizon or illuminated less than 30 percent) when at least 20 of
them over at least 3 nights exist, otherwise uses all frames with
``moon_included = true`` and reports the dark-minus-moonlit difference. H
and K use all frames.

Per frame, as in ``fit_thermal_continuum.py`` (D60): the sky is measured
from the **raw** frame (PypeIt's raw processing, divided by the pixel flat
and the exposure time), the median over the central half of the slit's
spatial rows with the frame's extracted objects masked (+-3 FWHM), on the
flat's wavelength image; a long2pos mask is measured in its narrowest bars
(the 0.7" bars, where the standard never sits; the ``specphot.bars`` of the
run manifest), a long slit in its one slit. The e-/s per pixel become a
surface brightness above the telescope,

    SB(lam) = e_rate / (A_tel * T_sys(lam) * w_slit * p * dlam) * 10      [ph/s/arcsec^2/nm/m^2]

with the band's end-to-end throughput for the night's era (the instrument
module's filter-free curve times the filter curve; the night's ``T_sys``)
and the Gemini model at the frame's airmass and the night's fitted PWV
(``pwv_fit`` of ``standards.ecsv``, else ``--pwv-default``), smoothed to the
slit's LSF, is the model. A CDS frame carries an additive electronic pedestal
(the reset level), read in the raw frame's 4-pixel reference border: about
-43 ADU (-92 e-) in a 1.45 s frame, near 0 ADU from 2.9 s on. It is
subtracted per frame as the reference-pixel median times the gain
(``ref_pedestal``). The closed-bar columns next to a slit are not the
pedestal: they read the reference level in a 1.45 s frame but about 2 e-/s
above it afterwards (leak or scattered light; +7 ADU at 2.9 s, +21 ADU at
22 s, 2015-09-17 and 2014-06-01), and subtracting them put every long2pos
floor 3-6 units below zero (2026-11-03). Their level is kept per frame as
``closed_bar_e_per_s`` for diagnosis. The offset between the reference
pixels and the open pixels is taken as zero (``REF_OFFSET_ADU``); 13 ADU
(28 e-) would lower a 179 s frame's floor by 0.2 Gemini units, the
systematic quoted in the meta.

The between-line floor is the 10th percentile in 100 A bins over the band
window. The inter-line H sky is about 1 Gemini unit (the Maihara
continuum), while a 1-5 s standard frame measures it with a noise of
several units per bin, and a percentile of noise is biased low by about
1.3 sigma: per-frame floors from short frames are useless. The shipped
``excess`` is therefore ``measured - model`` of the **exposure-weighted
stack** of every usable frame (weights exptime x columns), with
``excess_err`` half the difference between the floors of the two
half-stacks (alternate frames); the D61 statistic (per-frame floors, median
over frames per night, median over nights) is kept as
``excess_night_median`` with its MAD and night count for the day long
frames (the validation night's science exposures) make the two agree.
``excess`` is clipped at zero; ``excess_raw`` keeps the sign.

Writes ``keck_etcs/data/sky/mosfire_sky_excess_<band>.ecsv`` (registered in
``index.yaml`` as ``<CALIB_VERSION>-dev`` until the next release stamps it)
and the per-frame table ``$KECK_ETCS_DATA/mosfire/sky_excess/sky_excess_<band>_frames.ecsv``
(every frame, bin and Moon record; the provenance of the curve).
"""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.io import fits
from astropy.table import Table

import keck_etcs
from keck_etcs import paths
from keck_etcs.calib import monitor as mo
from keck_etcs.calib.harvest import EFF_APERTURE, slit_from_decker
from keck_etcs.core import atmosphere
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE, PLATESCALE

REPO = Path(__file__).resolve().parents[2]
INDEX = DATA_DIR / 'index.yaml'
CALIB_VERSION = 'mosfire-2026.10'
SCRIPT = 'scripts/mosfire/measure_sky_excess.py'
BIN_A = 100.0
PERCENTILE = 10.0
MIN_EXPTIME_S = 60.0     # shorter frames: the percentile noise bias, and the long2pos bars beside a bright A0V
                         # standard carry scattered starlight (+4 units in 7-25 s frames); see measure_night
MIN_SAMPLES = 10
TWILIGHT_SUN_ALT = MOSFIRE.monitor['twilight_sun_alt_deg']
MOON_ILLUM_DARK = 0.30
MOON_MIN_DARK_FRAMES, MOON_MIN_DARK_NIGHTS = 20, 3
PEDESTAL_MARGIN, PEDESTAL_REACH = 8, 48
REF_OFFSET_ADU = 0.0     # open pixels relative to the reference pixels (module docstring)
REF_PEDESTAL_UNC_ADU = 13.0  # the alternative offset (closed bars at 2.9 s): 28 e-, 0.2 units in a 179 s frame
"""Pedestal columns: at least 8 pixels from any slit edge, within 48 pixels of the measured slit (its own
readout channel, as far as possible). A short CDS frame carries an additive pedestal (the reset anomaly:
about -100 e- per pixel in a 1.5 s frame, comparable to the sky), which the closed CSU bars of a
long2pos mask measure next to each slit; a 46-bar long slit has no closed bars (pedestal None, which only
matters for its short frames)."""


def binned_floor(wave, value, lo, hi, step=BIN_A, pct=PERCENTILE):
    """``(centres, floor)``: the ``pct`` percentile of ``value`` in ``step``-wide bins over lo-hi (NaN when < 10 samples)."""
    edges = np.arange(lo, hi + step, step)
    cen, out = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        s = (wave >= a) & (wave < b) & np.isfinite(value)
        cen.append(0.5 * (a + b))
        out.append(float(np.percentile(value[s], pct)) if s.sum() >= MIN_SAMPLES else np.nan)
    return np.array(cen), np.array(out)


def weighted_stack(frames, key):
    """Exposure x column weighted mean of the frames' ``key`` spectra (NaN where no frame has a value)."""
    w = np.array([f['weight'] for f in frames], float)[:, None]
    v = np.array([f[key] for f in frames], float)
    ok = np.isfinite(v)
    num = np.nansum(np.where(ok, w * v, 0.0), axis=0)
    den = np.sum(np.where(ok, w, 0.0), axis=0)
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)


def stacked_floor(frames, grid, lo, hi):
    """``(excess, err, measured_floor, model_floor, column_seconds)`` per bin from the stack of ``frames``.

    The floors are the percentile of the weighted stack (not the mean of
    per-frame floors, whose noise bias at short exposures is -1.3 sigma per
    frame); ``err`` is half the difference between the floors of the two
    half-stacks (alternate frames)."""
    def floors(fr):
        _, m = binned_floor(grid, weighted_stack(fr, 'sb'), lo, hi)
        _, g = binned_floor(grid, weighted_stack(fr, 'model_sb'), lo, hi)
        return m, g
    meas, model = floors(frames)
    if len(frames) >= 2:
        ma, ga = floors(frames[0::2])
        mb, gb = floors(frames[1::2])
        err = 0.5 * np.abs((ma - ga) - (mb - gb))
    else:
        err = np.full(meas.size, np.nan)
    return meas - model, err, meas, model, float(sum(f['weight'] for f in frames))


def moon_state(mjd_mid, ra_deg, dec_deg, site):
    """Moon altitude [deg], illuminated fraction and separation [deg] from the pointing at ``mjd_mid`` (ephemeris)."""
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body, get_sun
    from astropy.time import Time
    t = Time(mjd_mid, format='mjd')
    loc = EarthLocation(lat=site['lat_deg'] * u.deg, lon=site['lon_deg'] * u.deg, height=site['height_m'] * u.m)
    moon, sun = get_body('moon', t, loc), get_sun(t)
    alt = float(moon.transform_to(AltAz(obstime=t, location=loc)).alt.deg)
    elong = float(sun.separation(moon).rad)
    illum = 0.5 * (1.0 - np.cos(elong))
    sep = (float(moon.separation(SkyCoord(ra_deg * u.deg, dec_deg * u.deg)).deg)
           if ra_deg is not None and dec_deg is not None else None)
    return alt, float(illum), sep


def pointing(hdr):
    """(ra, dec) in degrees from the header (sexagesimal or degrees), else (None, None)."""
    from astropy.coordinates import SkyCoord
    try:
        ra, dec = hdr['RA'], hdr['DEC']
        if isinstance(ra, str) and ':' in ra:
            c = SkyCoord(ra, dec, unit=('hourangle', 'deg'))
            return float(c.ra.deg), float(c.dec.deg)
        return float(ra), float(dec)
    except Exception:
        return None, None


def night_pwv(std, date_iso, band, default):
    sel = std[(std['date'] == date_iso) & (std['filter'] == band)]
    vals = [float(v) for v in sel['pwv_fit'] if np.isfinite(float(v))] if len(sel) else []
    return (float(np.median(vals)), 'pwv_fit') if vals else (default, 'default')


def slit_edges(slits_file):
    """``(left, right, spat_id)`` of every slit: edges per spectral row (spec, nslit), ids per slit."""
    from pypeit.slittrace import SlitTraceSet
    slits = SlitTraceSet.from_file(str(slits_file), chk_version=False)
    left, right, _ = slits.select_edges()
    return np.asarray(left, float), np.asarray(right, float), np.asarray(slits.spat_id, int)


def pedestal(img, left, right, i, margin=PEDESTAL_MARGIN, reach=PEDESTAL_REACH):
    """Per-row pedestal of slit ``i``: the median of the closed-bar columns within ``reach`` pixels of the slit
    and at least ``margin`` pixels from every slit edge (None when no such column exists, e.g. a long slit)."""
    spat = np.arange(img.shape[1])[None, :]
    open_ = np.zeros(img.shape, bool)
    for j in range(left.shape[1]):
        open_ |= (spat >= left[:, j][:, None] - margin) & (spat <= right[:, j][:, None] + margin)
    near = (spat >= left[:, i][:, None] - reach) & (spat <= right[:, i][:, None] + reach)
    dark = near & ~open_
    if dark.sum(axis=1).min() < 5:
        return None
    return np.nanmedian(np.where(dark, img, np.nan), axis=1)


def ref_pedestal(rawf):
    """The frame's electronic pedestal [e-/pixel]: the median of the raw frame's 4-pixel reference border
    plus ``REF_OFFSET_ADU``, times the detector gain (module docstring)."""
    from pypeit.spectrographs.util import load_spectrograph
    d = fits.getdata(rawf).astype(float)
    ref = np.concatenate([d[:4].ravel(), d[-4:].ravel(), d[:, :4].ravel(), d[:, -4:].ravel()])
    gain = float(np.atleast_1d(load_spectrograph('keck_mosfire').get_detector_par(1)['gain'])[0])
    return (float(np.median(ref)) + REF_OFFSET_ADU) * gain


def slits_to_measure(manifest, decker):
    """``[(spat_id or None, width_arcsec), ...]``: the narrowest bars of a long2pos mask, else the one long slit."""
    sp = manifest.get('specphot') or {}
    bars = [b for b in (sp.get('bars') or []) if b.get('spat_id') is not None]     # untraced bars have no slit
    if bars:
        wmin = min(float(b['width_arcsec']) for b in bars)
        return [(int(b['spat_id']), float(b['width_arcsec'])) for b in bars if float(b['width_arcsec']) == wmin]
    width, _ = slit_from_decker(decker)
    return [(None, width)] if width else []


def measure_night(date, band, std, pwv_default, grid, site, min_texp=0.0):
    """Per-frame excess records of one night; ``None`` when the night has no usable products.

    Frames shorter than ``min_texp`` seconds are skipped before any processing: a
    percentile of a short frame's noise is biased low, and the 0.7" bars of a
    long2pos mask next to a bright A0V standard read about +4 Gemini units in
    7-25 s frames (scattered starlight; the closed bars beside them carry
    2 e-/s), against 1.0 in the 179 s long-slit science frames of 2022-01-11
    (2026-11-03). The shipped curve rests on long science frames.
    """
    night = paths.night_dir('mosfire', date, band=band)
    raw_dir = paths.night_dir('mosfire', date, 'raw', band=band)
    mp = night / 'run_manifest.json'
    cal = night / 'redux' / 'Calibrations'
    if not mp.exists() or not cal.is_dir():
        return None
    m = json.loads(mp.read_text())
    from pypeit.flatfield import FlatImages
    from pypeit.specobjs import SpecObjs
    flats = sorted(cal.glob('Flat_*.fits'))
    slits_files = sorted(cal.glob('Slits_*.fits.gz'))
    if not flats or not slits_files:
        return None
    flat = FlatImages.from_file(str(flats[0]), chk_version=False)
    norm, waveimg = np.asarray(flat.pixelflat_norm, float), np.asarray(flat.pixelflat_waveimg, float)
    left, right, spat_ids = slit_edges(slits_files[0])
    date_iso = f'{date[:4]}-{date[4:6]}-{date[6:]}'
    era, _ = MOSFIRE.era_for_date(date_iso)
    group = MOSFIRE.group_of(band)
    lo, hi = MOSFIRE.band_window(band)
    th = MOSFIRE.throughput_for_window(era, lo - 300, hi + 300, group=group)
    fc = MOSFIRE.filter_curve(band)
    tsys = lambda w: (np.interp(w, th['wave_A'], th['thru'], left=np.nan, right=np.nan)
                      * np.interp(w, fc['wave_A'], fc['transmission'], left=0.0, right=0.0))
    g = MOSFIRE.sky_grid()
    sel_g = (g['wave_A'] >= lo - 300) & (g['wave_A'] <= hi + 300)
    gw = g['wave_A'][sel_g]
    step_g = float(np.median(np.diff(gw)))
    pwv, pwv_src = night_pwv(std, date_iso, band, pwv_default)
    sci = night / 'redux' / 'Science'
    onsky = [f for f in m['frames'] if ('science' in f['frametype']) or ('standard' in f['frametype'])]
    from scipy.ndimage import gaussian_filter1d
    recs = []
    for f in onsky:
        rawf = raw_dir / f['filename']
        if not rawf.exists():
            recs.append({'frame': f['filename'], 'skip': 'raw frame not local'})
            continue
        slits = slits_to_measure(m, f['decker'])
        if not slits:
            recs.append({'frame': f['filename'], 'skip': f'no slit width for decker {f["decker"]}'})
            continue
        hdr = fits.getheader(rawf)
        texp, airmass = float(hdr['TRUITIME']), float(hdr['AIRMASS'])
        if texp < min_texp:
            recs.append({'frame': f['filename'], 'skip': f'exptime {texp:.1f} s < {min_texp:g} s'})
            continue
        mjd_mid = float(hdr['MJD-OBS']) + 0.5 * texp / 86400.0
        sun = float(mo.sun_altitude(mjd_mid, site))
        ra, dec = pointing(hdr)
        m_alt, m_illum, m_sep = moon_state(mjd_mid, ra, dec, site)
        img_e, _ = mo.process_raw(rawf, frame='scienceframe')          # e- over the exposure
        objs = []
        for s1 in sorted(sci.glob(f'spec1d_{Path(f["filename"]).stem}-*.fits')):
            for so in SpecObjs.from_fitsfile(str(s1), chk_version=False):
                objs.append((float(so['SPAT_PIXPOS']), float(so['FWHM'] or 5.0)))
        sb_stack, model_stack, widths, peds, cbars, n_cols = [], [], [], [], [], 0
        ref_ped = ref_pedestal(rawf)
        for spat_id, width in slits:
            mask = mo.central_rows_mask(slits_files[0], norm.shape, spat_ids=None if spat_id is None else [spat_id])
            cols_ok = mask.any(axis=0)
            for cc, fw in objs:
                cols_ok[max(int(cc - 3 * fw), 0):int(cc + 3 * fw) + 1] = False
            cols = np.flatnonzero(cols_ok)
            if cols.size < 3:
                continue
            i_slit = int(np.argmin(np.abs(spat_ids - (spat_id if spat_id is not None else np.median(cols)))))
            cb = pedestal(img_e, left, right, i_slit)          # closed-bar level, diagnostic only (docstring)
            cbars.append(np.nan if cb is None else float(np.nanmedian(cb)) / texp)
            peds.append(ref_ped / texp)
            img = img_e - ref_ped
            img = np.where(norm > 0, img / texp / np.where(norm > 0, norm, 1.0), np.nan)
            sky_e = np.nanmedian(np.where(mask[:, cols], img[:, cols], np.nan), axis=1)
            wave = np.nanmedian(np.where(mask[:, cols], waveimg[:, cols], np.nan), axis=1)
            disp = np.abs(np.gradient(wave))
            ok = np.isfinite(sky_e) & np.isfinite(wave) & (wave > 0) & (disp > 0)
            if ok.sum() < 100:
                continue
            sb = sky_e[ok] / (EFF_APERTURE * tsys(wave[ok]) * width * PLATESCALE * disp[ok]) * 10.0
            n_cols += int(cols.size)
            srt = np.argsort(wave[ok])
            sb_stack.append(np.interp(grid, wave[ok][srt], sb[srt], left=np.nan, right=np.nan))
            sky_g, _ = atmosphere.interp_grid(g['skybg'][:, sel_g], g['airmass'], g['pwv_mm'], airmass, pwv)
            fwhm_pix, _ = MOSFIRE.lsf_fwhm_pix(width, band)
            sig = fwhm_pix * float(np.median(disp[ok])) / 2.3548 / step_g
            model_stack.append(np.interp(grid, gw, gaussian_filter1d(sky_g, sig), left=np.nan, right=np.nan))
            widths.append(width)
        if not sb_stack:
            recs.append({'frame': f['filename'], 'skip': 'no slit columns free of objects'})
            continue
        sb_med = np.nanmedian(sb_stack, axis=0)
        model_med = np.where(np.isfinite(sb_med), np.nanmedian(model_stack, axis=0), np.nan)
        cen, meas_floor = binned_floor(grid, sb_med, lo, hi)
        _, model_floor = binned_floor(grid, model_med, lo, hi)
        recs.append({'frame': f['filename'], 'frametype': f['frametype'], 'target': f['target'], 'decker': f['decker'],
                     'exptime_s': texp, 'airmass': airmass, 'mjd_mid': mjd_mid, 'pwv_mm': pwv, 'pwv_source': pwv_src,
                     'sun_alt_deg': sun, 'twilight': sun > TWILIGHT_SUN_ALT,
                     'moon_alt_deg': m_alt, 'moon_illum': m_illum, 'moon_sep_deg': m_sep,
                     'moonlit': (m_alt > 0) and (m_illum >= MOON_ILLUM_DARK),
                     'slit_width_arcsec': float(np.median(widths)), 'n_slits': len(sb_stack),
                     'pedestal_e_per_s': float(np.nanmedian(peds)) if np.isfinite(peds).any() else np.nan,
                     'closed_bar_e_per_s': float(np.nanmedian(cbars)) if np.isfinite(cbars).any() else np.nan,
                     'n_columns': int(n_cols), 'weight': texp * n_cols, 'sb': sb_med, 'model_sb': model_med,
                     'bin_A': cen, 'measured': meas_floor, 'model': model_floor, 'excess': meas_floor - model_floor})
    return {'night': date, 'era': era.name, 'pwv_mm': pwv, 'pwv_source': pwv_src, 'throughput_file': th['file'],
            'calib_version': th['calib_version'], 'provisional': bool(th['provisional']),
            'image': m.get('image'), 'pypeit_version': m.get('pypeit_version'), 'frames': recs}


def write_index(rel, entry):
    index = yaml.safe_load(INDEX.read_text()) or {}
    index.setdefault('files', {})[rel] = entry
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--band', required=True)
    ap.add_argument('--nights', nargs='+', help='YYYYMMDD nights (default: every locally reduced night of the band)')
    ap.add_argument('--pwv-default', type=float, default=1.6, help='PWV [mm] when the night has no pwv_fit')
    ap.add_argument('--moon-cut', action='store_true', help='the Y rule of D61: dark frames only, if enough exist')
    ap.add_argument('--no-write', action='store_true', help='report only; do not write the curve or index.yaml')
    ap.add_argument('--min-texp', type=float, default=MIN_EXPTIME_S,
                    help=f'skip frames shorter than this [s] (default {MIN_EXPTIME_S}; see measure_night)')
    a = ap.parse_args(argv)
    band = a.band
    site = MOSFIRE.monitor['site']
    std = Table.read(DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    lo, hi = MOSFIRE.band_window(band)
    dlam = MOSFIRE.bands[band].dispersion_A_per_pix
    grid = np.arange(lo - 200, hi + 200, dlam)
    root = paths.data_root() / 'mosfire'
    if a.nights:
        nights = list(a.nights)
    else:
        nights = sorted(p.parents[1].name for p in root.glob('2*/*/run_manifest.json')
                        if p.parent.name == band or (band in ('J', 'J2') and p.parent.name == p.parents[1].name))
        nights = sorted({n for n in nights if (paths.night_dir('mosfire', n, band=band) / 'run_manifest.json').exists()})
    print(f'band {band}: {len(nights)} night(s): {" ".join(nights)}')
    per_night, frame_rows = [], []
    for n in nights:
        r = measure_night(n, band, std, a.pwv_default, grid, site, min_texp=a.min_texp)
        if r is None:
            print(f'{n}: no products (run_manifest.json or Calibrations missing); skipped')
            continue
        used = [f for f in r['frames'] if 'skip' not in f and not f['twilight']]
        skipped = [f for f in r['frames'] if 'skip' in f]
        twi = [f for f in r['frames'] if 'skip' not in f and f['twilight']]
        for f in r['frames']:
            if 'skip' in f:
                continue
            for c, me, mo_, ex in zip(f['bin_A'], f['measured'], f['model'], f['excess']):
                frame_rows.append({'night': n, 'frame': f['frame'], 'target': f['target'], 'exptime_s': f['exptime_s'],
                                   'airmass': f['airmass'], 'pwv_mm': f['pwv_mm'], 'sun_alt_deg': f['sun_alt_deg'],
                                   'twilight': f['twilight'], 'moon_alt_deg': f['moon_alt_deg'],
                                   'moon_illum': f['moon_illum'],
                                   'moon_sep_deg': np.nan if f['moon_sep_deg'] is None else f['moon_sep_deg'],
                                   'moonlit': f['moonlit'], 'slit_width_arcsec': f['slit_width_arcsec'],
                                   'n_slits': f['n_slits'], 'pedestal_e_per_s': f['pedestal_e_per_s'],
                                   'closed_bar_e_per_s': f['closed_bar_e_per_s'],
                                   'wave_A': float(c), 'measured': me, 'model': mo_, 'excess': ex})
        r['used'], r['twilight_excluded'], r['skipped'] = used, twi, skipped
        per_night.append(r)
        if used:
            ex = np.nanmedian([f['excess'] for f in used], axis=0)
            mf = np.nanmedian([f['measured'] for f in used], axis=0)
            gf = np.nanmedian([f['model'] for f in used], axis=0)
            print(f"{n} {r['era']} PWV {r['pwv_mm']:.2f} ({r['pwv_source']}) T_sys {r['calib_version']}: "
                  f"{len(used)} frame(s) of {np.nanmedian([f['exptime_s'] for f in used]):.1f} s "
                  f"({len(twi)} twilight excluded, {len(skipped)} skipped), slit {used[0]['slit_width_arcsec']:.1f}\" "
                  f"x{used[0]['n_slits']}, pedestal {np.nanmedian([f['pedestal_e_per_s'] for f in used]):.1f} e-/s; "
                  f"moon alt {np.median([f['moon_alt_deg'] for f in used]):+.0f} deg illum "
                  f"{np.median([f['moon_illum'] for f in used]):.2f}; floors measured {np.nanmedian(mf):.1f} "
                  f"model {np.nanmedian(gf):.1f} excess {np.nanmedian(ex):.1f}")
        else:
            print(f'{n}: no usable frame ({len(twi)} twilight, {len(skipped)} skipped: '
                  f'{sorted({f["skip"] for f in skipped})})')
    nights_used = [r for r in per_night if r['used']]
    if not nights_used:
        print('no night with a usable frame; nothing written')
        return 1
    cen = nights_used[0]['used'][0]['bin_A']

    def night_curves(select):
        out = []
        for r in nights_used:
            fr = [f for f in r['used'] if select(f)]
            if fr:
                out.append(np.nanmedian([f['excess'] for f in fr], axis=0))
        return np.array(out) if out else np.empty((0, cen.size))

    all_curves = night_curves(lambda f: True)
    dark_curves = night_curves(lambda f: not f['moonlit'])
    n_dark_frames = sum(1 for r in nights_used for f in r['used'] if not f['moonlit'])
    n_dark_nights = int(dark_curves.shape[0])
    moon_included = True
    curves = all_curves
    if a.moon_cut and n_dark_frames >= MOON_MIN_DARK_FRAMES and n_dark_nights >= MOON_MIN_DARK_NIGHTS:
        curves, moon_included = dark_curves, False
    night_med = np.nanmedian(curves, axis=0)
    mad = np.nanmedian(np.abs(curves - night_med), axis=0)
    n_nights = np.isfinite(curves).sum(axis=0)
    # the shipped curve: the floor of the exposure-weighted stack of every selected frame (module docstring)
    frames_sel = [f for r in nights_used for f in r['used'] if moon_included or not f['moonlit']]
    raw, err, meas_all, model_all, column_seconds = stacked_floor(frames_sel, grid, lo, hi)
    moonlit_curves = night_curves(lambda f: f['moonlit'])
    dark_minus_moonlit = (float(np.nanmedian(np.nanmedian(dark_curves, axis=0) - np.nanmedian(moonlit_curves, axis=0)))
                          if dark_curves.shape[0] and moonlit_curves.shape[0] else None)
    print('\nexcess per bin: stacked floor +- split-half error (measured and model floors of the stack); '
          'night median +- MAD over n nights:')
    for c, e, s, mf, gf, nm, d, k in zip(cen, raw, err, meas_all, model_all, night_med, mad, n_nights):
        print(f'  {c:7.0f} A: {e:8.2f} +- {s:5.2f} (measured {mf:8.2f} model {gf:7.2f}) | nights {nm:8.2f} +- {d:6.2f} n={k:2d}')
    print(f'band median excess {np.nanmedian(raw):.2f} ph/s/arcsec^2/nm/m^2 (split-half error {np.nanmedian(err):.2f}; '
          f'measured floor {np.nanmedian(meas_all):.2f}, model floor {np.nanmedian(model_all):.2f}; '
          f'night median {np.nanmedian(night_med):.2f}); stack {column_seconds:.0f} column-seconds; '
          f'{len(nights_used)} night(s), {sum(len(r["used"]) for r in nights_used)} frame(s); '
          f'{sum(len(r["twilight_excluded"]) for r in per_night)} twilight frame(s) excluded; '
          f'dark frames {n_dark_frames} over {n_dark_nights} night(s); moon_included {moon_included}'
          + (f'; dark - moonlit {dark_minus_moonlit:+.2f}' if dark_minus_moonlit is not None else ''))
    if a.no_write:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    calib_version = f'{CALIB_VERSION}-dev'
    keep = (n_nights > 0) & np.isfinite(raw)     # bins without data are left out; compute holds the edge values
    t = Table({'wave_A': cen[keep], 'excess': np.clip(raw[keep], 0.0, None), 'excess_raw': raw[keep],
               'excess_err': err[keep], 'excess_night_median': night_med[keep], 'night_mad': mad[keep],
               'n_nights': n_nights[keep], 'measured_floor': meas_all[keep], 'model_floor': model_all[keep]})
    for c in ('excess', 'excess_raw', 'excess_err', 'excess_night_median', 'night_mad', 'measured_floor', 'model_floor'):
        t[c].format = '.4f'
    t['wave_A'].unit = 'Angstrom'
    t.meta = {
        'description': f'MOSFIRE {band} sky continuum excess over the Gemini model, additive, in Gemini units '
                       f'(photons/s/arcsec^2/nm/m^2): the 10th percentile per 100 A (the between-line floor) of the '
                       f'exposure-weighted stack of every usable frame minus the same floor of the stacked Gemini '
                       f'model (design D61, 5.3.8; the per-frame floors and their night median are kept as '
                       f'excess_night_median for the D61 statistic). excess is clipped at zero; excess_raw keeps '
                       f'the sign; excess_err is half the split-half difference. Added inside the sky_scale bracket '
                       f'by compute.',
        'method': 'stack: sum over frames of exptime x columns x SB / sum of weights, per wavelength; floors = 10th '
                  'percentile per 100 A bin of the stacked measured and model spectra; the per-frame percentile is '
                  'biased low by ~1.3 sigma at short exposures, the stack is not',
        'stack_column_seconds': column_seconds, 'n_frames_stacked': len(frames_sel),
        'instrument': 'keck_mosfire', 'band': band, 'units': 'photons/s/arcsec^2/nm/m^2',
        'window_A': [float(lo), float(hi)], 'bin_A': BIN_A, 'percentile': PERCENTILE,
        'frames': f'all non-twilight on-sky frames (Sun below -18 deg at mid-exposure) of >= {a.min_texp:g} s; objects masked to +-3 FWHM; '
                  'long2pos masks measured in their narrowest bars',
        'min_exptime_s': a.min_texp,
        'pedestal': f'per frame, the raw reference pixels + {REF_OFFSET_ADU:g} ADU times the gain (module docstring); '
                    f'an offset of {REF_PEDESTAL_UNC_ADU:g} ADU instead would lower the floor of a 179 s frame by '
                    f'about 0.2 units',
        'moon_included': moon_included, 'moon_rule': 'none (H and K use all frames)' if not a.moon_cut else
        f'dark frames (Moon below the horizon or illuminated < {MOON_ILLUM_DARK:.0%}) when >= {MOON_MIN_DARK_FRAMES} '
        f'over >= {MOON_MIN_DARK_NIGHTS} nights, else all frames',
        'dark_frames': int(n_dark_frames), 'dark_nights': n_dark_nights,
        'dark_minus_moonlit_median': dark_minus_moonlit,
        'n_nights': len(nights_used), 'n_frames': int(sum(len(r['used']) for r in nights_used)),
        'n_twilight_excluded': int(sum(len(r['twilight_excluded']) for r in per_night)),
        'exptime_s_range': [float(min(f['exptime_s'] for r in nights_used for f in r['used'])),
                            float(max(f['exptime_s'] for r in nights_used for f in r['used']))],
        'nights': [{'night': r['night'], 'era': r['era'], 'n_frames': len(r['used']),
                    'exptime_s_median': float(np.median([f['exptime_s'] for f in r['used']])),
                    'pwv_mm': r['pwv_mm'], 'pwv_source': r['pwv_source'], 'image': r['image'],
                    'throughput': r['calib_version'],
                    'moon_illum_median': float(np.median([f['moon_illum'] for f in r['used']]))}
                   for r in nights_used],
        'throughput_files': sorted({r['throughput_file'] for r in nights_used}),
        'throughput_calib_versions': sorted({r['calib_version'] for r in nights_used}),
        'throughput_provisional': any(r['provisional'] for r in nights_used),
        'images': sorted({str(r['image']) for r in nights_used}),
        'pypeit_versions': sorted({str(r['pypeit_version']) for r in nights_used}),
        'gemini_grid': str(MOSFIRE.sky_grid_file),
        'frames_table': f'$KECK_ETCS_DATA/mosfire/sky_excess/sky_excess_{band}_frames.ecsv',
        'calib_version': calib_version, 'keck_etcs_version': keck_etcs.__version__, 'created': now, 'script': SCRIPT,
    }
    rel = f'sky/mosfire_sky_excess_{band}.ecsv'
    out = DATA_DIR / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    t.write(out, format='ascii.ecsv', overwrite=True)
    fdir = paths.data_root() / 'mosfire' / 'sky_excess'
    fdir.mkdir(parents=True, exist_ok=True)
    ft = Table(rows=frame_rows)
    ft.meta = {'description': f'per-frame sky floors behind {rel}', 'band': band, 'created': now, 'script': SCRIPT,
               'keck_etcs_version': keck_etcs.__version__}
    ft.write(fdir / f'sky_excess_{band}_frames.ecsv', format='ascii.ecsv', overwrite=True)
    write_index(rel, {'calib_version': calib_version, 'bands': [band], 'created': now,
                      'sha256': hashlib.sha256(out.read_bytes()).hexdigest(), 'script': SCRIPT,
                      'pypeit_version': ','.join(t.meta['pypeit_versions']),
                      'provenance': f"{band} sky continuum excess over the Gemini model (D61): median over "
                                    f"{len(nights_used)} night(s), {t.meta['n_frames']} frame(s); T_sys from "
                                    f"{', '.join(t.meta['throughput_files'])}; images {', '.join(t.meta['images'])}"})
    print(f'wrote {out.relative_to(REPO)}, {fdir / f"sky_excess_{band}_frames.ecsv"}; index.yaml updated')
    return 0


if __name__ == '__main__':
    sys.exit(main())
