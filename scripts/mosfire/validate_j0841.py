#!/usr/bin/env python
"""Validate the ETC against the measured S/N of J0841+3814 on 2022-04-09 (plan S11, design 6.1, D14, D16, D18, N5).

Usage:
    conda run -n pypeit14b python scripts/mosfire/validate_j0841.py [--redo] [--no-figure]
    conda run -n pypeit14b python scripts/mosfire/validate_j0841.py --band H --date 20220111 --target J1532+2237 --standard GD153

Without arguments it is the S11 case below; with ``--band/--date/--target/--standard``
(S24b, design 9.7) the same method runs on another band's validation night
(:func:`config`: the science frames of the target from the band's run
manifest, the night's ``sens_<standard>_<date>.fits``, the criterion range =
the band's window, the slit width and read count from the headers; outputs
``validation_<target>_*`` under the band's ``validation/``).

Inputs, all from the in-pod (image 0.1.6) products synced to
``$KECK_ETCS_DATA/mosfire/20220409/`` (``redux/Science/spec1d_m220409_003[6-9]*``,
``sens/sens_LDS749B_20220409.fits``, the raw frames, ``Calibrations``).
Outputs go to ``<night>/validation/`` (never into ``redux/``, which mirrors
the bucket):

(a) the four spec1d files are copied, fluxed with the LDS749B sensfunc
    (``pypeit_flux_calib``) and coadded (``pypeit_coadd_1dspec``);
(b) measured: S/N per pixel per frame as ``OPT_FLAM * sqrt(OPT_FLAM_IVAR)``,
    the 4-frame S/N from the coadd (rescaled to the native pixel if the
    coadd grid differs) and as sqrt(sum of the frames' S/N^2); the spatial
    FWHM as the median ``FWHMFIT`` x 0.1798"/pix; the sky per spatial and
    spectral pixel from the raw frames (flat-fielded, objects masked, the
    central half of the slit), the same quantity as the ETC's b(lam).
    PypeIt's ``OPT_COUNTS_SKY`` is the profile-weighted sky (sky per pixel x
    the effective number of pixels), so it is not used for the sky level;
(c) ``compute`` with ``spectrum.shape = user``: the fluxed coadd, divided by
    the ETC's own LSF-convolved T_atm (the spectrum is not telluric
    corrected; ``compute`` multiplies T_atm back) and by the model slit
    fraction at the measured FWHM (the sensfunc comes from a 5" slit, so
    the fluxed 1" spectrum still carries the slit loss; ``compute`` applies
    it again), smoothed with a 51-pixel running median; ``source.mag`` is
    its own AB magnitude through J2. 1" slit, the measured FWHM, the
    per-frame exposure (TRUITIME), 4 frames, MCDS-16, ABBA, the mean
    airmass, the standard's fitted PWV, ``throughput.date = 2022-04-09``.
    The signal side is therefore a closure; the test is the noise model
    (sky, read noise, dark, aperture), as design 6.1 intends;
(d) a comparison ECSV in 50 A bins, a figure, and a summary JSON, each with
    the provenance of the products used.

Also: the D14 sky-level test (measured / Gemini x T_sys, in OH lines and
between them), the second N5 test (OH-line centroids of the measured sky
against the Gemini grid), the D16 effective aperture (the
``aperture.length_fwhm`` that brings the band-median ratio to 1) and the
criterion of D18: median ETC/measured within 20 percent over 1.117-1.260 um
and within 10 percent between OH lines.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table
from scipy.ndimage import median_filter

import keck_etcs
from keck_etcs import etc, paths
from keck_etcs.calib.harvest import slit_from_decker
from keck_etcs.core import source
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

DATE = '20220409'
FRAMES = ('m220409_0036', 'm220409_0037', 'm220409_0038', 'm220409_0039')
SENS = 'sens_LDS749B_20220409.fits'
BIN_A = 50.0
CRIT_RANGE = (11170.0, 12600.0)
J0841 = {'band': 'J2', 'date': DATE, 'target': 'J0841+3814', 'standard': 'LDS749B', 'frames': FRAMES,
         'sens': SENS, 'crit': CRIT_RANGE, 'slug': 'j0841'}
"""The S11 case (design 6.1): the defaults of :func:`config`; ``crit`` is the J2 half-power band."""


def config(band=None, date=None, target=None, standard=None, frames=None):
    """The validation case: the S11 J0841 night by default, else another (band, night, target, standard) (S24b).

    ``frames`` default to the night's science frames of ``target`` in the band's run manifest; ``sens`` is
    ``sens_<standard>_<date>.fits`` of the band's products; ``crit`` (the criterion range of D18) is the band's
    window (``MOSFIRE.band_window``; J2's half-power band for the S11 case)."""
    if band is None and date is None and target is None:
        return dict(J0841)
    band, date = band or J0841['band'], date or J0841['date']
    target, standard = target or J0841['target'], standard or J0841['standard']
    if frames is None:
        night = paths.night_dir('mosfire', date, band=band)
        m = json.loads((night / 'run_manifest.json').read_text())
        frames = tuple(Path(f['filename']).stem for f in m['frames']
                       if 'science' in f['frametype'] and str(f['target']).replace(' ', '') == target.replace(' ', ''))
        if not frames:
            raise SystemExit(f'no science frame of {target} in {night / "run_manifest.json"}')
    return {'band': band, 'date': date, 'target': target, 'standard': standard, 'frames': tuple(frames),
            'sens': f'sens_{standard}_{date}.fits',
            'crit': tuple(float(x) for x in MOSFIRE.band_window(band)) if band != 'J2' else CRIT_RANGE,
            'slug': target.lower().replace('+', 'p').replace('-', 'm').replace(' ', '')}
LINE_FACTOR, INTER_FACTOR = 3.0, 1.25          # OH-line / interline masks on the model sky
SMOOTH = 51
LENGTHS = np.round(np.arange(0.6, 3.001, 0.02), 2)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'{cmd[0]} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')


def flux_and_coadd(night, out, redo=False, cfg=None):
    """(a): copy, flux and coadd the science frames in ``out/work``."""
    from pypeit.specobjs import SpecObjs
    cfg = cfg or config()
    work = out / 'work'
    work.mkdir(parents=True, exist_ok=True)
    stem = cfg['target'].replace(' ', '').split('+')[0].split('-')[0] if cfg['slug'] != 'j0841' else 'J0841'
    coadd = out / f"{stem}_coadd_{cfg['date']}.fits"
    spec1d = []
    for fr in cfg['frames']:
        src = sorted((night / 'redux' / 'Science').glob(f'spec1d_{fr}-*.fits'))[0]
        dst = work / src.name
        if redo or not dst.exists():
            shutil.copy2(src, dst)
        spec1d.append(dst)
    if redo or not coadd.exists() or SpecObjs.from_fitsfile(str(spec1d[0]), chk_version=False)[0]['OPT_FLAM'] is None:
        sens = night / 'sens' / cfg['sens']
        (work / f'{stem}.flux').write_text('[rdx]\n  spectrograph = keck_mosfire\n\nflux read\n    filename | sensfile\n'
                                           + ''.join(f'    {p.name} | {sens if i == 0 else ""}\n'
                                                     for i, p in enumerate(spec1d)) + 'flux end\n')
        run(['pypeit_flux_calib', f'{stem}.flux'], work)
        names = [SpecObjs.from_fitsfile(str(p), chk_version=False)[0]['NAME'] for p in spec1d]
        (work / f'{stem}.coadd1d').write_text(
            f'[rdx]\n  spectrograph = keck_mosfire\n[coadd1d]\n  coaddfile = {coadd}\n\n'
            'coadd1d read\n    filename | obj_id\n'
            + ''.join(f'    {p.name} | {n}\n' for p, n in zip(spec1d, names)) + 'coadd1d end\n')
        run(['pypeit_coadd_1dspec', f'{stem}.coadd1d'], work)
    return spec1d, coadd


def measured_spectra(spec1d, coadd, grid, dlam, crit=CRIT_RANGE):
    """(b): per-frame and N-frame S/N, counts, FWHM on the ETC pixel grid."""
    from pypeit.onespec import OneSpec
    from pypeit.specobjs import SpecObjs
    frames = []
    for p in spec1d:
        o = SpecObjs.from_fitsfile(str(p), chk_version=False)[0]
        w = np.asarray(o['OPT_WAVE'], float)
        ok = (w > 0) & (np.asarray(o['OPT_FLAM_IVAR']) > 0) & np.asarray(o['OPT_MASK'], bool)
        snr = np.where(ok, o['OPT_FLAM'] * np.sqrt(np.clip(o['OPT_FLAM_IVAR'], 0, None)), np.nan)
        on = lambda a: np.interp(grid, w[ok], np.asarray(a, float)[ok], left=np.nan, right=np.nan)
        band = (w > crit[0]) & (w < crit[1]) & ok
        fwhm = np.asarray(o['FWHMFIT'], float)
        frames.append({'file': p.name, 'name': o['NAME'], 'snr': on(snr), 'counts': on(o['OPT_COUNTS']),
                       'fwhm_pix': float(np.median(fwhm[band & np.isfinite(fwhm) & (fwhm > 0)])),
                       'spat_pixpos': float(o['SPAT_PIXPOS'])})
    c = OneSpec.from_file(str(coadd))
    cw, cf, ci = np.asarray(c.wave, float), np.asarray(c.flux, float), np.asarray(c.ivar, float)
    cm = (cw > 0) & (ci > 0) & np.asarray(c.mask, bool)
    dw = float(np.median(np.diff(cw[cm])))
    coadd_snr = np.interp(grid, cw[cm], (cf * np.sqrt(ci))[cm], left=np.nan, right=np.nan) * np.sqrt(dlam / dw)
    coadd_flam = np.interp(grid, cw[cm], cf[cm], left=np.nan, right=np.nan) * 1e-17      # PypeIt units 1e-17 cgs
    frames_snr = np.sqrt(np.nansum([f['snr'] ** 2 for f in frames], axis=0))
    return frames, {'snr': coadd_snr, 'flam': coadd_flam, 'dwave': dw, 'sha256': sha(coadd)}, frames_snr


def measured_sky(night, frames, grid, raw_dir=None):
    """(b): sky e-/s per (spatial pix, spectral pix) from the raw frames, median of the frames."""
    from astropy.io import fits
    from pypeit.flatfield import FlatImages
    from keck_etcs.calib import monitor as mo
    raw_dir = raw_dir or (night / 'raw')
    cal = night / 'redux' / 'Calibrations'
    flat = FlatImages.from_file(str(sorted(cal.glob('Flat_*.fits'))[0]), chk_version=False)
    norm, waveimg = np.asarray(flat.pixelflat_norm, float), np.asarray(flat.pixelflat_waveimg, float)
    central = mo.central_rows_mask(sorted(cal.glob('Slits_*.fits.gz'))[0], norm.shape).any(axis=0)
    out = []
    for f in frames:
        raw = raw_dir / (f['file'].split('-')[0].replace('spec1d_', '') + '.fits')
        texp = float(fits.getheader(raw)['TRUITIME'])
        img, _ = mo.process_raw(raw, frame='scienceframe')
        img = np.where(norm > 0, img / texp / np.where(norm > 0, norm, 1.0), np.nan)
        cols = central.copy()
        fw = 5.0 if not np.isfinite(f['fwhm_pix']) else f['fwhm_pix']
        cols[max(int(f['spat_pixpos'] - 3 * fw), 0):int(f['spat_pixpos'] + 3 * fw) + 1] = False
        stack = []
        for j in np.flatnonzero(cols):
            wj, ij = waveimg[:, j], img[:, j]
            ok = (wj > 0) & np.isfinite(ij)
            if ok.sum() > 100:
                srt = np.argsort(wj[ok])
                stack.append(np.interp(grid, wj[ok][srt], ij[ok][srt], left=np.nan, right=np.nan))
        out.append(np.nanmedian(stack, axis=0))
    return np.nanmedian(out, axis=0), int(np.sum(central))


def centroids(wave, spec, peaks, half):
    """Flux-weighted centroids within +-half A of each peak (continuum = window minimum)."""
    res = []
    for p in peaks:
        s = np.abs(wave - p) <= half
        y = spec[s] - np.nanmin(spec[s])
        res.append(float(np.nansum(wave[s] * y) / np.nansum(y)) if np.nansum(y) > 0 else np.nan)
    return np.array(res)


def bin_table(grid, cols, inter, line, crit=CRIT_RANGE):
    edges = np.arange(crit[0], crit[1] + BIN_A, BIN_A)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        s = (grid >= lo) & (grid < hi) & np.isfinite(cols['snr_meas']) & np.isfinite(cols['snr_etc'])
        if s.sum() < 10:
            continue
        si = s & inter
        med = lambda a, m: float(np.nanmedian(a[m])) if m.sum() else np.nan
        rows.append({'wave_lo': lo, 'wave_hi': hi, 'n_pix': int(s.sum()), 'n_interline': int(si.sum()),
                     'snr_meas': med(cols['snr_meas'], s), 'snr_meas_frames': med(cols['snr_frames'], s),
                     'snr_etc': med(cols['snr_etc'], s),
                     'ratio': med(cols['snr_etc'], s) / med(cols['snr_meas'], s),
                     'ratio_interline': med(cols['snr_etc'], si) / med(cols['snr_meas'], si) if si.sum() else np.nan,
                     'sky_meas': med(cols['b_meas'], s), 'sky_etc': med(cols['b_etc'], s),
                     'sky_ratio_interline': med(cols['b_meas'], si) / med(cols['b_etc'], si) if si.sum() else np.nan,
                     'sky_ratio_lines': (float(np.nansum(cols['b_meas'][s & line]) / np.nansum(cols['b_etc'][s & line]))
                                         if (s & line).sum() else np.nan),
                     'counts_meas': med(cols['counts_meas'], s), 'counts_etc': med(cols['counts_etc'], s)})
    return Table(rows=rows)


def etc_inputs(seeing, texp, airmass, pwv, cfg=None, slit=1.0, n_reads=16, **extra):
    cfg = cfg or config()
    d = cfg['date']
    d = {'band': cfg['band'], 'slit_width_arcsec': slit, 'source': {'type': 'point', 'mag': 20.0, 'mag_system': 'AB'},
         'seeing_fwhm_arcsec': round(seeing, 4), 'exptime_s': round(texp, 4), 'n_frames': len(cfg['frames']),
         'readout': {'mode': 'MCDS', 'n_reads': n_reads}, 'nod': 'ABBA', 'airmass': round(airmass, 4),
         'pwv_mm': round(pwv, 4), 'throughput': {'date': f'{d[:4]}-{d[4:6]}-{d[6:]}'}}
    for k, v in extra.items():
        if isinstance(v, dict):
            d[k] = {**d.get(k, {}), **v}
        else:
            d[k] = v
    return d


def main(redo=False, figure=True, cfg=None):
    from astropy.io import fits
    cfg = cfg or config()
    band, date, crit_range = cfg['band'], cfg['date'], cfg['crit']
    date_iso = f'{date[:4]}-{date[4:6]}-{date[6:]}'
    night = paths.night_dir('mosfire', date, band=band)
    raw_dir = paths.night_dir('mosfire', date, 'raw', band=band)
    out = night / 'validation'
    out.mkdir(exist_ok=True)
    manifest = json.loads((night / 'run_manifest.json').read_text())
    prov = {k: manifest.get(k) for k in ('image', 'image_digest', 'pypeit_git_sha', 'pypeit_pin', 'keck_etcs_git_sha',
                                         'job_name', 's3_prefix')}
    prov['sens_file'] = cfg['sens']
    prov['sens_sha256'] = sha(night / 'sens' / cfg['sens'])
    spec1d, coadd = flux_and_coadd(night, out, redo, cfg)
    prov['spec1d'] = [p.name for p in spec1d]
    std = Table.read(DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    srow = std[(std['date'] == date_iso) & (std['filter'] == band)] if band != 'J2' else std[std['date'] == date_iso]
    pwv = float(srow['pwv_fit'][0])
    hdrs = [fits.getheader(raw_dir / f'{fr}.fits') for fr in cfg['frames']]
    texp = float(np.mean([h['TRUITIME'] for h in hdrs]))
    airmass = float(np.mean([h['AIRMASS'] for h in hdrs]))
    slit = slit_from_decker(hdrs[0].get('MASKNAME', ''))[0] or 1.0
    n_reads = int(hdrs[0].get('NUMREADS', 16))
    kw = dict(cfg=cfg, slit=slit, n_reads=n_reads)

    # preliminary run for the pixel grid, T_atm and the slit fraction
    probe = etc.compute(etc_inputs(0.9, texp, airmass, pwv, **kw))
    grid, dlam = np.array(probe['wave_A']), probe['dispersion_A_per_pix']
    frames, cd, frames_snr = measured_spectra(spec1d, coadd, grid, dlam, crit_range)
    fwhm_pix = float(np.median([f['fwhm_pix'] for f in frames]))
    seeing = fwhm_pix * MOSFIRE.platescale
    base = etc_inputs(seeing, texp, airmass, pwv, **kw)
    probe = etc.compute(base)
    t_atm = np.array(probe['atm_transmission'])
    f_slit = probe['slit_fraction']

    # (c) the ETC input: fluxed coadd / T_atm / slit fraction, smoothed
    good = np.isfinite(cd['flam']) & (t_atm > 0.3)
    intrinsic = np.interp(grid, grid[good], (cd['flam'] / t_atm)[good]) / f_slit
    intrinsic = median_filter(intrinsic, size=SMOOTH, mode='nearest')
    filt = MOSFIRE.filter_curve(band)
    mag = float(source.ab_mag(grid, intrinsic, filt['wave_A'], filt['transmission']))
    user = {'spectrum': {'shape': 'user', 'wave_A': grid.tolist(), 'flux': (intrinsic / 1e-17).tolist()},
            'source': {'mag': round(mag, 5)}}
    o = etc.compute({**base, **user, 'source': {**base['source'], 'mag': round(mag, 5)}})
    nf, t = o['summary']['n_frames'], o['summary']['exptime_s']
    b_etc = np.array(o['sky_e']) / (nf * t * o['n_spatial_pix'])
    b_meas, n_cols = measured_sky(night, frames, grid, raw_dir)
    counts_etc = np.array(o['signal_e']) / nf / o['aperture_fraction']       # e- per frame in the slit
    counts_meas = np.nanmedian([f['counts'] for f in frames], axis=0)
    med_b = np.nanmedian(b_etc)
    line, inter = b_etc >= LINE_FACTOR * med_b, b_etc <= INTER_FACTOR * med_b
    cols = {'snr_meas': cd['snr'], 'snr_frames': frames_snr, 'snr_etc': np.array(o['snr_pixel']),
            'b_meas': b_meas, 'b_etc': b_etc, 'counts_meas': counts_meas, 'counts_etc': counts_etc}
    crit = (grid >= crit_range[0]) & (grid <= crit_range[1]) & np.isfinite(cd['snr'])
    bins = bin_table(grid, cols, inter, line, crit_range)

    def ratios(snr_etc):
        return (float(np.nanmedian(snr_etc[crit] / cd['snr'][crit])),
                float(np.nanmedian(snr_etc[crit & inter] / cd['snr'][crit & inter])))

    r_all, r_inter = ratios(cols['snr_etc'])
    r_frames = float(np.nanmedian(cols['snr_etc'][crit] / frames_snr[crit]))
    per_frame = []
    o1 = etc.compute({**base, **user, 'n_frames': 1, 'source': {**base['source'], 'mag': round(mag, 5)}})
    for f in frames:
        per_frame.append(float(np.nanmedian(np.array(o1['snr_pixel'])[crit] / f['snr'][crit])))

    # D14: sky level; N5: OH centroids
    sky_lines = float(np.nansum(b_meas[crit & line]) / np.nansum(b_etc[crit & line]))
    sky_inter = float(np.nanmedian(b_meas[crit & inter]) / np.nanmedian(b_etc[crit & inter]))
    fwhm_A = o['lsf_fwhm_A']
    pk = [i for i in range(1, grid.size - 1) if line[i] and b_etc[i] >= b_etc[i - 1] and b_etc[i] >= b_etc[i + 1]
          and crit[i]]
    pk = [grid[i] for i in pk if np.sum(np.abs(grid[pk] - grid[i]) < 3 * fwhm_A) == 1]
    dc = centroids(grid, b_meas, pk, fwhm_A) - centroids(grid, b_etc, pk, fwhm_A)
    n5 = {'n_lines': int(np.isfinite(dc).sum()), 'median_offset_A': float(np.nanmedian(dc)),
          'mad_A': float(np.nanmedian(np.abs(dc - np.nanmedian(dc))))}

    # D16: effective aperture; and the effect of a measured sky scale
    scan = []
    for L in LENGTHS:
        oo = etc.compute({**base, **user, 'source': {**base['source'], 'mag': round(mag, 5)},
                          'aperture': {'length_fwhm': float(L)}})
        scan.append(ratios(np.array(oo['snr_pixel'])))
    scan = np.array(scan)
    i_best = int(np.argmin(np.abs(scan[:, 0] - 1)))
    o_sky = etc.compute({**base, **user, 'source': {**base['source'], 'mag': round(mag, 5)},
                         'sky_scale': round(min(max(sky_inter, 0.3), 3.0), 4)})
    r_sky = ratios(np.array(o_sky['snr_pixel']))

    summary = {
        'provenance': prov, 'keck_etcs_version': keck_etcs.__version__, 'calib_version': o['meta']['calib_version'],
        'era': o['meta']['era'], 'coadd_sha256': cd['sha256'], 'coadd_dwave_A': cd['dwave'],
        'inputs': {k: v for k, v in o['meta']['inputs'].items() if k != 'spectrum'},
        'measured': {'fwhm_pix': fwhm_pix, 'seeing_arcsec': seeing, 'fwhm_pix_per_frame': [f['fwhm_pix'] for f in frames],
                     'snr_coadd_median': float(np.nanmedian(cd['snr'][crit])),
                     'snr_frames_median': float(np.nanmedian(frames_snr[crit])), 'mag_ab_intrinsic': mag,
                     'mag_ab_intrinsic_J2': mag if band == 'J2' else None, 'band': band,
                     'slit_width_arcsec': slit, 'n_reads': n_reads, 'crit_range_A': list(crit_range),
                     'slit_fraction_model': f_slit, 'sky_columns': n_cols},
        'etc': {'snr_pixel_median': float(np.nanmedian(np.array(o['snr_pixel'])[crit])),
                'aperture_fraction': o['aperture_fraction'], 'n_spatial_pix': o['n_spatial_pix'],
                'warnings': o['warnings']},
        'ratio_etc_over_measured': {'band': r_all, 'interline': r_inter, 'vs_frames_quadrature': r_frames,
                                    'per_frame': per_frame},
        'criterion': {'band_within_20pct': abs(r_all - 1) <= 0.20, 'interline_within_10pct': abs(r_inter - 1) <= 0.10},
        'signal_ratio_etc_over_measured': float(np.nanmedian(counts_etc[crit] / counts_meas[crit])),
        'sky': {'ratio_lines_meas_over_gemini': sky_lines, 'ratio_interline_meas_over_gemini': sky_inter,
                'line_mask': f'model sky >= {LINE_FACTOR} x median', 'interline_mask': f'model sky <= {INTER_FACTOR} x median',
                'with_sky_scale_interline': {'sky_scale': round(sky_inter, 4), 'band': r_sky[0], 'interline': r_sky[1]}},
        'n5_oh_centroid_offset_meas_minus_gemini': n5,
        'effective_aperture': {'length_fwhm': float(LENGTHS[i_best]), 'band': float(scan[i_best, 0]),
                               'interline': float(scan[i_best, 1]),
                               'scan': {'length_fwhm': LENGTHS.tolist(), 'band': scan[:, 0].tolist(),
                                        'interline': scan[:, 1].tolist()}},
    }
    summary['case'] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in cfg.items()}
    slug = cfg['slug']
    bins.meta = {'description': f"{cfg['target']} {date_iso} ({band}): ETC against measured S/N in 50 A bins (design 6.1)",
                 'script': 'scripts/mosfire/validate_j0841.py', **{k: v for k, v in summary.items()
                                                                   if k not in ('effective_aperture',)}}
    bins.write(out / f'validation_{slug}_bins.ecsv', format='ascii.ecsv', overwrite=True)
    (out / f'validation_{slug}_summary.json').write_text(json.dumps(summary, indent=1, default=float) + '\n')
    if figure:
        make_figure(out / f'validation_{slug}.png', grid, cols, bins, summary, inter, cfg)
    report(summary)
    return summary


def make_figure(path, grid, cols, bins, s, inter, cfg=None):
    cfg = cfg or config()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(10, 11), sharex=True)
    ax[0].plot(grid, cols['snr_meas'], lw=0.5, color='k', label='measured (coadd)')
    ax[0].plot(grid, cols['snr_etc'], lw=0.5, color='C1', label='ETC')
    c = 0.5 * (bins['wave_lo'] + bins['wave_hi'])
    ax[0].plot(c, bins['snr_meas'], 'ko', ms=4)
    ax[0].plot(c, bins['snr_etc'], 'o', color='C1', ms=4)
    ax[0].set_ylabel(f"S/N per pixel ({len(cfg['frames'])} frames)")
    ax[0].legend()
    ax[1].plot(c, bins['ratio'], 'o-', label='all pixels')
    ax[1].plot(c, bins['ratio_interline'], 's--', label='between OH lines')
    for y in (0.8, 0.9, 1.0, 1.1, 1.2):
        ax[1].axhline(y, color='0.7', lw=0.5)
    ax[1].set_ylabel('ETC / measured S/N')
    ax[1].legend()
    scale = 1.0 / (s['measured'].get('slit_width_arcsec', 1.0) * MOSFIRE.platescale
                   * MOSFIRE.bands[cfg['band']].dispersion_A_per_pix)
    ax[2].semilogy(grid, np.clip(cols['b_meas'], 1e-3, None) * scale, lw=0.5, color='k', label='measured (raw frames)')
    ax[2].semilogy(grid, np.clip(cols['b_etc'], 1e-3, None) * scale, lw=0.5, color='C0', label='Gemini x T_sys (ETC)')
    ax[2].set_ylabel('sky e-/s/arcsec$^2$/A')
    ax[2].set_xlabel('vacuum wavelength (A)')
    ax[2].legend()
    p = s['provenance']
    d = cfg['date']
    fig.suptitle(f"{cfg['target']} {d[:4]}-{d[4:6]}-{d[6:]} ({cfg['band']}), {s['inputs']['slit_width_arcsec']}\" slit, "
                 f"{s['inputs']['n_frames']}x{s['inputs']['exptime_s']:.1f} s ABBA MCDS-{s['inputs']['readout']['n_reads']} | ETC/meas "
                 f"{s['ratio_etc_over_measured']['band']:.3f} (interline {s['ratio_etc_over_measured']['interline']:.3f})\n"
                 f"products {p['image']} {p['image_digest'][:19]} PypeIt {p['pypeit_git_sha'][:7]} | keck_etcs "
                 f"{s['keck_etcs_version']} {s['calib_version']} era {s['era']}", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def report(s):
    m, r, k = s['measured'], s['ratio_etc_over_measured'], s['sky']
    print(f"products: {s['provenance']['image']} ({s['provenance']['image_digest'][:19]}), PypeIt "
          f"{s['provenance']['pypeit_git_sha'][:7]}; ETC {s['calib_version']} era {s['era']}")
    print(f"measured FWHM {m['fwhm_pix']:.3f} px = {m['seeing_arcsec']:.3f}\" (frames "
          f"{', '.join(f'{x:.2f}' for x in m['fwhm_pix_per_frame'])}); model slit fraction {m['slit_fraction_model']:.4f}; "
          f"intrinsic {m.get('band', 'J2')} {m['mag_ab_intrinsic']:.3f} AB")
    cr = m.get('crit_range_A', CRIT_RANGE)
    print(f"S/N per pixel over {cr[0] / 1e4:.3f}-{cr[1] / 1e4:.3f} um: measured coadd {m['snr_coadd_median']:.2f} (frames in quadrature "
          f"{m['snr_frames_median']:.2f}); ETC {s['etc']['snr_pixel_median']:.2f}")
    print(f"ETC/measured: band {r['band']:.3f} ({'PASS' if s['criterion']['band_within_20pct'] else 'FAIL'} 20%), "
          f"interline {r['interline']:.3f} ({'PASS' if s['criterion']['interline_within_10pct'] else 'FAIL'} 10%); "
          f"vs frames-in-quadrature {r['vs_frames_quadrature']:.3f}; per frame "
          f"{', '.join(f'{x:.3f}' for x in r['per_frame'])}")
    print(f"signal (counts in slit) ETC/measured {s['signal_ratio_etc_over_measured']:.3f}")
    print(f"D14 sky measured/Gemini: OH lines {k['ratio_lines_meas_over_gemini']:.3f}, between lines "
          f"{k['ratio_interline_meas_over_gemini']:.3f}; with sky_scale {k['with_sky_scale_interline']['sky_scale']}: "
          f"band {k['with_sky_scale_interline']['band']:.3f}, interline {k['with_sky_scale_interline']['interline']:.3f}")
    n5 = s['n5_oh_centroid_offset_meas_minus_gemini']
    print(f"N5 OH centroids measured - Gemini: {n5['median_offset_A']:+.3f} A (MAD {n5['mad_A']:.3f}, {n5['n_lines']} lines)")
    e = s['effective_aperture']
    print(f"D16 effective aperture: length_fwhm {e['length_fwhm']:.2f} gives band {e['band']:.3f}, interline "
          f"{e['interline']:.3f} (default 1.5: {r['band']:.3f})")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--redo', action='store_true', help='re-copy, re-flux and re-coadd')
    p.add_argument('--no-figure', action='store_true')
    p.add_argument('--band', help='band of the night (S24b; default the S11 case, J2)')
    p.add_argument('--date', help='night YYYYMMDD (default 20220409)')
    p.add_argument('--target', help='science target as named in the run manifest (default J0841+3814)')
    p.add_argument('--standard', help='the night\'s standard, for the sensfunc name (default LDS749B)')
    p.add_argument('--frames', nargs='+', help='raw frame stems (default: the science frames of the target)')
    a = p.parse_args()
    s = main(a.redo, not a.no_figure, config(a.band, a.date, a.target, a.standard, a.frames))
    sys.exit(0 if all(s['criterion'].values()) else 1)
