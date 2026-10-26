"""Signal, noise, S/N and the exposure-time inversion (design 5.3.7, 5.3.10, 5.3.11, D15, D17, N7).

Per spectral pixel and per frame, in electrons summed over the extraction
aperture: ``S`` source, ``B_ap`` sky, ``n_spat D t`` dark and
``n_spat RN^2`` read variance. ``stare`` has one sky-free frame; ``ABBA``
differences each frame against an equal-time sky frame, which doubles the
background, dark and read-noise variance (D15).
"""
import numpy as np

NOD_FACTOR = {'stare': 1.0, 'ABBA': 2.0}
LINE_WINDOW_FRACTION = 0.7609681085
"""Flux fraction of a Gaussian within +/- FWHM/2, erf(sqrt(ln 2))."""


def nod_factor(nod):
    """Background-variance multiplier k: 1 for ``stare``, 2 for ``ABBA``."""
    try:
        return NOD_FACTOR[nod]
    except KeyError:
        raise ValueError(f'nod must be one of {tuple(NOD_FACTOR)}, got {nod!r}') from None


def signal_per_pixel(N0, T_atm, T_sys, f_ap, dlam, exptime):
    """Source electrons per spectral pixel per frame, S = N0 T_atm T_sys f_slit_ap dlam t (5.3.7)."""
    return np.asarray(N0, float) * T_atm * T_sys * f_ap * dlam * exptime


def frame_variance(S, B_ap, dark_e, rn2, nod):
    """Variance per spectral pixel of one frame (5.3.10).

    Args:
        S (array): Source electrons per frame.
        B_ap (array): Sky electrons per frame in the aperture.
        dark_e (float): Dark electrons in the aperture per frame, n_spat D t.
        rn2 (float): Read variance in the aperture per frame, n_spat RN^2.
        nod (str): ``stare`` or ``ABBA``.
    """
    return np.asarray(S, float) + nod_factor(nod) * (np.asarray(B_ap, float) + dark_e + rn2)


def snr_pixel(S, var1, n_frames):
    """S/N per pixel over ``n_frames`` frames, sqrt(N_f) S / sqrt(var_1)."""
    S, var1 = np.asarray(S, float), np.asarray(var1, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(var1 > 0, np.sqrt(n_frames) * S / np.sqrt(var1), 0.0)


def snr_resel(snr_pix, n_spec):
    """S/N per resolution element, SNR_pix sqrt(n_spec) (5.3.10)."""
    return np.asarray(snr_pix, float) * np.sqrt(n_spec)


def line_window(wave_A, center_A, fwhm_obs_A):
    """Boolean mask of the pixels within +/- FWHM_obs/2 of the line centre."""
    return np.abs(np.asarray(wave_A, float) - center_A) <= fwhm_obs_A / 2.0


def line_snr(S_tot, var_tot, mask):
    """S/N of the summed line window: sum(S_tot) / sqrt(sum(var_tot))."""
    s, v = float(np.sum(np.asarray(S_tot)[mask])), float(np.sum(np.asarray(var_tot)[mask]))
    return s / np.sqrt(v) if v > 0 else 0.0


def solve_exptime(rho, s, beta, d, r2, n_frames, nod):
    """Per-frame exposure time giving S/N ``rho`` over ``n_frames`` frames (5.3.10, N7).

    Solves ``N_f s^2 t^2 - rho^2 (s + k beta + k d) t - k rho^2 r2 = 0`` for
    its positive root.

    Args:
        rho (float): Target S/N (per pixel; divide by sqrt(n_spec) first for
            per-resel; for a line pass the window sums).
        s (array): Source rate [e-/s] per pixel (S / t).
        beta (array): Sky rate in the aperture [e-/s] (B_ap / t).
        d (float or array): Dark rate in the aperture [e-/s], n_spat D.
        r2 (float or array): Read variance in the aperture per frame, n_spat RN^2.
        n_frames (int): Number of frames.
        nod (str): ``stare`` or ``ABBA``.

    Returns:
        numpy.ndarray or float: t [s]; inf where s <= 0.
    """
    k = nod_factor(nod)
    s, beta = np.asarray(s, float), np.asarray(beta, float)
    b = rho ** 2 * (s + k * beta + k * np.asarray(d, float))
    a = n_frames * s ** 2
    with np.errstate(divide='ignore', invalid='ignore'):
        t = (b + np.sqrt(b ** 2 + 4.0 * a * k * rho ** 2 * np.asarray(r2, float))) / (2.0 * a)
    t = np.where(s > 0, t, np.inf)
    return float(t) if t.ndim == 0 else t


def snr_at(t, s, beta, d, r2, n_frames, nod):
    """S/N per pixel for per-frame time ``t`` from rates (the forward model of :func:`solve_exptime`)."""
    var1 = frame_variance(np.asarray(s, float) * t, np.asarray(beta, float) * t, np.asarray(d, float) * t, r2, nod)
    return snr_pixel(np.asarray(s, float) * t, var1, n_frames)


def solve_exptime_median(rho, s, beta, d, r2, n_frames, nod, t_max=1e7):
    """Per-frame time at which the median S/N per pixel over the arrays equals ``rho``.

    Each pixel's S/N rises monotonically with t, so the median does too. The
    root is bracketed from the smallest per-pixel solution upward (doubling
    the upper end until the median reaches ``rho``) and found with Brent's
    method.

    Returns:
        float: t [s]; inf if the median cannot reach ``rho`` below ``t_max``.
    """
    from scipy.optimize import brentq
    tp = np.atleast_1d(solve_exptime(rho, s, beta, d, r2, n_frames, nod))
    fin = tp[np.isfinite(tp)]
    if fin.size == 0:
        return np.inf
    f = lambda t: np.median(snr_at(t, s, beta, d, r2, n_frames, nod)) - rho
    lo = max(float(fin.min()), 1e-12)
    if f(lo) >= 0:
        return lo
    hi = max(float(np.median(fin)), lo * 2.0)
    while f(hi) < 0:
        if hi >= t_max:
            return np.inf
        hi = min(hi * 2.0, t_max)
    return float(brentq(f, lo, hi, xtol=1e-12, rtol=1e-12))


def saturation_peak(wave_A, N0, T_atm, T_sys, f_peak, dlam, exptime, b, dark_rate, gain, limits):
    """Brightest pixel of one frame, sky lines included (5.3.11).

    ``peak_e(lam) = N0 T_atm T_sys f_peak dlam t + b t + D t``, maximized over lam.

    Args:
        b (array): Sky rate per (spatial pix, spectral pix) [e-/s].
        dark_rate (float): Dark current [e-/s/pix].
        gain (float): e-/ADU.
        limits (sequence): ADU limits (1 percent, 5 percent, saturation).

    Returns:
        dict: ``peak_e_per_frame``, ``peak_adu_per_frame``, ``wave_A``, ``flag``.
    """
    from keck_etcs.core.detector import linearity_flag
    peak = np.asarray(N0, float) * T_atm * T_sys * f_peak * dlam * exptime \
        + np.asarray(b, float) * exptime + dark_rate * exptime
    i = int(np.argmax(peak))
    adu = float(peak[i] / gain)
    return {'peak_e_per_frame': float(peak[i]), 'peak_adu_per_frame': adu,
            'wave_A': float(np.asarray(wave_A)[i]), 'flag': linearity_flag(adu, limits)}
