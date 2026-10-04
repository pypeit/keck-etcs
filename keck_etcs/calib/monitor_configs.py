"""Per-instrument calibration-monitor configurations (design 4.9.6).

Until part 3's S8 adds ``keck_etcs/instruments/<inst>.py``, the MOSFIRE block
lives here. S8 moves it there and leaves a re-export, so the rows do not
change. Wavelengths are vacuum A.
"""

# Platescale (arcsec/pix, spatial) and detector nonlinearity limit (raw ADU)
MOSFIRE_PLATESCALE = 0.1798
MOSFIRE_NONLINEAR_ADU = 26000.0

MOSFIRE = {
    'instrument': 'keck_mosfire',
    'platescale': MOSFIRE_PLATESCALE,
    'site': {'lat_deg': 19.8263, 'lon_deg': -155.4747, 'height_m': 4145.0},   # Keck
    'twilight_sun_alt_deg': -18.0,      # OH rows flagged ``twilight`` above this (S6b)
    'gain': 2.15,                       # e-/ADU (PypeIt detector par)
    'nonlinear_adu': MOSFIRE_NONLINEAR_ADU,
    # spatial FWHM (D41): FWHMFIT medians within +-fwhm_halfwidth of these nodes
    'fwhm_nodes': {'J2': (11500.0, 12000.0, 12500.0), 'J': (12000.0, 12500.0, 13000.0)},
    'fwhm_halfwidth': 100.0,
    'moffat_beta': 3.5,                 # D26
    # dome-flat rates (D42, D43): every 250 A, +-50 A boxes, central 50% of slit rows
    'flat_kind': 'dome',
    'flat_nodes': {'J2': tuple(11250.0 + 250.0 * k for k in range(6)),
                   'J': tuple(11500.0 + 250.0 * k for k in range(8))},
    'flat_halfwidth': 50.0,
    'slit_row_fraction': 0.5,
    'lamp_cards': ('FLAMP1', 'FLAMP2', 'FPOWER', 'FLATSPEC', 'DOMEPOSN'),
    # line widths and fluxes (D44, D45)
    'line_lists': {'OH': 'OH_R24000_lines.dat', 'Ne': 'Ne_IR_MOSFIRE_lines.dat',
                   'Ar': 'Ar_IR_MOSFIRE_lines.dat'},
    'lsf_ref_wave': 12500.0,
    'band_windows': {'J2': (11170.0, 12600.0), 'J': (11530.0, 13520.0)},
    # monitor lines (D45, 4.9.4): provisional until the S15a freeze.
    # J2 from scripts/mosfire/select_monitor_lines.py on 2022-04-09 (rule 2 at 1",
    # S6b): 15 lines pass rules 1, 2 and 4; the brightest per sub-window is kept.
    # Output <night>/lsf/monitor_lines_J2.ecsv, sha256
    # d2da532862375e5408911aa699330ee49909de73c61a76aebeefdf28bd017fba.
    'monitor_lines': {'OH': {'J2': (11591.847, 11788.495, 12229.206, 12287.158), 'J': ()}},
    'monitor_lines_status': 'provisional',
}

CONFIGS = {'keck_mosfire': MOSFIRE}


def get_config(instrument):
    """Return the monitor config for a PypeIt spectrograph name."""
    try:
        return CONFIGS[instrument]
    except KeyError:
        raise KeyError(f'no calibration-monitor config for {instrument!r}') from None
