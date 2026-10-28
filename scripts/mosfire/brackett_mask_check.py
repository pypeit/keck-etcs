#!/usr/bin/env python
"""The hydrogen-line mask test of design D52: zero-point smoothness across the Brackett lines of an A0V standard in H.

Usage:
    python scripts/mosfire/brackett_mask_check.py DATE --standard NAME [--band H] [--widths 10 30]
        [--json OUT.json]

PypeIt masks the hydrogen lines of an A0V standard (``mask_hydrogen_lines``)
over ``hydrogen_mask_wid`` A; at R ~ 3000 the Brackett lines (n = 10-18
over 1.53-1.74 um, the dense series toward the Brackett limit at 1.458 um)
are 50-100 A wide, and a 10 A mask leaves their wings in the fit, where the
zero point then follows the line profile. D52 chose 30 A for H and K (10 A
in Y and J) and asked for the check on a night with an A0V star in H.

For each mask width the night's A0V ``.sens`` file
(``<night>/sens/<NAME>_<DATE>_A0V.sens``, written by ``build_sensfunc.py``)
is copied with ``hydrogen_mask_wid`` replaced, ``pypeit_sensfunc`` is run on
the night's coadded standard (``sens/spec1d_coadd_<NAME>_<DATE>.fits``, or
the first standard frame's spec1d), and the zero point is read back
(``inspect_sensfunc.load``). Two metrics, from
PypeIt's per-pixel zero point before the polynomial fit
(``SENS_ZEROPOINT``, with its good-pixel mask) and the fitted zero point
(``SENS_ZEROPOINT_FIT``, the smooth curve the ETC uses):

- per mask width, the rms of data minus fit within +-40 A of each Brackett
  line over the pixels the fit used (``line_rms``) against the same rms over
  the line-free part of the band's common window (``continuum_rms``): a
  mask that leaves the line wings in the fit shows them as structured
  residuals at the lines, and the ratio line/continuum says so;
- between the widths, the difference of the fitted zero points
  (``fit_diff``: rms and maximum over the window, in magnitudes), i.e. how
  much the mask choice moves the curve the ETC would use, with the
  wavelength of the maximum.

The width with the smaller line rms is the verdict. Both sensfuncs stay
under ``<night>/sens/brackett/`` for inspection. Runs
inside the Nautilus image (PypeIt at the pin, with the ``slitrange`` patch
of ``nautilus/patches/`` until the pin moves) or locally.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from keck_etcs import paths
from keck_etcs.instruments.mosfire import MOSFIRE

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts' / 'mosfire'))
import inspect_sensfunc  # noqa: E402

RYDBERG_H_M = 1.0967758e7       # m^-1, hydrogen (reduced-mass) Rydberg constant
LINE_HALF_A = 40.0              # the +-window of the line rms
EXCLUDE_HALF_A = 60.0           # the continuum rms excludes +-this around each line


def brackett_lines_A(n_lo=10, n_hi=18):
    """Vacuum wavelengths [A] of the Brackett lines n -> 4, n = n_lo..n_hi."""
    return {n: 1e10 / (RYDBERG_H_M * (1 / 16.0 - 1 / n ** 2)) for n in range(n_lo, n_hi + 1)}


def load_zeropoints(path):
    """``(wave, zp_data, gpm, zp_fit)`` of a PypeIt sensfunc: the per-pixel zero point before the fit and the fit."""
    from pypeit.sensfunc import SensFunc
    sf = SensFunc.from_file(str(path), chk_version=False)
    s = sf.sens
    wave = np.asarray(s['SENS_WAVE'][0], float)
    data = np.asarray(s['SENS_ZEROPOINT'][0], float)
    gpm = np.asarray(s['SENS_ZEROPOINT_GPM'][0], bool) if 'SENS_ZEROPOINT_GPM' in s.colnames else np.isfinite(data)
    if 'SENS_ZEROPOINT_FIT_GPM' in s.colnames:
        gpm &= np.asarray(s['SENS_ZEROPOINT_FIT_GPM'][0], bool)
    fit = np.asarray(s['SENS_ZEROPOINT_FIT'][0], float)
    return wave, data, gpm, fit


def metrics(wave, data, gpm, fit, window, lines):
    """Data-minus-fit residual statistics at the lines and in the continuum (see the module docstring)."""
    sel = (wave >= window[0]) & (wave <= window[1]) & gpm & np.isfinite(data) & np.isfinite(fit) & (fit > 0)
    resid = np.where(sel, data - fit, np.nan)
    out = {'lines': {}}
    cont = sel.copy()
    for n, lam in lines.items():
        near = sel & (np.abs(wave - lam) <= LINE_HALF_A)
        cont &= np.abs(wave - lam) > EXCLUDE_HALF_A
        out['lines'][f'Br{n}'] = {'wave_A': round(lam, 1), 'n_pix': int(near.sum()),
                                  'rms_mag': float(np.sqrt(np.nanmean(resid[near] ** 2))) if near.any() else None,
                                  'max_abs_mag': float(np.nanmax(np.abs(resid[near]))) if near.any() else None}
    rms_l = [v['rms_mag'] for v in out['lines'].values() if v['rms_mag'] is not None]
    out['line_rms_mag'] = float(np.sqrt(np.mean(np.square(rms_l)))) if rms_l else None
    out['continuum_rms_mag'] = float(np.sqrt(np.nanmean(resid[cont] ** 2))) if cont.any() else None
    out['ratio'] = (out['line_rms_mag'] / out['continuum_rms_mag']
                    if out['line_rms_mag'] and out['continuum_rms_mag'] else None)
    out['n_pix_window'] = int(sel.sum())
    return out


def main(date, standard, band='H', widths=(10.0, 30.0), json_out=None):
    night = paths.night_dir('mosfire', date, band=band)
    sens_dir = night / 'sens'
    base = sens_dir / f'{standard}_{date}_A0V.sens'
    if not base.exists():
        print(f'missing {base} (build_sensfunc.py first)')
        return 2
    spec = sens_dir / f'spec1d_coadd_{standard}_{date}.fits'
    if not spec.exists():
        m = json.loads((night / 'run_manifest.json').read_text())
        objs = [o for o in m['objects'] if 'standard' in o['frametype']]
        spec = night / 'redux' / 'Science' / objs[0]['spec1d']
    window = tuple(MOSFIRE.bands[band].common_window_A)
    lines = brackett_lines_A()
    work = sens_dir / 'brackett'
    work.mkdir(exist_ok=True)
    text = base.read_text()
    results = {}
    for w in widths:
        par = work / f'{standard}_{date}_hm{w:g}.sens'
        # PypeIt's parameter type check wants a float literal ("10.0", not "10")
        new = re.sub(r'(?m)^(\s*hydrogen_mask_wid\s*=\s*)\S+', rf'\g<1>{w:.1f}', text)
        if 'hydrogen_mask_wid' not in new:
            new = new.replace('[sensfunc]\n', f'[sensfunc]\n  hydrogen_mask_wid = {w:.1f}\n', 1)
        par.write_text(new)
        out = work / f'sens_{standard}_{date}_hm{w:g}.fits'
        log = out.with_suffix('.log')
        with open(log, 'w') as f:
            rc = subprocess.run(['pypeit_sensfunc', str(spec), '-s', str(par), '-o', str(out)],
                                stdout=f, stderr=subprocess.STDOUT, cwd=work).returncode
        if rc != 0 or not out.exists():
            print(f'pypeit_sensfunc failed for mask {w:g} A (exit {rc}); see {log}')
            return 1
        wave, data, gpm, fit = load_zeropoints(out)
        results[f'{w:g}'] = {'sens': str(out.relative_to(night)), **metrics(wave, data, gpm, fit, window, lines),
                             '_fit': (wave, fit)}
    # how much the mask choice moves the fitted zero point (the curve the ETC uses)
    keys = list(results)
    fit_diff = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            wa, fa = results[keys[i]]['_fit']
            wb, fb = results[keys[j]]['_fit']
            sel = (wa >= window[0]) & (wa <= window[1]) & np.isfinite(fa) & (fa > 0)
            d = fa[sel] - np.interp(wa[sel], wb[np.isfinite(fb) & (fb > 0)], fb[np.isfinite(fb) & (fb > 0)])
            k = int(np.argmax(np.abs(d)))
            fit_diff[f'{keys[i]}-{keys[j]}'] = {'rms_mag': float(np.sqrt(np.mean(d ** 2))), 'max_abs_mag': float(np.abs(d[k])),
                                                'wave_of_max_A': float(wa[sel][k]), 'median_mag': float(np.median(d))}
    for r in results.values():
        r.pop('_fit')
    print(f'{standard} {date} {band}: per-pixel zero point minus PypeIt\'s fit over {window[0]:.0f}-{window[1]:.0f} A '
          f'(pixels the fit used); rms within +-{LINE_HALF_A:.0f} A of each Brackett line, in mag')
    head = f'{"line":6s} {"wave":>8s} ' + ' '.join(f'{"mask " + k + " A":>14s}' for k in results)
    print(head)
    for n in lines:
        key = f'Br{n}'
        print(f'{key:6s} {lines[n]:8.1f} ' + ' '.join(
            f"{(r['lines'][key]['rms_mag'] if r['lines'][key]['rms_mag'] is not None else float('nan')):14.4f}" for r in results.values()))
    print(f'{"lines":6s} {"":8s} ' + ' '.join(f"{r['line_rms_mag']:14.4f}" for r in results.values()))
    print(f'{"cont.":6s} {"":8s} ' + ' '.join(f"{r['continuum_rms_mag']:14.4f}" for r in results.values()))
    print(f'{"ratio":6s} {"":8s} ' + ' '.join(f"{r['ratio']:14.2f}" for r in results.values()))
    for k, d in fit_diff.items():
        print(f"fitted zero point, mask {k.replace('-', ' A minus mask ')} A: rms {d['rms_mag']:.4f} mag, median "
              f"{d['median_mag']:+.4f} mag, max |diff| {d['max_abs_mag']:.4f} mag at {d['wave_of_max_A']:.0f} A")
    best = min(results, key=lambda k: results[k]['line_rms_mag'])
    verdict = (f'mask {best} A gives the smaller data-minus-fit residual at Br10-18 (line rms '
               + ', '.join(f"{k}: {r['line_rms_mag']:.4f} mag" for k, r in results.items()) + '; line/continuum '
               + ', '.join(f"{k}: {r['ratio']:.2f}" for k, r in results.items()) + ')')
    print(verdict)
    summary = {'night': date, 'band': band, 'standard': standard, 'spec1d': str(spec), 'window_A': list(window),
               'widths_A': [float(w) for w in widths], 'results': results, 'fit_diff': fit_diff, 'best_width_A': float(best),
               'verdict': verdict, 'brackett_lines_A': {f'Br{n}': round(l, 2) for n, l in lines.items()},
               'pypeit_patch': os.environ.get('PYPEIT_PATCH') or None,
               'created': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
               'script': 'scripts/mosfire/brackett_mask_check.py'}
    (work / f'brackett_{standard}_{date}.json').write_text(json.dumps(summary, indent=1) + '\n')
    if json_out:
        Path(json_out).write_text(json.dumps(summary, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('date')
    p.add_argument('--standard', required=True)
    p.add_argument('--band', default='H')
    p.add_argument('--widths', type=float, nargs='+', default=(10.0, 30.0))
    p.add_argument('--json', dest='json_out')
    a = p.parse_args()
    sys.exit(main(a.date, a.standard, a.band, tuple(a.widths), a.json_out))
