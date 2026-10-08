"""Line-spread function, resolving power and sampling on the pixel grid (design 5.3.6, D25).

The LSF is a Gaussian of ``FWHM_pix = max(w / slope, floor)`` pixels (form
``'max'``) or ``sqrt((w / slope)^2 + floor^2)`` (form ``'quadrature'``; MOSFIRE
since the first calibration release, D25), or the measured width for that
slit where the instrument has one. Source spectrum,
sky, transmission and throughput are all convolved with it and then sampled
at the pixel centres ``wave_A``.
"""
import numpy as np

SIGMA_PER_FWHM = 1.0 / (2.0 * np.sqrt(2.0 * np.log(2.0)))
KERNEL_HALFWIDTH_SIGMA = 5.0


def fwhm_pix(slit_width, slope, floor, measured=None, form='max'):
    """LSF FWHM in pixels: ``measured`` if given, else the D25 rule of ``form``.

    ``form = 'max'``: ``max(slit_width / slope, floor)``; ``form = 'quadrature'``:
    ``sqrt((slit_width / slope)^2 + floor^2)``.

    Args:
        slit_width (float): Slit width [arcsec].
        slope (float): Slit width per pixel of LSF FWHM [arcsec/pix]
            (MOSFIRE interim 0.277).
        floor (float): Minimum FWHM [pix] (MOSFIRE 2.2).
        measured (float, optional): Measured FWHM for this slit width [pix].
        form (str): ``'max'`` or ``'quadrature'``.
    """
    if measured is not None:
        return float(measured)
    if form == 'quadrature':
        return float(np.hypot(float(slit_width) / slope, float(floor)))
    if form != 'max':
        raise ValueError(f'unknown LSF form {form!r}')
    return max(float(slit_width) / slope, float(floor))


def resolving_power(wave_A, fwhm_A):
    """R = lam / FWHM_lsf."""
    return np.asarray(wave_A, float) / fwhm_A


def observed_line_fwhm(fwhm_line_A, fwhm_lsf_A):
    """Observed FWHM of a Gaussian line, sqrt(FWHM_line^2 + FWHM_lsf^2) [A]."""
    return float(np.hypot(fwhm_line_A, fwhm_lsf_A))


def pixel_grid(wave_lo, wave_hi, dlam):
    """Pixel-centre wavelengths from ``wave_lo`` in steps of ``dlam`` up to ``wave_hi``."""
    n = int(np.floor((wave_hi - wave_lo) / dlam + 1e-9)) + 1
    return wave_lo + dlam * np.arange(n)


def _is_uniform(wave, rtol=1e-6):
    d = np.diff(wave)
    return d.size > 0 and np.all(d > 0) and np.ptp(d) <= rtol * np.abs(d).max()


def gaussian_convolve(wave, flux, fwhm_A):
    """Convolve a spectrum on a uniform wavelength grid with a Gaussian of FWHM ``fwhm_A``.

    Edges are renormalized by the convolved unit spectrum, so a constant stays
    constant up to the ends of the grid.
    """
    wave, flux = np.asarray(wave, float), np.asarray(flux, float)
    if not _is_uniform(wave):
        raise ValueError('gaussian_convolve needs a uniform, increasing wavelength grid')
    step = wave[1] - wave[0]
    sigma = fwhm_A * SIGMA_PER_FWHM / step
    if sigma < 0.1:
        return flux.copy()
    half = int(np.ceil(KERNEL_HALFWIDTH_SIGMA * sigma))
    k = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma) ** 2)
    k /= k.sum()
    from scipy.signal import fftconvolve
    num = fftconvolve(flux, k, mode='same')
    den = fftconvolve(np.ones_like(flux), k, mode='same')
    return num / den


def convolve_to_pixels(wave, flux, fwhm_A, wave_pix):
    """Convolve with the LSF and sample at the pixel centres ``wave_pix``.

    A non-uniform input grid is first interpolated onto a uniform one with a
    step of the smaller of its median step and FWHM/10. Values outside the
    input range are 0.
    """
    wave, flux = np.asarray(wave, float), np.asarray(flux, float)
    if not _is_uniform(wave):
        srt = np.argsort(wave)
        wave, flux = wave[srt], flux[srt]
        step = min(np.median(np.diff(wave)), fwhm_A / 10.0)
        grid = np.arange(wave[0], wave[-1] + step / 2, step)
        flux, wave = np.interp(grid, wave, flux), grid
    conv = gaussian_convolve(wave, flux, fwhm_A)
    return np.interp(np.asarray(wave_pix, float), wave, conv, left=0.0, right=0.0)
