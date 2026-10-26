"""Atmospheric transmission from an (airmass, PWV) grid (design 5.3.3, N4).

The grid is ``values[n_grid, n_wave]`` with one ``(airmass, pwv_mm)`` pair
per row, as in ``keck_etcs/data/sky/gemini_mk_sky_grid.fits`` (HDUs ``TRANS``,
``SKYBG`` and ``GRID``). Interpolation is linear in airmass and linear in
log PWV; values outside the grid are clipped to its edge with a warning.
"""
import numpy as np


def _bracket(x, nodes):
    """Indices and weight of the linear interpolation of x between sorted nodes."""
    j = int(np.clip(np.searchsorted(nodes, x, side='right') - 1, 0, len(nodes) - 2))
    f = (x - nodes[j]) / (nodes[j + 1] - nodes[j])
    return j, float(f)


def interp_grid(values, grid_airmass, grid_pwv, airmass, pwv_mm):
    """Interpolate a spectral grid to (airmass, PWV).

    Args:
        values (array): ``[n_grid, n_wave]`` spectra, one per grid point.
        grid_airmass, grid_pwv (array): ``[n_grid]`` airmass and PWV [mm] of
            each row; together they must form a full rectangular grid.
        airmass (float): Requested airmass.
        pwv_mm (float): Requested PWV [mm].

    Returns:
        tuple: ``(spectrum, warnings)``; ``spectrum`` is ``[n_wave]`` and
        ``warnings`` a list of strings naming any clipped quantity.
    """
    values = np.asarray(values, float)
    ga, gp = np.asarray(grid_airmass, float), np.asarray(grid_pwv, float)
    am_nodes, pwv_nodes = np.unique(ga), np.unique(gp)
    if len(am_nodes) * len(pwv_nodes) != len(ga):
        raise ValueError('the (airmass, pwv) grid is not rectangular')
    warnings = []
    am = float(np.clip(airmass, am_nodes[0], am_nodes[-1]))
    if am != airmass:
        warnings.append(f'airmass {airmass} clipped to {am} (grid {am_nodes[0]}-{am_nodes[-1]})')
    pw = float(np.clip(pwv_mm, pwv_nodes[0], pwv_nodes[-1]))
    if pw != pwv_mm:
        warnings.append(f'pwv_mm {pwv_mm} clipped to {pw} (grid {pwv_nodes[0]}-{pwv_nodes[-1]})')
    ja, fa = _bracket(am, am_nodes)
    jp, fp = _bracket(np.log(pw), np.log(pwv_nodes))

    def row(a, p):
        return values[np.flatnonzero((ga == am_nodes[a]) & (gp == pwv_nodes[p]))[0]]

    spec = ((1 - fa) * (1 - fp) * row(ja, jp) + fa * (1 - fp) * row(ja + 1, jp)
            + (1 - fa) * fp * row(ja, jp + 1) + fa * fp * row(ja + 1, jp + 1))
    return spec, warnings


def transmission(trans_grid, grid_airmass, grid_pwv, airmass, pwv_mm):
    """Atmospheric transmission T_atm(lam; X, PWV) on the grid's wavelengths.

    Returns:
        tuple: ``(T_atm, warnings)``; T_atm is clipped to [0, 1].
    """
    t, warnings = interp_grid(trans_grid, grid_airmass, grid_pwv, airmass, pwv_mm)
    return np.clip(t, 0.0, 1.0), warnings
