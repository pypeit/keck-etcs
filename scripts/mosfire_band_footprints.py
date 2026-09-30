#!/usr/bin/env python
"""Report the wavelength footprint and dispersion of each MOSFIRE spectroscopic
band from PypeIt's archived wavelength templates.

Usage:
    conda run -n pypeit14 python scripts/mosfire_band_footprints.py

PypeIt reidentifies MOSFIRE wavelengths against ``keck_mosfire_OH_<band>.fits``
(and ``keck_mosfire_arcs_<band>.fits`` for long2pos_specphot).  Each template
holds a 1-D spectrum and its wavelength array, so its first and last
wavelengths give the detector footprint and the median step gives the
dispersion in A/pix.  These numbers feed the instrument table in
docs/keck_mosfire_design.md.  Also prints the J2 clean region PypeIt uses for
the standard star (keck_mosfire.tweak_standard).
"""
import numpy as np
from astropy.io import fits

from pypeit import dataPaths

BANDS = ['Y', 'J', 'J2', 'H', 'K']
CLEAN = {'Y': (9520., 11256.), 'J2': (11170., 12600.)}   # from tweak_standard


def main():
    print(f"{'band':5s} {'template':28s} {'wave_min':>9s} {'wave_max':>9s} "
          f"{'npix':>5s} {'A/pix':>6s} {'R@0.7\" (3.9 pix)':>17s}")
    for band in BANDS:
        for kind in ('OH', 'arcs'):
            name = f'keck_mosfire_{kind}_{band}.fits'
            try:
                path = dataPaths.reid_arxiv.get_file_path(name)
            except Exception as exc:
                print(f'{band:5s} {name:28s} missing ({exc})')
                continue
            with fits.open(path) as hdul:
                # Templates are written by pypeit.core.wavecal.templates; the
                # wavelength lives in a table column or the first HDU
                wave = None
                for h in hdul:
                    if getattr(h, 'columns', None) is not None and 'wave' in h.columns.names:
                        wave = np.asarray(h.data['wave'], dtype=float)
                        break
                if wave is None:
                    wave = np.asarray(hdul[0].data, dtype=float).ravel()
            wave = wave[wave > 0]
            disp = np.median(np.diff(wave))
            wcen = 0.5 * (wave.min() + wave.max())
            r07 = wcen / (3.9 * disp)   # 0.7" slit = 3.9 spatial pix, before anamorphism
            print(f'{band:5s} {name:28s} {wave.min():9.1f} {wave.max():9.1f} '
                  f'{wave.size:5d} {disp:6.3f} {r07:17.0f}')
    print('\nPypeIt tweak_standard clean regions (A):', CLEAN)


if __name__ == '__main__':
    main()
