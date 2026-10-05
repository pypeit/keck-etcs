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
    fw, src = MOSFIRE.lsf_fwhm_pix(0.7)
    assert fw == pytest.approx(0.7 / 0.277) and 'D25' in src
    assert MOSFIRE.lsf_fwhm_pix(0.4)[0] == 2.2


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
    assert t['file'] == 'mosfire/throughput/mosfire_thru_2017-2025.ecsv' and t['warnings'] == []
    assert t['calib_version'] == 'mosfire-J-2026.10-dev' and t['era'] is MOSFIRE.eras[1]
    # eras without standards use the nearest era that has a curve
    for e in (MOSFIRE.eras[0], MOSFIRE.eras[2]):
        f = MOSFIRE.throughput(e)
        assert f['era'] is MOSFIRE.eras[1] and 'no throughput curve yet' in f['warnings'][0]


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
