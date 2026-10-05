"""Keck/MOSFIRE instrument configuration (design sections 3, 5.4; plan step S8).

Every number carries its source. Wavelengths are vacuum A. Data files are
under ``keck_etcs/data/`` and are loaded on first use by
:class:`keck_etcs.instruments.base.Instrument`.
"""
from keck_etcs.instruments.base import Band, Era, Instrument

AREA_M2 = 72.3674
"""Keck effective collecting area [m^2]: PypeIt ``KeckTelescopePar`` (N1; XTcalc uses 75)."""

PLATESCALE = 0.1798
"""Spatial plate scale [arcsec/pix]: PypeIt keck_mosfire (header PSCALE 0.1799)."""

NONLINEAR_ADU = 26000.0
"""1 percent non-linearity [ADU]: Keck detector page (also in detector.ecsv)."""

# Detector footprint of the long slit (LONGSLIT-46, centred) in the J grating
# setting, from the 2022-04-09 J2 reduction: WaveCalib_A_1_DET01 (slit 1022),
# pixels 0 and 2047 at 11109.7 and 13754.8 A, mean dispersion 1.2922 A/pix.
# J, J2 and J3 share the grating setting, so J takes the same footprint; to be
# checked on a J night in part 5. PypeIt's templates (design section 3: 1.30
# A/pix) span 2600-3000 pixels stitched across CSU positions (N2).
J_FOOTPRINT_A = (11109.7, 13754.8)
J_DISPERSION = 1.2922

BANDS = {
    'J': Band('J', 'mosfire/filters/mosfire_J.ecsv', J_DISPERSION, J_FOOTPRINT_A,
              notes='Keck order-sorting J filter; footprint and dispersion from the J2 long slit (same grating)'),
    'J2': Band('J2', 'mosfire/filters/mosfire_J2.ecsv', J_DISPERSION, J_FOOTPRINT_A,
               clean_window_A=(11170.0, 12600.0),
               notes='clean window from PypeIt keck_mosfire.tweak_standard (design: 1.117-1.260 um)'),
}

ERAS = (
    # D6 and the MOSFIRE news page; name echoed in outputs, tag in the throughput file name
    Era('2012-04..2016-09', '2012-2016', '2012-04-04', '2016-09-15', 'first light to the collimator failure (original optics)'),
    Era('2017-02..2025-02', '2017-2025', '2017-02-13', '2025-02-11', 'after the collimator element repair'),
    Era('2025-04..', '2025-on', '2025-04-29', None, 'after the CSU repair'),
)

GAPS = (
    ('2016-09-15', '2017-02-13', 'MOSFIRE was offline 2016-09-15 to 2017-02-13 (collimator repair); '
                                 'using the era before the gap'),
    ('2025-02-11', '2025-04-29', 'the CSU was inoperable 2025-02-11 to 2025-04-29 (1" long slit only); '
                                 'using the era before the repair'),
)

LSF_SLOPE = 0.277
"""Slit width per pixel of LSF FWHM [arcsec/pix] (D25, interim): 2022-04-09 OH lines, 1" slit
FWHM 3.61 px (S13, 2026-10-04). Was 0.24 (XTcalc)."""

LSF_FLOOR_PIX = 2.2
"""Minimum LSF FWHM [pix] (D25); not constrained by a 1" slit."""

MOFFAT_BETA = 3.5
"""Moffat index for slit loss (D26)."""

# S11 validation (design 6.1, D14, D16, D18): J0841+3814_OFF on 2022-04-09, four
# 149.8 s ABBA MCDS-16 frames through the 1" slit, against the in-pod products of
# image keck-etcs:0.1.6 (sha256:0c5e88fd838e...), PypeIt pin 8017f47, with the
# 2017-02..2025-02 throughput (mosfire-J-2026.10-dev). scripts/mosfire/validate_j0841.py,
# output <night>/validation/validation_j0841_{bins.ecsv,summary.json,png}.
# The source is bright (J2 = 15.9 AB intrinsic; source 70% of the interline variance),
# so the sky and aperture terms are only weakly constrained by this night.
VALIDATION_J0841 = {
    'snr_ratio_etc_over_measured': {'band_1117_1260': 0.996, 'between_oh_lines': 1.003},   # D18: PASS 20% / 10%
    'signal_ratio_etc_over_measured': 0.999,
    'sky_measured_over_gemini': {'oh_lines': 0.859, 'between_lines': 1.332,
                                 'cleanest_50A_bins': (1.14, 1.19)},     # D14; 'between' includes OH-line wings
    'n5_oh_centroid_offset_A': -0.070,                                  # measured - Gemini, MAD 0.098, 26 lines
    'aperture_length_fwhm': {'best': 2.22, 'within_1pct': (1.48, 2.44), 'within_2pct': (1.32, 2.64)},   # D16
}

SKY_SCALE_DEFAULT = 1.0
"""D14 default ``sky_scale``: kept at 1.0. One night gives OH lines x0.86 and the
continuum between them x1.15-1.33 relative to Gemini, so a single scale cannot match
both; the choice (and whether to scale lines and continuum separately) waits for the
part-5 nights. At J2 = 20-22 AB a x1.33 continuum would lower the S/N by ~8%."""

APERTURE_LENGTH_FWHM_DEFAULT = 1.5
"""D16 extraction length in FWHM: the schema default 1.5 lies inside the range the
validation allows (1.48-2.44 for a band ratio within 1%; best fit 2.22)."""


# Calibration monitor (design 4.9.6, D40-D47). Moved verbatim from
# keck_etcs/calib/monitor_configs.py in S8, which re-exports it; the rows
# must not change.
MONITOR = {
    'instrument': 'keck_mosfire',
    'platescale': PLATESCALE,
    'site': {'lat_deg': 19.8263, 'lon_deg': -155.4747, 'height_m': 4145.0},   # Keck
    'twilight_sun_alt_deg': -18.0,      # OH rows flagged ``twilight`` above this (S6b)
    'gain': 2.15,                       # e-/ADU (PypeIt detector par; Keck detector page)
    'nonlinear_adu': NONLINEAR_ADU,
    # spatial FWHM (D41): FWHMFIT medians within +-fwhm_halfwidth of these nodes
    'fwhm_nodes': {'J2': (11500.0, 12000.0, 12500.0), 'J': (12000.0, 12500.0, 13000.0)},
    'fwhm_halfwidth': 100.0,
    'moffat_beta': MOFFAT_BETA,         # D26
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

MOSFIRE = Instrument(
    name='keck_mosfire',
    area_m2=AREA_M2,
    platescale=PLATESCALE,
    bands=BANDS,
    eras=ERAS,
    gaps=GAPS,
    lsf_slope=LSF_SLOPE,
    lsf_floor_pix=LSF_FLOOR_PIX,
    detector_file='mosfire/detector.ecsv',
    sky_grid_file='sky/gemini_mk_sky_grid.fits',
    lsf_file='mosfire/lsf_measurements.ecsv',
    throughput_pattern='mosfire/throughput/mosfire_thru_{tag}.ecsv',          # S10 (design 4.5)
    moffat_beta=MOFFAT_BETA,
    monitor=MONITOR,
)
