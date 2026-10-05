#!/usr/bin/env python
"""Download the MOSFIRE filter curves from Keck and write them as ECSV (plan step S8, design 5.4).

Usage:
    conda run -n pypeit14b python scripts/mosfire/fetch_keck_filter_curves.py [--offline]

For each band (J and J2 required; Y, J3, H, K while there) the ASCII curve
linked from https://www2.keck.hawaii.edu/inst/mosfire/filters.html is
downloaded, kept verbatim under ``$KECK_ETCS_DATA/external/keck_filters/``
(``--offline`` re-reads those copies), and written to
``keck_etcs/data/mosfire/filters/mosfire_<band>.ecsv`` with columns
``wave_A`` (vacuum) and ``transmission`` (0-1), and ``meta``:

- the source URL, download date and SHA-256 of the raw file;
- the wavelength convention. The Keck page does not state it; laboratory
  spectrophotometer scans are in air, so the curves are taken as air and
  converted to vacuum with PypeIt's ``airtovac`` (a +3.4 A shift at 1.25 um);
- the published centre and FWHM, and the half-power points measured from the
  curve (on a 9-sample running median, so single noisy samples do not set
  the peak);
- ``ab_minus_vega``: the synthetic AB magnitude of PypeIt's
  ``vega_tspectool_vacuum.dat`` through the curve (m_Vega = 0), computed
  with ``keck_etcs.core.source.vega_offset`` (design 5.3.1), so that
  ``core`` and ``etc`` never read the Vega file or import PypeIt;
- notes: the J2/J3 files are ``*_center_corr`` (the Keck name; taken to be
  the curve at the centre of the field) and contain small negative values
  (scan noise), clipped to 0 and counted.

Every file is registered in ``keck_etcs/data/index.yaml``.
"""
import argparse
import datetime
import hashlib
import sys
import urllib.request
from pathlib import Path

import numpy as np
import yaml
from astropy.table import Table
from scipy.ndimage import median_filter

import keck_etcs
from keck_etcs import paths
from keck_etcs.core import source

REPO = Path(__file__).resolve().parents[2]
OUTDIR = REPO / 'keck_etcs' / 'data' / 'mosfire' / 'filters'
INDEX = REPO / 'keck_etcs' / 'data' / 'index.yaml'
CALIB_VERSION = 'mosfire-J-2026.10-dev'
PAGE = 'https://www2.keck.hawaii.edu/inst/mosfire/filters.html'
BASE = 'https://www2.keck.hawaii.edu/inst/mosfire/data/filter/'
# band: (file, published centre um, published FWHM um), from the filters page
BANDS = {'Y': ('mosfire_Y.txt', 1.048, 0.152), 'J': ('mosfire_J.txt', 1.253, 0.200),
         'J2': ('J2_center_corr.txt', 1.181, 0.129), 'J3': ('J3_center_corr.txt', 1.288, 0.122),
         'H': ('mosfire_H.txt', 1.637, 0.341), 'K': ('mosfire_K.txt', 2.162, 0.483)}
SMOOTH = 9


def vega_spectrum():
    import pypeit
    p = Path(pypeit.__file__).parent / 'data' / 'standards' / 'vega_tspectool_vacuum.dat'
    w, f = np.loadtxt(p, usecols=(0, 1), unpack=True)
    return w, f, p, hashlib.sha256(p.read_bytes()).hexdigest()


def half_power(wave, trans):
    """Half-power wavelengths (first and last crossings of half the smoothed peak) and the peak."""
    sm = median_filter(trans, size=SMOOTH, mode='nearest')
    peak = float(sm.max())
    above = np.flatnonzero(sm >= 0.5 * peak)
    i, j = above[0], above[-1]

    def cross(a, b):    # linear interpolation of the half-power crossing between samples a and b
        return float(np.interp(0.5 * peak, sorted([sm[a], sm[b]]),
                               [wave[a], wave[b]] if sm[a] < sm[b] else [wave[b], wave[a]]))
    return cross(i - 1, i), cross(j, j + 1), peak


def update_index(entries):
    index = yaml.safe_load(INDEX.read_text()) or {} if INDEX.exists() else {}
    index.setdefault('files', {}).update(entries)
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))


def main(offline=False):
    import astropy.units as u
    from pypeit.core.wave import airtovac
    rawdir = paths.data_root() / 'external' / 'keck_filters'
    rawdir.mkdir(parents=True, exist_ok=True)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    vw, vf, vpath, vsha = vega_spectrum()
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    entries = {}
    print(f'{"band":4s} {"file":20s} {"n":>5s} {"neg":>4s} {"peak":>6s} {"half-power um (vac)":>21s} '
          f'{"centre":>7s} {"FWHM":>6s} {"published":>12s} {"AB-Vega":>8s}')
    for band, (fname, c_pub, w_pub) in BANDS.items():
        url = BASE + fname
        raw = rawdir / fname
        if not offline:
            with urllib.request.urlopen(url, timeout=60) as r:
                raw.write_bytes(r.read())
            (rawdir / (fname + '.downloaded')).write_text(now + '\n')
        downloaded = (rawdir / (fname + '.downloaded')).read_text().strip()
        sha = hashlib.sha256(raw.read_bytes()).hexdigest()
        wum, tr = np.loadtxt(raw, comments='#', usecols=(0, 1), unpack=True)
        srt = np.argsort(wum)
        wum, tr = wum[srt], tr[srt]
        scale = 0.01 if tr.max() > 1.5 else 1.0          # percent or fraction
        tr = tr * scale
        nneg = int(np.sum(tr < 0))
        tr = np.clip(tr, 0.0, None)
        wave = airtovac(wum * 1e4 * u.AA).to(u.AA).value
        lo, hi, peak = half_power(wave, tr)
        ab_vega = float(source.vega_offset(vw, vf, wave, tr))
        t = Table([wave, tr], names=('wave_A', 'transmission'))
        t['wave_A'].unit = u.AA
        t['wave_A'].format, t['transmission'].format = '.3f', '.6f'
        t.meta = {
            'description': f'MOSFIRE {band} filter transmission (design 5.4)',
            'instrument': 'keck_mosfire', 'band': band,
            'source_url': url, 'source_page': PAGE, 'downloaded': downloaded, 'source_sha256': sha,
            'source_columns': 'wavelength [um], transmission',
            'transmission_scale': scale,
            'waveref': 'vacuum',
            'waveref_source': 'not stated by Keck; taken as air (laboratory spectrophotometer scans) and '
                              'converted to vacuum with pypeit.core.wave.airtovac',
            'negative_samples_clipped': nneg,
            'smoothing_for_half_power': f'{SMOOTH}-sample running median',
            'peak_transmission': round(peak, 4),
            'half_power_A': [round(lo, 1), round(hi, 1)],
            'center_um': round((lo + hi) / 2e4, 4), 'fwhm_um': round((hi - lo) / 1e4, 4),
            'published_center_um': c_pub, 'published_fwhm_um': w_pub,
            'ab_minus_vega': round(ab_vega, 4),
            'vega_spectrum': 'pypeit/data/standards/vega_tspectool_vacuum.dat', 'vega_sha256': vsha,
            'ab_definition': 'energy-weighted <f_nu> (design 5.3.1, keck_etcs.core.source.ab_mag)',
            'notes': ('Keck *_center_corr file: curve at the centre of the field' if 'center_corr' in fname
                      else 'Keck order-sorting (broad-band) filter'),
            'calib_version': CALIB_VERSION, 'keck_etcs_version': keck_etcs.__version__,
            'created': now, 'script': 'scripts/mosfire/fetch_keck_filter_curves.py',
        }
        out = OUTDIR / f'mosfire_{band}.ecsv'
        t.write(out, format='ascii.ecsv', overwrite=True)
        entries[f'mosfire/filters/{out.name}'] = {
            'calib_version': CALIB_VERSION, 'created': now,
            'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
            'script': 'scripts/mosfire/fetch_keck_filter_curves.py',
            'waveref': 'vacuum (converted from assumed air)',
            'provenance': f'Keck MOSFIRE filters page {url} (downloaded {downloaded[:10]}, sha256 {sha[:12]}); '
                          f'AB-Vega {ab_vega:.3f} from PypeIt vega_tspectool_vacuum.dat'}
        print(f'{band:4s} {fname:20s} {len(t):5d} {nneg:4d} {peak:6.3f} {lo / 1e4:10.4f}-{hi / 1e4:.4f} '
              f'{(lo + hi) / 2e4:7.4f} {(hi - lo) / 1e4:6.4f} {c_pub:6.3f}/{w_pub:.3f} {ab_vega:8.4f}')
    update_index(entries)
    print(f'wrote {len(entries)} curves to {OUTDIR.relative_to(REPO)}; index.yaml updated')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--offline', action='store_true', help='re-read the raw copies instead of downloading')
    sys.exit(main(p.parse_args().offline))
