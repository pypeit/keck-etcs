# Keck/MOSFIRE J: implementation plan

*Version 0.1, 2026-09-29. Companion to `docs/keck_mosfire_design.md`; section
numbers below refer to that document. Each step is meant to be one working
session and to become one numbered prompt under "### Implementation" in
`claude_prompts/keck_mosfire_prompts.md`.*

Rules that apply to every step: Python via `conda run -n pypeit14`; git is the
user's; calculations are scripts on disk; nothing under `KECK_ETCS_DATA` is
committed; every new data file carries the provenance `meta` of design 5.4;
each step ends with a Log entry in the prompt doc.

## Dependency map

```
Phase 0  S1 data root ──┬── S3 sky grid FITS ──────────────┐
         S2 telluric grid ─┐                                 │
Phase 1  S4 reduce 2022-04-09 (needs S1) ── S5 LDS749B sensfunc (needs S2, S4) ── S6 harvest ── S10 throughput v0
         S13 LSF from OH lines (needs S4)                                                          │
Phase 2  S7 core modules (needs S3 for sky) ── S9 compute()/CLI/regression (needs S7, S8, S10 or provisional)
         S8 mosfire instrument module + data files (parallel with S7)                              │
Phase 3  S11 J0841 validation (needs S4, S9, S10)   S12 XTcalc comparison (needs S9)               │
Phase 4  S14 KOA search (own prompt doc; parallel from the start) ── S15 batch reductions (needs S6, S14) ── S16 trend + release
Phase 5  S17 PypeIt ronoise branch (needs S8)      S18 docs/README/CHANGES/WMKO note (needs S9, S16)
```

Parallel groups: {S1, S2, S14}; {S3, S4}; {S7, S8, S5}; {S11, S12, S13};
{S17, S18 draft}.

## Phase 0: foundations

### S1. Data root and external caches
- **Goal:** create the out-of-repo data root and put the XTcalc tarball there;
  give the package one place to resolve paths.
- **Inputs:** `KECK_ETCS_DATA` (default `/Users/xavier/Projects/PypeIt/keck-etcs-data`);
  `https://www2.keck.hawaii.edu/inst/mosfire/XTcalc.tar` (46 MB).
- **Outputs:** directory tree `external/xtcalc/XTcalc_dir/`,
  `mosfire/20220409/raw/` (symlink or copy of the 16 dev-suite frames);
  `keck_etcs/paths.py` (`data_root()`, `night_dir(instrument, date)`);
  `.gitignore` rules for `*.fits` outside `keck_etcs/data/`, `*.sav`, `*.tar`;
  a `README` line documenting the env var.
- **Verify:** `scripts/inspect_xtcalc_files.py $KECK_ETCS_DATA/external/xtcalc/XTcalc_dir`
  reproduces the numbers in the Prompt #1 log; `python -c "from keck_etcs import paths; print(paths.data_root())"`.
- **Depends on:** nothing.

### S2. Fetch the PypeIt telluric grid
- **Goal:** have `TellPCA_3000_26000_R10000.fits` in the PypeIt cache.
- **Inputs:** network access to PypeIt's S3 host.
- **Outputs:** the file in `~/.cache/pypeit/`; `scripts/fetch_telluric_grid.py`
  that calls `pypeit.dataPaths.tel_model.get_file_path(name)` and reports the
  cache path and size.
- **Verify:** `pypeit.pkg.cache.search_cache('TellPCA')` returns one path;
  size about 6 MB; the file opens with astropy.
- **Depends on:** nothing. **Risk:** the S3 host or the `dataPaths` API name
  may differ in PypeIt 2.0; fall back to `pypeit_cache_github_data` or the
  installing docs (`doc/installing.rst`, "Atmospheric Models").

### S3. Gemini sky and transmission grid as committed FITS
- **Goal:** design 5.4's `gemini_mk_sky_grid.fits`.
- **Inputs:** the 24 `.sav` files under `external/xtcalc/XTcalc_dir/Mauna_Kea_sky/`.
- **Outputs:** `scripts/mosfire/build_gemini_sky_grid.py` (flux-conserving
  rebin to 0.05 nm over 950-2450 nm; HDUs `WAVE`, `SKYBG`, `TRANS`, `GRID`;
  provenance header); `keck_etcs/data/sky/gemini_mk_sky_grid.fits` (~3 MB);
  entry in `keck_etcs/data/index.yaml`.
- **Verify:** for each grid, the integral of the rebinned sky over 1.17-1.33 um
  matches the native integral to 1e-3; the transmission median in J matches
  `inspect_xtcalc_files.py` (0.9976 at PWV 1.6, X 1.0); file size < 5 MB;
  `git status` shows only the new FITS, script and index entry.
- **Depends on:** S1. **Risk:** wavelength convention (assumed vacuum, N5) and
  whether the `.sav` transmission wavelengths are in micron while the sky is in
  nm (they are; the script must handle both).

## Phase 1: first sensfunc

### S4. Reduce the 2022-04-09 night
- **Goal:** spec1d files for LDS749B and J0841+3814.
- **Inputs:** `mosfire/20220409/raw/`, the dev-suite
  `keck_mosfire_j2_long.pypeit` (as a template; `PATH_TO_RAW_DATA` replaced).
- **Outputs:** `mosfire/20220409/redux/` with `Calibrations/`, `Science/spec1d_*`
  and `spec2d_*`, QA; `scripts/mosfire/reduce_standard.py` v0 (generates a
  pypeit file from a night directory, retypes standards longer than 20 s,
  runs `run_pypeit`); the repo-owned pypeit file used, under
  `keck_etcs/data/pypeit_par/` or `scripts/mosfire/pypeit_files/`.
- **Verify:** objects found in both standard frames (positive and negative
  traces) and in the four science frames; `FWHM` in pixels reported; the
  LDS749B `S2N` (`med_s2n`) logged; the wavelength solution RMS below PypeIt's
  threshold.
- **Depends on:** S1. **Risk:** PypeIt 2.0 may have changed `pypeit_setup`
  options or frame typing since the 1.8 template was written; the run takes
  tens of minutes; `snr_thresh = 80` in the template may need lowering for the
  standard.

### S5. LDS749B sensfunc (J2)
- **Goal:** a telluric-corrected `IR` sensfunc for J2.
- **Inputs:** `spec1d_*LDS749B*.fits` from S4; the telluric grid from S2.
- **Outputs:** `keck_etcs/data/pypeit_par/keck_mosfire_J.sens` (polyorder 6,
  design 4.3); `mosfire/20220409/sens/sens_LDS749B_20220409.fits` and QA
  plots; a short note on the fitted PWV and airmass.
- **Verify:** the zero point is finite over 1.117-1.260 um; the implied
  end-to-end throughput has median 0.15-0.45 over that window (XTcalc's 2012
  value is 0.28); telluric residuals near 1.13 um are below 5 percent; the red
  trim at 1.260 um judged from the fluxed spectrum (D8, open item).
- **Depends on:** S2, S4. **Risk:** low S/N (J ~ 15 star, 2 x 120 s, 5" slit
  admitting 7x the sky of a 0.7" slit) may make the polynomial fit unstable;
  fall back to polyorder 4-5 or a BOX extraction; if the telluric fit fails to
  converge, fix PWV and airmass at plausible values and note it.

### S6. Harvest zero points and throughput
- **Goal:** the per-standard table and curve archive of design 4.4.
- **Inputs:** `sens_*.fits` files (one so far).
- **Outputs:** `keck_etcs/calib/harvest.py` (reads `SensFunc` datamodel fields
  `wave`, `zeropoint`, `throughput`, `airmass`, `exptime`, `std_name`,
  `std_cal`, `telluric` model parameters; computes `zp_1200/1250/1300`,
  `thru_median_1117_1260`; divides out the filter curve); per-standard ECSV
  row in `keck_etcs/data/mosfire/throughput/standards.ecsv` and the curve
  file; `scripts/mosfire/harvest_sens.py` CLI.
- **Verify:** the LDS749B row has all fields; recomputing throughput from the
  zero point with `flux_calib.zeropoint_to_throughput` and A = 72.3674 m^2
  matches the stored curve to 1e-6; the row's `pypeit_version` matches
  `pypeit.__version__`.
- **Depends on:** S5, S8 (filter curves). **Risk:** the `SensFunc` datamodel
  or the telluric parameter layout (`TELL_THETA`) may differ from what was
  read on 2026-09-29; keep the reader tolerant and log the version.

### S13. LSF from OH lines (can run any time after S4)
- **Goal:** replace the XTcalc LSF constants (2.2 pix floor, 0.24"/pix slope).
- **Inputs:** the wavelength calibration of S4 (arc/tilt from the science
  frames' OH lines; PypeIt's `WaveCalib` `fwhm` per line) for the 1" slit,
  and, once available, other slit widths from KOA nights.
- **Outputs:** `scripts/mosfire/measure_lsf.py`; values written into
  `instruments/mosfire.py` with source comments; a figure of FWHM_pix versus
  slit width.
- **Verify:** for the 1" slit, FWHM_pix is within 20 percent of 1.0/0.24 = 4.2
  pix; R at 1.25 um within 15 percent of 3310 x 0.7 / 1.0 = 2300.
- **Depends on:** S4; more slit widths need S15.

## Phase 2: ETC core

### S7. Core modules and schemas
- **Goal:** design 5.1's `core/` and the two JSON schemas, without instrument
  specifics.
- **Inputs:** design 5.2 and 5.3; the sky grid FITS from S3 (a synthetic grid
  can stand in for unit tests).
- **Outputs:** `keck_etcs/core/{source,atmosphere,sky,slitloss,lsf,detector,snr}.py`;
  `keck_etcs/schema/etc_input.json`, `etc_output.json`; unit tests of design
  6.2 (analytic cases) in `keck_etcs/tests/test_core_*.py`.
- **Verify:** `pytest keck_etcs/tests -k core` passes; the Moffat plane
  integral is 1 to 1e-4; the exptime solver round-trips to 1e-6; the schemas
  validate the examples with `jsonschema` (add to `requirements.txt`).
- **Depends on:** S3 (loosely). **Risk:** numerical cost of the 2-D Moffat
  integral on a 0.01" grid for large apertures; cache by (FWHM, w, L).

### S8. MOSFIRE instrument module and data files
- **Goal:** `instruments/mosfire.py` and the data it loads.
- **Inputs:** Keck filters page ASCII curves (J, J2; also Y, J3, H, K while
  there), Keck detector page numbers, design section 3, band windows (N2).
- **Outputs:** `keck_etcs/instruments/base.py`, `mosfire.py`;
  `keck_etcs/data/mosfire/filters/mosfire_<band>.ecsv`;
  `keck_etcs/data/mosfire/detector.ecsv`; `keck_etcs/data/index.yaml` entries;
  `scripts/mosfire/fetch_keck_filter_curves.py`; a computed Vega-AB offset per
  band stored in the filter `meta`.
- **Verify:** `RN(16) = 5.8`, `RN(1) = 21`; the J Vega offset is 0.85-0.97;
  the J2 half-power bandpass from the curve matches 1.181 +/- 0.065 um to 0.01
  um; every data file has the provenance `meta` keys.
- **Depends on:** nothing (parallel with S7). **Risk:** the Keck filter ASCII
  files may be imaging-only curves or in air wavelengths; note which and
  convert to vacuum.

### S9. `compute()`, CLI and regression fixtures
- **Goal:** the public API end to end for J and J2.
- **Inputs:** S7, S8, and a throughput product: S10 if available, otherwise a
  provisional curve made from XTcalc's `Jeff.sm.dat` x 0.89^2 and labeled
  `calib_version = provisional-xtcalc-2012` (must be replaced before release).
- **Outputs:** `keck_etcs/etc.py` (`validate`, `compute`); `bin/keck_etc`;
  `keck_etcs/tests/data/reference_{J,J2,line}.json` and
  `test_regression.py`; `scripts/regen_regression_fixtures.py`.
- **Verify:** `keck_etc examples/J_point.json` prints a summary; regression
  tests pass; a J = 20 AB point source, 0.7" slit, 0.7" seeing, 4 x 120 s
  MCDS-16 ABBA at airmass 1.2 gives a band-median `snr_pixel` within a factor
  2 of XTcalc's number for the same inputs (the S12 script makes this exact).
- **Depends on:** S7, S8; S10 preferred.

## Phase 3: validation

### S10. Throughput product v0
- **Goal:** the first era file from the one standard we have.
- **Inputs:** S6 table and curve.
- **Outputs:** `keck_etcs/calib/combine.py`;
  `keck_etcs/data/mosfire/throughput/mosfire_thru_2017-2025.ecsv` with
  `n_std = 1` and `thru_mad = NaN`; `index.yaml` entry with
  `calib_version = mosfire-J-2026.10-dev`.
- **Verify:** the file loads through `instruments/mosfire.py`; `compute`
  echoes `meta.era = 2017-02..2025-02` for `throughput.date = 2022-04-09`.
- **Depends on:** S6.

### S11. Validation against J0841+3814
- **Goal:** design 6.1.
- **Inputs:** spec1d science files from S4; sensfunc from S5; `compute` from
  S9 with S10.
- **Outputs:** `scripts/mosfire/validate_j0841.py` (fluxes with
  `pypeit_flux_calib`, measures S/N per pixel per frame and for the coadd,
  runs the ETC with the fluxed spectrum as `user` shape, writes a comparison
  ECSV and a figure); `keck_etcs/tests/test_validation_j0841.py` marked
  `slow`; a results section appended to the design doc.
- **Verify:** median ratio ETC/measured within 20 percent over 1.117-1.260 um;
  within 10 percent between OH lines; the fitted effective aperture factor and
  any `sky_scale` recorded in the instrument config with provenance.
- **Depends on:** S4, S9, S10. **Risk:** the quasar is faint, so the measured
  S/N between OH lines may itself be noisy; use 50 A bins and the four-frame
  coadd.

### S12. XTcalc sanity comparison
- **Goal:** design 6.2's script.
- **Inputs:** XTcalc data files (S1) and formula (Prompt #1 log); `compute`.
- **Outputs:** `scripts/mosfire/compare_xtcalc.py` producing a table of
  S/N ratios for J magnitudes 17-23 and slits 0.7", 1.0" at 4 x 120 s; an
  appendix in the design doc.
- **Verify:** the script reproduces XTcalc's example (K, 0.7", 16 reads,
  m = 18.6 AB, 1000 s) within 10 percent when run in "XTcalc mode" against its
  own inputs; the ratio to ours is explained by the known differences
  (throughput era, RN model, slit loss, sky model).
- **Depends on:** S9.

## Phase 4: time series

### S14. KOA standards search (own prompt doc)
- **Goal:** the candidate list of design 4.1 and the `SAMPMODE` census.
- **Inputs:** KOA (koa.ipac.caltech.edu) MOSFIRE metadata; the standard lists
  (PypeIt `calspec_info.txt`, `xshooter_info.txt`; SIMBAD for A0V).
- **Outputs:** `claude_prompts/koa_search_prompts.md` (new prompt doc, per the
  project decisions); `scripts/koa/search_mosfire_standards.py`;
  `keck_etcs/data/mosfire/koa_standards_candidates.ecsv` (dates, KOA IDs,
  slit, filter, `SAMPMODE`, `NUMREADS`, airmass, program, 2MASS J for A0V);
  the `SAMPMODE` histogram for science frames; downloads into
  `mosfire/<YYYYMMDD>/raw/` for the first batch (priority: Hennawi/Yang/Wang
  nights; wide-slit standards).
- **Verify:** the 2022-04-09 LDS749B frames appear in the candidate list; the
  table has at least 10 wide-slit standards or, if not, the shortfall is
  reported against the Q3 open item.
- **Depends on:** S1 for the download location; otherwise independent.
  **Risk:** KOA query interface (TAP/PyKOA) and proprietary periods; the
  wide-slit sample may be small (Q3, Josh Walawender).

### S15. Batch reductions and harvest
- **Goal:** sensfuncs for every candidate night.
- **Inputs:** S14 downloads; `reduce_standard.py` from S4; `harvest_sens.py`
  from S6.
- **Outputs:** `mosfire/<YYYYMMDD>/{redux,sens}` per night; rows appended to
  `standards.ecsv`; a per-night status table (`success`, `no calibs`,
  `fit failed`) in the prompt-doc log.
- **Verify:** every processed night has a row or a recorded failure reason;
  narrow-slit standards land in the slit-loss sample with their `FWHM`.
- **Depends on:** S6, S14. **Risk:** nights without dome flats; masks with the
  standard in a `long2pos` configuration need PypeIt's `long2pos` handling;
  run time (allow several sessions; this step will likely be split by year).

### S16. Trend analysis and first calibration release
- **Goal:** design 4.5-4.6 and D28.
- **Inputs:** `standards.ecsv` with >= 10 wide-slit standards over >= 2 eras.
- **Outputs:** `keck_etcs/calib/trend.py`; `scripts/mosfire/plot_throughput_trend.py`;
  per-era `mosfire_thru_<era>.ecsv`; `index.yaml` bumped to
  `mosfire-J-YYYY.MM`; `CHANGES.md` section; the regression fixtures
  regenerated deliberately.
- **Verify:** per-era median and MAD reported; the 3-MAD exclusion list
  documented; the 2012-2016 era median within ~10 percent of XTcalc's curve
  after the aperture correction (design 4.6); `compute` with
  `throughput.date` in each era returns that era's curve.
- **Depends on:** S15.

## Phase 5: wrap-up

### S17. PypeIt `ronoise` branch
- **Goal:** D19.
- **Inputs:** the Keck RN table (S8) and, if feasible, an RN check from two
  dome flats at `NUMREADS = 1` (CDS) in our data (their difference divided by
  sqrt(2), in electrons).
- **Outputs:** a branch in `/Users/xavier/Projects/PypeIt/PypeIt` (the user
  creates it and commits; the session edits `keck_mosfire.py`'s
  `get_detector_par` to read `SAMPMODE`/`NUMREADS` from `hdu` and look up RN,
  defaulting to 5.8 when no header is given), plus a unit test in PypeIt.
- **Verify:** `get_detector_par(1, hdu)` returns 21 for the CDS flats and 5.8
  for the MCDS-16 frames; PypeIt's own tests pass.
- **Depends on:** S8. **Risk:** PypeIt's dev-suite expectations may encode the
  fixed 5.8 for the flats.

### S18. Documentation, README, CHANGES, WMKO API note
- **Goal:** items 4 and 6 of the definition of done.
- **Inputs:** everything above.
- **Outputs:** design doc updated to "as built" with validation and XTcalc
  appendices; `README.md` usage (Python and CLI, env var, how to refresh
  calibrations); `CHANGES.md`; `docs/wmko_api_note.md` (one page).
- **Verify:** README example runs as written; `index.yaml` and `CHANGES.md`
  agree on the calibration version; the WMKO note lists every schema field.
- **Depends on:** S9, S16 (a draft can be written after S9).

## Risks across steps

- **LDS749B S/N.** Faint star, wide slit, two frames: the first sensfunc may
  be noisy and the J2 red edge hard to judge; S5 has fallbacks and S15 brings
  brighter stars.
- **PypeIt 2.0 API drift.** Between the 1.8 template and today, standard
  lookup moved to `pypeit.core.standard`, the cache to `pypeit.pkg.cache`, and
  the data paths to `pypeit.dataPaths`; assume other names have moved and
  read the source before coding (S2, S4, S6).
- **Wide-slit sample size** depends on Keck practice (Q3, Josh Walawender).
- **Gemini grid provenance** is second hand (XTcalc `.sav`); verify against
  gemini.edu if it becomes reachable.
- **Network dependence** of S2 and S14; nothing else needs the network.
- **Run time.** S4 and S15 are compute-bound; keep them in their own
  sessions and log intermediate status.
- **Regression churn.** Every calibration release changes numbers; the
  fixtures are regenerated only in S16-type steps, with a `CHANGES.md` line.
