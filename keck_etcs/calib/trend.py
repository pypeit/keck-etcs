"""Trend analysis of the per-standard throughput and of the calibration monitor (design 4.6, D47; plan S16).

Pure numpy/scipy, no I/O: the callers (``scripts/mosfire/plot_throughput_trend.py``,
``scripts/mosfire/plot_monitor_trends.py``) read the committed tables.

Throughput metrics:

- ``thru_common``: the median of a standard's filter-free curve (``thru``,
  the filter divided out at harvest) over :data:`COMMON_WINDOW`, inside both
  the J (11530-13500 A) and the J2 (11170-12463 A) bands and redward of
  two systematics found in S16: the J filter curve's cut-on (J and J2
  curves of GD153 differ by 10 percent at 11650 A, 3 percent at 11800 A,
  0 at 12000 A) and a depression of the A0V curves blueward of about
  11900 A. It compares nights taken through different filters. The row columns
  ``thru_median_1117_1260`` and ``zp_1250`` include the filter (and J2's
  red cut-off falls at 1.25 um), so they are only compared within one
  filter (plan S16: GD153 gives 0.176 in J2 and 0.224 in J for those, but
  0.240 and 0.240 for ``thru_common``).
- Per era: median, MAD, and an ordinary least-squares slope of
  ``value / era median - 1`` against the year, in percent per year with
  its standard error (:func:`era_stats`).
- Correlations (:func:`correlation`): Pearson r, its two-sided p-value and
  the equivalent number of Gaussian sigma; on the residuals after each
  era's median is removed when ``by_era`` is given.

Monitor (D47): :func:`monitor_flags` groups the monitor rows by metric and
line or node, takes each night's median, and flags (does not exclude) the
nights more than 3 MAD from their era's median of night medians.
"""
import numpy as np

COMMON_WINDOW = (11900.0, 12450.0)
MAD_FLAG = 3.0
MIN_NIGHTS = 3
MONITOR_FLAG = 'trend_3mad'
SKIP_FLAGS = ('nonlinear', 'monitor_failed')
"""Monitor rows with these flags are neither used in nor flagged by the era statistics."""


def in_era(date, era):
    d = str(date)[:10]
    return d >= era.start and (era.end is None or d < era.end)


def era_of(date, eras):
    """The era containing an ISO date (None outside every era, e.g. in an instrument gap)."""
    return next((e for e in eras if in_era(date, e)), None)


def decimal_year(date):
    """ISO date -> decimal year (no leap-day care needed at this precision)."""
    y, m, d = (int(x) for x in str(date)[:10].split('-'))
    return y + ((m - 1) * 30.44 + (d - 1)) / 365.25


def curve_common_median(wave, thru, window=COMMON_WINDOW):
    """Median of a filter-free curve over ``window`` (NaN when it has no finite sample there)."""
    wave = np.asarray(wave, float)
    thru = np.ma.filled(np.ma.asarray(thru, float), np.nan)
    sel = (wave >= window[0]) & (wave <= window[1]) & np.isfinite(thru)
    return float(np.median(thru[sel])) if sel.any() else float('nan')


def mad(values):
    v = np.asarray(values, float)
    v = v[np.isfinite(v)]
    return float(np.median(np.abs(v - np.median(v)))) if v.size else float('nan')


def slope_pct_per_year(dates, values):
    """OLS slope of ``values / median - 1`` against decimal year: ``(slope %/yr, sigma)`` (NaN for < 3 points)."""
    x = np.array([decimal_year(d) for d in dates], float)
    y = np.asarray(values, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 3 or np.ptp(x) == 0:
        return float('nan'), float('nan')
    y = 100.0 * (y / np.median(y) - 1.0)
    A = np.vstack([x - x.mean(), np.ones_like(x)]).T
    coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
    dof = x.size - 2
    s2 = float(np.sum((y - A @ coef) ** 2) / dof) if dof > 0 else float('nan')
    sigma = float(np.sqrt(s2 / np.sum((x - x.mean()) ** 2))) if dof > 0 else float('nan')
    return float(coef[0]), sigma


def era_stats(dates, values, eras):
    """Per-era statistics: list of dicts ``era, n, median, mad, mad_pct, slope_pct_yr, slope_err``."""
    out = []
    for era in eras:
        sel = [(d, v) for d, v in zip(dates, values) if in_era(d, era) and np.isfinite(v)]
        if not sel:
            out.append({'era': era.name, 'n': 0, 'median': None, 'mad': None, 'mad_pct': None,
                        'slope_pct_yr': None, 'slope_err': None})
            continue
        d, v = zip(*sel)
        med, m = float(np.median(v)), mad(v)
        s, e = slope_pct_per_year(d, v)
        out.append({'era': era.name, 'n': len(v), 'median': med, 'mad': m,
                    'mad_pct': 100.0 * m / med if med else None,
                    'slope_pct_yr': None if np.isnan(s) else s, 'slope_err': None if np.isnan(e) else e})
    return out


def correlation(x, y, by_era=None):
    """Pearson correlation of ``y`` with ``x``: dict ``n, r, p, sigma`` (NaN for < 4 points).

    With ``by_era`` (a list of era labels, one per point), each era's median
    of ``y`` is removed first, so the test looks for a residual dependence,
    not for era-to-era steps.
    """
    from scipy import stats
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if by_era is not None:
        lab = np.asarray([str(b) for b in by_era])
        y = y.copy()
        for e in set(lab[ok]):
            s = ok & (lab == e)
            y[s] -= np.median(y[s])
    x, y = x[ok], y[ok]
    if x.size < 4 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return {'n': int(x.size), 'r': float('nan'), 'p': float('nan'), 'sigma': float('nan')}
    r, p = stats.pearsonr(x, y)
    sigma = float(stats.norm.isf(p / 2.0)) if p > 0 else float('inf')
    return {'n': int(x.size), 'r': float(r), 'p': float(p), 'sigma': sigma}


def monitor_group_key(row):
    """Group of a monitor row: metric, line or node, filter; for dome-flat rates also the lamp power.

    Dome-flat rates scale with the lamp power (``FPOWER`` in ``cards``: 4.0,
    9.0 and 13.5 among the S15 nights), so each power is its own series.
    """
    import json
    w = row['wave_A']
    w = '' if w is None or (isinstance(w, float) and np.isnan(w)) or np.ma.is_masked(w) else f'{float(w):.1f}'
    lid = row['line_id']
    lid = '' if lid is None or np.ma.is_masked(lid) else str(lid)
    key = (str(row['metric']), w, lid, str(row['filter']))
    if str(row['metric']).startswith('flat_rate') and 'cards' in row.colnames:
        try:
            power = json.loads(str(row['cards'])).get('FPOWER')
        except (ValueError, TypeError, AttributeError):
            power = None
        key += (f'FPOWER={power}',)
    return key


def monitor_flags(table, eras, flag=MONITOR_FLAG, nsig=MAD_FLAG, min_nights=MIN_NIGHTS):
    """Per-era 3-MAD flags of the monitor table (D47: flag, never exclude).

    Rows flagged :data:`SKIP_FLAGS` take no part. For every group
    (:func:`monitor_group_key`) and era, each night's median
    ``value`` is compared with the era median of the night medians; a night
    more than ``nsig`` MAD away has ``flag`` appended to the ``flag`` of
    all its rows of that group. Needs ``min_nights`` nights with a finite
    value. Returns ``(new_flags, summary)``: the new ``flag`` strings (one per
    row; earlier ``flag`` entries kept, an old ``flag`` of this name
    dropped first, so the function is idempotent) and a list of dicts
    ``group, era, n_nights, median, mad, flagged``.
    """
    vals = np.ma.filled(np.ma.asarray(table['value'], float), np.nan)
    flags = []
    for f in table['flag']:
        parts = [p for p in str(f).split(',') if p and p != flag]
        flags.append(parts)
    groups = {}
    for i, r in enumerate(table):
        groups.setdefault(monitor_group_key(r), []).append(i)
    summary = []
    nights = np.asarray([str(n) for n in table['night']])
    for key, idx in sorted(groups.items()):
        idx = np.asarray(idx)
        for era in eras:
            per_night = {}
            for i in idx:
                d = f'{nights[i][:4]}-{nights[i][4:6]}-{nights[i][6:8]}'
                if in_era(d, era) and np.isfinite(vals[i]) and not any(s in flags[i] for s in SKIP_FLAGS):
                    per_night.setdefault(nights[i], []).append(vals[i])
            if len(per_night) < min_nights:
                continue
            nm = {n: float(np.median(v)) for n, v in per_night.items()}
            med = float(np.median(list(nm.values())))
            m = mad(list(nm.values()))
            bad = sorted(n for n, v in nm.items() if m > 0 and abs(v - med) > nsig * m)
            for i in idx:
                if nights[i] in bad and flag not in flags[i] and not any(s in flags[i] for s in SKIP_FLAGS):
                    flags[i].append(flag)
            summary.append({'group': key, 'era': era.name, 'n_nights': len(nm), 'median': med, 'mad': m,
                            'flagged': bad})
    new = [','.join(p for p in f if p != 'ok') or 'ok' for f in flags]
    return new, summary
