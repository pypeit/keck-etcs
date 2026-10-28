"""MOSFIRE instrument module and its data files (plan step S8, design 5.4)."""
import hashlib
import subprocess
import sys

import numpy as np
import pytest
import yaml

from keck_etcs import instruments
from keck_etcs.instruments.base import DATA_DIR
from keck_etcs.instruments.mosfire import MOSFIRE

FILTER_KEYS = {'instrument', 'band', 'source_url', 'downloaded', 'source_sha256', 'waveref', 'waveref_source',
               'half_power_A', 'ab_minus_vega', 'vega_sha256', 'calib_version', 'keck_etcs_version', 'created',
               'script'}
DETECTOR_KEYS = {'instrument', 'gain_e_per_adu', 'dark_e_per_s_per_pix', 'linearity_adu',
                 'platescale_spatial_arcsec_per_pix', 'platescale_dispersion_arcsec_per_pix', 'min_integration_s',
                 'read_noise_source', 'gain_source', 'dark_source', 'linearity_source', 'min_integration_source',
                 'calib_version', 'keck_etcs_version', 'created', 'script'}
INDEX_KEYS = {'calib_version', 'created', 'sha256', 'script', 'provenance'}


def test_get():
    assert instruments.get('keck_mosfire') is MOSFIRE
    with pytest.raises(KeyError):
        instruments.get('keck_lris')


def test_read_noise():
    assert MOSFIRE.read_noise('MCDS', 16) == (pytest.approx(5.8), [])
    assert MOSFIRE.read_noise('CDS', 1) == (pytest.approx(21.0), [])
    rn, w = MOSFIRE.read_noise('CDS', 16)
    assert rn == pytest.approx(21.0) and w
    d = MOSFIRE.detector()
    assert d['meta']['gain_e_per_adu'] == 2.15 and d['meta']['dark_e_per_s_per_pix'] == 0.008
    assert dict(d['meta']['linearity_adu']) == {'nonlinear_1pct': 26000, 'nonlinear_5pct': 37000, 'saturated': 43000}


def test_vega_offsets_and_half_power():
    assert 0.85 <= MOSFIRE.vega_offset('J') <= 0.97          # XTcalc uses 0.91
    lo, hi = MOSFIRE.filter_curve('J2')['meta']['half_power_A']
    assert (lo + hi) / 2e4 == pytest.approx(1.181, abs=0.01)
    assert (hi - lo) / 2e4 == pytest.approx(0.065, abs=0.01)
    for band in ('J', 'J2'):
        f = MOSFIRE.filter_curve(band)
        assert np.all(np.diff(f['wave_A']) > 0) and f['transmission'].min() >= 0 and f['transmission'].max() <= 1


def test_band_windows_follow_n2():
    for band in ('J', 'J2'):
        lo, hi = MOSFIRE.band_window(band)
        hp = MOSFIRE.filter_curve(band)['meta']['half_power_A']
        fp = MOSFIRE.bands[band].footprint_A
        assert lo == max(hp[0], fp[0]) and hi == min(hp[1], fp[1])
    assert MOSFIRE.band_window('J2')[0] == pytest.approx(11169, abs=2)


def test_lsf_measured_row_takes_precedence():
    fw, src = MOSFIRE.lsf_fwhm_pix(1.0)
    assert fw == pytest.approx(3.6064) and src.startswith('measured')
    fw, src = MOSFIRE.lsf_fwhm_pix(0.7, 'J')             # no measured J row at 0.7": the rule
    assert fw == pytest.approx(np.hypot(0.7 / 0.292, 1.08)) and 'D25' in src and 'sqrt' in src
    assert fw == pytest.approx(2.627, abs=0.01)          # the 0.7" OH-line width it was fitted to (S16)
    assert MOSFIRE.lsf_fwhm_pix(0.4)[0] == pytest.approx(np.hypot(0.4 / 0.292, 1.08))
    # S23d: measured 0.7" rows of H and K (2012-11-28) and the 1.5" K row (2019-10-13) take precedence
    assert MOSFIRE.lsf_fwhm_pix(0.7, 'H')[0] == pytest.approx(2.5597) and MOSFIRE.lsf_fwhm_pix(0.7, 'K')[0] == pytest.approx(2.6135)
    assert MOSFIRE.lsf_fwhm_pix(1.5, 'K')[0] == pytest.approx(5.370, abs=0.001)
    assert MOSFIRE.lsf_fwhm_pix(1.5, 'H')[0] == pytest.approx(np.hypot(1.5 / 0.292, 1.08))   # no H row at 1.5"


def test_gate_windows_and_sens_files():
    from keck_etcs.instruments import mosfire as m
    g = m.gate_windows('J2')
    assert g['zp_window_A'] == (11170.0, 12600.0) and g['counts_window_A'] == (11700.0, 12400.0)   # S4b, unchanged
    assert g['thru_range'] == (0.15, 0.45)
    h = m.gate_windows('H')
    assert h['zp_window_A'] == (14900.0, 17800.0) and h['thru_range'] == (0.17, 0.54)
    assert h['counts_window_A'][0] == pytest.approx(14900 + 2900 / 3) and h['counts_window_A'][1] == pytest.approx(17800 - 2900 / 3)
    assert m.gate_windows('K')['thru_range'] == (0.16, 0.51) and m.gate_windows('Y')['thru_range'] == (0.12, 0.38)
    assert m.sens_par_file('H') == 'pypeit_par/keck_mosfire_H.sens' and m.sens_par_file('J2') == 'pypeit_par/keck_mosfire_J.sens'
    assert m.sens_par_file('Y') == 'pypeit_par/keck_mosfire_J.sens'


def test_eras():
    assert MOSFIRE.era_for_date(None)[0].name == '2025-04..'
    assert MOSFIRE.era_for_date('2022-04-09') == (MOSFIRE.eras[1], [])
    assert MOSFIRE.eras[1].name == '2017-02..2025-02' and MOSFIRE.eras[1].tag == '2017-2025'
    era, w = MOSFIRE.era_for_date('2016-12-01')
    assert era.name == '2012-04..2016-09' and 'offline' in w[0]
    era, w = MOSFIRE.era_for_date('2025-03-01')
    assert era.name == '2017-02..2025-02' and 'CSU' in w[0]
    assert MOSFIRE.era_for_date('2011-01-01')[0].name == '2012-04..2016-09'


def test_throughput_era_file_and_fallback():
    t = MOSFIRE.throughput(MOSFIRE.eras[1])
    assert t['file'] == 'mosfire/throughput/mosfire_thru_J_2017-2025.ecsv' and t['warnings'] == []
    assert t['calib_version'] == 'mosfire-2026.10' and t['era'] is MOSFIRE.eras[1]
    # since the first release (mosfire-J-2026.10) every era has its own curve; per group since S23b (D49)
    for e in MOSFIRE.eras:
        f = MOSFIRE.throughput(e)
        assert f['era'] is e and f['warnings'] == [] and f['file'] == MOSFIRE.throughput_file(e)


def test_throughput_file_needs_the_group_placeholder():
    import dataclasses
    import pytest
    bad = dataclasses.replace(MOSFIRE, throughput_pattern='mosfire/throughput/mosfire_thru_{tag}.ecsv')
    with pytest.raises(ValueError, match='group'):
        bad.throughput_file(MOSFIRE.eras[0], 'J')
    assert MOSFIRE.throughput_file(MOSFIRE.eras[0], 'H') == 'mosfire/throughput/mosfire_thru_H_2012-2016.ecsv'


def test_throughput_falls_back_to_nearest_era(monkeypatch):
    from keck_etcs.instruments import base
    real = base.Path.exists
    missing = base.DATA_DIR / MOSFIRE.throughput_file(MOSFIRE.eras[0])
    monkeypatch.setattr(base.Path, 'exists', lambda self: False if self == missing else real(self))
    MOSFIRE._cache.pop(('throughput', 'J', MOSFIRE.eras[0].name), None)
    try:
        f = MOSFIRE.throughput(MOSFIRE.eras[0])
        assert f['era'] is MOSFIRE.eras[1] and 'no throughput curve yet' in f['warnings'][0]
    finally:
        MOSFIRE._cache.pop(('throughput', 'J', MOSFIRE.eras[0].name), None)


def test_sky_grid_loads():
    g = MOSFIRE.sky_grid()
    assert g['skybg'].shape == g['trans'].shape == (12, g['wave_A'].size)
    assert g['wave_A'][0] == pytest.approx(9500.25)


def test_monitor_block_moved_and_reexported():
    from keck_etcs.calib import monitor_configs as mc
    assert mc.get_config('keck_mosfire') is MOSFIRE.monitor
    assert mc.MOSFIRE_PLATESCALE == MOSFIRE.platescale == MOSFIRE.monitor['platescale']


def test_data_files_carry_provenance():
    from astropy.table import Table
    for band in ('Y', 'J', 'J2', 'J3', 'H', 'K'):
        meta = Table.read(DATA_DIR / 'mosfire' / 'filters' / f'mosfire_{band}.ecsv', format='ascii.ecsv').meta
        assert FILTER_KEYS <= set(meta), band
    assert DETECTOR_KEYS <= set(MOSFIRE.detector()['meta'])


def test_index_registers_every_shipped_file_with_its_hash():
    index = yaml.safe_load((DATA_DIR / 'index.yaml').read_text())['files']
    for rel in ['mosfire/detector.ecsv'] + [f'mosfire/filters/mosfire_{b}.ecsv' for b in ('Y', 'J', 'J2', 'J3', 'H', 'K')]:
        assert rel in index, rel
    for rel, entry in index.items():
        assert INDEX_KEYS <= set(entry), rel
        assert hashlib.sha256((DATA_DIR / rel).read_bytes()).hexdigest() == entry['sha256'], rel


def test_instruments_import_without_pypeit():
    code = ('import sys\nfrom keck_etcs.instruments.mosfire import MOSFIRE\nMOSFIRE.filter_curve("J")\n'
            'MOSFIRE.detector()\nMOSFIRE.sky_grid()\n'
            "print(','.join(m for m in ('pypeit', 'boto3') if m in sys.modules))\n")
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ''


def test_recorded_defaults_match_the_schema():
    from keck_etcs import schema
    from keck_etcs.instruments import mosfire
    props = schema.load('etc_input')['properties']
    assert props['sky_scale']['default'] == mosfire.SKY_SCALE_DEFAULT
    assert props['aperture']['properties']['length_fwhm']['default'] == mosfire.APERTURE_LENGTH_FWHM_DEFAULT
    lo, hi = mosfire.VALIDATION_J0841['aperture_length_fwhm']['within_1pct']
    assert lo <= mosfire.APERTURE_LENGTH_FWHM_DEFAULT <= hi


def test_throughput_for_window_splices_uncovered_wavelengths():
    era = MOSFIRE.eras[-1]                                   # 2025-04..: one J2 night
    own = MOSFIRE.throughput(era)
    lo, hi = MOSFIRE.band_window('J')
    th = MOSFIRE.throughput_for_window(era, lo, hi)
    assert th['era'] is era and th['spliced'] and th['spliced'][0][0] == '2017-02..2025-02'
    assert th['covered_A'][1] > own['valid_range_A'][1]
    w = np.asarray(th['wave_A'])
    inside = (w >= own['valid_range_A'][0]) & (w <= own['valid_range_A'][1])
    np.testing.assert_allclose(th['thru'][inside], np.interp(w[inside], own['wave_A'], own['thru']))
    lo2, hi2 = MOSFIRE.band_window('J2')
    assert MOSFIRE.throughput_for_window(era, lo2, hi2, margin=5.0)['spliced'] == []


# ---- Y, H, K (S23a, design 9.5 D58, D59)

def test_band_groups_and_windows():
    assert sorted(MOSFIRE.bands) == ['H', 'J', 'J2', 'K', 'Y']
    assert MOSFIRE.group_of('J2') == 'J' and MOSFIRE.group_bands('J') == ['J', 'J2']
    for band in ('Y', 'H', 'K'):
        assert MOSFIRE.group_of(band) == band and MOSFIRE.bands[band].order in (6, 4, 3)
        lo, hi = MOSFIRE.band_window(band)
        hp = MOSFIRE.filter_curve(band)['meta']['half_power_A']
        fp = MOSFIRE.bands[band].footprint_A
        assert lo == max(hp[0], fp[0]) and hi == min(hp[1], fp[1])
        assert MOSFIRE.bands[band].zp_nodes_A[0] >= lo and MOSFIRE.bands[band].zp_nodes_A[-1] <= hi
        c = MOSFIRE.bands[band].common_window_A
        assert lo <= c[0] < c[1] <= hi
    assert MOSFIRE.band_window('Y') == pytest.approx((9718.5, 11242.8))       # filter-limited (Y_long footprint)
    # H and K footprints measured in S23d on the 2012-11-28 reference night (window = filter x footprint)
    assert MOSFIRE.band_window('H') == (14660.9, 17970.7) and not MOSFIRE.bands['H'].footprint_provisional   # filter at the blue end
    assert MOSFIRE.band_window('K') == (19535.9, 23991.1) and not MOSFIRE.bands['K'].footprint_provisional
    assert not MOSFIRE.bands['Y'].footprint_provisional and not MOSFIRE.bands['J'].footprint_provisional
    assert MOSFIRE.common_window('J') == MOSFIRE.SPLICE_WINDOW == (11900.0, 12450.0)
    assert MOSFIRE.common_window('H') == (14900.0, 17800.0)
    assert 0.6 <= MOSFIRE.vega_offset('Y') <= 0.7 and 1.3 <= MOSFIRE.vega_offset('H') <= 1.4
    assert 1.8 <= MOSFIRE.vega_offset('K') <= 1.9


def test_lsf_per_band():
    # the measured 1" row is a J2 row: it serves the whole J group and no other
    fw, src = MOSFIRE.lsf_fwhm_pix(1.0, 'J')
    assert fw == pytest.approx(3.6064) and src.startswith('measured')
    assert MOSFIRE.lsf_fwhm_pix(1.0, 'J2')[0] == pytest.approx(3.6064)
    for band in ('Y', 'H', 'K'):
        fw, src = MOSFIRE.lsf_fwhm_pix(1.0, band)
        assert fw == pytest.approx(np.hypot(1.0 / 0.292, 1.08)) and '(provisional)' in src and 'D25' in src
        assert MOSFIRE.lsf_rule(band)[3] is True
    assert MOSFIRE.lsf_rule('J')[3] is False and '(provisional)' not in MOSFIRE.lsf_fwhm_pix(0.7, 'J')[1]
    # without a band every band's measured rows apply (S23d: the H and K 0.7" rows), with a band only its group's
    assert MOSFIRE.lsf_fwhm_pix(0.7)[1].startswith('measured') and 'D25' in MOSFIRE.lsf_fwhm_pix(0.7, 'J')[1]


def test_provisional_throughput_for_groups_without_standards():
    for group in ('Y', 'H', 'K'):
        t = MOSFIRE.throughput(MOSFIRE.eras[1], group)
        assert t['provisional'] and t['era'] is None and t['calib_version'] == 'provisional-xtcalc-2012'
        assert t['file'] == f'mosfire/throughput/mosfire_thru_{group}_provisional.ecsv'
        assert any('PROVISIONAL' in w for w in t['warnings'])
        lo, hi = MOSFIRE.band_window(group)
        # XTcalc's H efficiency file ends at 17991 A, 49 A short of the nominal H window: the ETC holds
        # the edge value there with a warning, so the placeholder need only cover 98 percent of the window
        covered = min(t['valid_range_A'][1], hi) - max(t['valid_range_A'][0], lo)
        assert covered >= 0.98 * (hi - lo), (group, t['valid_range_A'], (lo, hi))
        assert 0.1 < np.median(t['thru']) < 0.6
        th = MOSFIRE.throughput_for_window(MOSFIRE.eras[1], lo, hi, group=group)
        assert th['spliced'] == [] and th['covered_A'] == t['valid_range_A']
    j = MOSFIRE.throughput(MOSFIRE.eras[1], 'J')
    assert not j['provisional'] and j['era'] is MOSFIRE.eras[1]
