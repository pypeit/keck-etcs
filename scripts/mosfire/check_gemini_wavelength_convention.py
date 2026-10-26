#!/usr/bin/env python
"""Test whether the Gemini Maunakea sky grids are in vacuum or air wavelengths.

Usage:
    conda run -n pypeit14b python scripts/mosfire/check_gemini_wavelength_convention.py [XTCALC_DIR]

XTCALC_DIR defaults to ``keck_etcs.paths.xtcalc_dir()``.

Design decision N5 assumes the Gemini/ATRAN grids are in vacuum. This script
locates the 10 strongest OH lines between 1.10 and 1.35 um in the Gemini sky
background (PWV 1.6 mm, airmass 1.0) and compares their centroids with the
nearest line of PypeIt's vacuum list ``OH_MOSFIRE_J_lines.dat``. At 1.2 um the
air-vacuum difference is about 3.3 A, far larger than the 0.2 A sampling.

Two measurements are made:
  * native: centroids at the native 0.02 nm sampling, matched to the nearest
    PypeIt line (PypeIt's list was built at R=3318, so some entries are
    blends of close doublets);
  * R=3318: the sky is smoothed with a Gaussian to R=3318 first, the regime
    in which the PypeIt list was built, so blends are treated alike.

For each, the median offset of the Gemini centroids from the PypeIt vacuum
wavelengths and from the same list converted to air
(``pypeit.core.wave.vactoair``) is reported. The verdict is the convention
with the smaller |median offset|; it is unambiguous when that offset is well
below half the air-vacuum shift (about 1.6 A).

Prints a JSON summary on the last line (used by build_gemini_sky_grid.py).
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from scipy.io import readsav
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from astropy.table import Table

from pypeit import dataPaths
from pypeit.core.wave import vactoair
import astropy.units as u

# Allow running from a checkout without ``pip install -e .``
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from keck_etcs import paths  # noqa: E402

SKYFILE = 'mk_skybg_zm_16_10_ph.sav'
WINDOW = (1100.0, 1350.0)       # nm
NLINES = 10
R_PYPEIT = 3318.0
MATCH_TOL = 0.6                 # nm; > the 0.33 nm air-vacuum shift, so an air grid
                                # would still match (at about -3.3 A) rather than be dropped


def read_oh_list():
    path = dataPaths.linelist.get_file_path('OH_MOSFIRE_J_lines.dat')
    tbl = Table.read(path, format='ascii.fixed_width', comment='#')
    return np.asarray(tbl['wave'], dtype=float) / 10.0, np.asarray(tbl['amplitude'], dtype=float)


def centroid(lam, flux, ipk, hw):
    s = slice(max(ipk - hw, 0), ipk + hw + 1)
    f = flux[s] - np.min(flux[s])
    return np.sum(lam[s] * f) / np.sum(f)


def measure(lam, flux, oh_wave, hw, label, min_sep):
    """Centroid the NLINES strongest isolated peaks and match them to oh_wave."""
    step = np.median(np.diff(lam))
    peaks, props = find_peaks(flux, prominence=0, distance=max(int(min_sep / step), 1))
    order = np.argsort(props['prominences'])[::-1]
    rows = []
    for ip in peaks[order]:
        c = centroid(lam, flux, ip, hw)
        j = np.argmin(np.abs(oh_wave - c))
        d = c - oh_wave[j]
        if abs(d) > MATCH_TOL:
            continue
        # vactoair returns Angstrom regardless of the input unit
        air = vactoair(oh_wave[j] * u.nm).to(u.nm).value
        rows.append((c, oh_wave[j], d, c - air, flux[ip]))
        if len(rows) == NLINES:
            break
    rows = np.array(rows)
    med = float(np.median(rows[:, 2]))
    med_air = float(np.median(rows[:, 3]))
    shift = float(np.median(rows[:, 3] - rows[:, 2]))   # vac - air at each line
    print(f'\n[{label}] {len(rows)} strongest lines matched to OH_MOSFIRE_J_lines.dat (vacuum)')
    print('   Gemini_nm   PypeIt_vac_nm  d(vac)_A  d(air)_A     peak')
    for c, w, d, a, p in rows:
        print(f'  {c:10.4f}  {w:12.4f}  {d * 10:+8.3f}  {a * 10:+8.3f}  {p:8.1f}')
    print(f'  median offset vs vacuum list: {med * 10:+.3f} A '
          f'(scatter {np.std(rows[:, 2]) * 10:.3f} A); '
          f'vs air list: {med_air * 10:+.3f} A; air-vacuum shift {shift * 10:.3f} A')
    return {'label': label, 'n': int(len(rows)), 'median_offset_A': med * 10,
            'std_offset_A': float(np.std(rows[:, 2]) * 10),
            'median_offset_vs_air_A': med_air * 10, 'air_vac_shift_A': shift * 10}


def check(xtdir):
    """Run the test and return the summary dict (``waveref``, ``median_offset_A``, ...)."""
    sav = readsav(os.path.join(xtdir, 'Mauna_Kea_sky', SKYFILE))
    lam = np.asarray(sav['lam'], dtype=float)
    sky = np.asarray(sav['mksky'], dtype=float)
    keep = (lam >= WINDOW[0]) & (lam <= WINDOW[1])
    lam, sky = lam[keep], sky[keep]
    oh_wave, _ = read_oh_list()
    print(f'Gemini sky {SKYFILE}: {lam.size} pts, {lam[0]:.2f}-{lam[-1]:.2f} nm, '
          f'step {np.median(np.diff(lam)):.4f} nm')
    print(f'PypeIt OH_MOSFIRE_J_lines.dat: {oh_wave.size} lines, '
          f'{oh_wave.min():.1f}-{oh_wave.max():.1f} nm')

    native = measure(lam, sky, oh_wave, hw=3, label='native 0.02 nm', min_sep=0.5)

    step = np.median(np.diff(lam))
    sig_pix = (1200.0 / R_PYPEIT) / 2.3548 / step
    smooth = gaussian_filter1d(sky, sig_pix)
    fwhm_pix = int(round(2.3548 * sig_pix))
    smoothed = measure(lam, smooth, oh_wave, hw=fwhm_pix // 2, label=f'R={R_PYPEIT:.0f}',
                       min_sep=1200.0 / R_PYPEIT)

    def verdict(m):
        return 'vacuum' if abs(m['median_offset_A']) < abs(m['median_offset_vs_air_A']) else 'air'
    waveref = verdict(native)
    ref = native['median_offset_A'] if waveref == 'vacuum' else native['median_offset_vs_air_A']
    half = 0.5 * native['air_vac_shift_A']
    agree = verdict(smoothed) == waveref and abs(ref) < half
    print(f'\nVerdict: Gemini grids are in {waveref.upper()} wavelengths '
          f'(native median offset {ref:+.3f} A, half the air-vacuum shift {half:.2f} A; '
          f'R={R_PYPEIT:.0f} check {"agrees" if verdict(smoothed) == waveref else "DISAGREES"}).')
    summary = {'waveref': waveref, 'median_offset_A': ref, 'native': native,
               'smoothed': smoothed, 'consistent': bool(agree), 'skyfile': SKYFILE}
    return summary


if __name__ == '__main__':
    xtdir = sys.argv[1] if len(sys.argv) > 1 else str(paths.xtcalc_dir())
    summary = check(xtdir)
    print(json.dumps(summary))
    sys.exit(0 if summary['consistent'] else 1)
