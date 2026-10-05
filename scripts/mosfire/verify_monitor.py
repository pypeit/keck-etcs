#!/usr/bin/env python
"""Verify the calibration monitor of one night (plan step S6b).

Usage:
    conda run -n pypeit14b python scripts/mosfire/verify_monitor.py DATE [--compare OTHER_monitor.ecsv]

Checks on ``<night>/harvest/<DATE>_monitor.ecsv``, against the night's
products and the committed tables:

1. ``line_fwhm_pix``, ``line_R`` and ``n`` reproduce the S13 row of
   ``keck_etcs/data/mosfire/lsf_measurements.ecsv`` exactly;
2. ``pixelflat_raw`` equals (lamp-on mean - lamp-off mean) from PypeIt's raw
   processing (gain 2.15) within 1 percent (``monitor.flat_conversion_check``);
3. the lamp-on peak raw ADU is reported against 26k;
4. the standard's scalar-FWHM rows match ``seeing_fwhm_pix`` in
   ``standards.ecsv``, and ``fwhmfit_pix`` exists at every node for every object;
5. ``slitloss_gt1pct`` is false for the standard; the science values are reported;
6. OH fluxes are finite for every on-sky frame. The fixed-window sums
   (``line_flux_sum``) of the 1" and 5" frames agree per arcsec^2 within 20
   percent after normalising each to the zenith with the van Rhijn factor of
   a thin emitting layer at 87 km. Frames flagged ``twilight`` (Sun above
   -18 deg) are excluded; with no dark frame on one side the comparison is
   reported NOT TESTABLE (S6b, user), not failed;
7. a first ``sky_scale`` is logged: the median of measured / Gemini model
   (``line_flux_above`` against its ``err`` column) on the science frames;
8. with ``--compare``, every numeric column of the two monitor files agrees
   to 1e-6 relative (the in-pod against local check).

Exit status 1 if a hard check (1, 2, 4, 5, 6, 8) fails.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

from keck_etcs import paths
from keck_etcs.calib import monitor as mo

REPO = Path(__file__).resolve().parents[2]
LSF = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'lsf_measurements.ecsv'
STD = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'throughput' / 'standards.ecsv'
R_EARTH, H_OH = 6371.0, 87.0     # km


def van_rhijn(airmass):
    """Path-length enhancement of a thin emitting layer at H_OH km, at the zenith angle of ``airmass``."""
    sinz2 = 1.0 - 1.0 / np.asarray(airmass, float) ** 2
    return 1.0 / np.sqrt(1.0 - (R_EARTH / (R_EARTH + H_OH)) ** 2 * sinz2)


def main(date, compare=None):
    night = paths.night_dir('mosfire', date)
    t = Table.read(night / 'harvest' / f'{date}_monitor.ecsv', format='ascii.ecsv')
    m = json.loads((night / 'run_manifest.json').read_text())
    ok = True
    sel = lambda metric: t[t['metric'] == metric]

    # 1
    lsf = Table.read(LSF, format='ascii.ecsv')
    ref = lsf[(lsf['date'] == f'{date[:4]}-{date[4:6]}-{date[6:]}') & (lsf['slit_width'] == 1.0)][0]
    fw, rr = sel('line_fwhm_pix')[0], sel('line_R')[0]
    c1 = (abs(fw['value'] - ref['fwhm_pix']) < 5e-4 and int(fw['n']) == int(ref['n_lines'])
          and abs(rr['value'] - ref['R_1250']) < 0.1)
    print(f"1. line widths: {fw['value']:.4f} px, n {fw['n']}, R {rr['value']:.1f} against S13 "
          f"{ref['fwhm_pix']}, {ref['n_lines']}, {ref['R_1250']}: {'PASS' if c1 else 'FAIL'}")
    ok &= c1

    # 2-3
    cal = night / 'redux' / 'Calibrations'
    flats = [f for f in m['frames'] if 'flat' in f['frametype']]
    chk = mo.flat_conversion_check(sorted(cal.glob('Flat_*.fits'))[0], sorted(cal.glob('Slits_*.fits.gz'))[0],
                                   night / 'raw', flats)
    c2 = abs(chk['ratio_median'] - 1) < 0.01
    print(f"2. pixelflat_raw / (on - off): median {chk['ratio_median']:.5f} (16-84% "
          f"{chk['ratio_p16_p84'][0]:.4f}-{chk['ratio_p16_p84'][1]:.4f}, {chk['n_pix']} px): "
          f"{'PASS' if c2 else 'FAIL'}")
    ok &= c2
    cards = json.loads(sel('flat_rate')[0]['cards'])
    print(f"3. lamp-on peak (99.99th pct) {cards['peak_adu_p9999']} ADU against 26000: "
          f"{'below' if cards['peak_adu_p9999'] < 26000 else 'ABOVE (flag nonlinear)'}")

    # 4
    std = Table.read(STD, format='ascii.ecsv')
    srow = std[std['date'] == f'{date[:4]}-{date[4:6]}-{date[6:]}'][0]
    stdframes = {f['filename'] for f in m['frames'] if 'standard' in f['frametype']}
    sf = sel('fwhm_scalar_pix')
    stdvals = [r['value'] for r in sf if r['frame'] in stdframes]
    c4a = abs(np.median(stdvals) - srow['seeing_fwhm_pix']) < 1e-6
    fit = sel('fwhmfit_pix')
    nodes = sorted(set(float(w) for w in fit['wave_A']))
    per_obj = {}
    for r in fit:
        per_obj.setdefault((r['frame'], r['line_id']), set()).add(float(r['wave_A']) if not np.ma.is_masked(r['value']) else None)
    c4b = all(set(nodes) <= v for v in per_obj.values()) and len(per_obj) == len(sf)
    print(f"4. standard scalar FWHM median {np.median(stdvals):.4f} = seeing_fwhm_pix {srow['seeing_fwhm_pix']:.4f}: "
          f"{'PASS' if c4a else 'FAIL'}; FWHMFIT at {nodes} for all {len(per_obj)} objects: {'PASS' if c4b else 'FAIL'}")
    ok &= c4a and c4b

    # 5
    sl = sel('slitloss_gt1pct')
    c5 = all(r['value'] == 0 for r in sl if r['frame'] in stdframes)
    print('5. slitloss_gt1pct: ' + '; '.join(f"{r['frame'][8:12]} {r['slit_width']:.0f}\" "
                                            f"{'T' if r['value'] else 'F'} ({100 * r['err']:.1f}%)" for r in sl)
          + f": standard false {'PASS' if c5 else 'FAIL'}")
    ok &= c5

    # 6
    onsky = sorted(f['filename'] for f in m['frames'] if ('science' in f['frametype']) or ('standard' in f['frametype']))
    s_all = sel('line_flux_sum')
    lf = sel('line_flux_window')
    tw = lambda r: 'twilight' in str(r['flag'])
    s = s_all[[not tw(r) for r in s_all]]
    finite = all(np.all(np.isfinite(lf[lf['frame'] == f]['value'])) and np.any(lf['frame'] == f) for f in onsky)
    zen = {r['frame']: (float(r['value']) / van_rhijn(r['airmass']), float(r['slit_width']), float(r['airmass']), float(r['mjd']))
           for r in s}
    narrow = [v[0] for v in zen.values() if v[1] <= 1.0]
    wide = [v[0] for v in zen.values() if v[1] > 1.0]
    twi = [f"{r['frame'][8:12]} (sun {json.loads(r['cards'])['sun_alt_deg']:.1f} deg)" for r in s_all if tw(r)]
    print('6. OH fixed-window sums, dark frames (e-/s/arcsec^2; zenith-normalised): ' +
          '; '.join(f"{f[8:12]} {v[1]:.0f}\" X{v[2]:.2f}: {v[0]:.1f}" for f, v in sorted(zen.items())))
    print(f"   twilight frames excluded: {twi or 'none'}")
    if narrow and wide:
        ratio = np.median(wide) / np.median(narrow)
        c6 = finite and abs(ratio - 1) < 0.20
        print(f"   finite for all {len(onsky)} frames: {finite}; 5\"/1\" median ratio {ratio:.3f} "
              f"(within 20%: {'PASS' if c6 else 'FAIL'})")
    else:
        c6 = finite
        print(f"   finite for all {len(onsky)} frames: {'PASS' if finite else 'FAIL'}; 1\"/5\" slit normalisation: "
              f"NOT TESTABLE on this night (no dark frame at {'5' if narrow else '1'}\")")
    ok &= c6

    # 7
    ab = sel('line_flux_above')
    sci = {f['filename'] for f in m['frames'] if 'science' in f['frametype']}
    per = [(r['value'] / r['err']) for r in ab if r['frame'] in sci and r['line_id'] != 'OH_sum'
           and r['err'] > 0 and not tw(r)]
    tot = [(r['value'] / r['err']) for r in ab if r['frame'] in sci and r['line_id'] == 'OH_sum'
           and r['err'] > 0 and not tw(r)]
    if per:
        print(f"7. first sky_scale (measured / Gemini, science frames): summed windows median {np.median(tot):.3f} "
              f"(per line median {np.median(per):.3f}, range {np.min(per):.3f}-{np.max(per):.3f}, {len(per)} values)")
    else:
        print('7. no line_flux_above rows (no harvest curve)')

    # 8
    if compare:
        o = Table.read(compare, format='ascii.ecsv')
        key = lambda r: tuple(str(r[c]) for c in ('metric', 'frame', 'wave_A', 'line_id'))   # str: masked cells
        a = {key(r): r for r in t}
        b = {key(r): r for r in o}
        bad = []
        for k in set(a) | set(b):
            if k not in a or k not in b:
                bad.append((k, 'missing'))
                continue
            for c in ('value', 'err', 'n', 'airmass', 'mjd', 'slit_width', 'wave_A', 'pwv_fit'):
                x, y = a[k][c], b[k][c]
                if np.ma.is_masked(x) or np.ma.is_masked(y):
                    if np.ma.is_masked(x) != np.ma.is_masked(y):
                        bad.append((k, c))
                    continue
                if abs(float(x) - float(y)) > 1e-6 * max(1.0, abs(float(y))):
                    bad.append((k, c))
        c8 = not bad
        print(f"8. compare with {Path(compare).name}: {len(a)} rows; {'PASS' if c8 else f'FAIL {bad[:5]}'}")
        ok &= c8
    print('VERIFY: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date')
    p.add_argument('--compare', help='another monitor file of the same night (e.g. the in-pod one)')
    a = p.parse_args()
    sys.exit(main(a.date, a.compare))
