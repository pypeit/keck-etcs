"""Analytic tests of keck_etcs.core.slitloss (design 5.3.5, 6.2)."""
import numpy as np
import pytest

from keck_etcs.core import slitloss as sl


def test_moffat_alpha_gives_fwhm():
    for fwhm, beta in [(0.7, 3.5), (1.3, 2.5)]:
        half = sl.moffat_2d(fwhm / 2, 0.0, fwhm, beta) / sl.moffat_2d(0.0, 0.0, fwhm, beta)
        assert half == pytest.approx(0.5, rel=1e-12)


def test_moffat_plane_integral_is_one():
    # direct 2-D sum on a 0.01" grid over a box holding all but ~1e-6 of the flux
    fwhm, step, half = 0.5, 0.01, 7.0
    c = np.arange(-half + step / 2, half, step)
    xx, yy = np.meshgrid(c, c, indexing='ij')
    assert np.sum(sl.moffat_2d(xx, yy, fwhm)) * step ** 2 == pytest.approx(1.0, abs=1e-4)
    # the semi-analytic slit x aperture integral over a large rectangle
    assert sl.slit_aperture_fraction(0.7, 40.0, 40.0) == pytest.approx(1.0, abs=1e-4)
    # the marginal integrates to one
    x = np.arange(-60.0, 60.0, 0.005) + 0.0025
    assert np.sum(sl.moffat_marginal(x, 0.7)) * 0.005 == pytest.approx(1.0, abs=1e-4)


def test_zero_width_source_passes_entirely():
    assert sl.slit_fraction(0.0, 0.7) == 1.0
    assert sl.slit_aperture_fraction(0.0, 0.7, 1.0) == 1.0
    assert sl.slit_fraction(1e-4, 0.3) == pytest.approx(1.0, abs=1e-6)
    assert sl.slit_aperture_fraction(1e-3, 0.3, 0.5) == pytest.approx(1.0, abs=1e-5)


def test_closed_form_slit_matches_long_aperture():
    for fwhm, w in [(0.5, 0.3), (0.7, 0.7), (0.9, 1.0), (2.0, 5.0)]:
        assert sl.slit_aperture_fraction(fwhm, w, 400.0) == pytest.approx(sl.slit_fraction(fwhm, w), abs=2e-6)


def test_aperture_quantities():
    q = sl.aperture_quantities(0.7, 0.7, 1.05, 0.1798)
    assert q['n_spatial_pix'] == 6
    assert q['f_slit_ap'] == pytest.approx(q['slit_fraction'] * q['aperture_fraction'])
    assert 0 < q['f_peak'] < q['f_slit_ap'] < q['slit_fraction'] < 1
    # monotonic in slit width and aperture length
    assert sl.slit_fraction(0.7, 1.0) > sl.slit_fraction(0.7, 0.7)
    assert sl.slit_aperture_fraction(0.7, 0.7, 2.0) > q['f_slit_ap']


def test_extended_source_limits():
    # a vanishing disk is a point source
    assert sl.extended_fraction(0.7, 0.7, 1.05, 0.0) == sl.slit_aperture_fraction(0.7, 0.7, 1.05)
    assert sl.extended_fraction(0.7, 0.7, 1.05, 0.02) == pytest.approx(
        sl.slit_aperture_fraction(0.7, 0.7, 1.05), rel=1e-3)
    # a disk much larger than the aperture: flux in the aperture -> SB * w * L
    D, w, L = 20.0, 0.7, 3.0
    assert sl.extended_fraction(0.7, w, L, D) * np.pi * D ** 2 / 4 == pytest.approx(w * L, rel=1e-3)
    # a larger disk puts a smaller fraction of its flux in the aperture
    assert sl.extended_fraction(0.7, w, L, 2.0) < sl.extended_fraction(0.7, w, L, 1.0)


def test_seeing_scaling():
    assert sl.seeing_at(0.7, 12500.0) == 0.7
    assert sl.seeing_at(0.7, 12500.0, seeing_wave_um=0.5) == pytest.approx(0.7 * 2.5 ** -0.2)
