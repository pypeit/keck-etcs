#!/usr/bin/env python
"""Measure the MOSFIRE line-spread function from the OH lines of a WaveCalib file (plan step S13).

Usage:
    conda run -n pypeit14b python scripts/mosfire/measure_lsf.py DATE [--wavecalib FILE]
        [--slit 1.0] [--record] [--plot]

Reads the night's ``WaveCalib`` (default
``$KECK_ETCS_DATA/mosfire/DATE/redux/Calibrations/WaveCalib_*.fits``, the
synced in-pod copy after ``s3_sync.py pull``). Its arc spectrum is the OH sky
of the science frames, which fill the slit, so this is the LSF of a
uniformly illuminated slit of width ``--slit`` (the slit of the frames that
made the arc). For every line PypeIt identified (``pixel_fit``,
``wave_fit``):

- fits a Gaussian plus a linear baseline to the arc spectrum within ±8 px;
- flags blends: a companion in PypeIt's resolved, vacuum
  ``OH_R24000_lines.dat`` within 1.5 x the expected FWHM, with at least 10
  percent of the line's amplitude. Unresolved Lambda-doublets and blends
  would bias the width high;
- converts the FWHM to A with the local dispersion of the wavelength
  solution, and computes R = lambda / FWHM_A.

From the clean lines, it fits FWHM_pix against wavelength (a line, with 3
sigma clipping) and reports FWHM_pix, FWHM_A and R at 1.25 um, compared with
design D25/5.3.6: ``FWHM_pix = max(slit / 0.24, 2.2)`` (4.17 px for 1") and
R = 3310 x 0.7 / slit (2317 for 1").

``--record`` writes or replaces the row ``(date, slit_width)`` in
``keck_etcs/data/mosfire/lsf_measurements.ecsv`` (with source, sha256 and
the night's reduction provenance from ``run_manifest.json``) and registers
it in ``keck_etcs/data/index.yaml``. The per-line table always goes to
``<night>/lsf/lsf_lines_<DATE>.ecsv``, and ``--plot`` adds a PNG there.
"""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table
from scipy.optimize import curve_fit

from keck_etcs import paths

REPO = Path(__file__).resolve().parents[2]
TABLE = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'lsf_measurements.ecsv'
INDEX = REPO / 'keck_etcs' / 'data' / 'index.yaml'
CALIB_VERSION = 'mosfire-J-2026.10-dev'
HALF = 8                 # fit window half-width, pixels
BLEND_FRAC = 0.10        # companion amplitude ratio that counts as a blend
BLEND_NFWHM = 1.5        # companion distance, in expected FWHMs
REF_WAVE = 12500.0       # A
SLOPE_ARCSEC_PER_PIX = 0.24   # design D25 (anamorphic dispersion-direction pixel)
FLOOR_PIX = 2.2
R0_SLIT = 3310.0 * 0.7        # design: R = 3310 x 0.7 / slit


def gauss(x, a, mu, sig, c0, c1):
    return a * np.exp(-0.5 * ((x - mu) / sig) ** 2) + c0 + c1 * (x - mu)


def sha256sum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_oh_hires():
    from pypeit import dataPaths
    t = Table.read(dataPaths.linelist.get_file_path('OH_R24000_lines.dat'),
                   format='ascii.fixed_width', comment='#')
    return np.asarray(t['wave'], float), np.asarray(t['amplitude'], float)


def measure(wavecalib, slit):
    from pypeit.wavecalib import WaveCalib
    wc = WaveCalib.from_file(str(wavecalib), chk_version=False)
    wf = wc.wv_fits[0]
    spec = np.asarray(wf.spec, float)
    wsol = np.asarray(wf.wave_soln, float)
    disp = np.gradient(wsol)
    xpix = np.arange(spec.size, dtype=float)
    expected_fwhm = max(slit / SLOPE_ARCSEC_PER_PIX, FLOOR_PIX)
    oh_w, oh_a = read_oh_hires()
    rows = []
    for px, wv in zip(np.asarray(wf.pixel_fit, float), np.asarray(wf.wave_fit, float)):
        i0, i1 = int(round(px)) - HALF, int(round(px)) + HALF + 1
        if i0 < 0 or i1 > spec.size:
            continue
        x, y = xpix[i0:i1], spec[i0:i1]
        p0 = [y.max() - np.median(y), px, expected_fwhm / 2.3548, np.median(y), 0.0]
        try:
            p, cov = curve_fit(gauss, x, y, p0=p0, maxfev=5000)
        except RuntimeError:
            continue
        a, mu, sig = p[0], p[1], abs(p[2])
        if a <= 0 or not np.isfinite(sig) or abs(mu - px) > 2:
            continue
        fwhm_pix = 2.3548 * sig
        d = float(np.interp(mu, xpix, disp))
        fwhm_a = fwhm_pix * abs(d)
        # blend test against the resolved list
        k = int(np.argmin(np.abs(oh_w - wv)))
        near = (np.abs(oh_w - oh_w[k]) < BLEND_NFWHM * expected_fwhm * abs(d)) & (np.arange(oh_w.size) != k)
        blended = bool(np.any(oh_a[near] >= BLEND_FRAC * oh_a[k])) or abs(oh_w[k] - wv) > 2 * abs(d)
        rows.append({'wave': float(wv), 'pixel': float(mu), 'amplitude': float(a),
                     'fwhm_pix': float(fwhm_pix),
                     'fwhm_pix_err': float(2.3548 * np.sqrt(cov[2, 2])) if np.isfinite(cov[2, 2]) else np.nan,
                     'dispersion': float(abs(d)), 'fwhm_A': float(fwhm_a),
                     'R': float(wv / fwhm_a), 'blended': blended})
    lines = Table(rows=rows)
    lines['wave'].unit = 'Angstrom'
    lines['fwhm_A'].unit = 'Angstrom'
    lines['dispersion'].unit = 'Angstrom / pix'
    return wc, wf, lines, expected_fwhm


def trend(lines):
    """Linear fit of FWHM_pix against wavelength for clean lines, 3-sigma clipped."""
    clean = lines[~lines['blended']]
    w, f = np.asarray(clean['wave']), np.asarray(clean['fwhm_pix'])
    keep = np.ones(w.size, bool)
    for _ in range(5):
        c = np.polyfit(w[keep] - REF_WAVE, f[keep], 1)
        resid = f - np.polyval(c, w - REF_WAVE)
        s = 1.4826 * np.median(np.abs(resid[keep] - np.median(resid[keep])))
        new = np.abs(resid) < 3 * s
        if np.array_equal(new, keep):
            break
        keep = new
    return c, keep, clean, float(s)


def main(date, wavecalib=None, slit=1.0, record=False, plot=False):
    night = paths.night_dir('mosfire', date)
    if wavecalib is None:
        hits = sorted((night / 'redux' / 'Calibrations').glob('WaveCalib_*.fits'))
        if not hits:
            print(f'no WaveCalib in {night}/redux/Calibrations (s3_sync.py pull first)')
            return 1
        wavecalib = hits[0]
    wavecalib = Path(wavecalib)
    wc, wf, lines, expected = measure(wavecalib, slit)
    coef, keep, clean, scatter = trend(lines)
    fwhm_ref = float(np.polyval(coef, 0.0))
    disp_ref = float(np.interp(REF_WAVE, np.asarray(wf.wave_soln), np.abs(np.gradient(np.asarray(wf.wave_soln)))))
    fwhm_a_ref = fwhm_ref * disp_ref
    r_ref = REF_WAVE / fwhm_a_ref
    r_model = R0_SLIT / slit

    print(f'{wavecalib}  (PypeIt arc FWHM estimate {wf.fwhm:.3f} px, RMS {wf.rms:.3f} px)')
    print(f'{len(lines)} identified lines fitted; {int(lines["blended"].sum())} flagged as blends; '
          f'{int(keep.sum())} clean lines used (3-sigma clipped), scatter {scatter:.3f} px')
    print(f'{"wave":>10s} {"FWHM px":>8s} {"err":>6s} {"FWHM A":>7s} {"R":>6s}  blend')
    for r in lines:
        print(f'{r["wave"]:10.2f} {r["fwhm_pix"]:8.3f} {r["fwhm_pix_err"]:6.3f} {r["fwhm_A"]:7.2f} '
              f'{r["R"]:6.0f}  {"B" if r["blended"] else ""}')
    print(f'\nFWHM_pix(lambda) = {coef[1]:.3f} + {coef[0] * 1e3:+.4f} x (lambda - 1.25 um)/1000 A')
    print(f'At 1.25 um: FWHM {fwhm_ref:.3f} px = {fwhm_a_ref:.2f} A (dispersion {disp_ref:.3f} A/px), '
          f'R = {r_ref:.0f}')
    ok_f = abs(fwhm_ref / expected - 1) < 0.20
    ok_r = abs(r_ref / r_model - 1) < 0.15
    print(f'Design: FWHM_pix = max({slit}/0.24, 2.2) = {expected:.2f} px -> measured/model '
          f'{fwhm_ref / expected:.3f} ({"within" if ok_f else "OUTSIDE"} 20%)')
    print(f'Design: R = 3310 x 0.7 / {slit} = {r_model:.0f} -> measured/model {r_ref / r_model:.3f} '
          f'({"within" if ok_r else "OUTSIDE"} 15%)')
    implied_slope = slit / fwhm_ref
    print(f'Implied slope for a slit-limited LSF: {slit}" / {fwhm_ref:.3f} px = {implied_slope:.4f} "/px '
          f'(design {SLOPE_ARCSEC_PER_PIX}); the floor ({FLOOR_PIX} px) is not constrained by a 1" slit')

    outdir = night / 'lsf'
    outdir.mkdir(exist_ok=True)
    lines['used'] = False
    lines['used'][np.where(~lines['blended'])[0][keep]] = True
    lines.meta.update({'wavecalib': str(wavecalib), 'wavecalib_sha256': sha256sum(wavecalib),
                       'slit_width_arcsec': slit, 'trend_coef_pix_per_A_and_pix': [float(c) for c in coef],
                       'script': 'scripts/mosfire/measure_lsf.py'})
    lines.write(outdir / f'lsf_lines_{date}.ecsv', format='ascii.ecsv', overwrite=True)
    print(f'per-line table: {outdir / f"lsf_lines_{date}.ecsv"}')

    if plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4), facecolor='#fcfcfb')
        b = lines['blended']
        ax.plot(lines['wave'][~b] / 1e4, lines['fwhm_pix'][~b], 'o', color='#2a78d6', ms=5, label='clean lines')
        ax.plot(lines['wave'][b] / 1e4, lines['fwhm_pix'][b], 'x', color='#6b6a64', ms=6, label='blends (not used)')
        ww = np.linspace(lines['wave'].min(), lines['wave'].max(), 50)
        ax.plot(ww / 1e4, np.polyval(coef, ww - REF_WAVE), color='#1f1f1e', lw=2, label='linear fit')
        ax.axhline(expected, color='#eb6834', lw=2, ls='--', label=f'design max({slit}/0.24, 2.2)')
        ax.set_xlabel(r'Vacuum wavelength ($\mu$m)')
        ax.set_ylabel('OH line FWHM (pixels)')
        ax.set_title(f'MOSFIRE J2 LSF from OH lines, {date}, {slit}" slit', fontsize=10)
        ax.legend(frameon=False, fontsize=8)
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        ax.grid(color='#e4e3dc', lw=0.5)
        fig.tight_layout()
        fig.savefig(outdir / f'lsf_{date}.png', dpi=130)
        print(f'plot: {outdir / f"lsf_{date}.png"}')

    if record:
        man = json.loads((night / 'run_manifest.json').read_text()) if (night / 'run_manifest.json').exists() else {}
        row = {'date': f'{date[:4]}-{date[4:6]}-{date[6:]}', 'filter': man.get('filter', ''),
               'slit_width': slit, 'fwhm_pix': round(fwhm_ref, 4), 'fwhm_pix_scatter': round(scatter, 4),
               'fwhm_A_1250': round(fwhm_a_ref, 3), 'R_1250': round(r_ref, 1),
               'dfwhm_dlam_pix_per_1000A': round(float(coef[0]) * 1e3, 4),
               'n_lines': int(keep.sum()), 'pypeit_arc_fwhm_pix': round(float(wf.fwhm), 4),
               'source': f'{man.get("s3_prefix", "mosfire/" + date)}/redux/Calibrations/{wavecalib.name}',
               'source_sha256': sha256sum(wavecalib),
               'image': man.get('image', 'local'), 'image_digest': man.get('image_digest') or '',
               'pypeit_git_sha': man.get('pypeit_git_sha') or '', 'keck_etcs_git_sha': man.get('keck_etcs_git_sha') or '',
               'job_name': man.get('job_name') or '',
               'method': 'Gaussian+linear fits to identified OH lines of the arc (sky) spectrum; '
                         'blends flagged with OH_R24000; linear FWHM(lambda), 3-sigma clipped'}
        rows = []
        if TABLE.exists():
            old = Table.read(TABLE, format='ascii.ecsv')
            rows = [dict(zip(old.colnames, r)) for r in old
                    if not (str(r['date']) == row['date'] and float(r['slit_width']) == slit)]
        rows.append(row)
        t = Table(rows=rows, names=list(row))
        t.sort(['date', 'slit_width'])
        for c, u in {'slit_width': 'arcsec', 'fwhm_pix': 'pix', 'fwhm_pix_scatter': 'pix', 'fwhm_A_1250': 'Angstrom',
                     'pypeit_arc_fwhm_pix': 'pix'}.items():
            t[c].unit = u
        t.meta.update({'description': 'MOSFIRE LSF measured from OH lines (S13); read by the instrument module (S8)',
                       'model': 'design D25/5.3.6: FWHM_pix = max(slit / 0.24, 2.2); R = 3310 x 0.7 / slit',
                       'ref_wave_A': REF_WAVE, 'calib_version': CALIB_VERSION,
                       'created': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                       'script': 'scripts/mosfire/measure_lsf.py --record'})
        TABLE.parent.mkdir(parents=True, exist_ok=True)
        t.write(TABLE, format='ascii.ecsv', overwrite=True)
        idx = yaml.safe_load(INDEX.read_text()) or {}
        idx.setdefault('files', {})['mosfire/lsf_measurements.ecsv'] = {
            'calib_version': CALIB_VERSION, 'created': t.meta['created'], 'sha256': sha256sum(TABLE),
            'script': 'scripts/mosfire/measure_lsf.py --record',
            'provenance': f'{len(t)} LSF measurement(s) from OH lines in PypeIt WaveCalib arc spectra'}
        head = ''.join(l for l in INDEX.read_text().splitlines(keepends=True) if l.startswith('#'))
        INDEX.write_text(head + yaml.safe_dump(idx, sort_keys=False, width=100))
        print(f'recorded in {TABLE.relative_to(REPO)} ({len(t)} row(s)); index.yaml updated')
    return 0 if (ok_f and ok_r) else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date')
    p.add_argument('--wavecalib', help='WaveCalib file (default: the night\'s)')
    p.add_argument('--slit', type=float, default=1.0, help='slit width (arcsec) of the arc frames')
    p.add_argument('--record', action='store_true', help='write the row to lsf_measurements.ecsv')
    p.add_argument('--plot', action='store_true', help='write a PNG of FWHM against wavelength')
    a = p.parse_args()
    sys.exit(main(a.date, a.wavecalib, a.slit, a.record, a.plot))
