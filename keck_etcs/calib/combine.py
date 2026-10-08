"""Combine per-standard throughput curves into per-era products (design 4.5, D22, D36; plan S10).

For one instrument era, on the common 1 A grid of the harvest
(``keck_etcs.calib.harvest``):

- each standard contributes its filter-free curve (telescope + spectrograph
  + detector). It is the curve's ``thru`` column when the harvest divided
  the filter out; for rows harvested without a filter curve (``flag =
  nofilter``) it is ``thru_raw`` divided here by the band's filter. In both
  cases only the filter's half-power band is kept, because outside it the
  division amplifies any mismatch between the filter curve and the
  instrument's real cut-on and cut-off;
- each night's band median is compared with the era median of band
  medians; nights more than 3 MAD away are excluded whole (D22). This needs
  at least 3 nights, since the MAD of fewer is not meaningful. The band
  median is taken over :data:`COMMON_WINDOW` (inside both the J and the J2
  half-power bands), so that nights through different filters are compared
  over the same wavelengths (plan S16); a curve without samples there uses
  its whole band;
- per pixel: the median of the remaining curves (``thru_median``), their
  median absolute deviation (``thru_mad``, NaN with one curve) and the count
  (``n_std``);
- ``meta`` carries the era, the standards used and excluded, and the
  distinct reduction provenance of the contributing rows (``images``,
  ``image_digests``, ``pypeit_git_shas``, ``keck_etcs_git_shas``,
  ``pypeit_versions``; D36).

No PypeIt import; the inputs are the committed ECSV tables.
"""
import numpy as np
from astropy.table import Table

# inside both the J and the J2 bands and redward of the J cut-on and A0V systematics (keck_etcs.calib.trend)
COMMON_WINDOW = (11900.0, 12450.0)
PROVENANCE = ('image', 'image_digest', 'pypeit_git_sha', 'keck_etcs_git_sha', 'pypeit_version')
MAD_CLIP = 3.0
MIN_FOR_CLIP = 3


def in_era(date, era):
    """True if an ISO date falls in ``era`` (``start <= date < end``; open end allowed)."""
    d = str(date)[:10]
    return d >= era.start and (era.end is None or d < era.end)


def filter_free(curve, filter_wave, filter_trans, half_power):
    """The filter-free throughput of one harvested curve, masked outside the half-power band.

    Args:
        curve (`astropy.table.Table`): harvest curve (``wave``, ``thru_raw``,
            optionally an unmasked ``thru``).
        filter_wave, filter_trans (array): the band's filter curve.
        half_power (tuple): (lo, hi) half-power wavelengths [A].

    Returns:
        tuple: ``(wave, thru, how)``; ``thru`` is NaN outside the half-power
        band, and ``how`` says whether the filter was divided at harvest or here.
    """
    wave = np.asarray(curve['wave'], float)
    inside = (wave >= half_power[0]) & (wave <= half_power[1])
    if 'thru' in curve.colnames and not np.all(np.ma.getmaskarray(curve['thru'])):
        thru = np.ma.filled(np.ma.asarray(curve['thru'], float), np.nan)
        how = 'filter divided at harvest'
    else:
        ft = np.interp(wave, filter_wave, filter_trans, left=0.0, right=0.0)
        thru = np.where(ft > 0, np.asarray(curve['thru_raw'], float) / np.where(ft > 0, ft, 1.0), np.nan)
        how = 'filter divided in combine (row flag nofilter)'
    return wave, np.where(inside, thru, np.nan), how


def combine_era(rows, curves, era, filters):
    """Combine the standards of one era.

    Args:
        rows (`astropy.table.Table`): per-standard rows (``standards.ecsv``).
        curves (dict): ``thru_curve_file`` -> curve table.
        era: an ``Era`` (``name``, ``start``, ``end``).
        filters (dict): band -> ``(wave_A, transmission, (half_lo, half_hi))``.

    Returns:
        tuple: ``(table, info)``; ``table`` has ``wave, thru_median,
        thru_mad, n_std`` (None if the era has no usable standard) and
        ``info`` the per-row decisions.
    """
    sel = [r for r in rows if in_era(r['date'], era) and 'excluded' not in str(r['flag'])]
    per_row = []
    for r in sel:
        fw, ft, hp = filters[str(r['filter'])]
        w, t, how = filter_free(curves[str(r['thru_curve_file'])], fw, ft, hp)
        common = (w >= COMMON_WINDOW[0]) & (w <= COMMON_WINDOW[1]) & np.isfinite(t)
        use = common if common.any() else np.isfinite(t)
        per_row.append({'row': r, 'wave': w, 'thru': t, 'how': how,
                        'band_median': float(np.median(t[use])) if use.any() else np.nan})
    per_row = [p for p in per_row if np.isfinite(p['band_median'])]
    info = {'excluded': [], 'used': []}
    if not per_row:
        return None, info
    bm = np.array([p['band_median'] for p in per_row])
    med = float(np.median(bm))
    mad = float(np.median(np.abs(bm - med)))
    keep = []
    for p in per_row:
        if len(per_row) >= MIN_FOR_CLIP and mad > 0 and abs(p['band_median'] - med) > MAD_CLIP * mad:
            info['excluded'].append(p)
        else:
            keep.append(p)
    info['used'] = keep
    lo = min(p['wave'][0] for p in keep)
    hi = max(p['wave'][-1] for p in keep)
    grid = np.arange(lo, hi + 0.5, 1.0)
    stack = np.full((len(keep), grid.size), np.nan)
    for i, p in enumerate(keep):
        k = np.round(p['wave'] - lo).astype(int)
        stack[i, k] = p['thru']
    n = np.sum(np.isfinite(stack), axis=0)
    good = n > 0
    with np.errstate(all='ignore'):
        tmed = np.nanmedian(stack[:, good], axis=0)
        tmad = np.nanmedian(np.abs(stack[:, good] - tmed), axis=0)
    tmad = np.where(n[good] > 1, tmad, np.nan)
    t = Table([grid[good], tmed, tmad, n[good]], names=('wave', 'thru_median', 'thru_mad', 'n_std'))
    t['wave'].unit = 'Angstrom'
    t['thru_median'].format = t['thru_mad'].format = '.6f'
    used_rows = [p['row'] for p in keep]
    t.meta = {
        'era': era.name, 'era_start': era.start, 'era_end': era.end,
        'standards': [{'standard': str(r['standard']), 'date': str(r['date']), 'koa_id': str(r['koa_id']),
                       'filter': str(r['filter']), 'slit_width': float(r['slit_width'])} for r in used_rows],
        'excluded': [{'standard': str(p['row']['standard']), 'date': str(p['row']['date']),
                      'band_median': round(p['band_median'], 5)} for p in info['excluded']],
        'filter_handling': sorted({p['how'] for p in keep}),
        'valid_range_A': [float(grid[good][0]), float(grid[good][-1])],
        'band_median_era': round(med, 5),
    }
    for col in PROVENANCE:
        t.meta[col + 's'] = sorted({str(r[col]) for r in used_rows if col in r.colnames})
    return t, info
