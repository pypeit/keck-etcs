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

# The other bands (design 9.2, D56, D58; scripts/mosfire/survey_other_bands.py, "Other bands"
# prompt #1). Y shares the J grating tilt: the dev suite's Y_long WaveCalib_A_1_DET01 (GD71,
# 2019-11-18) gives 9255-11471 A over 2040 pixels, which is the J2 footprint x 5/6 to 0.1 percent;
# the Y window is therefore the filter's. H and K have different tilts and are wider than the
# detector (filters 2099 and 2227 pixels wide), so the detector sets their windows. Their
# footprints were MEASURED in plan S23d (2026-10-30; scripts/mosfire/measure_footprint.py on the
# reference reductions of design D56, PypeIt at the pin b0447b7 in the 0.2.6 image; the 0.2.5
# image at bc18a3b gave the same footprints to 0.1 A):
# - H: dev-suite longslit_3x0.7_H, HIP 17971 on 2012-11-28 (LONGSLIT-3x0.7, the centred 3-bar slit,
#   spat_id 1034), mosfire/20121128/H/redux/Calibrations/WaveCalib_A_1_DET01.fits
#   (sha256 5ab32e499092009749b1820773ac42bb17ad3965016563e951f9697401976aa2): pixels 0-2039 at
#   14650.5-17970.7 A, 1.6284 A/pix, fit RMS 0.066 pix. The Keck page's nominal 14680-18040 A was
#   30 A too narrow at the blue end and 70 A too wide at the red end.
# - K: dev-suite longslit_3x0.7_K, the same star and night, mosfire/20121128/K/redux/Calibrations/
#   WaveCalib_A_1_DET01.fits (sha256 1cfcd3063204c39184ace99bdd0b8af0c419dccdb0cfbbad2ae84f1b4594935a):
#   19535.9-23991.1 A, 2.1850 A/pix, RMS 0.037 pix (nominal 19540-23970 A). The dev suite's K_long
#   (LONGSLIT-46x1.5, spat_id 1020, 2019-10-13; mosfire/20191013/K/redux/Calibrations/
#   WaveCalib_A_1_DET01.fits, sha256 237f9facdae959932fce29e27997e3d2fbe5d6e14609012f462305e1573611d3)
#   gives 19529.7-23957.1 A, 2.1713 A/pix: the K tilt reproduces to about 35 A (16 pixels) at the
#   red end between nights, the scale of a one-pixel-per-edge uncertainty on the window.
# Dispersions: the measured mean over the footprint (PypeIt's OH templates gave 1.627 and 2.169).
Y_FOOTPRINT_A = (9255.0, 11471.0)
Y_DISPERSION = 1.087
H_FOOTPRINT_A = (14650.5, 17970.7)
H_DISPERSION = 1.6284
H_FOOTPRINT_NOMINAL_A = (14680.0, 18040.0)      # Keck page, used until S23d
K_FOOTPRINT_A = (19535.9, 23991.1)
K_DISPERSION = 2.1850
K_FOOTPRINT_NOMINAL_A = (19540.0, 23970.0)      # Keck page, used until S23d
K_FOOTPRINT_2019_A = (19529.7, 23957.1)         # K_long, LONGSLIT-46x1.5, 2019-10-13 (the between-night spread)

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

LSF_FORM = 'quadrature'
"""D25 since the first calibration release (plan S16, Q&A S16-3): ``FWHM_pix = sqrt((w / LSF_SLOPE)^2 +
LSF_FLOOR_PIX^2)``, fitted to OH lines at 12500 A on 5 nights (1" slit: 3.56-3.61 pix on 4 nights;
0.7": 2.63 pix; scripts/mosfire/plot_monitor_trends.py). It matches both widths; the earlier
``max(w / 0.277, 2.2)`` was +0.5 % at 1" and -3.8 % at 0.7"."""

LSF_SLOPE = 0.292
"""Slit width per pixel of LSF FWHM [arcsec/pix] in the D25 quadrature rule (S16). Was 0.277
(``max`` rule, S13) and 0.24 (XTcalc)."""

LSF_FLOOR_PIX = 1.08
"""Instrumental LSF FWHM [pix] added in quadrature (D25, S16); set by the single 0.7" night. Was a
2.2 pix floor in the ``max`` rule."""

MOFFAT_BETA = 3.5
"""Moffat index for slit loss (D26)."""

LSF_J = {'slope': LSF_SLOPE, 'floor_pix': LSF_FLOOR_PIX, 'form': LSF_FORM, 'provisional': False,
         'provenance': 'D25 quadrature rule fitted to J2 OH lines at 12500 A on 5 nights (S16)'}
"""The J group's LSF rule (the instrument rule, measured)."""

LSF_PROVISIONAL = {**LSF_J, 'provisional': True,
                   'provenance': 'the J rule assumed in pixels (D59); per-band slope and floor come from the '
                                 'monitor OH widths (parts H, K, Y)'}
"""Y, H and K until measured: the same rule in pixels, flagged provisional (D59). XTcalc's resolving
powers imply a 0.7" image about 5 percent narrower in H and K than in Y and J. S23d measured the
0.7" OH widths on the 2012-11-28 reference night (lsf_measurements.ecsv): H 2.560 pix (8 clean lines),
K 2.613 pix (5 lines), against the J rule's 2.627 pix at 0.7", i.e. -2.6 and -0.5 percent; and K at
1.5" (K_long, 2019-10-13): 5.370 pix against the rule's 5.249 (+2.3 percent). Those rows take
precedence at their slit widths; the rule's slope and floor per band wait for the monitor sample."""

# Band groups (D49): one grating order per group; throughput products are per group. The common
# window, zero-point nodes and PWV windows are design 9.3 (P7 = D54); the combine rules are the
# S16 J rules (EDGE_TRIM_FRAC 0.9 for J, none for J2 as built; A0V_MIN_WAVE 11900 A) and 0.9 for
# the new bands (D49); A0V blue cuts for Y, H and K are set when their A0V curves are seen (H is
# expected to need one at the Brackett limit, 9.3).
J_COMMON_WINDOW_A = (11900.0, 12450.0)
BANDS = {
    'J': Band('J', 'mosfire/filters/mosfire_J.ecsv', J_DISPERSION, J_FOOTPRINT_A,
              notes='Keck order-sorting J filter; footprint and dispersion from the J2 long slit (same grating)',
              group='J', order=5, zp_nodes_A=(12000.0, 12500.0, 13000.0), common_window_A=J_COMMON_WINDOW_A,
              pwv_window_A=((11170.0, 12600.0),), edge_trim_frac=0.9, a0v_min_wave_A=11900.0, lsf=LSF_J),
    'J2': Band('J2', 'mosfire/filters/mosfire_J2.ecsv', J_DISPERSION, J_FOOTPRINT_A,
               clean_window_A=(11170.0, 12600.0),
               notes='clean window from PypeIt keck_mosfire.tweak_standard (design: 1.117-1.260 um)',
               group='J', order=5, zp_nodes_A=(11500.0, 12000.0, 12500.0), common_window_A=J_COMMON_WINDOW_A,
               pwv_window_A=((11170.0, 12600.0),), edge_trim_frac=None, a0v_min_wave_A=11900.0, lsf=LSF_J),
    'Y': Band('Y', 'mosfire/filters/mosfire_Y.ecsv', Y_DISPERSION, Y_FOOTPRINT_A,
              clean_window_A=(9520.0, 11256.0),
              notes='footprint measured (dev-suite Y_long, 2019-11-18); clean window from PypeIt tweak_standard; '
                    'PWV has no window inside the band (pwv_weak)',
              group='Y', order=6, zp_nodes_A=(10000.0, 10500.0, 11000.0), common_window_A=(9800.0, 11100.0),
              pwv_window_A=((9719.0, 11243.0),), pwv_weak=True, edge_trim_frac=0.9, lsf=LSF_PROVISIONAL),
    'H': Band('H', 'mosfire/filters/mosfire_H.ecsv', H_DISPERSION, H_FOOTPRINT_A,
              notes='footprint measured on the dev-suite longslit_3x0.7_H (HIP 17971, 2012-11-28; S23d); '
                    'detector-limited: the filter is wider than the detector; PWV only at the band edges (pwv_weak)',
              group='H', order=4, zp_nodes_A=(15500.0, 16500.0, 17500.0), common_window_A=(14900.0, 17800.0),
              pwv_window_A=((14661.0, 14800.0), (17900.0, 18076.0)), pwv_weak=True, edge_trim_frac=0.9,
              lsf=LSF_PROVISIONAL),
    'K': Band('K', 'mosfire/filters/mosfire_K.ecsv', K_DISPERSION, K_FOOTPRINT_A,
              notes='footprint measured on the dev-suite longslit_3x0.7_K (HIP 17971, 2012-11-28; S23d; K_long '
                    '2019-10-13 agrees to 35 A); detector-limited; PWV from the water at both edges (the CO2 '
                    'bands at 2.01 and 2.06 um are not water); thermal background term to come (D60, part K)',
              group='K', order=3, zp_nodes_A=(20500.0, 21500.0, 23000.0), common_window_A=(19800.0, 23700.0),
              pwv_window_A=((19500.0, 20000.0), (23800.0, 24000.0)), edge_trim_frac=0.9,
              lsf=LSF_PROVISIONAL),
}

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

# PypeIt sensfunc parameter files per band group (design 4.3, D52, D53; plan S23d): J's is the released
# S4b file; H and K are PROVISIONAL (polyorder 5, tell_npca 3, hydrogen_mask_wid 30 A) until the S24a
# polyorder test; Y uses the J file (hydrogen mask 10 A as in J, D52) until the Y work (part Y).
SENS_FILES = {'J': 'pypeit_par/keck_mosfire_J.sens', 'Y': 'pypeit_par/keck_mosfire_J.sens',
              'H': 'pypeit_par/keck_mosfire_H.sens', 'K': 'pypeit_par/keck_mosfire_K.sens'}

XTCALC_2012_MEDIAN = {'Y': 0.237, 'J': 0.276, 'H': 0.338, 'K': 0.317}
"""XTcalc 2012 end-to-end throughput, median over the band (design 9.2); the anchor of the throughput gate."""

THRU_GATE_RANGE = {'J': (0.15, 0.45),
                   **{b: (round(0.5 * m, 2), round(1.6 * m, 2)) for b, m in XTCALC_2012_MEDIAN.items() if b != 'J'}}
"""Per band group, the allowed median end-to-end throughput of one night's sensfunc (nautilus/gates.py):
0.5-1.6x the XTcalc 2012 median (D55; Y 0.12-0.38, H 0.17-0.54, K 0.16-0.51); J keeps the S4b range
0.15-0.45 (0.54-1.63x of 0.276)."""

LEGACY_GATE_WINDOWS = {'J': {'zp_window_A': (11170.0, 12600.0), 'counts_window_A': (11700.0, 12400.0)}}
"""The J group's gate windows as built in S4b (the J2 analysis window 1.117-1.260 um and 1.17-1.24 um),
kept so that no J gate outcome changes (S23d); the other groups use their common window."""

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
    'fwhm_nodes': {'J2': (11500.0, 12000.0, 12500.0), 'J': (12000.0, 12500.0, 13000.0),
                   # Y, H, K (9.6): the zero-point nodes of design 9.3
                   'Y': (10000.0, 10500.0, 11000.0), 'H': (15500.0, 16500.0, 17500.0), 'K': (20500.0, 21500.0, 23000.0)},
    'fwhm_halfwidth': 100.0,
    'moffat_beta': MOFFAT_BETA,         # D26
    # dome-flat rates (D42, D43): every 250 A, +-50 A boxes, central 50% of slit rows
    'flat_kind': 'dome',
    'flat_nodes': {'J2': tuple(11250.0 + 250.0 * k for k in range(6)),
                   'J': tuple(11500.0 + 250.0 * k for k in range(8)),
                   # every 250 A over the band window (9.6): Y 6, H 14, K 18 nodes
                   'Y': tuple(9750.0 + 250.0 * k for k in range(6)),
                   'H': tuple(14750.0 + 250.0 * k for k in range(14)),
                   'K': tuple(19500.0 + 250.0 * k for k in range(18))},
    'flat_halfwidth': 50.0,
    'slit_row_fraction': 0.5,
    'lamp_cards': ('FLAMP1', 'FLAMP2', 'FPOWER', 'FLATSPEC', 'DOMEPOSN'),
    # line widths and fluxes (D44, D45)
    'line_lists': {'OH': 'OH_R24000_lines.dat', 'Ne': 'Ne_IR_MOSFIRE_lines.dat',
                   'Ar': 'Ar_IR_MOSFIRE_lines.dat'},
    'lsf_ref_wave': 12500.0,
    # per-band reference wavelength of the line-width rows (the middle zero-point node; 9.6);
    # monitor.line_widths prefers this over lsf_ref_wave
    'lsf_ref_waves': {'J2': 12500.0, 'J': 12500.0, 'Y': 10500.0, 'H': 16500.0, 'K': 21500.0},
    'band_windows': {'J2': (11170.0, 12600.0), 'J': (11530.0, 13520.0),
                     'Y': (9719.0, 11243.0), 'H': (14650.0, 17971.0), 'K': (19536.0, 23991.0)},   # H, K measured (S23d)
    # monitor lines (D45, 4.9.4): frozen in S15a (2026-10-07).
    # J2 from scripts/mosfire/select_monitor_lines.py 20220409 20241230 20250723
    # --band J2 --nlines 5 (rule 2 at 1", S6b): 15 lines pass rules 1-4, every one
    # identified on 3/3 nights; the brightest per sub-window is kept (4: one
    # sub-window has none). Same four lines as the provisional 2022-04-09 list.
    # Output keck_etcs/data/mosfire/monitor/monitor_lines_J2.ecsv, sha256
    # faedee86e3d2cd9eab6cac04f84ff0ba1b950a7868c8579048146eddc5e332d3
    # (2024-12-30 and 2025-07-23 reduced locally at PypeIt etc-fixes + the
    # MOSFIRE (align) arc-extraction fix, pending the 0.2.2 pod rerun).
    # J (and Ne/Ar lamp lines) are not frozen yet: no J long-slit night has
    # been reduced (the J pilot nights are long2pos_specphot, rerun with 0.2.2).
    # Y, H and K: empty until frozen on their reference and pilot nights (parts H, K, Y).
    'monitor_lines': {'OH': {'J2': (11591.847, 11788.495, 12229.206, 12287.158), 'J': (),
                             'Y': (), 'H': (), 'K': ()}},
    'monitor_lines_status': 'frozen',
}

def sens_par_file(band):
    """Path under ``keck_etcs/data`` of the PypeIt ``.sens`` file of a band (by its group; :data:`SENS_FILES`)."""
    group = BANDS[str(band)].group_name
    return SENS_FILES[group]


def gate_windows(band):
    """The per-band windows and limits of ``nautilus/gates.py`` (design 4.8.7, D55).

    Returns:
        dict: ``zp_window_A`` (the group's common window: the zero point must
        be finite there), ``counts_window_A`` (its middle third: the
        ``OPT_COUNTS`` fidelity window), ``thru_range`` (the allowed median
        end-to-end throughput over ``zp_window_A``) and ``group``.
    """
    b = BANDS[str(band)]
    if b.group_name in LEGACY_GATE_WINDOWS:
        return {'group': b.group_name, **LEGACY_GATE_WINDOWS[b.group_name], 'thru_range': tuple(THRU_GATE_RANGE[b.group_name])}
    lo, hi = b.common_window_A
    third = (hi - lo) / 3.0
    return {'group': b.group_name, 'zp_window_A': (float(lo), float(hi)),
            'counts_window_A': (float(lo + third), float(hi - third)),
            'thru_range': tuple(THRU_GATE_RANGE[b.group_name])}


MOSFIRE = Instrument(
    name='keck_mosfire',
    area_m2=AREA_M2,
    platescale=PLATESCALE,
    bands=BANDS,
    eras=ERAS,
    gaps=GAPS,
    lsf_slope=LSF_SLOPE,
    lsf_floor_pix=LSF_FLOOR_PIX,
    lsf_form=LSF_FORM,
    detector_file='mosfire/detector.ecsv',
    sky_grid_file='sky/gemini_mk_sky_grid.fits',
    lsf_file='mosfire/lsf_measurements.ecsv',
    # S10 (design 4.5); one file per band group and era since S23b (D49): the J files, named
    # mosfire_thru_<tag>.ecsv in release mosfire-J-2026.10, are mosfire_thru_J_<tag>.ecsv from
    # mosfire-2026.10 on, with the same numbers
    throughput_pattern='mosfire/throughput/mosfire_thru_{group}_{tag}.ecsv',
    # placeholder for a group without any reduced standard (S23a): XTcalc's 2012 efficiency x KMRef^2
    # with the shipped filter divided out (scripts/mosfire/build_provisional_throughput.py); used
    # with a PROVISIONAL warning until the group's first era file exists
    throughput_provisional_pattern='mosfire/throughput/mosfire_thru_{group}_provisional.ecsv',
    moffat_beta=MOFFAT_BETA,
    monitor=MONITOR,
)
