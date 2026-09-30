# Keck MOSFIRE implementation, part 2: first sensfunc (Phase 1)

## Goals

Reduce the 2022-04-09 J2 long-slit night with PypeIt, build the LDS749B
sensitivity function with the `IR` (telluric) algorithm, harvest its zero
point and throughput into the per-standard table, and measure the line-spread
function from OH lines. These are steps S4, S5, S6 and S13 of the plan.

Run order: after part 1 (S1 for the data root, S2 for the telluric grid).
S4 -> S5 -> S6 in sequence; S13 needs only S4 and can run in parallel with S5
or S6. S6 also needs the filter curves from part 3 step S8; if part 3 has not
run yet, do S6 without the filter division and note it. Part 3 (ETC core) can
run in parallel with this doc. The reductions are compute-bound (tens of
minutes); keep S4 in its own session.

## Context

- Design: `docs/keck_mosfire_design.md`, sections 2 (D1-D8, D19, N1, N3),
  4.2 (workflow and data root), 4.3 (sensfunc and telluric settings), 4.4
  (metrics and the per-standard table columns), 5.3.6 (LSF model), 8 (open
  items: J2 red edge, LSF constants).
- Plan: `docs/keck_mosfire_implementation.md`, steps S4, S5, S6, S13 and
  the risks section.
- Data root `KECK_ETCS_DATA` (default
  `/Users/xavier/Projects/PypeIt/keck-etcs-data`): raw frames in
  `mosfire/20220409/raw/`; write reductions to `mosfire/20220409/redux/` and
  sensfuncs to `mosfire/20220409/sens/`. Nothing there is committed.
- Night contents (from `scripts/inspect_mosfire_j2_headers.py`): dome flats
  m220409_0017-0021 (lamp on) and 0022-0026 (lamp off), 10 s CDS; science
  J0841+3814_OFF m220409_0036-0039, 4 x 150 s, MCDS-16, ABBA +/-2" on
  LONGSLIT-46x1, airmass 1.07; standard LDS749B m220409_0218-0219, 2 x 120 s,
  MCDS-16, AB +/-6.5" on LONGSLIT-46x5, airmass 1.58. No seeing, read-noise or
  PWV cards in the headers.
- Template pypeit file:
  `/Users/xavier/Projects/PypeIt/PypeIt-development-suite/pypeit_files/keck_mosfire_j2_long.pypeit`
  (written with PypeIt 1.8; note the hand-typed `standard` rows, the
  `comb_id`/`bkg_id` pairing for nods, `snr_thresh = 80`, and
  `PATH_TO_RAW_DATA`). PypeIt types MOSFIRE standards by `exptime < 20 s`, so
  the 120 s LDS749B frames must be retyped by hand.
- PypeIt (2.0.2.dev at `/Users/xavier/Projects/PypeIt/PypeIt`): CLIs
  `pypeit_setup -s keck_mosfire -r RAW -d REDUX -c all`, `run_pypeit
  FILE.pypeit -r REDUX`, `pypeit_sensfunc SPEC1D --algorithm IR -s FILE.sens
  -o OUT.fits`. MOSFIRE defaults in `pypeit/spectrographs/keck_mosfire.py`:
  sensfunc `IR`, `polyorder = 13`, `telgridfile = TellPCA_3000_26000_R10000.fits`,
  `tweak_standard` zeroes J2 outside 11170-12600 A. The dev suite has one
  `.sens` example: `sensfunc_files/keck_mosfire_Y_long.sens`. The `SensFunc`
  datamodel (`pypeit/sensfunc.py`) holds `wave`, `zeropoint`, `throughput`,
  `airmass`, `exptime`, `std_name`, `std_cal`, `std_ra`, `std_dec`,
  `telluric` (model table with `TELL_THETA`: pressure, temperature, water,
  airmass, resolution, shift, stretch), `algorithm`. Zero point to throughput:
  `pypeit.core.flux_calib.zeropoint_to_throughput(wave, zeropoint,
  eff_aperture)` with Keck `eff_aperture = 72.3674` m^2 (decision N1).
  Standard lookup: `pypeit.core.standard.get_standard_spectrum(ra=, dec=)`;
  LDS749B resolves to CALSPEC `lds749b_stisnic_008.fits.gz`
  (`scripts/check_mosfire_standards.py`).
- spec1d fields for QA: `S2N` (`med_s2n`), `FWHM`, `FWHMFIT`, `OPT_COUNTS`,
  `OPT_COUNTS_IVAR`, `OPT_COUNTS_SKY`.
- Existing scripts: `scripts/inspect_mosfire_j2_headers.py`,
  `scripts/check_mosfire_standards.py`, `scripts/mosfire_band_footprints.py`
  (dispersion 1.30 A/pix in J2).
- Rules (CLAUDE.md): the user runs git; `conda run -n pypeit14`; scripts on
  disk; if a PypeIt value is verified wrong, fix it on a branch in the PypeIt
  checkout, not here; log each prompt.

## Prompts

1. **S4: reduce the 2022-04-09 night.** Write
   `scripts/mosfire/reduce_standard.py` (v0): given a night directory under
   the data root, run `pypeit_setup`, patch the generated pypeit file
   (retype standards longer than 20 s as `standard`, set nod pairs'
   `comb_id`/`bkg_id` from `dithpos`, apply the parameter block of the
   dev-suite template), and run `run_pypeit` into `redux/`. Keep the pypeit
   file it produces under `scripts/mosfire/pypeit_files/keck_mosfire_20220409_J2.pypeit`
   in the repo. Run it on `mosfire/20220409/`. Verify: spec1d files exist for
   both LDS749B frames (positive and negative traces) and all four J0841
   frames; report `FWHM` (pixels and arcsec) and `S2N` for every object; the
   wavelength-solution RMS is below PypeIt's threshold; the QA PNGs exist.
   Risks: PypeIt 2.0 may have changed `pypeit_setup` options or frame typing
   since the 1.8 template; `snr_thresh = 80` may need lowering for the
   standard; the run takes tens of minutes, so run it in the background and
   poll. Log your work, including run time and any parameter changes.

2. **S5: LDS749B sensfunc for J2.** Create
   `keck_etcs/data/pypeit_par/keck_mosfire_J.sens` with the settings of
   design 4.3 (`algorithm = IR`, `polyorder = 6`, `extrap_blu = extrap_red =
   0`, `[[IR]] telgridfile = TellPCA_3000_26000_R10000.fits`, `maxiter = 2`)
   and run `pypeit_sensfunc` on the LDS749B spec1d, output
   `mosfire/20220409/sens/sens_LDS749B_20220409.fits` plus QA. Write
   `scripts/mosfire/inspect_sensfunc.py` that opens a `SensFunc` file and
   prints the fitted telluric parameters (PWV, airmass), the zero point at
   1.20, 1.25 and 1.30 um, and the implied end-to-end throughput (via
   `zeropoint_to_throughput` with 72.3674 m^2) at those wavelengths and its
   median over 1.117-1.260 um; also plot the fluxed standard against the
   CALSPEC model to judge the red trim (open item: is 1.260 um the clean red
   edge?). Verify: the zero point is finite over 1.117-1.260 um; the median
   throughput is between 0.15 and 0.45 (XTcalc's 2012 value is 0.28);
   telluric residuals near 1.13 um are below 5 percent. Risks: the star is
   faint (J ~ 15) in a 5" slit with two 120 s frames, so the fit may be
   unstable; fall back to `polyorder` 4-5 or `--extr BOX`; if the telluric
   fit does not converge, fix PWV and airmass at plausible values and say so.
   Log your work, with the PWV, airmass, zero points and red-edge judgement.

3. **S6: harvest zero points and throughput.** Write
   `keck_etcs/calib/harvest.py` (importable; may import PypeIt) that reads
   one or more `sens_*.fits` files and produces (a) one ECSV row per standard
   with the columns of design 4.4 (`date, mjd, koa_id, standard, std_class,
   std_model, filter, slit_width, slit_length, sampmode, numreads, exptime,
   airmass, pwv_fit, seeing_fwhm_pix, zp_1200, zp_1250, zp_1300,
   thru_median_1117_1260, thru_curve_file, pypeit_version,
   keck_etcs_version, flag`), reading slit width and readout mode from the
   raw header via the sensfunc's spec1d provenance or a night manifest, and
   (b) the telescope+spectrograph+detector throughput curve on a common 1 A
   vacuum grid with the filter curve divided out (skip the division and set
   `flag = nofilter` if part 3's filter files do not exist yet). Outputs go to
   `keck_etcs/data/mosfire/throughput/standards.ecsv` and
   `keck_etcs/data/mosfire/throughput/standards/<standard>_<date>.ecsv`, each
   with the provenance `meta` of design 5.4. Add the CLI
   `scripts/mosfire/harvest_sens.py`. Verify: the LDS749B row has every
   column filled; recomputing throughput from the stored zero point with
   `zeropoint_to_throughput` and 72.3674 m^2 matches the stored curve to
   1e-6 before filter division; `pypeit_version` in the row equals
   `pypeit.__version__`. Risk: the `SensFunc` datamodel or `TELL_THETA` layout
   may differ from the notes above; read `pypeit/sensfunc.py` and
   `pypeit/core/telluric.py` first and keep the reader tolerant. Log your
   work.

4. **S13: LSF from OH lines.** Write `scripts/mosfire/measure_lsf.py` that
   reads the `WaveCalib` product of S4 (per-line FWHM from the OH-line fits in
   the J0841 frames, 1" slit) and reports the LSF FWHM in pixels and in A
   versus wavelength, and R at 1.25 um. Compare with the design's model
   `FWHM_pix = max(slit / 0.24, 2.2)` (4.2 pix for 1") and R = 3310 x 0.7 /
   1.0 = 2300. Record the measured values in a table
   `keck_etcs/data/mosfire/lsf_measurements.ecsv` (slit width, FWHM_pix, R,
   date, source) with provenance; the instrument module of part 3 (S8) will
   read it. Verify: FWHM_pix for the 1" slit is within 20 percent of 4.2; R
   within 15 percent of 2300; if not, say which of the floor or the slope is
   off and propose the revised constants. Only one slit width is available
   now; the slope needs the KOA nights of part 5. Log your work.

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
