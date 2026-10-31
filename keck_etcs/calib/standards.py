"""Standard-star models and classification for the sensfunc (design D2, N3; plan S15a).

Two classes of standard (D2):

- **archive**: stars with a spectrophotometric spectrum in one of PypeIt's
  archives (CALSPEC white dwarfs such as LDS749B and GD71, X-shooter, ESO,
  ...). PypeIt finds them by position; nothing to do here.
- **A0V**: telluric stars (mostly HIP), fluxed with PypeIt's Vega spectrum
  (``vega_tspectool_vacuum.dat``) scaled so that its synthetic 2MASS
  magnitude in the **band's own 2MASS band** equals the star's catalogue
  value (N3 for J; design D51 for the other bands: J for Y and J, H for H,
  Ks for K; :func:`tmass_band`).

PypeIt's model hook is ``[sensfunc] star_type = A0`` with ``star_mag = V``,
which returns ``VegaStandard(V)`` = the Vega spectrum x 10^(0.4 (0.03 - V))
(Vega V = 0.03). A model scaled to a 2MASS magnitude ``m`` is therefore
exactly PypeIt's Vega model at the *V-equivalent* magnitude ``V_eq = 0.03 +
m_star - m_synth(Vega)``, and :func:`sens_par_lines` writes that, so no
PypeIt change is needed.

Synthetic 2MASS magnitudes: photon-counting, ``-2.5 log10(int F R lam dlam
/ int F0 R lam dlam)`` with PypeIt's ``TMASS-J/H/K`` responses and the
Cohen, Wheaton & Megeath (2003, AJ 126, 1090) zero points F0 = 3.129e-13
(J), 1.133e-13 (H), 4.283e-14 (Ks) W cm^-2 um^-1 (x 1e3 for erg s^-1 cm^-2
A^-1), in which Vega has J = -0.001, H = +0.019, Ks = -0.017. PypeIt's Vega
spectrum comes out at J = +0.024 this way (+0.013 energy-weighted), so the
J-scaled model is 2.3 percent fainter in J than a scaling relative to Vega's
-0.001 would make it; the synthetic Vega magnitude is recorded with every
A0V sensfunc (``vega_tmass_synthetic``) and the A0V/WD cross-tie (D2)
measures it. When a star's 2MASS J is also known, the record carries the
offset between the band-scaled and the J-scaled models
(``a0v_jhk_offset_mag``, D51's cross-check).

PypeIt is imported inside the functions only (``calib`` may import it;
``core`` and ``etc`` never do).
"""
from functools import lru_cache

import numpy as np

TMASS = {
    'J': {'pypeit_filter': 'TMASS-J', 'f0_flam': 3.129e-10, 'vega_mag': -0.001},
    'H': {'pypeit_filter': 'TMASS-H', 'f0_flam': 1.133e-10, 'vega_mag': 0.019},
    'K': {'pypeit_filter': 'TMASS-K', 'f0_flam': 4.283e-11, 'vega_mag': -0.017},
}
"""Per 2MASS band: PypeIt's response name, the zero-magnitude flux density [erg/s/cm^2/A] and Vega's
magnitude (Cohen, Wheaton & Megeath 2003, Table 2); ``K`` is Ks."""

TMASS_J_F0 = TMASS['J']['f0_flam']
"""2MASS J zero-magnitude flux density [erg/s/cm^2/A] (Cohen et al. 2003)."""

TMASS_J_VEGA = TMASS['J']['vega_mag']
"""Vega's 2MASS J magnitude (Cohen et al. 2003), for the check of the synthetic photometry."""

BAND_TO_TMASS = {'Y': 'J', 'J': 'J', 'J2': 'J', 'J3': 'J', 'H': 'H', 'K': 'K', 'Ks': 'K'}
"""Instrument band -> the 2MASS band its A0V model is scaled to (D51)."""


def tmass_band(band):
    """The 2MASS band (``J``, ``H`` or ``K``) an instrument band's A0V model is scaled to."""
    try:
        return BAND_TO_TMASS[str(band)]
    except KeyError:
        raise KeyError(f'no 2MASS band for instrument band {band!r}; add it to BAND_TO_TMASS') from None


def mag_column(band):
    """The night-manifest column holding the 2MASS magnitude an instrument band's A0V model is scaled to.

    ``jmag_2mass`` for Y and the J group, ``hmag_2mass`` for H, ``kmag_2mass``
    for K (the census columns of ``koa_standards_candidates.ecsv``; the night
    job exports each as its upper-cased name, e.g. ``HMAG_2MASS``).
    """
    return f'{tmass_band(band).lower()}mag_2mass'


def mag_from_env(band, environ=None):
    """The band's 2MASS magnitude from the night-manifest environment (``None`` when unset or empty)."""
    import os
    v = (environ if environ is not None else os.environ).get(mag_column(band).upper())
    return None if v in (None, '') else float(v)

VEGA_V = 0.03
"""Vega's V magnitude as assumed by PypeIt's ``VegaStandard``."""

A0V_MATCH_ARCSEC = 60.0
"""Frames within this distance of an A0V standard's position are typed ``standard``."""


@lru_cache(maxsize=3)
def tmass_response(tmass='J'):
    """PypeIt's 2MASS relative spectral response of a 2MASS band, ``(wave_A, R)``."""
    from pypeit.core.flux_calib import load_filter_file
    w, r = load_filter_file(TMASS[tmass]['pypeit_filter'])
    return np.asarray(w, float), np.asarray(r, float)


def tmass_j_response():
    """PypeIt's 2MASS J relative spectral response, ``(wave_A, R)``."""
    return tmass_response('J')


@lru_cache(maxsize=1)
def vega_spectrum():
    """PypeIt's Vega spectrum (vacuum A, erg/s/cm^2/A), the file ``VegaStandard`` uses."""
    from astropy import table
    from pypeit import dataPaths
    t = table.Table.read(dataPaths.standards.get_file_path('vega_tspectool_vacuum.dat'), comment='#',
                         format='ascii')
    return np.asarray(t['col1'], float), np.asarray(t['col2'], float)


def synthetic_tmass(wave, flam, tmass='J'):
    """Synthetic 2MASS magnitude of f_lambda [erg/s/cm^2/A] in a 2MASS band (photon counting, Cohen et al. 2003)."""
    rw, rr = tmass_response(tmass)
    f = np.interp(rw, np.asarray(wave, float), np.asarray(flam, float), left=0.0, right=0.0)
    num = np.trapezoid(f * rr * rw, rw)
    den = np.trapezoid(TMASS[tmass]['f0_flam'] * rr * rw, rw)
    return float(-2.5 * np.log10(num / den))


def synthetic_tmass_j(wave, flam):
    """Synthetic 2MASS J magnitude of f_lambda [erg/s/cm^2/A] (photon counting, Cohen et al. 2003 zero point)."""
    return synthetic_tmass(wave, flam, 'J')


@lru_cache(maxsize=3)
def vega_tmass(tmass='J'):
    """Synthetic 2MASS magnitude of PypeIt's Vega spectrum in a 2MASS band (expected near Cohen's value)."""
    return synthetic_tmass(*vega_spectrum(), tmass)


def vega_tmass_j():
    """Synthetic 2MASS J of PypeIt's Vega spectrum (expected near -0.001)."""
    return vega_tmass('J')


def v_equivalent(mag, band='J'):
    """V magnitude to give PypeIt's ``VegaStandard`` so that the model's synthetic 2MASS magnitude is ``mag``.

    ``band`` is the instrument band (:func:`tmass_band` picks the 2MASS band).
    """
    return VEGA_V + float(mag) - vega_tmass(tmass_band(band))


def a0v_model(band, mag):
    """The A0V model of an instrument band: PypeIt's Vega spectrum scaled to the band's 2MASS magnitude.

    Args:
        band (str): instrument band (``Y``, ``J``, ``J2``, ``H``, ``K``): the
            model is scaled in :func:`tmass_band` of it (N3, D51).
        mag (float): the star's catalogue 2MASS magnitude in that 2MASS band.

    Returns:
        tuple: ``(wave_A, flam)``.
    """
    w, f = vega_spectrum()
    return w, f * 10 ** (-0.4 * (float(mag) - vega_tmass(tmass_band(band))))


def jhk_offset_mag(band, mag, j_mag):
    """Magnitude offset between the band-scaled and the J-scaled A0V models of one star (D51 cross-check).

    Positive means the band-scaled model is fainter. It equals the star's
    ``(m_band - J)`` colour minus Vega's synthetic colour, i.e. the star's
    departure from an A0V colour; zero by construction when the band is
    scaled in J.
    """
    tb = tmass_band(band)
    return float((float(mag) - vega_tmass(tb)) - (float(j_mag) - vega_tmass('J')))


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


def sens_par_lines(mag, band='J', j_mag=None):
    """Lines to add under ``[sensfunc]`` for an A0V standard, and the model record.

    Args:
        mag (float): the star's 2MASS magnitude in the band's 2MASS band
            (:func:`tmass_band`; J for the J group).
        band (str): instrument band.
        j_mag (float, optional): the star's 2MASS J when the band is not
            scaled in J, for the ``a0v_jhk_offset_mag`` cross-check.
    """
    tb = tmass_band(band)
    v = v_equivalent(mag, band)
    j = float(mag) if tb == 'J' else (None if j_mag is None else float(j_mag))
    rec = {'model': f'Vega (vega_tspectool_vacuum.dat) scaled to 2MASS {tb} (N3, D51)',
           'band': str(band), 'band_2mass': tb, 'a0v_scaled_to': f'2MASS {tb}', 'mag_2mass': float(mag),
           'j_2mass': j, 'a0v_jhk_offset_mag': (None if j is None else round(jhk_offset_mag(band, mag, j), 5)),
           'v_equivalent': round(v, 5), 'vega_tmass_synthetic': round(vega_tmass(tb), 5),
           'vega_tmass_j_synthetic': round(vega_tmass_j(), 5),
           'tmass_zero_point_flam': TMASS[tb]['f0_flam'], 'tmass_j_zero_point_flam': TMASS_J_F0,
           'pypeit_hook': "star_type = A0, star_mag = V_eq"}
    return [f'  star_type = A0', f'  star_mag = {v:.5f}'], rec


def write_sens_par(base_text, mag, band='J', j_mag=None):
    """A copy of a ``.sens`` file with the A0V model lines inserted under ``[sensfunc]``.

    Returns:
        tuple: ``(text, record)``.
    """
    lines, rec = sens_par_lines(mag, band, j_mag)
    out, done = [], False
    for ln in base_text.splitlines():
        out.append(ln)
        if not done and ln.strip() == '[sensfunc]':
            out.extend(lines)
            done = True
    if not done:
        out.extend(['[sensfunc]'] + lines)
    header = [f'# A0V standard, 2MASS {rec["band_2mass"]} = {mag}: PypeIt Vega model at V_eq = '
              f'{rec["v_equivalent"]} (keck_etcs.calib.standards, design N3, D51)']
    return '\n'.join(header + out) + '\n', rec
