"""Unit tests for keck_etcs.calib.monitor helpers that need no data files."""
import numpy as np
import pytest

from keck_etcs.calib import monitor as mo
from keck_etcs.calib import monitor_configs as mc


def test_object_fwhm_uses_core_slit_fraction():
    # the provisional copy is gone; the D26 integral lives in keck_etcs.core.slitloss
    from keck_etcs.core import slitloss
    assert mo.slit_fraction is slitloss.slit_fraction
    assert not hasattr(mo, 'moffat_slit_fraction')


def test_sky_line_fwhm_uses_interim_slope_and_floor():
    assert mo.sky_line_fwhm_A(1.0, 1.3) == pytest.approx(1.0 / 0.277 * 1.3)
    assert mo.sky_line_fwhm_A(0.3, 1.3) == pytest.approx(2.2 * 1.3)   # floor


def test_line_sum_total_and_continuum():
    # one row, flat continuum 2 plus a Gaussian line at 12000 A (0.5 A samples)
    wave = np.linspace(11900.0, 12100.0, 401)
    line = 100.0 / (np.sqrt(2 * np.pi) * 2.0) * np.exp(-0.5 * ((wave - 12000.0) / 2.0) ** 2) * 0.5
    img = (2.0 + line)[:, None]
    waveimg = wave[:, None]
    rows_ok = np.array([True])
    tot, n = mo._line_sum(img, waveimg, rows_ok, 12000.0, 4.7, continuum=False)
    sub, _ = mo._line_sum(img, waveimg, rows_ok, 12000.0, 4.7, continuum=True)
    assert n == 1
    # the flank continuum includes a little of the line's wings: agree to 0.1%
    assert sub[0] == pytest.approx(np.sum(line[np.abs(wave - 12000) <= 1.5 * 4.7]), rel=1e-3)
    assert tot[0] > sub[0]          # the total includes the continuum


def test_monitor_table_dtypes_and_masks():
    rows = [mo.row(night='20220409', metric='flat_rate', value=1.5, n=3, wave_A=11250.0),
            mo.row(night='20220409', metric='monitor_error', flag='monitor_failed')]
    t = mo.monitor_table(rows)
    assert list(t.colnames) == list(mo.TABLE_COLUMNS)
    assert t['value'][0] == 1.5 and np.ma.is_masked(t['value'][1])
    assert t['flag'][1] == 'monitor_failed'


def test_mosfire_config():
    cfg = mc.get_config('keck_mosfire')
    assert cfg['flat_nodes']['J2'] == (11250.0, 11500.0, 11750.0, 12000.0, 12250.0, 12500.0)
    assert len(cfg['flat_nodes']['J']) == 8
    assert 4 <= len(cfg['monitor_lines']['OH']['J2']) <= 6
    assert cfg['monitor_lines_status'] == 'provisional'
    with pytest.raises(KeyError):
        mc.get_config('keck_lris_red')
