"""Tests of keck_etcs.core.source, atmosphere, sky and lsf (design 5.3.1-5.3.8)."""
import numpy as np
import pytest

from keck_etcs.core import atmosphere, lsf, sky, source

# a J-like top-hat filter with soft edges
FW = np.linspace(11000.0, 14000.0, 3001)
FT = np.clip((200.0 - np.abs(FW - 12530.0) + 800.0) / 200.0, 0, 1) * 0.9


def test_flat_fnu_ab_mag_is_exact():
    wave = np.linspace(10000.0, 15000.0, 5001)
    f = source.normalize_to_mag(wave, source.shape_flambda(wave, 'flat_fnu'), FW, FT, 20.0)
    assert source.ab_mag(wave, f, FW, FT) == pytest.approx(20.0, abs=1e-10)
    # flat f_nu: f_nu = 10^(-0.4 (20 + 48.6)) at every wavelength
    np.testing.assert_allclose(f * wave ** 2 / source.C_A_PER_S, 10 ** (-0.4 * 68.6), rtol=1e-12)


def test_power_law_and_user_shapes():
    wave = np.linspace(10000.0, 15000.0, 11)
    np.testing.assert_allclose(source.shape_flambda(wave, 'power_law', alpha=0.0),
                               source.shape_flambda(wave, 'flat_fnu'))
    pl = source.shape_flambda(wave, 'power_law', alpha=-2.0)       # f_lambda constant
    np.testing.assert_allclose(pl, 1.0)
    u = source.shape_flambda(wave, 'user', user_wave=[12000, 11000, 13000], user_flux=[2, 1, 3])
    assert u[0] == 0.0 and u[4] == pytest.approx(2.0)
    f = source.normalize_to_mag(wave, pl, FW, FT, 18.0)
    assert source.ab_mag(wave, f, FW, FT) == pytest.approx(18.0, abs=1e-10)
    with pytest.raises(ValueError):
        source.shape_flambda(wave, 'line')


def test_vega_conversion():
    assert source.to_ab(15.0, 'AB', 0.91) == 15.0
    assert source.to_ab(15.0, 'Vega', 0.91) == pytest.approx(15.91)
    # Vega offset of a source with m_AB = 0.91 at m_Vega = 0
    wave = np.linspace(10000.0, 15000.0, 5001)
    f = source.normalize_to_mag(wave, source.shape_flambda(wave, 'flat_fnu'), FW, FT, 0.91)
    assert source.vega_offset(wave, f, FW, FT) == pytest.approx(0.91, abs=1e-10)


def test_gaussian_line_and_photon_rate():
    wave = np.arange(12700.0, 12900.0, 0.05)
    fwhm = source.line_fwhm_A(12800.0, 150.0)
    assert fwhm == pytest.approx(12800.0 * 150.0 / 299792.458)
    g = source.gaussian_line(wave, 12800.0, 1e-17, fwhm)
    assert np.trapezoid(g, wave) == pytest.approx(1e-17, rel=1e-9)
    # one erg/s/cm^2/A at 12500 A on 1 cm^2 is lam / hc photons/s/A
    assert source.photon_rate(12500.0, 1.0, 1.0) == pytest.approx(12500.0 / 1.98644586e-8)


GA = np.array([1.0, 1.5, 2.0] * 4)
GP = np.repeat([1.0, 1.6, 3.0, 5.0], 3)
VALS = np.stack([np.full(5, 10 * a + p) for a, p in zip(GA, GP)])   # each row tags its node


def test_grid_interpolation_at_nodes_and_between():
    for a, p in zip(GA, GP):
        spec, w = atmosphere.interp_grid(VALS, GA, GP, a, p)
        np.testing.assert_allclose(spec, 10 * a + p)
        assert w == []
    # linear in airmass
    spec, _ = atmosphere.interp_grid(VALS, GA, GP, 1.25, 1.6)
    np.testing.assert_allclose(spec, 12.5 + 1.6)
    # linear in log PWV: the geometric mean of 1.6 and 3.0 is half way
    pm = np.sqrt(1.6 * 3.0)
    spec, _ = atmosphere.interp_grid(VALS, GA, GP, 1.0, pm)
    np.testing.assert_allclose(spec, 10 + 0.5 * (1.6 + 3.0))


def test_grid_clipping_warns_and_names_the_field():
    spec, w = atmosphere.interp_grid(VALS, GA, GP, 2.4, 0.5)
    np.testing.assert_allclose(spec, 20 + 1.0)
    assert any(s.startswith('airmass 2.4 clipped to 2.0') for s in w)
    assert any(s.startswith('pwv_mm 0.5 clipped to 1.0') for s in w)
    t, _ = atmosphere.transmission(VALS / 100.0, GA, GP, 1.2, 1.6)
    assert np.all((t >= 0) & (t <= 1))
    with pytest.raises(ValueError):
        atmosphere.interp_grid(VALS[:11], GA[:11], GP[:11], 1.2, 1.6)


def test_sky_scale_and_rate_per_pixel():
    b, _ = sky.sky_background(VALS, GA, GP, 1.0, 1.0, sky_scale=0.5)
    np.testing.assert_allclose(b, 0.5 * 11.0)
    # 100 ph/s/arcsec^2/nm/m^2 = 10 per A; x 72.3674 m^2 x 0.3 x 0.7" x 0.1798" x 1.3 A
    rate = sky.sky_rate_per_pixel(100.0, 72.3674, 0.3, 0.7, 0.1798, 1.3)
    assert rate == pytest.approx(10 * 72.3674 * 0.3 * 0.7 * 0.1798 * 1.3)
    assert sky.sky_in_aperture(rate, 6, 120.0) == pytest.approx(rate * 6 * 120.0)


def test_lsf_width_rules():
    assert lsf.fwhm_pix(1.0, 0.277, 2.2) == pytest.approx(1.0 / 0.277)
    assert lsf.fwhm_pix(0.3, 0.277, 2.2) == 2.2
    assert lsf.fwhm_pix(1.0, 0.277, 2.2, measured=3.606) == 3.606
    assert lsf.fwhm_pix(0.7, 0.292, 1.08, form='quadrature') == pytest.approx(np.hypot(0.7 / 0.292, 1.08))
    with pytest.raises(ValueError):
        lsf.fwhm_pix(0.7, 0.292, 1.08, form='other')
    assert lsf.resolving_power(12500.0, 3.606 * 1.3) == pytest.approx(12500.0 / (3.606 * 1.3))
    assert lsf.observed_line_fwhm(3.0, 4.0) == pytest.approx(5.0)
    g = lsf.pixel_grid(11530.0, 13520.0, 1.3)
    assert g[0] == 11530.0 and g[-1] <= 13520.0 < g[-1] + 1.3


def test_gaussian_convolution():
    wave = np.arange(12000.0, 12400.0, 0.5)
    flux = np.zeros_like(wave)
    flux[400] = 1.0 / 0.5                                  # a unit-flux delta at 12200 A
    conv = lsf.gaussian_convolve(wave, flux, 4.68)
    assert np.trapezoid(conv, wave) == pytest.approx(1.0, rel=1e-9)
    above = wave[conv >= conv.max() / 2]
    assert above[-1] - above[0] == pytest.approx(4.68, abs=1.0)          # half-max span, quantized to the 0.5 A grid
    sig = np.sqrt(np.sum(conv * (wave - 12200.0) ** 2) / np.sum(conv))
    assert sig * 2 * np.sqrt(2 * np.log(2)) == pytest.approx(4.68, rel=1e-3)
    # a constant stays constant, to the edges
    np.testing.assert_allclose(lsf.gaussian_convolve(wave, np.full_like(wave, 3.0), 4.68), 3.0, rtol=1e-12)
    with pytest.raises(ValueError):
        lsf.gaussian_convolve(wave[[0, 1, 3]], flux[[0, 1, 3]], 4.68)
    # sampling on pixels, from a non-uniform grid
    pix = lsf.pixel_grid(12100.0, 12300.0, 1.3)
    wn = np.sort(np.concatenate([wave, wave[:-1] + 0.2]))
    out = lsf.convolve_to_pixels(wn, np.full_like(wn, 2.0), 4.68, pix)
    np.testing.assert_allclose(out, 2.0, rtol=1e-9)
