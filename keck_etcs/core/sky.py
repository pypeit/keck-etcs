"""Sky emission lookup and per-pixel sky rates (design 5.3.8, D14, N6).

The Gemini background ``B(lam; X, PWV)`` is in photons/s/arcsec^2/nm/m^2 as
seen from the ground, so the atmospheric transmission is never applied to it
(N6).
"""
import numpy as np

from keck_etcs.core.atmosphere import interp_grid


def sky_background(sky_grid, grid_airmass, grid_pwv, airmass, pwv_mm, sky_scale=1.0):
    """Sky background ``sky_scale * B(lam; X, PWV)`` on the grid's wavelengths.

    Returns:
        tuple: ``(B, warnings)``, B in photons/s/arcsec^2/nm/m^2.
    """
    b, warnings = interp_grid(sky_grid, grid_airmass, grid_pwv, airmass, pwv_mm)
    return sky_scale * np.clip(b, 0.0, None), warnings


def sky_rate_per_pixel(B_nm, area_m2, T_sys, slit_width_arcsec, platescale, dlam):
    """Sky electrons per second per (spatial pixel, spectral pixel), b(lam) of 5.3.8.

    ``b = B / 10 [per A] * A_m2 * T_sys * w * p * dlam``.

    Args:
        B_nm (array): Sky (already scaled and LSF-convolved) on the pixel
            grid [photons/s/arcsec^2/nm/m^2].
        area_m2 (float): Effective collecting area [m^2].
        T_sys (array): System throughput on the pixel grid.
        slit_width_arcsec (float): Slit width w [arcsec].
        platescale (float): Spatial plate scale p [arcsec/pix].
        dlam (float or array): Dispersion [A/pix].

    Returns:
        numpy.ndarray: e-/s per spatial pixel per spectral pixel.
    """
    return np.asarray(B_nm, float) / 10.0 * area_m2 * np.asarray(T_sys, float) \
        * slit_width_arcsec * platescale * dlam


def sky_in_aperture(b, n_spat, exptime):
    """Sky electrons per spectral pixel per frame in the aperture, B_ap = b n_spat t."""
    return np.asarray(b, float) * n_spat * exptime
