#!/usr/bin/env python
"""Build ``keck_etcs/data/sky/gemini_mk_sky_grid.fits`` from the Gemini Maunakea grids.

Usage:
    conda run -n pypeit14b python scripts/mosfire/build_gemini_sky_grid.py [XTCALC_DIR]

XTCALC_DIR defaults to ``keck_etcs.paths.xtcalc_dir()``.

Reads the 24 IDL save files in ``XTCALC_DIR/Mauna_Kea_sky/``:
``mk_skybg_zm_WW_AA_ph.sav`` (sky background, ``lam`` in nm, ``mksky`` in
photons/s/arcsec^2/nm/m^2) and ``mktrans_zm_WW_AA.sav`` (``tran_lam`` in
micron, ``trans``), for PWV WW/10 mm in {1.0, 1.6, 3.0, 5.0} and airmass
AA/10 in {1.0, 1.5, 2.0}. The native sampling is 0.02 nm from 900 nm; the
files store the wavelengths as float32, so the exact grid ``900 + 0.02 i`` is
rebuilt in float64 (and checked against the stored values).

Each spectrum is treated as piecewise constant over native pixels of width
0.02 nm and rebinned, conserving the integral, onto 30000 pixels of 0.05 nm
whose edges run from 950 to 2450 nm (``WAVE`` holds the pixel centres,
950.025 ... 2449.975 nm). Transmission is rebinned the same way (the mean
over each output pixel).

The vacuum/air convention (design decision N5) is tested by
``check_gemini_wavelength_convention.py`` on every build; its verdict goes to
the ``WAVEREF`` and ``WAVEOFF`` header cards, and an air grid would be
converted to vacuum before rebinning.

Output HDUs: ``WAVE`` (nm, vacuum), ``SKYBG`` (12 x 30000), ``TRANS``
(12 x 30000), ``GRID`` (``airmass``, ``pwv_mm``, source file names), and the
file is registered in ``keck_etcs/data/index.yaml``. The script then runs the
S3 verifications (integral conservation over 1.17-1.33 um, the J-band
transmission at PWV 1.6 mm, airmass 1.0, and the file size) and exits
non-zero if any fails.

The J-band transmission check: the native median is 0.9976 (as reported by
``inspect_xtcalc_files.py``), but the median is not preserved by averaging.
Unresolved absorption lines mixed into 0.05 nm pixels lower the typical
pixel, so the rebinned median is 0.9972 (a 3-pixel boxcar of the native
grid gives the same). The check therefore requires the native median to be
0.9976 and the rebinned mean over the J window to equal the native mean,
and it reports the rebinned median.
"""
import datetime
import hashlib
import os
import re
import sys
from pathlib import Path

import numpy as np
import yaml
from astropy.io import fits
from astropy.table import Table
import astropy.units as u
from scipy.io import readsav

REPO = Path(__file__).resolve().parents[2]
# Allow running from a checkout without ``pip install -e .``
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import keck_etcs  # noqa: E402
from keck_etcs import paths  # noqa: E402
from check_gemini_wavelength_convention import check as check_waveref  # noqa: E402

OUTFILE = REPO / 'keck_etcs' / 'data' / 'sky' / 'gemini_mk_sky_grid.fits'
INDEX = REPO / 'keck_etcs' / 'data' / 'index.yaml'
SCRIPT = 'scripts/mosfire/build_gemini_sky_grid.py'
CALIB_VERSION = 'mosfire-J-2026.10-dev'
SOURCE = ('Gemini Observatory IR sky background and ATRAN transmission, '
          'as redistributed in Keck XTcalc v2.3')
XTCALC_URL = 'https://www2.keck.hawaii.edu/inst/mosfire/XTcalc.tar'

NATIVE_START, NATIVE_STEP = 900.0, 0.02     # nm
OUT_START, OUT_STEP, OUT_N = 950.0, 0.05, 30000
PWV = (10, 16, 30, 50)                      # WW, PWV = WW/10 mm
AIRMASS = (10, 15, 20)                      # AA, airmass = AA/10

# Verification targets
INTEG_WINDOW = (1170.0, 1330.0)             # nm
INTEG_TOL = 1e-3
JBAND = (1170.0, 1350.0)                    # nm, as in inspect_xtcalc_files.py
JMED_REF, JMED_TOL = 0.9976, 5e-5           # native median, PWV 1.6 mm, airmass 1.0
JMEAN_TOL = 1e-4                            # rebinned vs native mean, relative
MAX_BYTES = 5 * 1024**2


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def native_grid(stored, label):
    """Exact float64 native grid, checked against the stored float32 values (nm).

    The stored values deviate by up to ~1.2e-3 nm above 4096 nm (float32
    rounding) and by <1e-4 nm below 2450 nm; the tolerance is 10% of a pixel.
    """
    lam = NATIVE_START + NATIVE_STEP * np.arange(stored.size)
    dev = np.max(np.abs(lam - stored))
    if dev > 0.1 * NATIVE_STEP:
        raise ValueError(f'{label}: stored wavelengths deviate from 900+0.02i by {dev:.2e} nm')
    return lam


def rebin(lam, flux, edges):
    """Flux-conserving rebin of piecewise-constant pixels centred on ``lam``.

    Returns the mean of ``flux`` over each output pixel [edges[k], edges[k+1]].
    """
    step = np.median(np.diff(lam))
    nat_edges = np.concatenate([lam - step / 2, [lam[-1] + step / 2]])
    cum = np.concatenate([[0.0], np.cumsum(flux * np.diff(nat_edges))])
    if edges[0] < nat_edges[0] or edges[-1] > nat_edges[-1]:
        raise ValueError('output grid extends beyond the native grid')
    # The cumulative integral is exactly piecewise linear between native edges
    c = np.interp(edges, nat_edges, cum)
    return np.diff(c) / np.diff(edges)


def read_grid(xtdir, ww, aa, waveref):
    skydir = Path(xtdir) / 'Mauna_Kea_sky'
    skyfile = f'mk_skybg_zm_{ww}_{aa}_ph.sav'
    trfile = f'mktrans_zm_{ww}_{aa}.sav'
    s = readsav(skydir / skyfile)
    t = readsav(skydir / trfile)
    lam_s = native_grid(np.asarray(s['lam'], dtype=float), skyfile)
    # Transmission wavelengths are in micron
    lam_t = native_grid(np.asarray(t['tran_lam'], dtype=float) * 1e3, trfile)
    if lam_s.size != lam_t.size:
        raise ValueError(f'{skyfile} and {trfile} have different lengths')
    if waveref == 'air':
        from pypeit.core.wave import airtovac
        lam_s = airtovac(lam_s * u.nm).to(u.nm).value
        lam_t = airtovac(lam_t * u.nm).to(u.nm).value
    return (skyfile, trfile, lam_s, np.asarray(s['mksky'], dtype=float),
            lam_t, np.asarray(t['trans'], dtype=float))


def update_index(entry_key, entry):
    index = {}
    if INDEX.exists():
        index = yaml.safe_load(INDEX.read_text()) or {}
    index.setdefault('files', {})[entry_key] = entry
    header = ('# Registry of the data products shipped in keck_etcs/data/ (design 5.4).\n'
              '# Keys are paths relative to keck_etcs/data/. Entries are written by the\n'
              '# build scripts named in each entry; do not edit them by hand.\n')
    INDEX.write_text(header + yaml.safe_dump(index, sort_keys=False, width=100))


def main(xtdir):
    xtdir = Path(xtdir)
    print(f'XTcalc directory: {xtdir}')

    wv = check_waveref(str(xtdir))
    waveref, waveoff = wv['waveref'], wv['median_offset_A']
    if not wv['consistent']:
        print('ERROR: the vacuum/air test is not conclusive; not building.')
        return 1
    print(f'\nN5 test: grids are in {waveref}, median OH offset {waveoff:+.3f} A\n')

    edges = OUT_START + OUT_STEP * np.arange(OUT_N + 1)
    wave = 0.5 * (edges[:-1] + edges[1:])

    rows, skybg, trans, checks = [], [], [], []
    for ww in PWV:
        for aa in AIRMASS:
            skyfile, trfile, lam_s, sky, lam_t, tr = read_grid(xtdir, ww, aa, waveref)
            sky_r = rebin(lam_s, sky, edges)
            tr_r = rebin(lam_t, tr, edges)
            skybg.append(sky_r)
            trans.append(tr_r)
            rows.append((aa / 10, ww / 10, skyfile, trfile))

            # Integral over 1.17-1.33 um: native (trapezoid on the samples)
            # vs rebinned (sum over output pixels; the window falls on edges)
            nat = (lam_s >= INTEG_WINDOW[0]) & (lam_s <= INTEG_WINDOW[1])
            i_nat = np.trapezoid(sky[nat], lam_s[nat])
            out = (edges[:-1] >= INTEG_WINDOW[0] - 1e-9) & (edges[1:] <= INTEG_WINDOW[1] + 1e-9)
            i_out = np.sum(sky_r[out] * OUT_STEP)
            checks.append((ww, aa, i_nat, i_out, i_out / i_nat - 1))
            if (ww, aa) == (16, 10):
                # Native median over the window, and the native mean over the
                # native pixels that tile the same span as the output pixels
                nj = (lam_t > JBAND[0]) & (lam_t < JBAND[1])
                nin = ((lam_t - NATIVE_STEP / 2 >= JBAND[0] - 1e-9)
                       & (lam_t + NATIVE_STEP / 2 <= JBAND[1] + 1e-9))
                jnat = {'median': float(np.median(tr[nj])), 'mean': float(np.mean(tr[nin]))}

    skybg = np.array(skybg, dtype=np.float32)
    trans = np.array(trans, dtype=np.float32)
    grid = Table(rows=rows, names=('airmass', 'pwv_mm', 'skyfile', 'transfile'),
                 dtype=(np.float32, np.float32, 'U32', 'U32'))

    tar = xtdir.parent / 'XTcalc.tar'
    tarsha = sha256sum(tar) if tar.exists() else 'unknown'
    created = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

    prim = fits.PrimaryHDU()
    h = prim.header
    h['SOURCE'] = (SOURCE, 'origin of the grids')
    h['SRCURL'] = (XTCALC_URL, 'Keck XTcalc tarball')
    h['SRCSHA'] = (tarsha, 'sha256 of XTcalc.tar')
    h['REBIN'] = ('flux-conserving', f'{NATIVE_STEP} nm native -> {OUT_STEP} nm')
    h['WAVEREF'] = (waveref, 'wavelength convention (design N5)')
    h['WAVEOFF'] = (round(waveoff, 4), '[A] median OH offset from PypeIt vacuum list')
    h['SCRIPT'] = (SCRIPT, 'build script')
    h['CREATED'] = (created, 'UTC')
    h['KETCSVER'] = (keck_etcs.__version__, 'keck_etcs version')
    h['CALIBVER'] = (CALIB_VERSION, 'calib_version in index.yaml')
    h['NGRID'] = (len(rows), 'number of (airmass, PWV) grid points')

    hwave = fits.ImageHDU(wave, name='WAVE')
    hwave.header['BUNIT'] = 'nm'
    hwave.header['WAVEREF'] = waveref
    hwave.header['COMMENT'] = f'Pixel centres; pixel edges {OUT_START}-{OUT_START + OUT_STEP * OUT_N} nm'
    hsky = fits.ImageHDU(skybg, name='SKYBG')
    hsky.header['BUNIT'] = 'photon / (s arcsec2 nm m2)'
    htr = fits.ImageHDU(trans, name='TRANS')
    htr.header['BUNIT'] = ''
    hgrid = fits.BinTableHDU(grid, name='GRID')

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    fits.HDUList([prim, hwave, hsky, htr, hgrid]).writeto(OUTFILE, overwrite=True, checksum=True)
    size = OUTFILE.stat().st_size
    digest = sha256sum(OUTFILE)
    print(f'Wrote {OUTFILE.relative_to(REPO)}: {size} bytes ({size / 1024**2:.2f} MiB), '
          f'sha256 {digest}')

    update_index('sky/gemini_mk_sky_grid.fits', {
        'calib_version': CALIB_VERSION,
        'created': created,
        'sha256': digest,
        'script': SCRIPT,
        'waveref': waveref,
        'provenance': f'{SOURCE}; {len(rows)} (airmass, PWV) grids, flux-conserving rebin '
                      f'to {OUT_STEP} nm over {OUT_START:.0f}-{OUT_START + OUT_STEP * OUT_N:.0f} nm',
    })
    print(f'Registered in {INDEX.relative_to(REPO)} (calib_version {CALIB_VERSION})')

    # ---- Verification
    ok = True
    print(f'\nIntegral of SKYBG over {INTEG_WINDOW[0]:.0f}-{INTEG_WINDOW[1]:.0f} nm, '
          f'rebinned vs native (tolerance {INTEG_TOL:g}):')
    for ww, aa, i_nat, i_out, rel in checks:
        flag = 'ok' if abs(rel) < INTEG_TOL else 'FAIL'
        ok &= flag == 'ok'
        print(f'  PWV {ww / 10:.1f} mm, airmass {aa / 10:.1f}: native {i_nat:.6e}, '
              f'rebinned {i_out:.6e}, rel {rel:+.2e}  {flag}')

    with fits.open(OUTFILE) as hdul:
        g = Table(hdul['GRID'].data)
        irow = int(np.where(np.isclose(g['pwv_mm'], 1.6) & np.isclose(g['airmass'], 1.0))[0][0])
        w = hdul['WAVE'].data
        inj = (w > JBAND[0]) & (w < JBAND[1])
        tj = hdul['TRANS'].data[irow][inj].astype(float)
    jmed, jmean = float(np.median(tj)), float(np.mean(tj))
    med_ok = abs(jnat['median'] - JMED_REF) < JMED_TOL
    rel = jmean / jnat['mean'] - 1
    mean_ok = abs(rel) < JMEAN_TOL
    ok &= med_ok and mean_ok
    print(f'J-band ({JBAND[0]:.0f}-{JBAND[1]:.0f} nm) TRANS, PWV 1.6 mm, airmass 1.0:')
    print(f'  native median {jnat["median"]:.4f} (expected {JMED_REF})  {"ok" if med_ok else "FAIL"}')
    print(f'  rebinned mean {jmean:.6f} vs native {jnat["mean"]:.6f}, rel {rel:+.1e}  '
          f'{"ok" if mean_ok else "FAIL"}')
    print(f'  rebinned median {jmed:.4f} (informational; averaging lowers the median)')
    sok = size < MAX_BYTES
    ok &= sok
    print(f'File size {size / 1024**2:.2f} MiB < 5 MiB  {"ok" if sok else "FAIL"}')
    print('\nAll verifications passed.' if ok else '\nSOME VERIFICATIONS FAILED.')
    return 0 if ok else 1


if __name__ == '__main__':
    xtdir = sys.argv[1] if len(sys.argv) > 1 else str(paths.xtcalc_dir())
    sys.exit(main(xtdir))
