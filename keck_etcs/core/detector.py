"""Detector terms: read noise, dark current, linearity (design 5.3.9, 5.3.11, D12, D13)."""
import numpy as np

LINEARITY_FLAGS = ('ok', 'nonlinear_1pct', 'nonlinear_5pct', 'saturated')


def effective_reads(mode, n_reads):
    """Number of reads for the read-noise table: CDS is 1, MCDS is ``n_reads``.

    Returns:
        tuple: ``(n, warnings)``.
    """
    if mode == 'CDS':
        return 1, ([] if n_reads in (None, 1) else [f'readout.n_reads {n_reads} ignored for CDS (uses 1)'])
    if mode == 'MCDS':
        return int(n_reads), []
    raise ValueError(f'readout mode {mode!r} is not supported (CDS, MCDS)')


def read_noise(n_reads, table_n, table_rn):
    """Read noise [e- rms per pixel per frame], linear in log2(N_reads) between table rows.

    Outside the table the end value is used.
    """
    tn, tr = np.asarray(table_n, float), np.asarray(table_rn, float)
    srt = np.argsort(tn)
    return float(np.interp(np.log2(n_reads), np.log2(tn[srt]), tr[srt]))


def dark_electrons(dark_rate, exptime, n_spat=1):
    """Dark electrons in ``n_spat`` pixels for one frame."""
    return dark_rate * exptime * n_spat


def linearity_flag(peak_adu, limits):
    """Linearity flag of the brightest pixel.

    Args:
        peak_adu (float): Peak counts per frame [ADU].
        limits (sequence): ADU limits for 1 percent nonlinearity, 5 percent
            nonlinearity and saturation (MOSFIRE 26000, 37000, 43000).

    Returns:
        str: One of :data:`LINEARITY_FLAGS`.
    """
    l1, l5, lsat = limits
    if peak_adu >= lsat:
        return 'saturated'
    if peak_adu >= l5:
        return 'nonlinear_5pct'
    if peak_adu >= l1:
        return 'nonlinear_1pct'
    return 'ok'
