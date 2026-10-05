"""Moffat slit loss and extraction aperture (design 5.3.5, D16, D26).

A circular Moffat PSF of FWHM ``s`` and index ``beta`` (3.5),

    I(r) = (beta - 1) / (pi alpha^2) [1 + (r/alpha)^2]^-beta,
    alpha = s / (2 sqrt(2^(1/beta) - 1)),

normalized to 1 over the plane. The slit is along ``y`` (length ``L`` of the
extraction aperture) and ``x`` is across it (width ``w``).

The slit x aperture integral is evaluated on a 0.01" grid in ``x`` (finer
for a PSF narrower than 0.2"; composite Simpson) with the ``y`` integral done
exactly for each column: for fixed ``x`` the Moffat is a Student-t-like profile whose integral
over ``|y| <= Y`` is an incomplete beta function. The infinite-slit
fraction is closed form, ``I_z(1/2, beta - 1)`` with
``z = (w/2)^2 / ((w/2)^2 + alpha^2)``. Results are cached by (FWHM, w, L).
"""
from functools import lru_cache

import numpy as np
from scipy.integrate import simpson
from scipy.special import beta as beta_fn, betainc

GRID_STEP = 0.01
"""Integration step across the slit [arcsec] (design 5.3.5)."""

BETA = 3.5
"""Default Moffat index (D26)."""


def moffat_alpha(fwhm, beta=BETA):
    """Moffat core radius alpha for a FWHM (same units)."""
    return fwhm / (2.0 * np.sqrt(2.0 ** (1.0 / beta) - 1.0))


def moffat_2d(x, y, fwhm, beta=BETA):
    """Normalized circular Moffat surface density at (x, y) [1/arcsec^2]."""
    a = moffat_alpha(fwhm, beta)
    return (beta - 1.0) / (np.pi * a ** 2) * (1.0 + (np.asarray(x) ** 2 + np.asarray(y) ** 2) / a ** 2) ** -beta


def moffat_marginal(x, fwhm, beta=BETA):
    """Integral of :func:`moffat_2d` over all y: the profile across an infinite slit [1/arcsec]."""
    a = moffat_alpha(fwhm, beta)
    u = 1.0 + np.asarray(x, float) ** 2 / a ** 2
    return (beta - 1.0) / (np.pi * a) * beta_fn(0.5, beta - 0.5) * u ** -(beta - 0.5)


def slit_fraction(fwhm, slit_width, beta=BETA):
    """Fraction of a centred Moffat passing an infinitely long slit of width ``slit_width``.

    Same signature as the provisional ``keck_etcs.calib.monitor.moffat_slit_fraction``.
    A zero-width source passes entirely.
    """
    if fwhm <= 0:
        return 1.0
    a = moffat_alpha(fwhm, beta)
    h2 = (slit_width / 2.0) ** 2
    return float(betainc(0.5, beta - 1.0, h2 / (h2 + a ** 2)))


def _y_integral(x, y_lo, y_hi, a, beta):
    """Integral over y in [y_lo, y_hi] of [1 + (x^2 + y^2)/a^2]^-beta, for arrays x."""
    c = a * np.sqrt(1.0 + x ** 2 / a ** 2)
    full = c * beta_fn(0.5, beta - 0.5) * (1.0 + x ** 2 / a ** 2) ** -beta

    def half(yv):   # signed integral from 0 to yv
        yv = np.asarray(yv, float)
        return np.sign(yv) * 0.5 * full * betainc(0.5, beta - 0.5, yv ** 2 / (yv ** 2 + c ** 2))

    return half(y_hi) - half(y_lo)


def _x_nodes(slit_width, fwhm):
    """Simpson nodes across the slit: an even number of 0.01" intervals (finer for a narrow PSF)."""
    step = min(GRID_STEP, fwhm / 20.0)
    n = max(2, int(np.ceil(slit_width / step - 1e-9)))
    n += n % 2
    return np.linspace(-slit_width / 2.0, slit_width / 2.0, n + 1)


@lru_cache(maxsize=4096)
def _slit_aperture_cached(fwhm, slit_width, length, beta):
    a = moffat_alpha(fwhm, beta)
    x = _x_nodes(slit_width, fwhm)
    norm = (beta - 1.0) / (np.pi * a ** 2)
    return float(norm * simpson(_y_integral(x, -length / 2.0, length / 2.0, a, beta), x=x))


def slit_aperture_fraction(fwhm, slit_width, length, beta=BETA):
    """f_slit_ap: fraction of a centred Moffat inside the slit (width) x aperture (length) rectangle."""
    if fwhm <= 0:
        return 1.0
    return _slit_aperture_cached(round(float(fwhm), 6), round(float(slit_width), 6),
                                 round(float(length), 6), float(beta))


def aperture_quantities(fwhm, slit_width, length, platescale, beta=BETA):
    """The slit-loss quantities of design 5.3.5 for a point source.

    Returns:
        dict: ``slit_fraction`` (x only), ``f_slit_ap`` (slit x aperture),
        ``aperture_fraction`` (= f_slit_ap / slit_fraction), ``f_peak`` (slit
        x one pixel at the profile peak, for saturation) and ``n_spatial_pix``
        (= ceil(L / p)).
    """
    fs = slit_fraction(fwhm, slit_width, beta)
    fsa = slit_aperture_fraction(fwhm, slit_width, length, beta)
    return {'slit_fraction': fs, 'f_slit_ap': fsa, 'aperture_fraction': fsa / fs if fs > 0 else 0.0,
            'f_peak': slit_aperture_fraction(fwhm, slit_width, platescale, beta),
            'n_spatial_pix': int(np.ceil(length / platescale - 1e-9))}


@lru_cache(maxsize=1024)
def _extended_cached(fwhm, slit_width, length, size, beta):
    a = moffat_alpha(fwhm, beta)
    r = size / 2.0
    step = min(fwhm / 4.0, max(GRID_STEP, size / 200.0))
    # quarter disk (the rectangle and the disk share both symmetry axes)
    n = max(1, int(np.ceil(r / step)))
    c = (np.arange(n) + 0.5) * (r / n)
    xs, ys = np.meshgrid(c, c, indexing='ij')
    keep = xs ** 2 + ys ** 2 <= r ** 2
    if not keep.any():
        keep[0, 0] = True
    xs, ys = xs[keep], ys[keep]
    x = _x_nodes(slit_width, fwhm)
    norm = (beta - 1.0) / (np.pi * a ** 2)
    frac = np.empty(xs.size)
    for k0 in range(0, xs.size, 2000):           # bounded memory: chunks of source points
        sx, sy = xs[k0:k0 + 2000, None], ys[k0:k0 + 2000, None]
        frac[k0:k0 + 2000] = norm * simpson(
            _y_integral(x[None, :] - sx, -length / 2.0 - sy, length / 2.0 - sy, a, beta), x=x, axis=1)
    return float(frac.mean())


def extended_fraction(fwhm, slit_width, length, size, beta=BETA):
    """Fraction of a uniform disk source's flux inside the slit x aperture rectangle.

    The source is a top-hat disk of diameter ``size`` (``source.size_arcsec``)
    convolved with the Moffat (D26). The disk's total flux is the surface
    brightness times pi size^2 / 4, so the flux in the aperture is
    ``SB * pi size^2 / 4 * extended_fraction``; for a disk much larger than
    the rectangle this tends to ``SB * w * L``. Computed as the mean, over the
    disk, of the point-source fraction of a Moffat offset to each point.
    """
    if size <= 0:
        return slit_aperture_fraction(fwhm, slit_width, length, beta)
    return _extended_cached(round(float(fwhm), 6), round(float(slit_width), 6),
                            round(float(length), 6), round(float(size), 6), float(beta))


def seeing_at(fwhm_ref, wave_A, seeing_wave_um=None):
    """Seeing FWHM at ``wave_A``, scaled as lambda^-0.2 from ``seeing_wave_um`` (D26).

    With ``seeing_wave_um`` None the FWHM is taken as given at the band.
    """
    if seeing_wave_um is None:
        return fwhm_ref
    return fwhm_ref * (np.asarray(wave_A, float) / (seeing_wave_um * 1e4)) ** -0.2
