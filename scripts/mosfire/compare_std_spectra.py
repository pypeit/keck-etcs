#!/usr/bin/env python
"""Compare PypeIt's archive spectra of a standard in the J band (plan S15a verification).

Usage:
    conda run -n pypeit14b python scripts/mosfire/compare_std_spectra.py [NAME ...]

For each standard (default Feige110 and GD153), reads every PypeIt archive
spectrum of it (``pypeit/data/standards/<set>/<set>_info.txt``) and prints the
median flux over 1.117-1.260 um (the throughput gate window) and its ratio to
the CALSPEC spectrum, the reference for the absolute scale. PypeIt's sensfunc
takes the first archive match by position (``standard.get_archive_standard``),
which for both WDs is X-shooter; a reference spectrum that is wrong in J
changes the zero point by the same factor.
"""
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

from pypeit import dataPaths

WINDOW = (11170.0, 12600.0)


def read(set_name, fname):
    path = Path(dataPaths.standards.get_file_path(f'{set_name}/{fname}'))
    if fname.endswith(('.fits', '.fits.gz')):
        d = fits.getdata(path, 1)
        return np.asarray(d['WAVELENGTH'], float), np.asarray(d['FLUX'], float)
    t = np.loadtxt(path, comments='#')
    w, f = t[:, 0], t[:, 1]
    if set_name == 'esofil':
        f = f * 1e-16       # 1e-16 erg/s/cm2/A (PypeIt standard.py); xshooter is in erg/s/cm2/A
    return w, f


def main(names):
    root = Path(dataPaths.standards.get_file_path('calspec/calspec_info.txt')).parents[1]
    for name in names:
        print(f'== {name}')
        rows = []
        for info in sorted(root.glob('*/*_info.txt')):
            set_name = info.parent.name
            for ln in info.read_text().splitlines():
                p = ln.split()
                if len(p) > 1 and p[1].replace(' ', '').lower() == name.lower():
                    try:
                        w, f = read(set_name, p[0])
                    except Exception as exc:  # noqa: BLE001 - report and continue
                        print(f'  {set_name:9s} {p[0]:32s} unreadable: {exc}')
                        continue
                    sel = (w > WINDOW[0]) & (w < WINDOW[1])
                    med = float(np.median(f[sel])) if sel.any() else None
                    rows.append((set_name, p[0], float(w.min()), float(w.max()), med))
        ref = next((r[4] for r in rows if r[0] == 'calspec' and r[4]), None)
        for s, fn, wmin, wmax, med in rows:
            ratio = f'{med / ref:.3f}' if (med and ref) else '-'
            print(f'  {s:9s} {fn:32s} {wmin:8.0f}-{wmax:8.0f} A  median J2 flux '
                  f'{med if med is None else f"{med:.4e}"}  /CALSPEC {ratio}')


if __name__ == '__main__':
    main(sys.argv[1:] or ['Feige110', 'GD153'])
