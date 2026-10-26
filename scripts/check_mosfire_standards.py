#!/usr/bin/env python
"""Check whether the standards observed with MOSFIRE in the dev suite have
NIR flux models in PypeIt's standards data, and what they cover.

Usage:
    conda run -n pypeit14 python scripts/check_mosfire_standards.py

For each standard it runs PypeIt's own coordinate lookup (the same one
pypeit_sensfunc uses), then opens the matched file and reports the wavelength
range, the sampling in the J band, and the J-band flux level.
"""
import numpy as np

from pypeit.core import standard

# (name in dev-suite pypeit file, RA deg, Dec deg, setup where it was observed)
STANDARDS = [
    ('LDS749B', 323.06782305, 0.25447328, 'J2_long, LONGSLIT-46x5, 2022-04-09'),
    ('GD 71', 88.12398597, 15.88291243, 'Y_long, LONGSLIT-46x1, 2019-11-18'),
    ('HIP 17971 (A0V)', 57.63367891, 29.70977818, 'K_long, LONGSLIT-46x1.5, 2019-10-13'),
    ('Feige 110', 349.9933, -5.1656, 'not observed; common Keck NIR standard'),
    ('G191-B2B', 76.3776, 52.8311, 'not observed; common Keck NIR standard'),
    ('GD 153', 194.2597, 22.0313, 'not observed; common Keck NIR standard'),
]

# J-band (and J2) rough limits in Angstrom
JBAND = (11500., 13500.)
J2BAND = (11170., 12600.)   # PypeIt's clean J2 region (keck_mosfire.tweak_standard)


def main():
    # Find the lookup function; its name has moved between PypeIt versions
    lookup = getattr(standard, "get_standard_spectrum", None)
    print('PypeIt lookup function:', lookup.__name__ if lookup else None)
    print()

    for name, ra, dec, note in STANDARDS:
        print('=' * 70)
        print(f'{name}  ({note})')
        try:
            std = standard.get_standard_spectrum(ra=ra, dec=dec)
        except Exception as exc:
            print('  lookup failed:', repr(exc))
            continue
        wave = np.asarray(std.wave)
        flux = np.asarray(std.flux)
        print(f'  class: {type(std).__name__}')
        print(f'  file: {getattr(std, "file", None)}')
        meta = getattr(std, 'meta', None)
        if meta is not None:
            try:
                print('  meta:', {k: meta[k] for k in meta.keys()} if hasattr(meta, 'keys') else meta)
            except Exception:
                print('  meta:', meta)
        print(f'  wavelength range: {wave.min():.0f} - {wave.max():.0f} A '
              f'({wave.size} points)')
        for label, (w0, w1) in (('J', JBAND), ('J2 clean', J2BAND)):
            inb = (wave > w0) & (wave < w1)
            if inb.sum() < 2:
                print(f'  {label}: no coverage')
                continue
            dw = np.median(np.diff(wave[inb]))
            fmed = np.median(flux[inb])
            print(f'  {label}: {inb.sum()} pts, median step {dw:.1f} A, '
                  f'median flux {fmed:.3e} x 1e-17 erg/s/cm2/A')
        print()


if __name__ == '__main__':
    main()
