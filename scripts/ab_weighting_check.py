#!/usr/bin/env python
"""Energy- versus photon-weighted synthetic AB magnitudes (S7 note on design 5.3.1).

Usage:
    conda run -n pypeit14b python scripts/ab_weighting_check.py

``keck_etcs.core.source.ab_mag`` follows design 5.3.1, <f_nu> = int f_nu F dnu
/ int F dnu (energy weighting). Photon-counting detectors are usually
described with int f_nu F dnu/nu / int F dnu/nu. The two agree for a flat
f_nu source; this script prints the difference for PypeIt's Vega spectrum
through top-hat bandpasses at the MOSFIRE filter centres and FWHMs of design
section 3. The real filter curves arrive in S8, so this only sizes the effect.
"""
from pathlib import Path

import numpy as np

from keck_etcs.core import source

VEGA = Path('~/Projects/PypeIt/PypeIt/pypeit/data/standards/vega_tspectool_vacuum.dat').expanduser()
BANDS = {'Y': (1.048, 0.152), 'J': (1.253, 0.200), 'J2': (1.181, 0.129), 'J3': (1.288, 0.122),
         'H': (1.637, 0.341), 'K': (2.162, 0.483)}


def photon_weighted_ab(wave, flam, fw, ft):
    f = np.interp(fw, wave, flam)
    nu = source.C_A_PER_S / fw
    # int f_nu F dnu/nu = int f_lambda F lam / c dlam ; int F dnu/nu = int F / lam dlam
    fnu = np.trapezoid(f * ft * fw / source.C_A_PER_S, fw) / np.trapezoid(ft / fw, fw)
    return -2.5 * np.log10(fnu) - source.AB_ZEROPOINT


def main():
    wave, flam = np.loadtxt(VEGA, usecols=(0, 1), unpack=True)
    print(f'Vega: {VEGA}')
    print('band  centre/FWHM um   AB(energy)  AB(photon)  difference')
    for b, (c, w) in BANDS.items():
        fw = np.linspace((c - w / 2) * 1e4, (c + w / 2) * 1e4, 4001)
        ft = np.ones_like(fw)
        e = source.vega_offset(wave, flam, fw, ft)
        p = photon_weighted_ab(wave, flam, fw, ft)
        print(f'{b:4s}  {c:.3f}/{w:.3f}      {e:8.4f}    {p:8.4f}    {e - p:+.4f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
