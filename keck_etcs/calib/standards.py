"""Standard-star models and classification for the sensfunc (design D2, N3; plan S15a).

Two classes of standard (D2):

- **archive**: stars with a spectrophotometric spectrum in one of PypeIt's
  archives (CALSPEC white dwarfs such as LDS749B and GD71, X-shooter, ESO,
  ...). PypeIt finds them by position; nothing to do here.
- **A0V**: telluric stars (mostly HIP), fluxed with PypeIt's Vega spectrum
  (``vega_tspectool_vacuum.dat``) scaled so that its synthetic 2MASS J
  magnitude equals the star's 2MASS J (N3).

PypeIt's model hook is ``[sensfunc] star_type = A0`` with ``star_mag = V``,
which returns ``VegaStandard(V)`` = the Vega spectrum x 10^(0.4 (0.03 - V))
(Vega V = 0.03). A J-scaled model is therefore exactly PypeIt's Vega model at
the *V-equivalent* magnitude ``V_eq = 0.03 + J_star - J_synth(Vega)``, and
:func:`sens_par_lines` writes that, so no PypeIt change is needed.

Synthetic 2MASS J: photon-counting, ``-2.5 log10(int F R lam dlam / int F0 R
lam dlam)`` with PypeIt's ``TMASS-J`` response and the Cohen, Wheaton &
Megeath (2003, AJ 126, 1090) zero point F0(J) = 3.129e-13 W cm^-2 um^-1 =
3.129e-10 erg s^-1 cm^-2 A^-1, in which Vega has J = -0.001. PypeIt's Vega
spectrum comes out at J = +0.024 this way (+0.013 energy-weighted), so the
J-scaled model is 2.3 percent fainter in J than a scaling relative to Vega's
-0.001 would make it; the offset is recorded with every A0V sensfunc
(``vega_tmass_j_synthetic``) and the A0V/WD cross-tie (D2) measures it.

PypeIt is imported inside the functions only (``calib`` may import it;
``core`` and ``etc`` never do).
"""
from functools import lru_cache

import numpy as np

TMASS_J_F0 = 3.129e-10
"""2MASS J zero-magnitude flux density [erg/s/cm^2/A] (Cohen et al. 2003)."""

TMASS_J_VEGA = -0.001
"""Vega's 2MASS J magnitude (Cohen et al. 2003), for the check of the synthetic photometry."""

VEGA_V = 0.03
"""Vega's V magnitude as assumed by PypeIt's ``VegaStandard``."""

A0V_MATCH_ARCSEC = 60.0
"""Frames within this distance of an A0V standard's position are typed ``standard``."""


@lru_cache(maxsize=1)
def tmass_j_response():
    """PypeIt's 2MASS J relative spectral response, ``(wave_A, R)``."""
    from pypeit.core.flux_calib import load_filter_file
    w, r = load_filter_file('TMASS-J')
    return np.asarray(w, float), np.asarray(r, float)


@lru_cache(maxsize=1)
def vega_spectrum():
    """PypeIt's Vega spectrum (vacuum A, erg/s/cm^2/A), the file ``VegaStandard`` uses."""
    from astropy import table
    from pypeit import dataPaths
    t = table.Table.read(dataPaths.standards.get_file_path('vega_tspectool_vacuum.dat'), comment='#',
                         format='ascii')
    return np.asarray(t['col1'], float), np.asarray(t['col2'], float)


def synthetic_tmass_j(wave, flam):
    """Synthetic 2MASS J magnitude of f_lambda [erg/s/cm^2/A] (photon counting, Cohen et al. 2003 zero point)."""
    rw, rr = tmass_j_response()
    f = np.interp(rw, np.asarray(wave, float), np.asarray(flam, float), left=0.0, right=0.0)
    num = np.trapezoid(f * rr * rw, rw)
    den = np.trapezoid(TMASS_J_F0 * rr * rw, rw)
    return float(-2.5 * np.log10(num / den))


def vega_tmass_j():
    """Synthetic 2MASS J of PypeIt's Vega spectrum (expected near -0.001)."""
    return synthetic_tmass_j(*vega_spectrum())


def v_equivalent(j_mag):
    """V magnitude to give PypeIt's ``VegaStandard`` so that the model's synthetic 2MASS J is ``j_mag``."""
    return VEGA_V + float(j_mag) - vega_tmass_j()


def a0v_model(j_mag):
    """The N3 model: PypeIt's Vega spectrum scaled to 2MASS J = ``j_mag``; ``(wave_A, flam)``."""
    w, f = vega_spectrum()
    return w, f * 10 ** (-0.4 * (float(j_mag) - vega_tmass_j()))


def classify(ra=None, dec=None, sptype=None, std_class=None):
    """Class of a standard: ``archive`` (PypeIt has its spectrum), ``A0V`` or ``unknown``.

    An explicit ``std_class`` from the night manifest wins, except that a
    star PypeIt finds in an archive is always ``archive`` (its measured
    spectrum beats a model).

    Returns:
        dict: ``std_class``, and for archive stars ``archive``, ``name`` and
        ``file``.
    """
    if ra is not None and dec is not None:
        from pypeit.core import standard
        try:
            s = standard.get_archive_standard(float(ra), float(dec))
        except Exception:  # noqa: BLE001 - PypeIt raises when nothing is found
            s = None
        if s is not None:
            m = getattr(s, 'meta', {}) or {}
            return {'std_class': 'archive', 'archive': str(m.get('source')), 'name': str(m.get('Name')),
                    'file': str(m.get('File'))}
    if std_class:
        c = str(std_class).strip()
        if c.upper().startswith('A0'):
            return {'std_class': 'A0V'}
        if c.upper() in ('WD', 'ARCHIVE'):
            return {'std_class': 'archive'}
    if sptype and str(sptype).strip().upper().startswith('A0'):
        return {'std_class': 'A0V'}
    return {'std_class': 'unknown'}


def sens_par_lines(j_mag):
    """Lines to add under ``[sensfunc]`` for an A0V standard of 2MASS J = ``j_mag``, and the record."""
    v = v_equivalent(j_mag)
    rec = {'model': 'Vega (vega_tspectool_vacuum.dat) scaled to 2MASS J (N3)', 'j_2mass': float(j_mag),
           'v_equivalent': round(v, 5), 'vega_tmass_j_synthetic': round(vega_tmass_j(), 5),
           'tmass_j_zero_point_flam': TMASS_J_F0, 'pypeit_hook': "star_type = A0, star_mag = V_eq"}
    return [f'  star_type = A0', f'  star_mag = {v:.5f}'], rec


def write_sens_par(base_text, j_mag):
    """A copy of a ``.sens`` file with the A0V model lines inserted under ``[sensfunc]``.

    Returns:
        tuple: ``(text, record)``.
    """
    lines, rec = sens_par_lines(j_mag)
    out, done = [], False
    for ln in base_text.splitlines():
        out.append(ln)
        if not done and ln.strip() == '[sensfunc]':
            out.extend(lines)
            done = True
    if not done:
        out.extend(['[sensfunc]'] + lines)
    header = [f'# A0V standard, 2MASS J = {j_mag}: PypeIt Vega model at V_eq = {rec["v_equivalent"]} '
              '(keck_etcs.calib.standards, design N3)']
    return '\n'.join(header + out) + '\n', rec
