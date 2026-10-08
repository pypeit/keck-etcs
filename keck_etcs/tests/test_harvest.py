"""Unit tests for keck_etcs.calib.harvest helpers that need no data files."""
import numpy as np
import pytest

from keck_etcs.calib import harvest as hv


def test_slit_from_decker():
    assert hv.slit_from_decker('LONGSLIT-46x5') == (5.0, 46.0)
    assert hv.slit_from_decker('LONGSLIT-3x0.7') == (0.7, 3.0)
    assert hv.slit_from_decker('long2pos') == (None, None)


def test_std_class():
    assert hv.std_class_of('lds749b_stisnic_008.fits.gz') == 'WD'
    assert hv.std_class_of('vega_model_J=7.1') == 'A0V'


def test_throughput_curve_grid_and_consistency():
    pytest.importorskip('pypeit')
    wave = np.linspace(11170.3, 12599.7, 700)
    zp = 19.0 + 1e-4 * (wave - 11170.0)
    curve = hv.throughput_curve(wave, zp)
    # common 1 A grid on integer Angstrom, inside the fitted range
    assert curve['wave'][0] == 11171.0 and curve['wave'][-1] == 12599.0
    assert np.all(np.diff(curve['wave']) == 1.0)
    # thru_raw is exactly the recomputed throughput; no filter -> thru masked
    assert np.allclose(curve['thru_raw'], hv.zeropoint_to_throughput(curve['wave'], curve['zeropoint']),
                       rtol=1e-12)
    assert np.all(curve['thru'].mask)
    assert hv.zp_at(curve, 13000.0) is None
    assert hv.zp_at(curve, 12000.0) == pytest.approx(19.0 + 1e-4 * 830.0)


def test_throughput_curve_filter_division():
    pytest.importorskip('pypeit')
    wave = np.linspace(11170.3, 12599.7, 700)
    curve = hv.throughput_curve(wave, np.full(wave.size, 19.0),
                                filter_wave=np.array([11000.0, 13000.0]),
                                filter_trans=np.array([0.5, 0.5]))
    assert not np.any(curve['thru'].mask)
    assert np.allclose(curve['thru'], curve['thru_raw'] / 0.5)


def test_row_table_masks_none():
    row = {c: None for c in hv.ROW_COLUMNS}
    row.update({'standard': 'LDS749B', 'date': '2022-04-09', 'koa_id': 'MF.1', 'zp_1200': 19.6,
                'flag': 'nofilter'})
    t = hv.row_table([row])
    assert list(t.colnames) == list(hv.ROW_COLUMNS)
    assert np.ma.is_masked(t['zp_1300'][0]) and t['zp_1200'][0] == 19.6
    assert str(t['zp_1200'].unit) == 'mag'


def test_standard_peak_adu(tmp_path):
    from astropy.io import fits
    img = np.full((2048, 2048), 100.0, dtype=np.float32)
    img[1000:1006, :] = 40000.0      # a saturated trace at rows 1000-1005
    img[500:506, :] = 9000.0         # a faint one at rows 500-505
    fits.PrimaryHDU(img).writeto(tmp_path / 'a.fits')
    fits.PrimaryHDU(img).writeto(tmp_path / 'b.fits')
    obj = lambda f, s, **kw: {'frame': f, 'sign': 'positive', 'spat_pixpos': s, **kw}
    m = {'objects': [obj('a.fits', 1002.5), obj('b.fits', 502.5)]}
    assert hv.standard_peak_adu(m, ['b.fits'], tmp_path) == pytest.approx(9000.0)
    assert hv.standard_peak_adu(m, ['a.fits', 'b.fits'], tmp_path) == pytest.approx(40000.0)
    assert hv.standard_peak_adu(m, ['missing.fits'], tmp_path) is None
    # long2pos_specphot: only the objects the sensfunc used
    m = {'specphot': {'wide': [1]}, 'objects': [obj('a.fits', 1002.5, specphot_use=False),
                                                obj('b.fits', 502.5, specphot_use=True)]}
    assert hv.standard_peak_adu(m, ['a.fits', 'b.fits'], tmp_path) == pytest.approx(9000.0)
