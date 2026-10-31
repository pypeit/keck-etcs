#!/usr/bin/env python
"""Rank OH lines for the calibration monitor by the rules of design 4.9.4 (S6b; frozen in S15a).

Usage:
    conda run -n pypeit14b python scripts/mosfire/select_monitor_lines.py DATE [DATE ...]
        [--band J2] [--nlines 5] [--out FILE.ecsv]

Candidates are the lines of PypeIt's resolved, vacuum ``OH_R24000_lines.dat``
inside the band window. Rules, per design 4.9.4:

1. identified: within 2 A of a line PypeIt identified (``wave_fit``) in
   the night's ``WaveCalib``, on at least 80 percent of the nights given
   whose arcs are OH lines. A night calibrated with Ne/Ar lamps (every
   long2pos_specphot night, S24a) identifies no OH line and is left out of
   this rule (printed); its on-sky frames still carry the OH sky lines the
   monitor measures;
2. isolated: no companion with more than 10 percent of its amplitude within
   3 FWHM of a sky line in a 1" slit (interim D25 slope). Revised in S6b:
   at 5" the J2 OH lines blend and only 1 of 74 passes. Wide slits use
   the fixed windows of ``line_flux_window`` instead;
3. bright but linear: ranked by the measured flux in the narrowest slit of
   the first night (``keck_etcs.calib.monitor.line_fluxes`` on its on-sky
   frames; 1" for the J2 reference, 0.7" for the H one).
   Rejected if a frame's raw 99.9th-percentile level exceeds 26k ADU (a
   frame-level check; sky lines are far below the limit in J);
4. at least 100 A inside the band window, with Gemini ``TRANS`` > 0.9 at
   airmass 1.5 and PWV 1.6 mm, averaged over the line window;
5. the brightest surviving line in each of ``--nlines`` equal sub-windows of
   the band, so that the list is spread out.

Prints the ranked table and writes it (with its sha256 in the log) to
``--out`` (default ``<night>/lsf/monitor_lines_<band>.ecsv`` of the first
date). The chosen wavelengths go into
``MONITOR`` of ``keck_etcs/instruments/mosfire.py`` by hand (re-exported by
``keck_etcs/calib/monitor_configs.py``), as the provisional list
(frozen after the S15a pilot). Y, H and K nights keep their products under
``<night>/<band>/`` (D55) and share the night's ``raw/``; ``--band`` selects
them. The isolation window (rule 2) uses the band's dispersion.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

from keck_etcs import paths
from keck_etcs.calib import monitor as mo
from keck_etcs.calib import monitor_configs as mc
from keck_etcs.calib.harvest import SKYGRID

ISOLATION_SLIT = 1.0   # design 4.9.4 rule 2 as revised in S6b (5" leaves 1 of 74 J2 lines)


def night_inputs(date, band=None):
    night = paths.night_dir('mosfire', date, band=band)
    m = json.loads((night / 'run_manifest.json').read_text())
    cal = night / 'redux' / 'Calibrations'
    sci = night / 'redux' / 'Science'
    onsky = [f for f in m['frames'] if ('science' in f['frametype']) or ('standard' in f['frametype'])]
    spec1d = {f['filename']: next(iter(sorted(sci.glob(f'spec1d_{Path(f["filename"]).stem}-*.fits'))), None)
              for f in onsky}
    return night, m, cal, onsky, spec1d


def raw_dir_of(date, band=None):
    """The night's raw directory (shared by the bands of a night, D55)."""
    return paths.night_dir('mosfire', date, 'raw', band=band)


def gemini_trans_ok(lam, half, thresh=0.9):
    with fits.open(SKYGRID) as h:
        wave = h['WAVE'].data.astype(float) * 10.0
        trans = h['TRANS'].data.astype(float)
        grid = h['GRID'].data
    i = int(np.where(np.isclose(grid['airmass'], 1.5) & np.isclose(grid['pwv_mm'], 1.6))[0][0])
    sel = np.abs(wave - lam) <= half
    return float(np.mean(trans[i][sel]))


def main(dates, band='J2', nlines=5, out=None, widest_slit=ISOLATION_SLIT):
    cfg = mc.get_config('keck_mosfire')
    lo, hi = cfg['band_windows'][band]
    oh_w, oh_a = mo.read_line_list(cfg['line_lists']['OH'])
    inband = (oh_w > lo + 100) & (oh_w < hi - 100)
    nights = [night_inputs(d, band) for d in dates]
    # identified lines per night; a night whose arcs are Ne/Ar lamps (long2pos_specphot) identifies no OH
    # line and does not count for rule 1
    from pypeit.wavecalib import WaveCalib
    ident = []
    for d, (night, m, cal, onsky, spec1d) in zip(dates, nights):
        wc = WaveCalib.from_file(str(sorted(cal.glob('WaveCalib_*.fits'))[0]), chk_version=False)
        fit = next((f for f in wc.wv_fits if f is not None and f.wave_fit is not None and len(f.wave_fit)), None)
        w = np.asarray(fit.wave_fit, float) if fit is not None else np.array([])
        oh_frac = float(np.mean([np.any(np.abs(oh_w - x) <= 2.0) for x in w])) if w.size else 0.0
        if oh_frac < 0.5:
            print(f'{d}: {w.size} identified lines, {oh_frac:.0%} OH -> lamp arcs; left out of rule 1')
            continue
        ident.append(w)
    if not ident:
        print('no night with OH arcs: rule 1 cannot be applied')
        return 1
    from keck_etcs.instruments.mosfire import MOSFIRE
    disp = float(MOSFIRE.bands[band].dispersion_A_per_pix)
    fwhm5 = mo.sky_line_fwhm_A(widest_slit, disp)
    cands = []
    for k in np.where(inband)[0]:
        lam, amp = oh_w[k], oh_a[k]
        frac_id = np.mean([np.any(np.abs(w - lam) <= 2.0) for w in ident])
        near = (np.abs(oh_w - lam) <= 3 * fwhm5) & (np.arange(oh_w.size) != k)
        isolated = not np.any(oh_a[near] > 0.10 * amp)
        trans = gemini_trans_ok(lam, 1.5 * fwhm5)
        cands.append({'wave': float(lam), 'amplitude_list': float(amp), 'frac_identified': float(frac_id),
                      'isolated': isolated, 'gemini_trans': trans})
    tbl = Table(rows=cands)
    tbl['rule1'] = tbl['frac_identified'] >= 0.8
    tbl['rule2'] = tbl['isolated']
    tbl['rule4'] = tbl['gemini_trans'] > 0.9
    pre = tbl[tbl['rule1'] & tbl['rule2'] & tbl['rule4']]
    print(f'{len(tbl)} OH_R24000 lines in {band} (>=100 A inside {lo:.0f}-{hi:.0f} A); '
          f'rule1 {int(tbl["rule1"].sum())}, rule2 {int(tbl["rule2"].sum())}, rule4 {int(tbl["rule4"].sum())}; '
          f'all three: {len(pre)}')
    # rule 3: measured flux and raw peak, first night
    night, m, cal, onsky, spec1d = nights[0]
    flats = sorted(cal.glob('Flat_*.fits'))[0]
    slits = sorted(cal.glob('Slits_*.fits.gz'))[0]
    raw = raw_dir_of(dates[0], band)
    meas = mo.line_fluxes(onsky, spec1d, flats, slits, raw, list(pre['wave']), cfg, band, str(dates[0]))
    widths = sorted({float(r['slit_width']) for r in meas
                     if r['metric'] == 'line_flux' and r['value'] is not None and r['slit_width'] is not None})
    narrow = widths[0] if widths else None
    print(f'rule 3 flux from the {narrow}" slit of {dates[0]} (slit widths measured: {widths})')
    flux = {}
    for r in meas:
        if r['metric'] == 'line_flux' and r['value'] is not None and r['slit_width'] is not None \
                and float(r['slit_width']) == narrow:
            flux.setdefault(r['wave_A'], []).append(r['value'])
    pre['flux_1arcsec'] = [float(np.median(flux.get(w, [np.nan]))) for w in pre['wave']]
    peaks = []
    for w in pre['wave']:
        pk = 0.0
        for f in onsky:
            d = fits.getdata(raw / f['filename']).astype(float)
            pk = max(pk, float(np.percentile(d, 99.9)))
        peaks.append(pk)
    pre['raw_peak_p999'] = peaks
    pre['rule3'] = np.isfinite(pre['flux_1arcsec']) & (pre['flux_1arcsec'] > 0) & \
        (pre['raw_peak_p999'] < cfg['nonlinear_adu'])
    ok = pre[pre['rule3']]
    edges = np.linspace(lo + 100, hi - 100, nlines + 1)
    chosen = []
    for a, b in zip(edges[:-1], edges[1:]):
        sub = ok[(ok['wave'] >= a) & (ok['wave'] < b)]
        if len(sub):
            chosen.append(float(sub['wave'][np.argmax(sub['flux_1arcsec'])]))
    pre['chosen'] = [w in chosen for w in pre['wave']]
    pre.sort('wave')
    pre.pprint(max_lines=-1, max_width=-1)
    print(f'chosen ({len(chosen)}): {chosen}')
    out = Path(out) if out else night / 'lsf' / f'monitor_lines_{band}.ecsv'
    out.parent.mkdir(exist_ok=True)
    pre.meta.update({'dates': [str(d) for d in dates], 'band': band, 'rules': 'design 4.9.4',
                     'chosen': chosen, 'fwhm_5arcsec_A': fwhm5, 'isolation_slit_arcsec': widest_slit,
                     'dispersion_A_per_pix': disp, 'rule1_nights_with_OH_arcs': len(ident),
                     'rule3_slit_arcsec': narrow})
    pre.write(out, format='ascii.ecsv', overwrite=True)
    print(f'wrote {out} sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('dates', nargs='+')
    p.add_argument('--band', default='J2')
    p.add_argument('--nlines', type=int, default=5)
    p.add_argument('--out')
    p.add_argument('--widest-slit', type=float, default=ISOLATION_SLIT,
                   help='slit (arcsec) whose sky-line FWHM sets the isolation window (rule 2; default 1)')
    a = p.parse_args()
    sys.exit(main(a.dates, a.band, a.nlines, a.out, a.widest_slit))
