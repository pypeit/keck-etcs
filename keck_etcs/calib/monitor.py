"""Calibration monitor: per-night instrument and sky metrics from PypeIt products (design 4.9, D40-D47).

Instrument-agnostic; PypeIt is imported only inside functions. Each
function takes PypeIt products (spec1d, ``WaveCalib``, ``Flat``) or raw
frames plus a monitor config (:mod:`keck_etcs.calib.monitor_configs`) and
returns rows (dicts) of the long table of design 4.9.5.
:func:`monitor_night` gathers them for one reduced night. Metrics are flags,
never gates (D47).

Metrics: ``fwhm_scalar_pix``, ``fwhm_scalar_arcsec``, ``fwhmfit_pix``,
``slitloss_gt1pct`` (:func:`object_fwhm`); ``flat_rate``,
``flat_rate_per_arcsec`` (:func:`flat_rates`); ``line_fwhm_pix``,
``line_fwhm_A``, ``line_R``, ``line_fwhm_slope`` (:func:`line_widths`);
``line_flux``, ``line_flux_above``, ``line_flux_sum`` (:func:`line_fluxes`).
"""
import json
from pathlib import Path

import numpy as np
from astropy.table import Table

ROW_COLUMNS = ('night', 'mjd', 'instrument', 'metric', 'source', 'frame', 'target', 'decker',
               'slit_width', 'filter', 'wave_A', 'line_id', 'value', 'unit', 'err', 'n', 'airmass',
               'pwv_fit', 'cards', 'flag')
PROVENANCE = ('image', 'image_digest', 'pypeit_git_sha', 'keck_etcs_git_sha', 'job_name', 's3_prefix')

# S13 line-width fit (moved unchanged from scripts/mosfire/measure_lsf.py)
HALF = 8                 # fit window half-width, pixels
BLEND_FRAC = 0.10        # companion amplitude ratio that counts as a blend
BLEND_NFWHM = 1.5        # companion distance, in expected FWHMs
LSF_SLOPE_ARCSEC_PER_PIX = 0.24   # the S13 blend window used the original D25 slope
LSF_FLOOR_PIX = 2.2


def row(**kw):
    """A monitor row with every column of :data:`ROW_COLUMNS` (missing -> None)."""
    r = {c: None for c in ROW_COLUMNS}
    r.update(kw)
    return r


def slit_from_decker(decker):
    from keck_etcs.calib.harvest import slit_from_decker as s
    return s(decker)


# ------------------------------------------------------------------ slit loss (provisional)

def moffat_slit_fraction(fwhm_arcsec, slit_arcsec, beta=3.5, n=401):
    """Fraction of a centred, circular Moffat PSF passing an infinitely long slit.

    Provisional local copy of the D26 integral (design 4.9.1); replaced by
    ``keck_etcs.core.slitloss`` once S7 exists.
    """
    alpha = fwhm_arcsec / (2.0 * np.sqrt(2.0 ** (1.0 / beta) - 1.0))
    r_max = 30.0 * fwhm_arcsec
    x = np.linspace(-r_max, r_max, 4 * n + 1)
    xx, yy = np.meshgrid(x, x, indexing='ij')
    prof = (1.0 + (xx ** 2 + yy ** 2) / alpha ** 2) ** (-beta)
    inside = np.abs(xx) <= slit_arcsec / 2.0
    return float(prof[inside].sum() / prof.sum())


# ------------------------------------------------------------------ spatial FWHM (D41)

def object_fwhm(spec1d_files, frames, config, band, night):
    """FWHM rows for every extracted object of every spec1d (standards and science).

    Args:
        spec1d_files (list): spec1d paths.
        frames (dict): frame-table rows of ``run_manifest.json`` keyed by raw
            file name (``frametype``, ``target``, ``decker``, ``airmass``).
        config (dict): monitor config.
        band (str): filter (``J2``, ``J``).
        night (str): YYYYMMDD.
    """
    from pypeit.specobjs import SpecObjs
    nodes = config['fwhm_nodes'].get(band, ())
    hw = config['fwhm_halfwidth']
    ps = config['platescale']
    rows = []
    for f in spec1d_files:
        f = Path(f)
        raw = f.name.split('spec1d_', 1)[1].split('-', 1)[0] + '.fits'
        fr = frames.get(raw, {})
        width, _ = slit_from_decker(fr.get('decker'))
        sobjs = SpecObjs.from_fitsfile(str(f), chk_version=False)
        for so in sobjs:
            base = dict(night=night, instrument=config['instrument'], source='object', frame=raw,
                        target=str(fr.get('target', so['NAME'])), decker=fr.get('decker'),
                        slit_width=width, filter=band, airmass=fr.get('airmass'),
                        line_id=so['NAME'], flag='ok')
            fwhm = None if so['FWHM'] is None else float(so['FWHM'])
            rows.append(row(metric='fwhm_scalar_pix', value=fwhm, unit='pix', **base))
            rows.append(row(metric='fwhm_scalar_arcsec', value=None if fwhm is None else fwhm * ps,
                            unit='arcsec', **base))
            fit, wave = so['FWHMFIT'], so['OPT_WAVE']
            for w0 in nodes:
                val, n = None, 0
                if fit is not None and wave is not None:
                    sel = (np.abs(np.asarray(wave) - w0) <= hw) & np.isfinite(fit) & (np.asarray(fit) > 0)
                    n = int(sel.sum())
                    val = float(np.median(np.asarray(fit)[sel])) if n else None
                rows.append(row(metric='fwhmfit_pix', wave_A=w0, value=val, unit='pix', n=n, **base))
            if fwhm is not None and width is not None:
                frac = moffat_slit_fraction(fwhm * ps, width, config['moffat_beta'])
                rows.append(row(metric='slitloss_gt1pct', value=float(1.0 - frac > 0.01),
                                err=float(1.0 - frac), unit='bool',
                                **{**base, 'flag': 'slitloss=provisional'}))
    return rows


# ------------------------------------------------------------------ line widths (D44; S13 fit)

def _gauss(x, a, mu, sig, c0, c1):
    return a * np.exp(-0.5 * ((x - mu) / sig) ** 2) + c0 + c1 * (x - mu)


def read_line_list(name):
    """(wave, amplitude) of a PypeIt line list (vacuum A)."""
    from pypeit import dataPaths
    t = Table.read(dataPaths.linelist.get_file_path(name), format='ascii.fixed_width', comment='#')
    amp = t['amplitude'] if 'amplitude' in t.colnames else np.ones(len(t))
    return np.asarray(t['wave'], float), np.asarray(amp, float)


def fit_line_widths(wavecalib, slit, list_name='OH_R24000_lines.dat'):
    """Gaussian fits to the identified lines of a WaveCalib arc spectrum (the S13 algorithm).

    Returns ``(wf, lines)``: the first ``WaveFit`` and a per-line table
    (``wave, pixel, amplitude, fwhm_pix, fwhm_pix_err, dispersion, fwhm_A, R,
    blended``).
    """
    from pypeit.wavecalib import WaveCalib
    from scipy.optimize import curve_fit
    wc = WaveCalib.from_file(str(wavecalib), chk_version=False)
    wf = wc.wv_fits[0]
    spec = np.asarray(wf.spec, float)
    wsol = np.asarray(wf.wave_soln, float)
    disp = np.gradient(wsol)
    xpix = np.arange(spec.size, dtype=float)
    expected_fwhm = max(slit / LSF_SLOPE_ARCSEC_PER_PIX, LSF_FLOOR_PIX)
    ref_w, ref_a = read_line_list(list_name)
    rows = []
    for px, wv in zip(np.asarray(wf.pixel_fit, float), np.asarray(wf.wave_fit, float)):
        i0, i1 = int(round(px)) - HALF, int(round(px)) + HALF + 1
        if i0 < 0 or i1 > spec.size:
            continue
        x, y = xpix[i0:i1], spec[i0:i1]
        p0 = [y.max() - np.median(y), px, expected_fwhm / 2.3548, np.median(y), 0.0]
        try:
            p, cov = curve_fit(_gauss, x, y, p0=p0, maxfev=5000)
        except RuntimeError:
            continue
        a, mu, sig = p[0], p[1], abs(p[2])
        if a <= 0 or not np.isfinite(sig) or abs(mu - px) > 2:
            continue
        fwhm_pix = 2.3548 * sig
        d = float(np.interp(mu, xpix, disp))
        fwhm_a = fwhm_pix * abs(d)
        k = int(np.argmin(np.abs(ref_w - wv)))
        near = (np.abs(ref_w - ref_w[k]) < BLEND_NFWHM * expected_fwhm * abs(d)) & (np.arange(ref_w.size) != k)
        blended = bool(np.any(ref_a[near] >= BLEND_FRAC * ref_a[k])) or abs(ref_w[k] - wv) > 2 * abs(d)
        rows.append({'wave': float(wv), 'pixel': float(mu), 'amplitude': float(a),
                     'fwhm_pix': float(fwhm_pix),
                     'fwhm_pix_err': float(2.3548 * np.sqrt(cov[2, 2])) if np.isfinite(cov[2, 2]) else np.nan,
                     'dispersion': float(abs(d)), 'fwhm_A': float(fwhm_a),
                     'R': float(wv / fwhm_a), 'blended': blended})
    lines = Table(rows=rows)
    lines['wave'].unit = 'Angstrom'
    lines['fwhm_A'].unit = 'Angstrom'
    lines['dispersion'].unit = 'Angstrom / pix'
    return wf, lines


def width_trend(lines, ref_wave):
    """Linear fit of FWHM_pix against wavelength for clean lines, 3-sigma clipped (S13)."""
    clean = lines[~lines['blended']]
    w, f = np.asarray(clean['wave']), np.asarray(clean['fwhm_pix'])
    keep = np.ones(w.size, bool)
    s = 0.0
    for _ in range(5):
        c = np.polyfit(w[keep] - ref_wave, f[keep], 1)
        resid = f - np.polyval(c, w - ref_wave)
        s = 1.4826 * np.median(np.abs(resid[keep] - np.median(resid[keep])))
        new = np.abs(resid) < 3 * s
        if np.array_equal(new, keep):
            break
        keep = new
    return c, keep, clean, float(s)


def lsf_summary(wavecalib, slit, ref_wave=12500.0, list_name='OH_R24000_lines.dat'):
    """The S13 numbers for one WaveCalib: dict plus the per-line table."""
    wf, lines = fit_line_widths(wavecalib, slit, list_name)
    coef, keep, clean, scatter = trend_out = width_trend(lines, ref_wave)
    fwhm_ref = float(np.polyval(coef, 0.0))
    wsol = np.asarray(wf.wave_soln)
    disp_ref = float(np.interp(ref_wave, wsol, np.abs(np.gradient(wsol))))
    lines['used'] = False
    lines['used'][np.where(~lines['blended'])[0][keep]] = True
    return {'fwhm_pix': fwhm_ref, 'fwhm_A': fwhm_ref * disp_ref, 'R': ref_wave / (fwhm_ref * disp_ref),
            'dispersion': disp_ref, 'scatter_pix': scatter, 'slope_pix_per_1000A': float(coef[0]) * 1e3,
            'coef': [float(c) for c in coef], 'n_lines': int(keep.sum()), 'n_fitted': len(lines),
            'n_blended': int(lines['blended'].sum()), 'pypeit_arc_fwhm_pix': float(wf.fwhm),
            'pypeit_arc_rms_pix': float(wf.rms)}, lines


def line_widths(wavecalib_files, slit_of, config, band, night, arc_source='OH'):
    """Line-width rows per WaveCalib (D44). ``slit_of`` maps a WaveCalib path to its slit width."""
    rows = []
    ref = config['lsf_ref_wave']
    for wcf in wavecalib_files:
        slit = slit_of(wcf)
        if slit is None:
            continue
        s, _ = lsf_summary(wcf, slit, ref, config['line_lists'][arc_source])
        base = dict(night=night, instrument=config['instrument'], source=arc_source,
                    frame=f'group:{Path(wcf).stem.replace("WaveCalib_", "")}', slit_width=slit,
                    filter=band, n=s['n_lines'], flag='ok' if s['n_lines'] >= 5 else 'few_lines')
        rows += [row(metric='line_fwhm_pix', wave_A=ref, value=s['fwhm_pix'], err=s['scatter_pix'],
                     unit='pix', **base),
                 row(metric='line_fwhm_A', wave_A=ref, value=s['fwhm_A'], unit='Angstrom', **base),
                 row(metric='line_R', wave_A=ref, value=s['R'], unit='', **base),
                 row(metric='line_fwhm_slope', wave_A=ref, value=s['slope_pix_per_1000A'],
                     unit='pix / 1000 Angstrom', **base)]
    return rows


# ------------------------------------------------------------------ raw processing

def process_raw(path, spectrograph='keck_mosfire', det=1, frame='pixelflatframe'):
    """A raw frame through PypeIt's raw-image steps, without flat fielding.

    Uses the spectrograph's default processing parameters for ``frame``
    (gain applied, overscan/bias/dark as the spectrograph sets them, trimmed
    and in PypeIt orientation ``(spec, spat)``), with pixel, illumination
    and spectral flats and CR masking turned off. Returns the image in
    electrons (total over the exposure) and the bad-pixel mask.
    """
    from pypeit.images.rawimage import RawImage
    from pypeit.spectrographs.util import load_spectrograph
    spec = load_spectrograph(spectrograph)
    full = spec.default_pypeit_par()
    par = (full[frame] if frame in ('scienceframe',) else full['calibrations'][frame])['process']
    for k in ('use_pixelflat', 'use_illumflat', 'use_specillum', 'mask_cr'):
        par[k] = False
    img = RawImage(str(path), spec, det).process(par)
    bpm = img.select_flag(flag='BPM') if getattr(img, 'fullmask', None) is not None else None
    return np.asarray(img.image, float), bpm


def central_rows_mask(slits_file, shape, fraction=0.5):
    """Boolean (spec, spat) mask of each slit's central ``fraction`` of spatial rows."""
    from pypeit.slittrace import SlitTraceSet
    slits = SlitTraceSet.from_file(str(slits_file), chk_version=False)
    left, right, _ = slits.select_edges()
    spat = np.arange(shape[1])[None, :]
    mask = np.zeros(shape, bool)
    for i in range(left.shape[1]):
        lo = left[:, i] + 0.5 * (1 - fraction) * (right[:, i] - left[:, i])
        hi = right[:, i] - 0.5 * (1 - fraction) * (right[:, i] - left[:, i])
        mask |= (spat >= lo[:, None]) & (spat <= hi[:, None])
    return mask


# ------------------------------------------------------------------ flat brightness (D42, D43)

def flat_rates(flat_file, slits_file, raw_dir, flat_frames, config, band, night, group=None):
    """Dome/internal flat count rates at the config's wavelength nodes (design 4.9.2).

    Args:
        flat_file, slits_file: the group's ``Flat_*.fits`` and ``Slits_*.fits.gz``.
        raw_dir: directory of the raw frames.
        flat_frames (list): frame-table rows of the group's flats (lamp-on
            frames have ``pixelflat`` in ``frametype``; lamp-off frames
            ``lampoffflats``).
    Returns:
        (rows, info): monitor rows, and a dict with the cards, frame counts,
        peak ADU and the waveimg source.
    """
    from astropy.io import fits as afits
    from pypeit.flatfield import FlatImages
    flat = FlatImages.from_file(str(flat_file), chk_version=False)
    raw = np.asarray(flat.pixelflat_raw, float)
    waveimg = flat.pixelflat_waveimg
    wave_src = 'pixelflat_waveimg'
    if waveimg is None or not np.any(np.asarray(waveimg) > 0):
        wave_src = 'missing'
        waveimg = np.zeros_like(raw)
    waveimg = np.asarray(waveimg, float)
    central = central_rows_mask(slits_file, raw.shape, config['slit_row_fraction'])
    on = [f for f in flat_frames if 'pixelflat' in f['frametype']]
    off = [f for f in flat_frames if 'lampoffflat' in f['frametype']]
    hdr = afits.getheader(Path(raw_dir) / on[0]['filename'])
    t_frame = float(hdr['TRUITIME'])
    cards = {k: (hdr.get(k).item() if hasattr(hdr.get(k), 'item') else hdr.get(k)) for k in config['lamp_cards']}
    cards.update({'TRUITIME': t_frame, 'SAMPMODE': hdr.get('SAMPMODE'), 'NUMREADS': hdr.get('NUMREADS'),
                  'n_on': len(on), 'n_off': len(off)})
    peak = 0.0
    for f in on:
        d = afits.getdata(Path(raw_dir) / f['filename'], 0).astype(float)
        peak = max(peak, float(np.percentile(d, 99.99)))
    cards['peak_adu_p9999'] = round(peak, 1)
    width, _ = slit_from_decker(on[0]['decker'])
    flags = ['nonlinear'] if peak > config['nonlinear_adu'] else []
    if wave_src == 'missing':
        flags.append('no_waveimg')
    base = dict(night=night, instrument=config['instrument'], source=config['flat_kind'],
                frame=f'group:{group or Path(flat_file).stem.replace("Flat_", "")}', target='DOME FLATS',
                decker=on[0]['decker'], slit_width=width, filter=band, cards=json.dumps(cards),
                flag=','.join(flags) or 'ok')
    rows = []
    for w0 in config['flat_nodes'].get(band, ()):
        sel = central & (np.abs(waveimg - w0) <= config['flat_halfwidth']) & np.isfinite(raw)
        n = int(sel.sum())
        rate = float(np.median(raw[sel]) / t_frame) if n else None
        rows.append(row(metric='flat_rate', wave_A=w0, value=rate, unit='electron / (s pix)', n=n, **base))
        rows.append(row(metric='flat_rate_per_arcsec', wave_A=w0,
                        value=None if (rate is None or not width) else rate / width,
                        unit='electron / (s pix arcsec)', n=n, **base))
    return rows, {'cards': cards, 'waveimg': wave_src, 't_frame': t_frame, 'peak_adu': peak}


def flat_conversion_check(flat_file, slits_file, raw_dir, flat_frames, spectrograph='keck_mosfire'):
    """Compare ``pixelflat_raw`` with (mean lamp-on - mean lamp-off), both from PypeIt raw processing.

    Returns the median ratio ``pixelflat_raw / (on - off)`` over the slits'
    central rows, and the same against the plain raw-ADU difference times
    the header gain (``SYSGAIN``), to confirm units (e- and the gain).
    """
    from pypeit.flatfield import FlatImages
    flat = FlatImages.from_file(str(flat_file), chk_version=False)
    raw = np.asarray(flat.pixelflat_raw, float)
    central = central_rows_mask(slits_file, raw.shape)
    on = [process_raw(Path(raw_dir) / f['filename'], spectrograph)[0] for f in flat_frames
          if 'pixelflat' in f['frametype']]
    off = [process_raw(Path(raw_dir) / f['filename'], spectrograph)[0] for f in flat_frames
           if 'lampoffflat' in f['frametype']]
    diff = np.mean(on, axis=0) - np.mean(off, axis=0)
    good = central & np.isfinite(diff) & (diff > 0)
    return {'ratio_median': float(np.median(raw[good] / diff[good])),
            'ratio_p16_p84': [float(np.percentile(raw[good] / diff[good], q)) for q in (16, 84)],
            'n_pix': int(good.sum()), 'n_on': len(on), 'n_off': len(off),
            'pixelflat_raw_median': float(np.median(raw[good])), 'diff_median': float(np.median(diff[good]))}


# ------------------------------------------------------------------ line brightness (D45)

LSF_SLOPE_INTERIM = 0.277   # "/pix, D25 as revised by S13 (sky lines fill the slit)


def sky_line_fwhm_A(slit, dispersion):
    """Expected FWHM (A) of a sky line filling a slit of width ``slit`` (design D25, interim slope)."""
    return max(slit / LSF_SLOPE_INTERIM, LSF_FLOOR_PIX) * dispersion


def _line_sum(img, waveimg, rows_ok, lam, fwhm_a, continuum=True):
    """Per spatial row: the sum over |lam'-lam| <= 1.5 FWHM.

    With ``continuum`` (per-line fluxes in the frame's own narrow window), a
    linear continuum fitted to 1.5-2 FWHM flanks is subtracted. Without it
    (the fixed windows), the total flux in the window is returned: in wide
    windows the flanks fall on neighbouring OH lines and a flank continuum is
    biased high (S6b). ``img`` is (spec, spat) in e-/s/pix. Returns
    (per-row sums, n rows used).
    """
    win = 1.5 * fwhm_a
    sums = []
    for j in np.where(rows_ok)[0]:
        w = waveimg[:, j]
        f = img[:, j]
        core = np.abs(w - lam) <= win
        if core.sum() < 3 or not np.all(np.isfinite(f[core])):
            continue
        if not continuum:
            sums.append(float(np.sum(f[core])))
            continue
        flank = (np.abs(w - lam) > win) & (np.abs(w - lam) <= 2 * win) & np.isfinite(f)
        if flank.sum() < 4:
            continue
        c = np.polyfit(w[flank] - lam, f[flank], 1)
        sums.append(float(np.sum(f[core] - np.polyval(c, w[core] - lam))))
    return np.asarray(sums), len(sums)


def gemini_line_flux(lam, fwhm_a, airmass, pwv, skygrid=None, continuum=False):
    """Gemini SKYBG integrated over the line window (photons/s/arcsec^2/m^2), after LSF convolution.

    The model is convolved with a Gaussian of ``fwhm_a`` and integrated over
    ±1.5 FWHM: the total in the window, or (``continuum``) minus the same
    flank continuum as the data.
    """
    from astropy.io import fits as afits
    from scipy.ndimage import gaussian_filter1d
    from keck_etcs.calib.harvest import SKYGRID
    with afits.open(skygrid or SKYGRID) as h:
        wave = h['WAVE'].data.astype(float) * 10.0          # A
        sky = h['SKYBG'].data.astype(float) / 10.0           # per A
        grid = h['GRID'].data
    am, pw = np.asarray(grid['airmass'], float), np.asarray(grid['pwv_mm'], float)
    ams, pws = np.unique(am), np.unique(pw)
    a = np.clip(airmass, ams[0], ams[-1])
    ia = int(np.clip(np.searchsorted(ams, a) - 1, 0, len(ams) - 2))
    fa = (a - ams[ia]) / (ams[ia + 1] - ams[ia])
    lp, lpw = np.log(np.clip(pwv, pws[0], pws[-1])), np.log(pws)
    ip = int(np.clip(np.searchsorted(lpw, lp) - 1, 0, len(pws) - 2))
    fp = (lp - lpw[ip]) / (lpw[ip + 1] - lpw[ip])
    rowv = lambda aa, pp: sky[np.where(np.isclose(am, aa) & np.isclose(pw, pp))[0][0]]
    s = ((1 - fa) * ((1 - fp) * rowv(ams[ia], pws[ip]) + fp * rowv(ams[ia], pws[ip + 1]))
         + fa * ((1 - fp) * rowv(ams[ia + 1], pws[ip]) + fp * rowv(ams[ia + 1], pws[ip + 1])))
    dw = np.median(np.diff(wave))
    s = gaussian_filter1d(s, fwhm_a / 2.3548 / dw)
    win = 1.5 * fwhm_a
    core = np.abs(wave - lam) <= win
    if not continuum:
        return float(np.sum(s[core] * dw))
    flank = (np.abs(wave - lam) > win) & (np.abs(wave - lam) <= 2 * win)
    c = np.polyfit(wave[flank] - lam, s[flank], 1)
    return float(np.sum((s[core] - np.polyval(c, wave[core] - lam)) * dw))


WINDOW_SLIT = 5.0          # " ; fixed windows sized for a sky line in this slit (design 4.9.4, S6b)
PERLINE_MAX_SLIT = 1.0     # " ; per-line fluxes on wider slits are flagged ``blended``


def sun_altitude(mjd_mid, site):
    """Solar altitude (deg) at ``mjd_mid`` for a site dict (lat_deg, lon_deg, height_m)."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, get_sun
    from astropy.time import Time
    loc = EarthLocation(lat=site['lat_deg'] * u.deg, lon=site['lon_deg'] * u.deg, height=site['height_m'] * u.m)
    t = Time(mjd_mid, format='mjd')
    return float(get_sun(t).transform_to(AltAz(obstime=t, location=loc)).alt.deg)


def line_fluxes(raw_frames, spec1d_of, flat_file, slits_file, raw_dir, lines, config, band, night,
                thru_curve=None, pwv=None, spectrograph='keck_mosfire', source='OH', provisional=True):
    """OH (sky) line fluxes per on-sky frame (design 4.9.4, as revised in S6b).

    For every frame and monitor line:

    - ``line_flux``: the line summed over the frame's own ±1.5 FWHM (FWHM of a
      sky line filling that slit), ``flag = blended`` on slits wider than
      :data:`PERLINE_MAX_SLIT`;
    - ``line_flux_window``: the *total* flux (no continuum subtraction) in a
      fixed ±1.5 x FWHM(5") window, identical for every frame and
      comparable between slit widths;
    - ``line_flux_above``: the fixed-window flux above the instrument
      (photons/s/arcsec^2/m^2), with the Gemini model for the same window in
      ``err``, where ``thru_curve`` is given;

    plus per frame ``line_flux_sum`` (sum of the fixed windows) and its
    ``line_flux_above`` (``line_id = <source>_sum``).

    All fluxes are medians over the slit's central rows with the frame's
    objects masked to ±3 FWHM, divided by platescale x slit width
    (e-/s/arcsec^2, integrated over the line).
    """
    from astropy.io import fits as afits
    from pypeit.flatfield import FlatImages
    from pypeit.specobjs import SpecObjs
    from keck_etcs.calib.harvest import EFF_APERTURE
    flat = FlatImages.from_file(str(flat_file), chk_version=False)
    norm = np.asarray(flat.pixelflat_norm, float)
    waveimg = np.asarray(flat.pixelflat_waveimg, float)
    central = central_rows_mask(slits_file, norm.shape, config['slit_row_fraction'])
    spat_central = central.any(axis=0)
    disp = float(np.nanmedian(np.abs(np.diff(waveimg[:, spat_central], axis=0))))
    fwhm_win = sky_line_fwhm_A(WINDOW_SLIT, disp)
    rows = []
    for fr in raw_frames:
        path = Path(raw_dir) / fr['filename']
        hdr = afits.getheader(path)
        texp = float(hdr['TRUITIME'])
        img, _ = process_raw(path, spectrograph, frame='scienceframe')
        img = np.where(norm > 0, img / texp / np.where(norm > 0, norm, 1.0), np.nan)
        width, _ = slit_from_decker(fr['decker'])
        fwhm_a = sky_line_fwhm_A(width, disp)
        mask = spat_central.copy()
        s1 = spec1d_of.get(fr['filename'])
        if s1:
            for so in SpecObjs.from_fitsfile(str(s1), chk_version=False):
                c, fw = float(so['SPAT_PIXPOS']), float(so['FWHM'] or 5.0)
                lo, hi = int(np.floor(c - 3 * fw)), int(np.ceil(c + 3 * fw))
                mask[max(lo, 0):hi + 1] = False
        area = config['platescale'] * width
        prov = ['lines=provisional'] if provisional else []
        # twilight (S6b): a bright, rising continuum inflates the sky; flag, never fail
        sun = sun_altitude(float(hdr['MJD-OBS']) + 0.5 * texp / 86400.0, config['site'])
        if sun > config['twilight_sun_alt_deg']:
            prov = prov + ['twilight']
        base = dict(night=night, mjd=float(hdr['MJD-OBS']), instrument=config['instrument'],
                    source=source, frame=fr['filename'], target=fr.get('target'), decker=fr['decker'],
                    slit_width=width, filter=band, airmass=float(hdr['AIRMASS']), pwv_fit=pwv,
                    cards=json.dumps({'sun_alt_deg': round(sun, 2), 'TRUITIME': texp}))
        tot = {'flux': 0.0, 'above': 0.0, 'model': 0.0, 'n': 0}
        for lam in lines:
            lid = f'{source}{lam:.2f}'
            # per line, the frame's own window
            sums, n = _line_sum(img, waveimg, mask, lam, fwhm_a)
            fl = prov + (['blended'] if width > PERLINE_MAX_SLIT else [])
            rows.append(row(metric='line_flux', wave_A=lam, line_id=lid,
                            value=float(np.median(sums) / area) if n else None,
                            err=float(1.2533 * np.std(sums) / np.sqrt(n) / area) if n > 1 else None,
                            unit='electron / (s arcsec2)', n=n,
                            **{**base, 'flag': ','.join(fl + ([] if n else ['no_rows'])) or 'ok'}))
            # fixed window, the same for every frame: total flux, no flank continuum
            sums, n = _line_sum(img, waveimg, mask, lam, fwhm_win, continuum=False)
            if not n:
                continue
            flux = float(np.median(sums) / area)
            rows.append(row(metric='line_flux_window', wave_A=lam, line_id=lid, value=flux,
                            err=float(1.2533 * np.std(sums) / np.sqrt(n) / area) if n > 1 else None,
                            unit='electron / (s arcsec2)', n=n,
                            **{**base, 'flag': ','.join(prov + [f'window={1.5 * fwhm_win:.1f}A'])}))
            tot['flux'] += flux
            tot['n'] += 1
            if thru_curve is not None:
                t = float(np.interp(lam, thru_curve['wave'], thru_curve['thru_raw'], left=np.nan, right=np.nan))
                if np.isfinite(t) and t > 0:
                    above = flux / (t * EFF_APERTURE)
                    model = gemini_line_flux(lam, fwhm_win, base['airmass'], pwv if pwv else 1.6)
                    rows.append(row(metric='line_flux_above', wave_A=lam, line_id=lid, value=above, err=model,
                                    unit='photon / (s arcsec2 m2)', n=n,
                                    **{**base, 'flag': ','.join(prov + ['err=gemini_model'])}))
                    tot['above'] += above
                    tot['model'] += model
        rows.append(row(metric='line_flux_sum', line_id=f'{source}_sum', value=tot['flux'],
                        unit='electron / (s arcsec2)', n=tot['n'],
                        **{**base, 'flag': ','.join(prov + ['fixed_windows']) }))
        if thru_curve is not None and tot['model'] > 0:
            rows.append(row(metric='line_flux_above', line_id=f'{source}_sum', value=tot['above'],
                            err=tot['model'], unit='photon / (s arcsec2 m2)', n=tot['n'],
                            **{**base, 'flag': ','.join(prov + ['err=gemini_model', 'sum'])}))
    return rows


# ------------------------------------------------------------------ one night

def monitor_night(night_dir, run_manifest_path=None, raw_dir=None, harvest_dir=None, config=None):
    """All monitor rows for one reduced night (design 4.9.5).

    Reads ``<night>/run_manifest.json``, ``redux/Science/spec1d_*``,
    ``redux/Calibrations/{Flat,Slits,WaveCalib}_*``, the raw frames and, if
    present, the night's harvest (``harvest/*_row.ecsv`` and curve) for
    ``line_flux_above`` and ``pwv_fit``. Every metric block is guarded: an
    exception adds a ``monitor_error`` row with ``flag = monitor_failed``
    and never stops the night (D47).

    Returns:
        list of row dicts, with the D36 provenance and ``keck_etcs_version``
        of the night's reduction filled in.
    """
    import traceback
    from keck_etcs.calib import monitor_configs
    night_dir = Path(night_dir)
    mpath = Path(run_manifest_path) if run_manifest_path else night_dir / 'run_manifest.json'
    m = json.loads(mpath.read_text())
    raw_dir = Path(raw_dir) if raw_dir else night_dir / 'raw'
    cfg = config or monitor_configs.get_config(m.get('instrument', 'keck_mosfire'))
    band, night = m.get('filter'), str(m['night'])
    frames = {f['filename']: f for f in m['frames']}
    sci = night_dir / 'redux' / 'Science'
    cal = night_dir / 'redux' / 'Calibrations'
    spec1d = sorted(sci.glob('spec1d_*.fits'))
    spec1d_of = {f'{p.name.split("spec1d_", 1)[1].split("-", 1)[0]}.fits': p for p in spec1d}
    onsky = [f for f in m['frames'] if ('science' in f['frametype']) or ('standard' in f['frametype'])]
    flats = [f for f in m['frames'] if 'flat' in f['frametype']]

    thru, pwv = None, None
    hdir = Path(harvest_dir) if harvest_dir else night_dir / 'harvest'
    rowfiles = sorted(hdir.glob('*_row.ecsv')) if hdir.exists() else []
    if rowfiles:
        hrow = Table.read(rowfiles[0], format='ascii.ecsv')[0]
        pwv = None if np.ma.is_masked(hrow['pwv_fit']) else float(hrow['pwv_fit'])
        curve = rowfiles[0].with_name(rowfiles[0].name.replace('_row.ecsv', '.ecsv'))
        if curve.exists():
            thru = Table.read(curve, format='ascii.ecsv')

    rows = []

    def guarded(name, fn):
        try:
            out = fn()
            rows.extend(out[0] if isinstance(out, tuple) else out)
        except Exception as exc:  # noqa: BLE001 - D47: a monitor failure flags, never fails
            rows.append(row(night=night, instrument=cfg['instrument'], metric='monitor_error',
                            source=name, value=None, flag='monitor_failed',
                            cards=json.dumps({'error': f'{type(exc).__name__}: {exc}',
                                              'traceback': traceback.format_exc()[-800:]})))

    guarded('object', lambda: object_fwhm(spec1d, frames, cfg, band, night))
    for ff in sorted(cal.glob('Flat_*.fits')):
        key = ff.stem.replace('Flat_', '')
        sl = cal / f'Slits_{key}.fits.gz'
        guarded(cfg['flat_kind'], lambda ff=ff, sl=sl, key=key:
                flat_rates(ff, sl, raw_dir, flats, cfg, band, night, group=key))

    def slit_of(wcf):
        calib = Path(wcf).stem.split('_')[2]      # WaveCalib_<setup>_<calib>_<det>
        arcs = [f for f in m['frames'] if 'arc' in f['frametype'] and str(f.get('calib')) in (calib, 'all')]
        return slit_from_decker(arcs[0]['decker'])[0] if arcs else None
    guarded('OH_width', lambda: line_widths(sorted(cal.glob('WaveCalib_*.fits')), slit_of, cfg, band, night))

    lines = cfg['monitor_lines'].get('OH', {}).get(band, ())
    flat0 = sorted(cal.glob('Flat_*.fits'))
    if lines and flat0:
        key = flat0[0].stem.replace('Flat_', '')
        guarded('OH', lambda: line_fluxes(onsky, spec1d_of, flat0[0], cal / f'Slits_{key}.fits.gz', raw_dir,
                                          lines, cfg, band, night, thru_curve=thru, pwv=pwv,
                                          provisional=cfg.get('monitor_lines_status') == 'provisional'))

    prov = {k: m.get(k) for k in PROVENANCE}
    for r in rows:
        r.update(prov)
        r['keck_etcs_version'] = m.get('keck_etcs_version')
    return rows


TABLE_COLUMNS = ROW_COLUMNS + PROVENANCE + ('keck_etcs_version',)
FLOAT_COLS = ('mjd', 'slit_width', 'wave_A', 'value', 'err', 'airmass', 'pwv_fit')
INT_COLS = ('n',)


def monitor_table(rows):
    """Rows to an astropy Table with fixed dtypes; None becomes a masked value."""
    from astropy.table import MaskedColumn
    cols = []
    for c in TABLE_COLUMNS:
        vals = [r.get(c) for r in rows]
        mask = [v is None for v in vals]
        if c in FLOAT_COLS:
            data = [np.nan if v is None else float(v) for v in vals]
        elif c in INT_COLS:
            data = [0 if v is None else int(v) for v in vals]
        else:
            data = ['' if v is None else str(v) for v in vals]
        cols.append(MaskedColumn(data, name=c, mask=mask))
    return Table(cols)
