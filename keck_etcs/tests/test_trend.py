from collections import namedtuple

import numpy as np
from astropy.table import Table

from keck_etcs.calib import trend

Era = namedtuple('Era', 'name tag start end')
ERAS = [Era('2012-04..2016-09', 'a', '2012-04-01', '2016-10-01'), Era('2017-02..', 'b', '2017-02-01', None)]


def test_slope_and_era_stats():
    dates = ['2018-01-01', '2019-01-01', '2020-01-01', '2021-01-01']
    vals = [1.00, 0.98, 0.96, 0.94]             # -2 percent of the median per year, roughly
    s, e = trend.slope_pct_per_year(dates, vals)
    assert -2.2 < s < -1.9 and e < 0.1
    st = trend.era_stats(dates + ['2014-05-01'], vals + [0.5], ERAS)
    assert st[0]['n'] == 1 and st[0]['median'] == 0.5 and st[0]['slope_pct_yr'] is None
    assert st[1]['n'] == 4 and abs(st[1]['median'] - 0.97) < 1e-9


def test_correlation_by_era_removes_steps():
    rng = np.random.default_rng(1)
    x = rng.uniform(1.0, 2.0, 40)
    era = np.array(['a'] * 20 + ['b'] * 20)
    y = np.where(era == 'a', 1.0, 2.0) + rng.normal(0, 0.01, 40)   # a step, no x dependence
    xs = np.where(era == 'a', x - 0.5, x + 0.5)                    # x correlated with the era
    assert trend.correlation(xs, y)['sigma'] > 3
    assert trend.correlation(xs, y, by_era=era)['sigma'] < 3


def test_curve_common_median_and_monitor_flags():
    w = np.arange(11000., 13000.)
    assert trend.curve_common_median(w, np.full(w.size, 0.25)) == 0.25
    nights = ['20180101', '20180201', '20180301', '20180401', '20180501']
    t = Table({'night': nights * 2, 'metric': ['fwhm'] * 10, 'wave_A': [np.nan] * 10, 'line_id': [''] * 10,
               'filter': ['J'] * 10, 'value': [1.0, 1.01, 0.99, 1.0, 2.0] * 2, 'flag': ['ok'] * 10})
    new, summary = trend.monitor_flags(t, ERAS)
    assert [f for f in new[:5]] == ['ok', 'ok', 'ok', 'ok', 'trend_3mad']
    assert summary[0]['flagged'] == ['20180501']
    t['flag'] = new
    again, _ = trend.monitor_flags(t, ERAS)
    assert again == new                          # idempotent
