"""Source spectra, AB/Vega magnitudes and normalization to a filter (design 5.3.1-5.3.2).

All spectra are f_lambda in erg/s/cm^2/A on vacuum wavelengths in A. Filter
curves are passed as ``(filt_wave, filt_trans)`` arrays.
"""
import numpy as np

C_A_PER_S = 2.99792458e18
"""Speed of light [A/s]."""

C_KM_PER_S = 2.99792458e5
"""Speed of light [km/s]."""

HC_ERG_A = 1.98644586e-8
"""Planck constant times the speed of light [erg A]."""

AB_ZEROPOINT = 48.6
"""m_AB = -2.5 log10(f_nu [erg/s/cm^2/Hz]) - 48.6."""

SHAPES = ('flat_fnu', 'power_law', 'user', 'line')


def shape_flambda(wave, shape, alpha=0.0, user_wave=None, user_flux=None):
    """Un-normalized continuum shape f_lambda on ``wave``.

    Args:
        wave (array): Wavelengths [A].
        shape (str): ``flat_fnu`` (f_lambda ~ lam^-2), ``power_law``
            (f_nu ~ nu^alpha, i.e. f_lambda ~ lam^-(alpha+2)) or ``user``.
            ``line`` has no continuum shape; use :func:`gaussian_line`.
        alpha (float): Power-law index of f_nu in nu.
        user_wave, user_flux (array): User spectrum (f_lambda in any units),
            linearly interpolated; zero outside its range.

    Returns:
        numpy.ndarray: f_lambda in arbitrary units.
    """
    wave = np.asarray(wave, float)
    if shape == 'flat_fnu':
        return (wave / 1e4) ** -2
    if shape == 'power_law':
        return (wave / 1e4) ** -(alpha + 2.0)
    if shape == 'user':
        uw, uf = np.asarray(user_wave, float), np.asarray(user_flux, float)
        srt = np.argsort(uw)
        return np.interp(wave, uw[srt], uf[srt], left=0.0, right=0.0)
    raise ValueError(f'no continuum shape for {shape!r}; one of flat_fnu, power_law, user')


def _on_filter_grid(wave, flam, filt_wave, filt_trans):
    fw, ft = np.asarray(filt_wave, float), np.asarray(filt_trans, float)
    srt = np.argsort(fw)
    fw, ft = fw[srt], np.clip(ft[srt], 0.0, None)
    w = np.asarray(wave, float)
    f = np.interp(fw, w, np.asarray(flam, float), left=0.0, right=0.0)
    return fw, ft, f


def mean_fnu(wave, flam, filt_wave, filt_trans):
    """Filter-weighted mean f_nu, int f_nu F dnu / int F dnu (design 5.3.1).

    With f_nu = f_lambda lam^2 / c and dnu = c dlam / lam^2, the numerator is
    int f_lambda F dlam and the denominator int F c / lam^2 dlam. This is the
    energy-weighted definition of the design; the photon-counting one would
    weight both integrals by 1/nu.

    Returns:
        float: Mean f_nu [erg/s/cm^2/Hz] for f_lambda in erg/s/cm^2/A.
    """
    fw, ft, f = _on_filter_grid(wave, flam, filt_wave, filt_trans)
    return np.trapezoid(f * ft, fw) / np.trapezoid(ft * C_A_PER_S / fw ** 2, fw)


def ab_mag(wave, flam, filt_wave, filt_trans):
    """Synthetic AB magnitude of f_lambda [erg/s/cm^2/A] through a filter."""
    return -2.5 * np.log10(mean_fnu(wave, flam, filt_wave, filt_trans)) - AB_ZEROPOINT


def vega_offset(vega_wave, vega_flam, filt_wave, filt_trans):
    """(m_AB - m_Vega) for a filter: the synthetic AB magnitude of Vega (m_Vega = 0)."""
    return ab_mag(vega_wave, vega_flam, filt_wave, filt_trans)


def to_ab(mag, mag_system, offset=0.0):
    """Convert a magnitude to AB; ``offset`` is (m_AB - m_Vega) of the band."""
    if mag_system == 'AB':
        return float(mag)
    if mag_system == 'Vega':
        return float(mag) + float(offset)
    raise ValueError(f'mag_system must be AB or Vega, got {mag_system!r}')


def normalize_to_mag(wave, flam, filt_wave, filt_trans, mag_ab):
    """Scale f_lambda so that its synthetic AB magnitude through the filter is ``mag_ab``.

    Returns:
        numpy.ndarray: f_lambda [erg/s/cm^2/A] (or per arcsec^2 for a surface
        brightness).
    """
    flam = np.asarray(flam, float)
    fnu = mean_fnu(wave, flam, filt_wave, filt_trans)
    if not fnu > 0:
        raise ValueError('the spectrum has no flux in the filter')
    target = 10 ** (-0.4 * (mag_ab + AB_ZEROPOINT))
    return flam * (target / fnu)


def line_fwhm_A(center_A, fwhm_kms):
    """Intrinsic line FWHM in A for a velocity FWHM in km/s."""
    return center_A * fwhm_kms / C_KM_PER_S


def gaussian_line(wave, center_A, flux_cgs, fwhm_A):
    """Gaussian emission line of integrated flux ``flux_cgs`` [erg/s/cm^2] as f_lambda."""
    sigma = fwhm_A / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    x = (np.asarray(wave, float) - center_A) / sigma
    return flux_cgs / (np.sqrt(2.0 * np.pi) * sigma) * np.exp(-0.5 * x ** 2)


def photon_rate(wave, flam, area_cm2):
    """Photon rate above the atmosphere N0 = f_lambda A lam / (h c) [photons/s/A] (5.3.2)."""
    return np.asarray(flam, float) * area_cm2 * np.asarray(wave, float) / HC_ERG_A
