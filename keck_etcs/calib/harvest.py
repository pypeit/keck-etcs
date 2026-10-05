"""Harvest a PypeIt sensitivity function into a per-standard row and throughput curve (design 4.4, D34).

The row has the columns of design 4.4 (:data:`ROW_COLUMNS`). The curve is
the end-to-end throughput on a common 1 A vacuum grid (:data:`GRID_START`,
1 A steps), with the filter divided out when a filter curve is supplied.
Both carry the provenance ``meta`` of design 5.4. The functions here read
files but do no plotting. :func:`harvest` returns plain Python and astropy
objects, so the night job (``scripts/mosfire/harvest_sens.py harvest``) and
a local re-harvest of the same files give the same row.

Inputs for one standard on one night:

- the coadded ``sens_<standard>_<date>.fits`` (``build_sensfunc.py``);
- the night's ``run_manifest.json`` (``reduce_standard.py``): frame
  table, objects (FWHM), filter, the six reduction-provenance fields and the
  PypeIt version;
- the night's ``raw/manifest.ecsv`` (KOA IDs, ``SAMPMODE``, ``NUMREADS``,
  MJD) when present, else the raw FITS headers.

Conventions:

- ``zp_*``: the zero point (AB mag for 1 e-/s/A) of PypeIt's fit at that
  wavelength, masked where the fit does not reach. J2 ends at 1.260 um, so
  ``zp_1300`` is masked for J2.
- ``thru_median_1117_1260``: the median ``thru_raw`` over 1.117-1.260 um
  (design 4.4). ``thru_median_1117_1250`` is the same over the window that
  S5 found free of red-edge artefacts.
- ``pwv_fit``: PypeIt's PCA telluric model fits no PWV, so this is the PWV
  at which the Gemini ATRAN grid (``keck_etcs/data/sky/gemini_mk_sky_grid.fits``),
  interpolated per design N4 to the sensfunc's airmass and smoothed to the
  fitted resolution, best matches PypeIt's fitted transmission
  (:func:`estimate_pwv`).
- ``seeing_fwhm_pix``: the median PypeIt spatial FWHM of the standard's
  extracted objects.
- ``flag``: comma-separated; ``ok`` if empty. ``nofilter`` when no filter
  curve was divided out (``thru`` is then masked).
"""
import datetime
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import MaskedColumn, Table
from scipy.ndimage import gaussian_filter1d

EFF_APERTURE = 72.3674           # m^2, Keck (decision N1)
GRID_START = 9000.0              # A; the common 1 A vacuum grid is GRID_START + k
ZP_WAVES = {'zp_1200': 12000.0, 'zp_1250': 12500.0, 'zp_1300': 13000.0}
MEDIAN_WINDOWS = {'thru_median_1117_1260': (11170.0, 12600.0),
                  'thru_median_1117_1250': (11170.0, 12500.0)}
PWV_SEARCH = (0.5, 10.0)         # mm
SKYGRID = Path(__file__).resolve().parents[1] / 'data' / 'sky' / 'gemini_mk_sky_grid.fits'

ROW_COLUMNS = ('date', 'mjd', 'koa_id', 'standard', 'std_class', 'std_model', 'filter',
               'slit_width', 'slit_length', 'sampmode', 'numreads', 'exptime', 'airmass',
               'pwv_fit', 'seeing_fwhm_pix', 'zp_1200', 'zp_1250', 'zp_1300',
               'thru_median_1117_1260', 'thru_median_1117_1250', 'thru_curve_file',
               'pypeit_version', 'keck_etcs_version', 'image', 'image_digest', 'pypeit_git_sha',
               'keck_etcs_git_sha', 'job_name', 's3_prefix', 'flag')
UNITS = {'mjd': 'd', 'slit_width': 'arcsec', 'exptime': 's', 'pwv_fit': 'mm',
         'seeing_fwhm_pix': 'pix', 'zp_1200': 'mag', 'zp_1250': 'mag', 'zp_1300': 'mag'}
PROVENANCE = ('image', 'image_digest', 'pypeit_git_sha', 'keck_etcs_git_sha', 'job_name', 's3_prefix')


def sha256sum(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ throughput

def zeropoint_to_throughput(wave, zeropoint):
    """End-to-end throughput from the zero point (PypeIt's formula, Keck aperture)."""
    from pypeit.core.flux_calib import zeropoint_to_throughput as z2t
    return z2t(np.asarray(wave, float), np.asarray(zeropoint, float), EFF_APERTURE)


def throughput_curve(wave, zeropoint, filter_wave=None, filter_trans=None):
    """Zero point and throughput on the common 1 A grid over the covered range.

    Args:
        wave, zeropoint (array): PypeIt's fit (``SensFunc.wave``,
            ``SensFunc.zeropoint``); non-positive or non-finite values are
            excluded.
        filter_wave, filter_trans (array, optional): filter curve (A, 0-1).

    Returns:
        `astropy.table.Table`: ``wave`` (A, vacuum), ``zeropoint``,
        ``thru_raw`` (including the filter), ``filter_trans`` and ``thru``
        (filter divided out); the last two masked without a filter curve.
    """
    wave = np.asarray(wave, float).ravel()
    zp = np.asarray(zeropoint, float).ravel()
    good = (wave > 0) & np.isfinite(zp) & (zp > 0)
    wave, zp = wave[good], zp[good]
    k0 = int(np.ceil(wave.min() - GRID_START))
    k1 = int(np.floor(wave.max() - GRID_START))
    grid = GRID_START + np.arange(k0, k1 + 1, dtype=float)
    zp_g = np.interp(grid, wave, zp)
    thru_raw = zeropoint_to_throughput(grid, zp_g)
    tbl = Table()
    tbl['wave'] = grid
    tbl['wave'].unit = 'Angstrom'
    tbl['zeropoint'] = zp_g
    tbl['zeropoint'].unit = 'mag'
    tbl['thru_raw'] = thru_raw
    if filter_wave is not None:
        ft = np.interp(grid, np.asarray(filter_wave, float), np.asarray(filter_trans, float),
                       left=0.0, right=0.0)
        ok = ft > 0.05
        tbl['filter_trans'] = MaskedColumn(ft, mask=~ok)
        tbl['thru'] = MaskedColumn(np.where(ok, thru_raw / np.where(ok, ft, 1.0), np.nan), mask=~ok)
    else:
        tbl['filter_trans'] = MaskedColumn(np.full(grid.size, np.nan), mask=np.ones(grid.size, bool))
        tbl['thru'] = MaskedColumn(np.full(grid.size, np.nan), mask=np.ones(grid.size, bool))
    return tbl


def zp_at(curve, w):
    """Zero point at wavelength ``w`` (A), or None outside the curve."""
    if w < curve['wave'][0] or w > curve['wave'][-1]:
        return None
    return float(np.interp(w, curve['wave'], curve['zeropoint']))


def median_in(curve, lo, hi, col='thru_raw'):
    sel = (curve['wave'] >= lo) & (curve['wave'] <= hi)
    return float(np.median(np.asarray(curve[col])[sel])) if sel.any() else None


# ------------------------------------------------------------------ PWV

def gemini_trans(airmass, pwv, skygrid=SKYGRID):
    """Gemini transmission at (airmass, pwv), linear in airmass and in log PWV (design N4)."""
    with fits.open(skygrid) as h:
        wave_nm = h['WAVE'].data.astype(float)
        trans = h['TRANS'].data.astype(float)
        grid = h['GRID'].data
    am, pw = np.asarray(grid['airmass'], float), np.asarray(grid['pwv_mm'], float)
    ams, pws = np.unique(am), np.unique(pw)
    a = np.clip(airmass, ams[0], ams[-1])
    ia = int(np.clip(np.searchsorted(ams, a) - 1, 0, len(ams) - 2))
    fa = (a - ams[ia]) / (ams[ia + 1] - ams[ia])
    lp, lpw = np.log(pwv), np.log(pws)
    ip = int(np.clip(np.searchsorted(lpw, lp) - 1, 0, len(pws) - 2))
    fp = (lp - lpw[ip]) / (lpw[ip + 1] - lpw[ip])       # extrapolates outside the grid

    def row(aa, pp):
        return trans[np.where(np.isclose(am, aa) & np.isclose(pw, pp))[0][0]]
    t = ((1 - fa) * ((1 - fp) * row(ams[ia], pws[ip]) + fp * row(ams[ia], pws[ip + 1]))
         + fa * ((1 - fp) * row(ams[ia + 1], pws[ip]) + fp * row(ams[ia + 1], pws[ip + 1])))
    return wave_nm * 10.0, np.clip(t, 0, 1)


def estimate_pwv(tell_wave, tell_trans, resolution, airmass, window=(11170.0, 12600.0),
                 skygrid=SKYGRID):
    """PWV (mm) at which the Gemini grid best matches a fitted telluric transmission.

    Returns a dict: ``pwv_mm``, ``rms_resid``, ``extrapolated`` (outside the
    grid's 1-5 mm), ``at_search_edge``.
    """
    w = np.asarray(tell_wave, float)
    tell = np.asarray(tell_trans, float)
    sel = (w >= window[0]) & (w <= window[1]) & np.isfinite(tell) & (tell > 0)
    w, tell = w[sel], tell[sel]
    pwvs = np.exp(np.linspace(np.log(PWV_SEARCH[0]), np.log(PWV_SEARCH[1]), 121))
    chi2 = []
    for p in pwvs:
        gw, gt = gemini_trans(airmass, p, skygrid)
        k = (gw > w.min() - 50) & (gw < w.max() + 50)
        gw, gt = gw[k], gt[k]
        sigma_pix = (np.median(w) / resolution) / 2.3548 / np.median(np.diff(gw))
        chi2.append(np.sum((np.interp(w, gw, gaussian_filter1d(gt, sigma_pix)) - tell) ** 2))
    chi2 = np.array(chi2)
    i = int(np.argmin(chi2))
    return {'pwv_mm': float(pwvs[i]), 'rms_resid': float(np.sqrt(chi2[i] / len(w))),
            'extrapolated': bool(pwvs[i] < 1.0 or pwvs[i] > 5.0),
            'at_search_edge': bool(i in (0, len(pwvs) - 1))}


# ------------------------------------------------------------------ inputs

def read_sensfunc(path):
    """The parts of a PypeIt ``SensFunc`` file the harvest needs, tolerant of layout changes."""
    from pypeit.sensfunc import SensFunc
    sf = SensFunc.from_file(str(path), chk_version=False)
    out = {'wave': np.asarray(sf.wave, float).ravel(),
           'zeropoint': np.asarray(sf.zeropoint, float).ravel(),
           'std_name': sf.std_name, 'std_cal': sf.std_cal, 'airmass': float(sf.airmass),
           'exptime': float(sf.exptime), 'spec1df': sf.spec1df, 'algorithm': sf.algorithm,
           'telluric': None}
    tel = getattr(sf, 'telluric', None)
    model = getattr(tel, 'model', None) if tel is not None else None
    if model is not None and 'TELLURIC' in model.colnames:
        get = lambda c: model[c][0] if c in model.colnames else None
        out['telluric'] = {
            'grid': getattr(tel, 'telgrid', None), 'teltype': getattr(tel, 'teltype', None),
            'npca': getattr(tel, 'tell_npca', None),
            'wave': np.asarray(get('WAVE'), float), 'trans': np.asarray(get('TELLURIC'), float),
            'resolution': None if get('TELL_RESLN') is None else float(get('TELL_RESLN')),
            'chi2': None if get('CHI2') is None else float(get('CHI2')),
            'success': None if get('SUCCESS') is None else bool(get('SUCCESS'))}
    return out


def standard_frames(manifest, standard=None):
    """Frame-table rows of the standard (``frametype`` contains ``standard``)."""
    rows = [f for f in manifest['frames'] if 'standard' in f['frametype']]
    if standard is not None:
        named = [f for f in rows if str(f['target']).replace(' ', '').upper()
                 in standard.replace(' ', '').upper()]
        rows = named or rows
    return rows


def raw_info(raw_dir, filenames):
    """KOA ID, SAMPMODE, NUMREADS and MJD per file: ``raw_dir/manifest.ecsv``, else the headers."""
    raw_dir = Path(raw_dir)
    man = raw_dir / 'manifest.ecsv'
    info = {}
    if man.exists():
        t = Table.read(man, format='ascii.ecsv')
        for r in t:
            if r['file'] in filenames:
                info[r['file']] = {'koaid': str(r['koaid']), 'sampmode': int(r['sampmode']),
                                   'numreads': int(r['numreads']), 'mjd': float(r['mjd'])}
    for fn in filenames:
        if fn in info:
            continue
        h = fits.getheader(raw_dir / fn)
        info[fn] = {'koaid': str(h.get('KOAID', fn.replace('.fits', ''))),
                    'sampmode': int(h['SAMPMODE']), 'numreads': int(h['NUMREADS']),
                    'mjd': float(h['MJD-OBS'])}
    return info


def slit_from_decker(decker):
    """(width arcsec, length in CSU bars) from a MOSFIRE long-slit mask name, e.g. LONGSLIT-46x5."""
    try:
        length, width = str(decker).split('-', 1)[1].split('(')[0].split('x')
        return float(width), float(length)
    except (IndexError, ValueError):
        return None, None


def std_class_of(std_cal, model=None):
    """Class of the standard behind a sensfunc.

    ``A0V`` when ``build_sensfunc.py`` used the J-scaled Vega model (its
    ``<NAME>_<DATE>_std_model.json`` record is passed as ``model``; PypeIt
    records ``std_cal = None`` for model standards) or ``std_cal`` names a Vega
    spectrum; ``WD`` for an archive file (the CALSPEC NIR standards used are
    white dwarfs); ``unknown`` when there is neither.
    """
    if model is not None or 'vega' in str(std_cal).lower():
        return 'A0V'
    if std_cal is None or str(std_cal) in ('', 'None'):
        return 'unknown'
    return 'WD'


def std_model_record(sens_path, standard, night):
    """The A0V model record written by ``build_sensfunc.py`` next to the sensfunc, or None."""
    p = Path(sens_path).parent / f'{standard}_{night}_std_model.json'
    return json.loads(p.read_text()) if p.exists() else None


# ------------------------------------------------------------------ harvest

def harvest(sens_path, run_manifest_path, standard=None, filter_curve=None, curve_dir='standards',
            raw_dir=None):
    """Harvest one standard's sensfunc.

    Args:
        sens_path (str or Path): the night's coadded ``sens_<standard>_<date>.fits``.
        run_manifest_path (str or Path): the night's ``run_manifest.json``.
            Its directory is the night directory, holding ``raw/``.
        standard (str, optional): name used in file names (default: the
            sensfunc's ``std_name``).
        filter_curve (tuple, optional): ``(wave_A, trans)`` to divide out.
        curve_dir (str): directory of the curve, relative to the
            ``standards.ecsv`` table, for ``thru_curve_file``.
        raw_dir (str or Path, optional): the night's raw directory (default
            ``<night>/raw``, the manifest's directory + ``raw``).

    Returns:
        tuple: ``(row, curve)``. ``row`` is a dict with :data:`ROW_COLUMNS`
        (None for a masked value); ``curve`` is an `astropy.table.Table` with
        design 5.4 ``meta``.
    """
    import keck_etcs
    sens_path, run_manifest_path = Path(sens_path), Path(run_manifest_path)
    m = json.loads(run_manifest_path.read_text())
    night_dir = run_manifest_path.parent
    sf = read_sensfunc(sens_path)
    standard = standard or sf['std_name']
    frames = standard_frames(m, standard)
    files = [f['filename'] for f in frames]
    raw = raw_info(raw_dir or night_dir / 'raw', files)
    night = str(m['night'])
    date_iso = f'{night[:4]}-{night[4:6]}-{night[6:]}'

    fwave, ftrans = (filter_curve if filter_curve is not None else (None, None))
    curve = throughput_curve(sf['wave'], sf['zeropoint'], fwave, ftrans)
    flags = [] if filter_curve is not None else ['nofilter']

    pwv = None
    if sf['telluric'] is not None and sf['telluric']['resolution']:
        pwv = estimate_pwv(sf['telluric']['wave'], sf['telluric']['trans'],
                           sf['telluric']['resolution'], sf['airmass'])
        if pwv['extrapolated'] or pwv['at_search_edge']:
            flags.append('pwv_extrapolated')
    fwhm = [o['fwhm_pix'] for o in m.get('objects', [])
            if o['frame'] in files and o.get('fwhm_pix') is not None]
    width, length = slit_from_decker(frames[0]['decker']) if frames else (None, None)
    uniq = lambda k: sorted({raw[f][k] for f in files})
    one = lambda vals: vals[0] if len(vals) == 1 else None

    model = std_model_record(sens_path, standard, night)
    curve_file = f'{curve_dir}/{standard}_{night}.ecsv'
    row = {
        'date': date_iso,
        'mjd': float(np.mean([raw[f]['mjd'] for f in files])) if files else None,
        'koa_id': '+'.join(raw[f]['koaid'] for f in files),
        'standard': standard,
        'std_class': std_class_of(sf['std_cal'], model),
        'std_model': (f"vega_tspectool_vacuum.dat J={model['j_2mass']} (V_eq {model['v_equivalent']})"
                      if model is not None else str(sf['std_cal'])),
        'filter': m.get('filter'),
        'slit_width': width, 'slit_length': length,
        'sampmode': one(uniq('sampmode')) if files else None,
        'numreads': one(uniq('numreads')) if files else None,
        'exptime': sf['exptime'],
        'airmass': sf['airmass'],
        'pwv_fit': None if pwv is None else pwv['pwv_mm'],
        'seeing_fwhm_pix': float(np.median(fwhm)) if fwhm else None,
        **{k: zp_at(curve, w) for k, w in ZP_WAVES.items()},
        **{k: median_in(curve, *w) for k, w in MEDIAN_WINDOWS.items()},
        'thru_curve_file': curve_file,
        'pypeit_version': m.get('pypeit_version'),
        'keck_etcs_version': m.get('keck_etcs_version'),
        **{k: m.get(k) for k in PROVENANCE},
        'flag': ','.join(flags) or 'ok',
    }
    if any(row[k] in (None, 'unknown') for k in ('pypeit_git_sha', 'keck_etcs_git_sha')):
        from keck_etcs import provenance
        shas = provenance.git_shas()
        row['pypeit_git_sha'] = row['pypeit_git_sha'] or shas['pypeit']
        row['keck_etcs_git_sha'] = row['keck_etcs_git_sha'] or shas['keck_etcs']

    curve.meta.update({
        'instrument': m.get('instrument', 'keck_mosfire'), 'band': m.get('filter'), 'era': None,
        'standards': [{'name': standard, 'date': date_iso, 'koa_id': row['koa_id']}],
        'row': {k: row[k] for k in ROW_COLUMNS},
        'pypeit_version': row['pypeit_version'], 'keck_etcs_version': row['keck_etcs_version'],
        'harvest_keck_etcs_version': keck_etcs.__version__,
        **{k: row[k] for k in PROVENANCE},
        'pypeit_pin': m.get('pypeit_pin'), 'pin_check_pass': (m.get('pin_check') or {}).get('pass'),
        'sens_file': sens_path.name, 'sens_sha256': sha256sum(sens_path),
        'run_manifest_sha256': sha256sum(run_manifest_path),
        'telluric': None if sf['telluric'] is None else {
            k: sf['telluric'][k] for k in ('grid', 'teltype', 'npca', 'resolution', 'chi2', 'success')},
        'pwv_method': 'Gemini ATRAN grid matched to the PypeIt telluric model (keck_etcs.calib.harvest.estimate_pwv)',
        'pwv_detail': pwv,
        'eff_aperture_m2': EFF_APERTURE, 'grid': f'{GRID_START:.0f} + k A, 1 A steps, vacuum',
        'filter_divided': filter_curve is not None,
        'created': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'script': 'keck_etcs.calib.harvest',
    })
    return row, curve


def row_table(rows):
    """Rows (dicts) to a table with :data:`ROW_COLUMNS`, masking None, with units."""
    cols = {}
    for c in ROW_COLUMNS:
        vals = [r.get(c) for r in rows]
        mask = [v is None for v in vals]
        sample = next((v for v in vals if v is not None), '')
        fill = 0 if isinstance(sample, (int, float, np.integer, np.floating)) and not isinstance(sample, bool) else ''
        data = [fill if v is None else v for v in vals]
        cols[c] = MaskedColumn(data, mask=mask, name=c) if any(mask) else data
    t = Table(cols, names=ROW_COLUMNS)
    for c, u in UNITS.items():
        t[c].unit = u
    return t


def write_outputs(row, curve, outdir):
    """Write ``<standard>_<date>.ecsv`` (curve) and ``<standard>_<date>_row.ecsv`` into ``outdir``."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = Path(row['thru_curve_file']).stem
    cpath = outdir / f'{stem}.ecsv'
    rpath = outdir / f'{stem}_row.ecsv'
    curve.write(cpath, format='ascii.ecsv', overwrite=True)
    rt = row_table([row])
    rt.meta.update({k: curve.meta[k] for k in ('instrument', 'band', 'standards', 'created', 'script',
                                               'harvest_keck_etcs_version', 'sens_sha256',
                                               'run_manifest_sha256')})
    rt.write(rpath, format='ascii.ecsv', overwrite=True)
    return rpath, cpath
