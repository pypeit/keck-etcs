#!/usr/bin/env python
"""Validate the ETC against the measured S/N of J0841+3814 on 2022-04-09 (plan S11, design 6.1, D14, D16, D18, N5).

Usage:
    conda run -n pypeit14b python scripts/mosfire/validate_j0841.py [--redo] [--no-figure]

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
from keck_etcs.core import source
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

DATE = '20220409'
FRAMES = ('m220409_0036', 'm220409_0037', 'm220409_0038', 'm220409_0039')
SENS = 'sens_LDS749B_20220409.fits'
BIN_A = 50.0
CRIT_RANGE = (11170.0, 12600.0)
LINE_FACTOR, INTER_FACTOR = 3.0, 1.25          # OH-line / interline masks on the model sky
SMOOTH = 51
LENGTHS = np.round(np.arange(0.6, 3.001, 0.02), 2)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'{cmd[0]} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')


def flux_and_coadd(night, out, redo=False):
    """(a): copy, flux and coadd the four frames in ``out/work``."""
    from pypeit.specobjs import SpecObjs
    work = out / 'work'
    work.mkdir(parents=True, exist_ok=True)
    coadd = out / 'J0841_coadd_20220409.fits'
    spec1d = []
    for fr in FRAMES:
        src = sorted((night / 'redux' / 'Science').glob(f'spec1d_{fr}-*.fits'))[0]
        dst = work / src.name
        if redo or not dst.exists():
            shutil.copy2(src, dst)
        spec1d.append(dst)
    if redo or not coadd.exists() or SpecObjs.from_fitsfile(str(spec1d[0]), chk_version=False)[0]['OPT_FLAM'] is None:
        sens = night / 'sens' / SENS
        (work / 'J0841.flux').write_text('[rdx]\n  spectrograph = keck_mosfire\n\nflux read\n    filename | sensfile\n'
                                         + ''.join(f'    {p.name} | {sens if i == 0 else ""}\n'
                                                   for i, p in enumerate(spec1d)) + 'flux end\n')
        run(['pypeit_flux_calib', 'J0841.flux'], work)
        names = [SpecObjs.from_fitsfile(str(p), chk_version=False)[0]['NAME'] for p in spec1d]
        (work / 'J0841.coadd1d').write_text(
            f'[rdx]\n  spectrograph = keck_mosfire\n[coadd1d]\n  coaddfile = {coadd}\n\n'
            'coadd1d read\n    filename | obj_id\n'
            + ''.join(f'    {p.name} | {n}\n' for p, n in zip(spec1d, names)) + 'coadd1d end\n')
        run(['pypeit_coadd_1dspec', 'J0841.coadd1d'], work)
    return spec1d, coadd


def measured_spectra(spec1d, coadd, grid, dlam):
    """(b): per-frame and 4-frame S/N, counts, FWHM on the ETC pixel grid."""
    from pypeit.onespec import OneSpec
    from pypeit.specobjs import SpecObjs
    frames = []
    for p in spec1d:
        o = SpecObjs.from_fitsfile(str(p), chk_version=False)[0]
        w = np.asarray(o['OPT_WAVE'], float)
        ok = (w > 0) & (np.asarray(o['OPT_FLAM_IVAR']) > 0) & np.asarray(o['OPT_MASK'], bool)
        snr = np.where(ok, o['OPT_FLAM'] * np.sqrt(np.clip(o['OPT_FLAM_IVAR'], 0, None)), np.nan)
        on = lambda a: np.interp(grid, w[ok], np.asarray(a, float)[ok], left=np.nan, right=np.nan)
        band = (w > CRIT_RANGE[0]) & (w < CRIT_RANGE[1]) & ok
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


def measured_sky(night, frames, grid):
    """(b): sky e-/s per (spatial pix, spectral pix) from the raw frames, median of the frames."""
    from astropy.io import fits
    from pypeit.flatfield import FlatImages
    from keck_etcs.calib import monitor as mo
    cal = night / 'redux' / 'Calibrations'
    flat = FlatImages.from_file(str(sorted(cal.glob('Flat_*.fits'))[0]), chk_version=False)
    norm, waveimg = np.asarray(flat.pixelflat_norm, float), np.asarray(flat.pixelflat_waveimg, float)
    central = mo.central_rows_mask(sorted(cal.glob('Slits_*.fits.gz'))[0], norm.shape).any(axis=0)
    out = []
    for f in frames:
        raw = night / 'raw' / (f['file'].split('-')[0].replace('spec1d_', '') + '.fits')
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


def bin_table(grid, cols, inter, line):
    edges = np.arange(CRIT_RANGE[0], CRIT_RANGE[1] + BIN_A, BIN_A)
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


def etc_inputs(seeing, texp, airmass, pwv, **extra):
    d = {'band': 'J2', 'slit_width_arcsec': 1.0, 'source': {'type': 'point', 'mag': 20.0, 'mag_system': 'AB'},
         'seeing_fwhm_arcsec': round(seeing, 4), 'exptime_s': round(texp, 4), 'n_frames': 4,
         'readout': {'mode': 'MCDS', 'n_reads': 16}, 'nod': 'ABBA', 'airmass': round(airmass, 4),
         'pwv_mm': round(pwv, 4), 'throughput': {'date': '2022-04-09'}}
    for k, v in extra.items():
        if isinstance(v, dict):
            d[k] = {**d.get(k, {}), **v}
        else:
            d[k] = v
    return d


def main(redo=False, figure=True):
    from astropy.io import fits
    night = paths.night_dir('mosfire', DATE)
    out = night / 'validation'
    out.mkdir(exist_ok=True)
    manifest = json.loads((night / 'run_manifest.json').read_text())
    prov = {k: manifest.get(k) for k in ('image', 'image_digest', 'pypeit_git_sha', 'pypeit_pin', 'keck_etcs_git_sha',
                                         'job_name', 's3_prefix')}
    prov['sens_file'] = SENS
    prov['sens_sha256'] = sha(night / 'sens' / SENS)
    spec1d, coadd = flux_and_coadd(night, out, redo)
    prov['spec1d'] = [p.name for p in spec1d]
    std = Table.read(DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    pwv = float(std[std['date'] == '2022-04-09']['pwv_fit'][0])
    hdrs = [fits.getheader(night / 'raw' / f'{fr}.fits') for fr in FRAMES]
    texp = float(np.mean([h['TRUITIME'] for h in hdrs]))
    airmass = float(np.mean([h['AIRMASS'] for h in hdrs]))

    # preliminary run for the pixel grid, T_atm and the slit fraction
    probe = etc.compute(etc_inputs(0.9, texp, airmass, pwv))
    grid, dlam = np.array(probe['wave_A']), probe['dispersion_A_per_pix']
    frames, cd, frames_snr = measured_spectra(spec1d, coadd, grid, dlam)
    fwhm_pix = float(np.median([f['fwhm_pix'] for f in frames]))
    seeing = fwhm_pix * MOSFIRE.platescale
    base = etc_inputs(seeing, texp, airmass, pwv)
    probe = etc.compute(base)
    t_atm = np.array(probe['atm_transmission'])
    f_slit = probe['slit_fraction']

    # (c) the ETC input: fluxed coadd / T_atm / slit fraction, smoothed
    good = np.isfinite(cd['flam']) & (t_atm > 0.3)
    intrinsic = np.interp(grid, grid[good], (cd['flam'] / t_atm)[good]) / f_slit
    intrinsic = median_filter(intrinsic, size=SMOOTH, mode='nearest')
    filt = MOSFIRE.filter_curve('J2')
    mag = float(source.ab_mag(grid, intrinsic, filt['wave_A'], filt['transmission']))
    user = {'spectrum': {'shape': 'user', 'wave_A': grid.tolist(), 'flux': (intrinsic / 1e-17).tolist()},
            'source': {'mag': round(mag, 5)}}
    o = etc.compute({**base, **user, 'source': {**base['source'], 'mag': round(mag, 5)}})
    nf, t = o['summary']['n_frames'], o['summary']['exptime_s']
    b_etc = np.array(o['sky_e']) / (nf * t * o['n_spatial_pix'])
    b_meas, n_cols = measured_sky(night, frames, grid)
    counts_etc = np.array(o['signal_e']) / nf / o['aperture_fraction']       # e- per frame in the slit
    counts_meas = np.nanmedian([f['counts'] for f in frames], axis=0)
    med_b = np.nanmedian(b_etc)
    line, inter = b_etc >= LINE_FACTOR * med_b, b_etc <= INTER_FACTOR * med_b
    cols = {'snr_meas': cd['snr'], 'snr_frames': frames_snr, 'snr_etc': np.array(o['snr_pixel']),
            'b_meas': b_meas, 'b_etc': b_etc, 'counts_meas': counts_meas, 'counts_etc': counts_etc}
    crit = (grid >= CRIT_RANGE[0]) & (grid <= CRIT_RANGE[1]) & np.isfinite(cd['snr'])
    bins = bin_table(grid, cols, inter, line)

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
                     'snr_frames_median': float(np.nanmedian(frames_snr[crit])), 'mag_ab_intrinsic_J2': mag,
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
    bins.meta = {'description': 'J0841+3814 2022-04-09: ETC against measured S/N in 50 A bins (design 6.1)',
                 'script': 'scripts/mosfire/validate_j0841.py', **{k: v for k, v in summary.items()
                                                                   if k not in ('effective_aperture',)}}
    bins.write(out / 'validation_j0841_bins.ecsv', format='ascii.ecsv', overwrite=True)
    (out / 'validation_j0841_summary.json').write_text(json.dumps(summary, indent=1, default=float) + '\n')
    if figure:
        make_figure(out / 'validation_j0841.png', grid, cols, bins, summary, inter)
    report(summary)
    return summary


def make_figure(path, grid, cols, bins, s, inter):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(10, 11), sharex=True)
    ax[0].plot(grid, cols['snr_meas'], lw=0.5, color='k', label='measured (coadd)')
    ax[0].plot(grid, cols['snr_etc'], lw=0.5, color='C1', label='ETC')
    c = 0.5 * (bins['wave_lo'] + bins['wave_hi'])
    ax[0].plot(c, bins['snr_meas'], 'ko', ms=4)
    ax[0].plot(c, bins['snr_etc'], 'o', color='C1', ms=4)
    ax[0].set_ylabel('S/N per pixel (4 frames)')
    ax[0].legend()
    ax[1].plot(c, bins['ratio'], 'o-', label='all pixels')
    ax[1].plot(c, bins['ratio_interline'], 's--', label='between OH lines')
    for y in (0.8, 0.9, 1.0, 1.1, 1.2):
        ax[1].axhline(y, color='0.7', lw=0.5)
    ax[1].set_ylabel('ETC / measured S/N')
    ax[1].legend()
    scale = 1.0 / (1.0 * MOSFIRE.platescale * MOSFIRE.bands['J2'].dispersion_A_per_pix)
    ax[2].semilogy(grid, np.clip(cols['b_meas'], 1e-3, None) * scale, lw=0.5, color='k', label='measured (raw frames)')
    ax[2].semilogy(grid, np.clip(cols['b_etc'], 1e-3, None) * scale, lw=0.5, color='C0', label='Gemini x T_sys (ETC)')
    ax[2].set_ylabel('sky e-/s/arcsec$^2$/A')
    ax[2].set_xlabel('vacuum wavelength (A)')
    ax[2].legend()
    p = s['provenance']
    fig.suptitle(f"J0841+3814 2022-04-09, 1\" slit, 4x{s['inputs']['exptime_s']:.1f} s ABBA MCDS-16 | ETC/meas "
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
          f"intrinsic J2 {m['mag_ab_intrinsic_J2']:.3f} AB")
    print(f"S/N per pixel over 1.117-1.260 um: measured coadd {m['snr_coadd_median']:.2f} (frames in quadrature "
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
    a = p.parse_args()
    s = main(a.redo, not a.no_figure)
    sys.exit(0 if all(s['criterion'].values()) else 1)
