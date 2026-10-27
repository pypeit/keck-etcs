"""keck_etcs.calib.combine (plan S10, design 4.5, D22, D36)."""
import numpy as np
from astropy.table import MaskedColumn, Table

from keck_etcs.calib import combine
from keck_etcs.instruments.base import Era

ERA = Era('2017-02..2025-02', '2017-2025', '2017-02-13', '2025-02-11')
FW = np.arange(11000.0, 12700.0, 1.0)
FT = np.where((FW >= 11200) & (FW <= 12400), 0.9, 0.2)          # half power at 11200-12400
FILTERS = {'J2': (FW, FT, (11200.0, 12400.0))}


def make(n, level, outlier=None, divided=False):
    rows, curves = [], {}
    for i in range(n):
        lev = outlier if (outlier is not None and i == n - 1) else level * (1 + 0.01 * i)
        w = np.arange(11172.0, 12600.0, 1.0)
        ft = np.interp(w, FW, FT)
        c = Table({'wave': w, 'thru_raw': lev * ft})
        c['thru'] = MaskedColumn(np.full(w.size, lev), mask=np.zeros(w.size, bool)) if divided else \
            MaskedColumn(np.full(w.size, np.nan), mask=np.ones(w.size, bool))
        name = f'standards/S{i}.ecsv'
        curves[name] = c
        rows.append({'standard': f'S{i}', 'date': f'2022-04-{i + 1:02d}', 'koa_id': f'K{i}', 'filter': 'J2',
                     'slit_width': 5.0, 'thru_curve_file': name, 'flag': 'nofilter' if not divided else 'ok',
                     'image': f'img:{i % 2}', 'image_digest': f'sha256:{i % 2}', 'pypeit_git_sha': 'pin',
                     'keck_etcs_git_sha': 'abc', 'pypeit_version': '2.0'})
    return Table(rows=rows), curves


def test_single_standard_divides_filter_and_masks_outside_half_power():
    rows, curves = make(1, 0.25)
    t, info = combine.combine_era(rows, curves, ERA, FILTERS)
    assert np.all(t['n_std'] == 1) and np.all(np.isnan(t['thru_mad']))
    np.testing.assert_allclose(t['thru_median'], 0.25)                       # filter divided out
    assert t['wave'][0] == 11200 and t['wave'][-1] == 12400                  # half-power band only
    assert t.meta['filter_handling'] == ['filter divided in combine (row flag nofilter)']
    assert t.meta['images'] == ['img:0'] and t.meta['pypeit_git_shas'] == ['pin']


def test_median_mad_and_three_mad_exclusion():
    rows, curves = make(5, 0.25, outlier=0.10, divided=True)
    t, info = combine.combine_era(rows, curves, ERA, FILTERS)
    assert [p['row']['standard'] for p in info['excluded']] == ['S4']
    assert t.meta['excluded'][0]['standard'] == 'S4'
    assert np.all(t['n_std'] == 4)
    np.testing.assert_allclose(t['thru_median'], np.median(0.25 * (1 + 0.01 * np.arange(4))))
    assert np.all(t['thru_mad'] > 0)
    # meta.images is the set of image values of the contributing rows (D36)
    assert t.meta['images'] == sorted({str(r['image']) for r in rows if r['standard'] != 'S4'})
    assert t.meta['filter_handling'] == ['filter divided at harvest']


def test_no_clipping_below_three_nights_and_era_selection():
    rows, curves = make(2, 0.25, outlier=0.05)
    t, info = combine.combine_era(rows, curves, ERA, FILTERS)
    assert info['excluded'] == [] and np.all(t['n_std'] == 2)
    other = Era('2025-04..', '2025-on', '2025-04-29')
    assert combine.combine_era(rows, curves, other, FILTERS) == (None, {'excluded': [], 'used': []})
    assert combine.in_era('2025-02-10', ERA) and not combine.in_era('2025-02-11', ERA)


def test_shipped_era_file_provenance_matches_its_rows():
    from keck_etcs.instruments.base import DATA_DIR
    from keck_etcs.instruments.mosfire import MOSFIRE
    era = MOSFIRE.eras[1]
    t = Table.read(DATA_DIR / MOSFIRE.throughput_file(era), format='ascii.ecsv')
    rows = Table.read(DATA_DIR / 'mosfire' / 'throughput' / 'standards.ecsv', format='ascii.ecsv')
    used = [r for r in rows if combine.in_era(r['date'], era) and 'excluded' not in str(r['flag'])]
    assert t.meta['images'] == sorted({str(r['image']) for r in used})
    assert t.meta['pypeit_git_shas'] == sorted({str(r['pypeit_git_sha']) for r in used})
    assert t.colnames == ['wave', 'thru_median', 'thru_mad', 'n_std']
    assert t.meta['calib_version'] == 'mosfire-2026.10' and t.meta['era'] == era.name
    assert t.meta['band_group'] == 'J' and t.meta['bands'] == ['J', 'J2']            # per group since S23b (D49)
    # the two nights an earlier combine flagged excluded_3mad are reported again on a rerun
    assert [(e['standard'], e['date']) for e in t.meta['excluded']] == [('GD153', '2025-01-25')]


def test_edge_trim_and_a0v_cut():
    w = np.arange(11172.0, 12600.0, 1.0)
    c = Table({'wave': w, 'thru_raw': np.interp(w, FW, FT) * 0.25,
               'thru': MaskedColumn(np.full(w.size, 0.25), mask=np.zeros(w.size, bool))})
    # FT is 0.9 (its peak) in 11200-12400: a 0.9-of-peak trim keeps exactly that band
    _, t1, _ = combine.filter_free(c, FW, FT, (11200.0, 12400.0), edge_frac=0.9)
    assert np.isnan(t1[w < 11200]).all() and np.isfinite(t1[(w >= 11200) & (w <= 12400)]).all()
    _, t2, _ = combine.filter_free(c, FW, FT, (11200.0, 12400.0), min_wave=11900.0)
    assert np.isnan(t2[w < 11900]).all() and np.isfinite(t2[(w >= 11900) & (w <= 12400)]).all()
    rows, curves = make(3, 0.25, divided=True)
    rows['std_class'] = ['WD', 'A0V', 'WD']
    t, info = combine.combine_era(rows, curves, ERA, FILTERS)
    blue = t['wave'] < 11900
    assert np.all(t['n_std'][blue] == 2) and np.all(t['n_std'][~blue & (t['wave'] <= 12400)] == 3)


def test_rules_per_band_from_the_instrument_module():
    from keck_etcs.instruments.mosfire import MOSFIRE
    # J as built: 0.9 trim, A0V cut; J2 as built: no trim, A0V cut; new bands: 0.9 trim, no A0V cut yet
    assert combine.rules_for('J', MOSFIRE.bands) == ((11900.0, 12450.0), 0.9, 11900.0)
    assert combine.rules_for('J2', MOSFIRE.bands) == ((11900.0, 12450.0), None, 11900.0)
    assert combine.rules_for('H', MOSFIRE.bands) == ((14900.0, 17800.0), 0.9, None)
    assert combine.rules_for('J2') == (combine.COMMON_WINDOW, None, combine.A0V_MIN_WAVE)   # legacy constants
    rows, curves = make(3, 0.25, divided=True)
    rows['std_class'] = ['WD', 'A0V', 'WD']
    a, _ = combine.combine_era(rows, curves, ERA, FILTERS)
    b, _ = combine.combine_era(rows, curves, ERA, FILTERS, bands=MOSFIRE.bands)
    np.testing.assert_array_equal(a['thru_median'], b['thru_median'])        # the J2 rules are unchanged
    assert combine.combine_era(rows, curves, ERA, FILTERS, bands=MOSFIRE.bands, group='H')[0] is None
    assert combine.combine_era(rows, curves, ERA, FILTERS, bands=MOSFIRE.bands, group='J')[0] is not None


def test_prior_excluded_3mad_rows_are_reported_not_used():
    # a row an earlier combine flagged excluded_3mad (S23b): no part in the statistics, listed as excluded
    rows, curves = make(4, 0.25, outlier=0.10)
    rows['flag'] = rows['flag'].astype('U32')
    rows['flag'][-1] = 'excluded_3mad'
    t, info = combine.combine_era(rows, curves, ERA, FILTERS)
    assert [p['row']['standard'] for p in info['used']] == ['S0', 'S1', 'S2']
    assert [(p['row']['standard'], round(p['band_median'], 3)) for p in info['excluded']] == [('S3', 0.1)]
    assert t.meta['excluded'] == [{'standard': 'S3', 'date': '2022-04-04', 'band_median': 0.1}]
    assert np.all(t['n_std'] == 3)
    # other 'excluded_*' flags (nonlinear) are skipped silently, as before
    rows['flag'][-1] = 'excluded_nonlinear'
    t2, info2 = combine.combine_era(rows, curves, ERA, FILTERS)
    assert info2['excluded'] == [] and len(info2['used']) == 3 and t2.meta['excluded'] == []
