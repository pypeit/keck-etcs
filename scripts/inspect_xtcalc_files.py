#!/usr/bin/env python
"""Inspect the data files shipped with the Keck MOSFIRE XTcalc ETC tarball.

Usage:
    conda run -n pypeit14 python scripts/inspect_xtcalc_files.py XTCALC_DIR

where XTCALC_DIR is the unpacked ``XTcalc_dir`` from
https://www2.keck.hawaii.edu/inst/mosfire/XTcalc.tar

Reports, for each band, the wavelength range, peak and median of the
end-to-end throughput tables (``mosfire/[band]_tp_tot.txt``) and the filter
curves (``mosfire/mosfire_[band].txt``), and inspects the Gemini Maunakea sky
background / transmission IDL save files in ``Mauna_Kea_sky/`` (variable
names, wavelength range, sampling, and the J-band level).
"""
import glob
import os
import sys

import numpy as np
from scipy.io import readsav

JBAND = (1.17, 1.35)   # micron, roughly the J2 clean region


def table_stats(path, label):
    w, t = np.loadtxt(path, unpack=True)
    print(f'  {label:32s} {w.min():.3f}-{w.max():.3f} um, {w.size} pts, '
          f'peak {t.max():.3f} at {w[np.argmax(t)]:.3f} um, '
          f'median(>0.5*peak) {np.median(t[t > 0.5 * t.max()]):.3f}')
    return w, t


def main(xtdir):
    print('Throughput and filter tables:')
    for band in ('Y', 'J', 'H', 'K', 'Ks'):
        tp = os.path.join(xtdir, 'mosfire', f'{band}_tp_tot.txt')
        if os.path.exists(tp):
            table_stats(tp, f'{band}_tp_tot (end-to-end throughput)')
        ft = os.path.join(xtdir, 'mosfire', f'mosfire_{band}.txt')
        if os.path.exists(ft):
            table_stats(ft, f'mosfire_{band} (filter curve)')
    print()

    print('Gemini Maunakea sky files (IDL save):')
    for path in sorted(glob.glob(os.path.join(xtdir, 'Mauna_Kea_sky', '*.sav'))):
        try:
            sav = readsav(path)
        except Exception as exc:
            print(f'  {os.path.basename(path)}: cannot read ({exc})')
            continue
        keys = list(sav.keys())
        arrs = {k: np.asarray(sav[k]) for k in keys}
        # Guess wavelength as the monotonic array, the other as the value
        wkey = next((k for k in keys if np.all(np.diff(arrs[k]) > 0)), keys[0])
        vkey = next((k for k in keys if k != wkey), None)
        w = arrs[wkey]
        v = arrs[vkey] if vkey else None
        # Gemini files are in nm; report both
        line = (f'  {os.path.basename(path):30s} vars={keys}  '
                f'{wkey}: {w.min():.1f}-{w.max():.1f} ({w.size} pts, '
                f'step {np.median(np.diff(w)):.3f})')
        if v is not None:
            wum = w / 1000. if w.max() > 100 else w
            inj = (wum > JBAND[0]) & (wum < JBAND[1])
            if inj.any():
                line += (f'  J: median {np.median(v[inj]):.4g}, '
                         f'max {v[inj].max():.4g}')
        print(line)
    print()
    print('Gemini conventions (from the Gemini site): mk_skybg_zm_WW_AA_ph = sky '
          'background in ph/s/arcsec^2/nm/m^2 for water vapour WW/10 mm and '
          'airmass AA/10; mktrans_zm_WW_AA = transmission. Wavelength in nm.')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])


def measured_files(xtdir):
    """The files XTcalc.pro actually reads: MosfireSpecEff/[band]eff.sm.dat
    (instrument-only throughput, multiplied in the code by KMRef^2 for the two
    Keck mirrors) and MosfireSkySpec/[band]sky_cal_pA.sav (sky measured with
    MOSFIRE, erg/s/cm2/A per spatial pixel through a 0.7 arcsec slit)."""
    kmref = {'Y': 0.85, 'J': 0.89, 'H': 0.94, 'K': 0.95}   # from XTcalc.pro
    print('\nFiles actually used by XTcalc.pro:')
    for band in ('Y', 'J', 'H', 'K'):
        eff = os.path.join(xtdir, 'MosfireSpecEff', f'{band}eff.sm.dat')
        if os.path.exists(eff):
            w, t = np.loadtxt(eff, unpack=True)
            w = w / 1e4 if w.max() > 100 else w
            good = t > 0.5 * t.max()
            print(f'  {band}eff.sm.dat: {w.min():.3f}-{w.max():.3f} um, '
                  f'{w.size} pts, instrument-only peak {t.max():.3f}, '
                  f'median(>0.5 peak) {np.median(t[good]):.3f}; '
                  f'x KMRef^2={kmref[band]**2:.3f} -> end-to-end peak '
                  f'{t.max()*kmref[band]**2:.3f}, median {np.median(t[good])*kmref[band]**2:.3f}')
        sky = os.path.join(xtdir, 'MosfireSkySpec', f'{band}sky_cal_pA.sav')
        if os.path.exists(sky):
            s = readsav(sky)
            lam = np.asarray(s['lam'])
            sk = np.asarray(s['mksky'])
            print(f'  {band}sky_cal_pA.sav: vars={list(s.keys())}, lam '
                  f'{lam.min():.0f}-{lam.max():.0f} A ({lam.size} pts, step '
                  f'{np.median(np.diff(lam)):.2f} A), sky median {np.median(sk):.3e}, '
                  f'max {sk.max():.3e} erg/s/cm2/A per spatial pix (0.7" slit)')


if __name__ == '__main__':
    measured_files(sys.argv[1])
