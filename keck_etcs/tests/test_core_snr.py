"""Analytic tests of keck_etcs.core.snr and keck_etcs.core.detector (design 6.2)."""
import numpy as np
import pytest

from keck_etcs.core import detector, snr

# MOSFIRE read-noise table (design section 3; Keck detector page). S8 ships it
# as keck_etcs/data/mosfire/detector.ecsv.
RN_N = (1, 4, 8, 16, 32, 64, 128)
RN_E = (21.0, 10.8, 7.7, 5.8, 4.2, 3.5, 3.0)
LIMITS = (26000.0, 37000.0, 43000.0)


def test_poisson_only_limit():
    S = np.array([1.0, 100.0, 1e4])
    var1 = snr.frame_variance(S, B_ap=0.0, dark_e=0.0, rn2=0.0, nod='ABBA')
    np.testing.assert_allclose(snr.snr_pixel(S, var1, 1), np.sqrt(S), rtol=1e-12)
    np.testing.assert_allclose(snr.snr_pixel(S, var1, 9), 3 * np.sqrt(S), rtol=1e-12)


def test_abba_is_stare_plus_background():
    S, B, D, R2 = np.array([50.0, 500.0]), np.array([300.0, 10.0]), 4.0, 36.0
    stare = snr.frame_variance(S, B, D, R2, 'stare')
    abba = snr.frame_variance(S, B, D, R2, 'ABBA')
    np.testing.assert_allclose(stare, S + B + D + R2)
    np.testing.assert_allclose(abba - stare, B + D + R2)
    with pytest.raises(ValueError):
        snr.frame_variance(S, B, D, R2, 'ABAB')


def test_snr_resel():
    assert snr.snr_resel(10.0, 4.0) == pytest.approx(20.0)


@pytest.mark.parametrize('nod', ['stare', 'ABBA'])
def test_exptime_solver_round_trip(nod):
    rng = np.random.default_rng(1)
    s = rng.uniform(0.5, 50.0, 200)          # e-/s per pixel
    beta = rng.uniform(1.0, 400.0, 200)      # sky e-/s in the aperture
    d, r2, nf, rho = 0.05, 6 * 5.8 ** 2, 4, 10.0
    t = snr.solve_exptime(rho, s, beta, d, r2, nf, nod)
    np.testing.assert_allclose(snr.snr_at(t, s, beta, d, r2, nf, nod), rho, rtol=1e-6)
    tm = snr.solve_exptime_median(rho, s, beta, d, r2, nf, nod)
    assert np.median(snr.snr_at(tm, s, beta, d, r2, nf, nod)) == pytest.approx(rho, rel=1e-6)
    # scalar in, scalar out; no signal means no finite time
    assert isinstance(snr.solve_exptime(rho, 3.0, 10.0, d, r2, nf, nod), float)
    assert snr.solve_exptime(rho, 0.0, 10.0, d, r2, nf, nod) == np.inf


def test_exptime_read_noise_limit():
    # no source shot noise, no sky or dark: N s^2 t^2 = rho^2 k r2  ->  t = rho sqrt(k r2 / N) / s
    s, r2, nf, rho = 2.0, 100.0, 4, 5.0
    t = snr.solve_exptime(rho, s, 0.0, 0.0, r2, nf, 'ABBA')
    # the source term adds rho^2 s t, so solve the full quadratic by hand
    a, b, c = nf * s ** 2, rho ** 2 * s, 2 * rho ** 2 * r2
    assert t == pytest.approx((b + np.sqrt(b ** 2 + 4 * a * c)) / (2 * a), rel=1e-12)


def test_line_snr_window():
    wave = np.arange(12000.0, 12010.0, 1.0)
    mask = snr.line_window(wave, 12004.5, 3.0)          # 12003-12006
    assert mask.sum() == 4
    S, V = np.ones(10) * 4.0, np.ones(10) * 4.0
    assert snr.line_snr(S, V, mask) == pytest.approx(16.0 / np.sqrt(16.0))
    assert snr.LINE_WINDOW_FRACTION == pytest.approx(0.761, abs=5e-4)


def test_read_noise_table():
    assert detector.read_noise(16, RN_N, RN_E) == pytest.approx(5.8)
    assert detector.read_noise(1, RN_N, RN_E) == pytest.approx(21.0)
    # linear in log2 N between 8 and 16
    assert detector.read_noise(12, RN_N, RN_E) == pytest.approx(7.7 + (5.8 - 7.7) * (np.log2(12) - 3))
    # 2 reads lies between CDS (1) and MCDS-4
    assert detector.read_noise(2, RN_N, RN_E) == pytest.approx(21.0 + (10.8 - 21.0) * 0.5)
    assert detector.effective_reads('CDS', 16) == (1, ['readout.n_reads 16 ignored for CDS (uses 1)'])
    assert detector.effective_reads('MCDS', 16) == (16, [])


def test_linearity_flags_and_saturation_peak():
    assert [detector.linearity_flag(a, LIMITS) for a in (1e3, 26000, 40000, 5e4)] == \
        ['ok', 'nonlinear_1pct', 'nonlinear_5pct', 'saturated']
    wave = np.array([12000.0, 12001.3, 12002.6])
    b = np.array([1.0, 500.0, 1.0])           # an OH line in the middle pixel
    out = snr.saturation_peak(wave, N0=np.ones(3) * 1e3, T_atm=1.0, T_sys=0.3, f_peak=0.14, dlam=1.3,
                              exptime=120.0, b=b, dark_rate=0.008, gain=2.15, limits=LIMITS)
    assert out['wave_A'] == 12001.3
    assert out['peak_e_per_frame'] == pytest.approx(1e3 * 0.3 * 0.14 * 1.3 * 120 + 500 * 120 + 0.008 * 120)
    assert out['peak_adu_per_frame'] == pytest.approx(out['peak_e_per_frame'] / 2.15)
    assert out['flag'] == 'nonlinear_1pct'
