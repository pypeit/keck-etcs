# Keck MOSFIRE implementation, part 3: ETC core (Phase 2)

## Goals

Build the instrument-agnostic ETC core and its JSON schemas, the MOSFIRE
instrument module with its data files, and the public `compute(dict) -> dict`
entry point with a CLI and regression fixtures. These are steps S7, S8 and S9
of the plan. Everything in this doc runs locally (design D38); nothing here
touches Nautilus or S3.

Run order: S7 and S8 are independent of each other and can run in parallel
(or in either order); S9 needs both. S7 needs the sky-grid FITS from part 1
(S3). S9 prefers the throughput product of part 4 (S10); if it does not exist
yet, use the provisional XTcalc curve described in prompt 3 and label it as
such. This whole doc can run in parallel with part 2. Note for scheduling:
the filter curves of S8 are read by the in-pod harvest of part 2, so S8
should be merged before the `0.2.0` image build that precedes part 5's
batches; until then in-pod harvest rows carry `flag = nofilter`.

## Context

- Design: `docs/keck_mosfire_design.md` (v0.3), sections 2 (D10-D13, D15-D17,
  D20-D21, D25-D28, D38, N1, N2, N4-N7), 3 (instrument facts), 5.1 (package
  layout), 5.2 (input and output fields, units, defaults, ranges), 5.3 (all
  equations), 5.4 (data files and provenance), 5.5 (versioning), 6.2 (unit
  and regression tests).
- Plan: `docs/keck_mosfire_implementation.md` (v0.3), steps S7, S8, S9.
- Inputs already in the repo after part 1: `keck_etcs/data/sky/gemini_mk_sky_grid.fits`
  (HDUs `WAVE` nm, `SKYBG`, `TRANS`, `GRID`), `keck_etcs/data/index.yaml`,
  `keck_etcs/paths.py`.
- Instrument numbers (design section 3): area 72.3674 m^2; plate scale
  0.1798"/pix spatial, 0.24"/pix dispersion; gain 2.15; RN CDS 21, MCDS-4
  10.8, -8 7.7, -16 5.8, -32 4.2, -64 3.5, -128 3.0 e-; dark 0.008 e-/s/pix;
  linearity 26k/37k/43k ADU; min integration 1.455 s; dispersion Y 1.08,
  J 1.30, J2 1.30, H 1.63, K 2.17 A/pix; filters J 1.253/0.200 um, J2
  1.181/0.129 um (center/FWHM), with ASCII curves on
  `https://www2.keck.hawaii.edu/inst/mosfire/filters.html`; J2 clean window
  1.117-1.260 um; era boundaries 2016-09-15 / 2017-02-13 and 2025-02-11 /
  2025-04-29; LSF constants floor 2.2 pix and slope 0.277"/pix (interim,
  from part 2 S13, 2026-10-04; it was 0.24"/pix), with the measured rows of
  `keck_etcs/data/mosfire/lsf_measurements.ecsv` taking precedence for
  their slit width (1": FWHM 3.61 px, R 2677 at 1.25 um).
- Vega spectrum for the AB-Vega offsets: PypeIt's
  `pypeit/data/standards/vega_tspectool_vacuum.dat` (vacuum wavelengths). Copy
  it or its synthetic magnitudes into `keck_etcs/data/` so that `core` and
  `etc` never import PypeIt (design 5.1); only `calib` may.
- XTcalc reference for the provisional throughput and the sanity check:
  `$KECK_ETCS_DATA/external/xtcalc/XTcalc_dir/MosfireSpecEff/Jeff.sm.dat`
  (instrument-only; multiply by 0.89^2 for the Keck mirrors); XTcalc's
  formulas are summarized in the Prompt #1 log of `keck_mosfire_prompts.md`
  and in `docs/MOSFIRE_XTcalc.pdf` from the Keck ETC page.
- Existing scripts: `scripts/inspect_xtcalc_files.py`,
  `scripts/mosfire_band_footprints.py` (template wavelength ranges span
  2600-3000 pixels because they are stitched across CSU positions; the ETC
  band window is the filter half-power bandpass intersected with the 2048-pix
  window at the long-slit position, decision N2).
- Rules (CLAUDE.md): the user runs git; `conda run -n pypeit14`; scripts on
  disk; `pytest.ini` points at `keck_etcs/tests`; add `jsonschema` and
  `pyyaml` to `requirements.txt` and `setup.py` if you use them (they then
  also enter the image's dependency layer, part 2 prompt 5); log each
  prompt.

## Prompts

1. **S7: core modules and JSON schemas.** Implement
   `keck_etcs/core/{source,atmosphere,sky,slitloss,lsf,detector,snr}.py` as
   pure functions on numpy arrays following design 5.3 exactly: source
   normalization to a filter (AB and Vega), photon rate above the atmosphere,
   transmission and sky lookup with linear interpolation in airmass and log
   PWV and clipping with a warning (N4), sky applied without atmospheric
   transmission (N6), Moffat beta 3.5 slit x aperture integral on a 0.01"
   grid with caching, top-hat extended sources, Gaussian LSF with
   `FWHM_pix = max(w/0.277, floor)` (or the measured row for that slit), RN interpolated in log2 N_reads, dark,
   stare and ABBA variances, S/N per pixel and per resolution element, line
   mode, the exposure-time quadratic (N7), and the saturation peak pixel.
   Write `keck_etcs/schema/etc_input.json` and `etc_output.json` (JSON
   Schema draft 2020-12) with every field, unit, default and range of design
   5.2. Add unit tests `keck_etcs/tests/test_core_*.py` for the analytic cases
   of design 6.2 (Poisson-only limit, unit slit fraction for a zero-width
   source, Moffat plane integral = 1 to 1e-4, RN(16) = 5.8 and RN(1) = 21,
   ABBA versus stare variance, exptime solver round-trip to 1e-6, schema
   accepts the examples and rejects an out-of-range field by name). Verify:
   `conda run -n pypeit14 pytest keck_etcs/tests -k core` passes. Risk: the
   2-D Moffat integral can be slow for large apertures; cache by (FWHM, w,
   L). Log your work.

2. **S8: MOSFIRE instrument module and data files.** Implement
   `keck_etcs/instruments/base.py` (an `Instrument` dataclass that loads its
   data files once) and `keck_etcs/instruments/mosfire.py` with the band
   table (window per N2, dispersion, filter file, clean window), detector
   table, era boundaries and LSF parameters, each value with a source
   comment. Write `scripts/mosfire/fetch_keck_filter_curves.py` to download
   the Keck filter ASCII curves (J and J2 required; Y, J3, H, K while there)
   into `keck_etcs/data/mosfire/filters/mosfire_<band>.ecsv` with
   `meta.source_url`, download date and whether the curve is in air or
   vacuum (convert to vacuum if needed and say so). Compute the AB-Vega
   offset per band from the Vega spectrum through each curve and store it in
   the filter `meta`. Write `keck_etcs/data/mosfire/detector.ecsv` (RN table
   plus `meta` for gain, dark, linearity, plate scales, minimum integration,
   source URLs). Register everything in `keck_etcs/data/index.yaml`. Verify:
   `RN(16) = 5.8`, `RN(1) = 21`; the J Vega offset is 0.85-0.97 (XTcalc uses
   0.91); the J2 half-power bandpass from the curve is 1.181 +/- 0.065 um to
   within 0.01 um; every data file has the provenance keys of design 5.4.
   Risk: the Keck ASCII files may be imaging curves or in air wavelengths;
   record which. Note in the log that the `0.2.0` image (part 2 prompt 5)
   must be rebuilt after this step so the in-pod harvest can divide out the
   filter. *v0.4:* if part 2 prompt 7 (S6b) has run, move the MOSFIRE
   monitor block from `keck_etcs/calib/monitor_configs.py` into
   `instruments/mosfire.py` (design 4.9.6). Leave a re-export behind so
   `monitor.py` keeps working, and check that the monitor rows for
   2022-04-09 do not change. In S7, `core.slitloss` should expose the slit
   integral that `monitor.object_fwhm` will switch to from its provisional
   copy. Log your work.

3. **S9: `compute()`, CLI and regression fixtures.** Implement
   `keck_etcs/etc.py` with `validate(inputs)` (schema check, defaults filled,
   warnings collected) and `compute(inputs) -> dict` producing every output
   field of design 5.2 with `meta.keck_etcs_version`, `meta.calib_version`,
   `meta.era`, `meta.pypeit_version` (read from `index.yaml`, not by
   importing PypeIt). Add `bin/keck_etc` (JSON file in, JSON out, `--summary`
   option) and register `bin/` in `setup.py`. Throughput: use
   `keck_etcs/data/mosfire/throughput/mosfire_thru_<era>.ecsv` from part 4
   (S10) if present; otherwise build a provisional product from XTcalc's
   `Jeff.sm.dat` x 0.89^2 with `calib_version = provisional-xtcalc-2012`,
   flagged in `index.yaml` and in every output's `warnings`, to be replaced
   before any release. Create `examples/J_point.json`, `J2_point.json`,
   `J_line.json`, freeze their outputs in
   `keck_etcs/tests/data/reference_{J,J2,line}.json`, add
   `keck_etcs/tests/test_regression.py` (fails on any relative change above
   1e-6) and `scripts/regen_regression_fixtures.py` (explicit regeneration
   only; each regeneration gets a `CHANGES.md` line). Verify:
   `conda run -n pypeit14 python bin/keck_etc examples/J_point.json
   --summary` prints the band-median S/N, per-frame peak ADU and flag; all
   tests pass; a J = 20 AB point source, 0.7" slit, 0.7" seeing, 4 x 120 s
   MCDS-16 ABBA at airmass 1.2, PWV 1.6 gives a band-median `snr_pixel`
   within a factor of 2 of XTcalc's value for the same inputs (compute
   XTcalc's number by hand from its formula, or defer the exact comparison to
   part 4 step S12 and say so); `keck_etcs.core` and `keck_etcs.etc` import
   without PypeIt, boto3 or any network access. Log your work, stating which
   throughput product the fixtures were frozen against.

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-10-05 (Prompt #1 / S7: ETC core modules, JSON schemas and analytic tests; 39 core tests pass)

**What was built** (all local, no Nautilus or S3; Python in `pypeit14b`):

- `keck_etcs/core/`, pure functions on numpy arrays. There is no I/O and no
  PypeIt, astropy or plotting import; only numpy and scipy, and
  `test_core_imports.py` enforces this.
  - `source.py`:
    - shapes (`flat_fnu`, `power_law`, `user`);
    - `mean_fnu` and `ab_mag` with the energy-weighted definition of 5.3.1;
    - `normalize_to_mag`, `vega_offset`, `to_ab`;
    - `gaussian_line` and `line_fwhm_A`;
    - `photon_rate` N0 = f_lambda A lam / hc.
  - `atmosphere.py`: `interp_grid`, which is linear in airmass and linear in
    log PWV over a rectangular (airmass, PWV) grid. Out-of-grid values are
    clipped, with warnings that name `airmass` or `pwv_mm` (N4).
    `transmission()` clips T to [0, 1].
  - `sky.py`:
    - `sky_background` = `sky_scale` x B, with no T_atm (N6);
    - `sky_rate_per_pixel` = b(lam) of 5.3.8;
    - `sky_in_aperture` = B_ap.
  - `slitloss.py`: Moffat beta 3.5 (alpha from the FWHM), giving
    `moffat_2d`, `moffat_marginal`, `slit_fraction`,
    `slit_aperture_fraction`, `aperture_quantities` (`slit_fraction`,
    `f_slit_ap`, `aperture_fraction`, `f_peak`, `n_spatial_pix`),
    `extended_fraction` (a top-hat disk convolved with the Moffat) and
    `seeing_at` (lambda^-0.2).
  - `lsf.py`:
    - `fwhm_pix` = max(w/slope, floor), or the measured value;
    - `resolving_power`, `observed_line_fwhm`, `pixel_grid`;
    - `gaussian_convolve` on a uniform grid, with the edges renormalized;
    - `convolve_to_pixels`, which first resamples a non-uniform grid.
  - `detector.py`:
    - `read_noise`, linear in log2 N_reads and clipped at the table ends;
    - `effective_reads` (CDS forces 1, with a warning);
    - `dark_electrons`;
    - `linearity_flag` (`ok`, `nonlinear_1pct`, `nonlinear_5pct`,
      `saturated`).
  - `snr.py`:
    - `signal_per_pixel` (5.3.7) and `frame_variance` (stare; ABBA with
      k = 2, D15);
    - `snr_pixel`, `snr_resel`;
    - `line_window` / `line_snr` (+/- FWHM_obs/2; flux fraction
      0.7610);
    - `solve_exptime`, the N7 quadratic, vectorized, and inf where there
      is no signal;
    - `snr_at`, the forward model;
    - `solve_exptime_median`, for the band-median reference: Brent's method
      on the monotonic median, with an expanding bracket;
    - `saturation_peak` (5.3.11).
- `keck_etcs/schema/etc_input.json` and `etc_output.json` (JSON Schema
  draft 2020-12):
  - every field of design 5.2 with its type, default, range or enum,
    description and an `x-unit` annotation;
  - `additionalProperties: false` at every level;
  - conditionals: `shape = user` needs `wave_A` and `flux`;
    `shape = line` needs `line`, which needs `wave_A` and `flux_cgs`;
  - five input examples and one output example.
  - `keck_etcs/schema/__init__.py` has `load(name)` and `errors(instance)`.
    Each message starts with the dotted field path, e.g.
    `readout.n_reads: 12 is not one of [...]`, which `etc.validate` (S9)
    can reuse.
- Tests:
  - `test_core_snr.py`, `test_core_slitloss.py`, `test_core_spectra.py`,
    `test_core_schema.py`, `test_core_imports.py`.
  - The analytic cases of 6.2 are all present:
    - Poisson-only S/N = sqrt(N_f S);
    - a zero-width source passes entirely;
    - the Moffat plane integral is 1 to 1e-4, both by a direct 2-D 0.01"
      sum and by the slit x aperture integral;
    - RN(16) = 5.8 and RN(1) = 21;
    - ABBA - stare = B + D + RN^2;
    - the exposure-time round trip holds to 1e-6, per pixel and for the
      median;
    - the schema accepts every example and rejects 8 out-of-range fields,
      each by its dotted name, plus unknown fields and missing conditional
      fields.
  - Also tested:
    - an exact AB mag for flat f_nu;
    - grid interpolation at the nodes, in airmass and in log PWV;
    - clipping warnings;
    - the convolution's integral, width and constant preservation;
    - the extended-source limits (a vanishing disk is a point source; a
      20" disk gives SB x w x L to 1e-3).
- `requirements.txt` and `setup.py`: added `jsonschema` and `pyyaml`
  (`measure_lsf.py` already imports yaml); `schema/*.json` is added to
  `package_data`. `jsonschema` 4.26.0 was installed into `pypeit14b` (pip).
  The next image build picks both up through the requirements layer.
- `scripts/ab_weighting_check.py`: the size of the AB-definition choice
  (below).

**Verify:** `conda run -n pypeit14b python -m pytest keck_etcs/tests -k
core`: 39 passed (10 deselected); the full suite has 49 passed.

**Choices and findings for review:**

- **Slit x aperture integral:** a 0.01" grid across the slit, with
  composite Simpson. Along the slit the y integral is exact: for fixed x,
  the Moffat integrates to an incomplete beta function.
  - The infinite-slit fraction is closed form, I_z(1/2, beta-1) with
    z = (w/2)^2 / ((w/2)^2 + alpha^2).
  - Design 5.3.5 says "numerically on a 0.01" grid". A plain midpoint 2-D
    grid has a relative error of about 7e-5 for a 0.5" PSF (the test caught
    this); Simpson brings it to about 1e-8.
  - Results are cached by (FWHM, w, L).
  - Point source: 0.3 ms. Extended worst case (20" disk, 5" x 15"
    aperture, 0.3" seeing): 2.5 s on the first call, then cached.
- **The monitor's provisional `moffat_slit_fraction`** (a 0.034" 2-D box)
  is up to 1.2 points off:
  - FWHM 0.896" in a 1" slit gives 0.692 against the exact 0.705, so
    J0841's slit loss of 30.8% becomes 29.5% when S8 switches
    `monitor.object_fwhm` to `core.slitloss.slit_fraction`, which has the
    same signature;
  - LDS749B's 0.6% is unchanged to 6e-5.
  - The `slitloss_gt1pct` flags do not change, but the `err` values of
    those rows will, so S8's "monitor rows do not change" check must allow
    for this.
- **AB definition:** `ab_mag` uses the design's energy weighting. The
  photon-counting form differs for Vega through top-hat MOSFIRE bands by
  -0.004 mag (J), -0.002 (J2), -0.006 (H) and -0.008 (K), below the 2MASS
  floor (`scripts/ab_weighting_check.py`). The top-hat J Vega offset is
  0.930, in line with XTcalc's 0.91. Kept as designed.
- **Vega spectrum:** not copied yet. S7's core only needs the function, and
  S8 computes the per-band offsets through the real filter curves and
  stores them in the filter `meta`. S8 should copy
  `vega_tspectool_vacuum.dat` (952 kB) or keep only those offsets.
- **Extended sources:** `extended_fraction` is the fraction of the disk's
  total flux (SB x pi D^2/4) inside the rectangle, so that S9 treats point
  and extended sources the same way. For D >> w, L it tends to
  SB x w x L / (SB x pi D^2/4), as 5.3.5 requires.
- **Output schema:** `slit_fraction`, `aperture_fraction`, `resolving_power`,
  `dark_e` and `read_noise_e` may be a scalar or an array, because a
  `seeing_wave_um` scaling makes the slit loss wavelength dependent. S9 may
  tighten this.

**Learned about the repository:**

- `pypeit14b` (numpy 2.5, scipy 1.18) had no `jsonschema`.
- The sky grid's `GRID` HDU is a full 3 x 4 rectangle (airmass 1.0/1.5/2.0
  by PWV 1.0/1.6/3.0/5.0) on a uniform 0.5 A vacuum grid, so a bilinear
  (X, log PWV) lookup is exact at the nodes.
- `keck_etcs/__init__.py` imports nothing, so `core` stays light.

### 2026-10-05 (Prompt #2 / S8: MOSFIRE instrument module, filter curves, detector table; monitor block moved)

**Data files** (each written by a script and registered in `index.yaml`):

- `scripts/mosfire/fetch_keck_filter_curves.py` →
  `keck_etcs/data/mosfire/filters/mosfire_{Y,J,J2,J3,H,K}.ecsv`, with
  columns `wave_A` (vacuum) and `transmission` (0-1).
  - Sources: the files linked from the Keck filters page. Y/J/H/K are
    `mosfire_<band>.txt` (the order-sorting filters). J2 and J3 are
    `J2_center_corr.txt` and `J3_center_corr.txt` (intermediate band).
  - The raw copies are kept, with their download stamp, in
    `$KECK_ETCS_DATA/external/keck_filters/`; `--offline` re-reads them.
  - `meta` holds: source URL and page, download date, raw sha256; waveref
    and how it was set; the number of negative samples clipped (J2 22, J3
    20, H 24, all scan noise); the peak; the half-power points (on a
    9-sample running median); centre and FWHM; the published values;
    `ab_minus_vega` with the Vega file's sha256; the AB definition;
    `calib_version`, `keck_etcs_version`, `created` and `script`.
  - **Air or vacuum:** the Keck page does not say. Laboratory scans are in
    air, so the curves are taken as air and converted with PypeIt's
    `airtovac` (+3.4 A at 1.25 um), and `waveref_source` says so.
  - **Imaging or spectroscopic curves?** These are the filter
    transmissions themselves; the page uses them for both. The J2/J3
    `center_corr` name is recorded in `notes` and is taken to mean the
    curve at the centre of the field.
  - Measured half-power bands against the published values; every centre
    and FWHM matches to <= 0.001 um:

    | band | half-power (um) | centre / FWHM | published | AB-Vega |
    |---|---|---|---|---|
    | Y | 0.9719-1.1243 | 1.0481/0.1524 | 1.048/0.152 | 0.655 |
    | J | 1.1535-1.3523 | 1.2529/0.1988 | 1.253/0.200 | **0.930** |
    | J2 | 1.1169-1.2463 | **1.1816/0.1293** | 1.181/0.129 | 0.833 |
    | J3 | 1.2269-1.3500 | 1.2885/0.1231 | 1.288/0.122 | 0.989 |
    | H | 1.4661-1.8076 | 1.6369/0.3415 | 1.637/0.341 | 1.365 |
    | K | 1.9215-2.4046 | 2.1630/0.4830 | 2.162/0.483 | 1.845 |

  - The AB-Vega offsets use the S7 `core.source.vega_offset` on PypeIt's
    `vega_tspectool_vacuum.dat` through the full curve. They are stored in
    each filter's `meta`, so `core` and `etc` never read the Vega file.
    That resolves the S7 open item; the spectrum itself is not copied.
- `scripts/mosfire/build_detector_table.py` →
  `keck_etcs/data/mosfire/detector.ecsv`.
  - Columns: `n_reads` (1 = CDS; 4-128 = MCDS), `read_noise_e` (21, 10.8,
    7.7, 5.8, 4.2, 3.5, 3.0) and `read_noise_lab_e` (Kulas+12, reference
    only).
  - `meta`: gain 2.15; dark 0.008; linearity 26k/37k/43k ADU and
    56k/80k/97k e-; plate scales 0.1798 (spatial) and 0.24 (dispersion);
    minimum integration 1.455 s; SAMPMODE codes; persistence; a source for
    each.
  - I re-checked the Keck detector page today, and every value matches.

**Code:**

- `keck_etcs/instruments/base.py`:
  - `Band` (filter file, dispersion, detector footprint, clean window),
    `Era` (name, start, end) and `Instrument`. `Instrument` loads each
    data file once, on first use, through a per-instance cache, and never
    imports PypeIt.
  - Accessors: `filter_curve`, `detector`, `sky_grid` (`wave_A` in A,
    `skybg`, `trans`, `airmass`, `pwv_mm`), `lsf_measurements`.
  - Derived values:
    - `band_window` (N2: half-power ∩ footprint);
    - `vega_offset`;
    - `read_noise(mode, n_reads)`, through `core.detector`;
    - `lsf_fwhm_pix(w)`: the measured median if a row matches within
      0.01", else D25;
    - `era_for_date`, with a warning inside a gap.
- `keck_etcs/instruments/mosfire.py`: a `MOSFIRE` instance, with a source
  comment on every value.
  - Area 72.3674 m^2 (N1); plate scale 0.1798.
  - **Bands J and J2:**
    - **Footprint:** 11109.7-13754.8 A at 1.2922 A/pix, from the
      2022-04-09 J2 long-slit `WaveCalib_A_1_DET01` (pixels 0 and 2047).
      J shares the grating setting, so it takes the same footprint; to be
      confirmed on a J night in part 5.
    - **Windows:** the half-power bands lie inside the footprint, so they
      are J 11535-13523 A and J2 11169-12463 A.
    - J2 also has its clean window, 11170-12600 A.
  - **Eras** (named by start month), with gap warnings:
    - `2012-04`: 2012-04-04 to 2016-09-15;
    - `2017-02`: 2017-02-13 to 2025-02-11;
    - `2025-04`: from 2025-04-29;
    - a date in a gap (the 2016-09-15 to 2017-02-13 offline period; the
      2025-02-11 to 2025-04-29 CSU outage, with the 1" long slit only)
      takes the era before it, with a warning.
  - LSF slope 0.277 and floor 2.2; Moffat beta 3.5.
  - The `MONITOR` block. `keck_etcs.instruments.get(name)` returns the
    instance.
- **The monitor block moved** (design 4.9.6), verbatim, into
  `instruments/mosfire.py`; `platescale` and `nonlinear_adu` now come from
  the module constants. `calib/monitor_configs.py` re-exports it under the
  old names.
  - **Check:** the monitor re-run on the 0.1.6 products of 2022-04-09 is
    identical to the in-pod `20220409_monitor.ecsv`: zero difference in
    every column (`verify_monitor.py --compare`: PASS).
- **`monitor.object_fwhm` now uses `core.slitloss.slit_fraction`.** The
  provisional `moffat_slit_fraction` is removed, and its test is replaced
  by one that checks the switch.
  - Only the `err` of the six `slitloss_gt1pct` rows changes:
    - J0841 0036/0037: 0.3077 → 0.2953/0.2996;
    - J0841 0038/0039: 0.3388 → 0.3480/0.3436;
    - LDS749B: 0.0064/0.0048 → 0.0064/0.0048, unchanged to 5e-5.
  - The old 0.034" grid gave identical values to frames with different
    FWHMs. The values and flags (`slitloss=provisional`, which marks the
    still-uncalibrated D26 model) are unchanged.
  - The committed `calib_monitor.ecsv` keeps the 0.1.6 in-pod values until
    the next image reruns the night.
- **`harvest_sens.py harvest DATE`** without `--filter` now takes the
  night's band curve from the instrument module (`default_filter`).
  - The night job calls `harvest NIGHT --standard` without `--filter`, so
    without this change rebuilding the image would not have removed
    `nofilter`.
  - Locally, on 2022-04-09 (scratch output only): `filter curve:
    mosfire_J2.ecsv`, `flag = ok`, and identical ZPs.
- `scripts/mosfire/select_monitor_lines.py`: the docstring now points at
  `instruments/mosfire.py`.
- `nautilus/Dockerfile`: the import guard adds
  `keck_etcs.instruments.mosfire`.
- **Tests:** `keck_etcs/tests/test_instruments.py` (12 tests). The suite
  now has 60, all passing.
  - The S8 verification items:
    - RN(16) = 5.8 and RN(1) = 21;
    - J Vega offset 0.930, inside 0.85-0.97;
    - J2 half-power 1.1816 ± 0.0647 um, inside 1.181 ± 0.065 (within
      0.01);
    - every filter and detector file has the 5.4 provenance keys.
  - Also:
    - every `index.yaml` entry has `calib_version`, `created`, `sha256`,
      `script` and `provenance`, and its sha256 matches the file on disk;
    - the N2 windows, the measured LSF taking precedence, the eras and
      gaps, and the monitor re-export;
    - the instruments load without importing PypeIt or boto3.

**For the user:**

- **Image 0.2.0 must be rebuilt after this step** (part 2 prompt 5) so that
  the in-pod harvest divides out the filter. With this change the night
  job does it automatically from 0.2.0 on.
- S7 and S8 are both uncommitted; they can go in one commit.

**Choices for review:**

1. Dispersion 1.2922 A/pix, measured on the long slit, rather than design
   section 3's 1.30 (from the stitched templates). S and B_ap scale with
   it, so it shifts S/N by 0.3%.
2. The air → vacuum assumption for the filter curves (a 3.4 A shift; it
   changes the J AB-Vega offset by < 0.001 mag).
3. Era names `2012-04` / `2017-02` / `2025-04`. Dates in a gap take the
   era before it.

**Learned:**

- The Keck filters page links nine curves (`mosfire_{Y,J,H,K,Ks}.txt` and
  `{J2,J3,H1,H2}_center_corr.txt`). They are in um with fractional
  transmission, and some contain negative scan noise.
- The J2 half-power blue edge (1.1169 um) is where PypeIt's J2 clean
  window starts (1.117).
- The night job's harvest call never passed `--filter`.

### 2026-10-05 (Prompt #3 / S9: compute(), CLI, regression fixtures; frozen against the PROVISIONAL XTcalc throughput)

**Throughput product used:** no S10 curve exists yet, so
`scripts/mosfire/build_provisional_throughput.py` builds
`keck_etcs/data/mosfire/throughput/mosfire_thru_provisional-xtcalc-2012.ecsv`.

- It uses the S10 column layout `wave, thru_median, thru_mad, n_std` on a
  1 A grid, 11000-14000 A, with `calib_version = provisional-xtcalc-2012`.
- `index.yaml` carries `provisional: true`, `pypeit_version: n/a`, and
  every output carries a "PROVISIONAL throughput" warning.
- Recipe: XTcalc `Jeff.sm.dat` x 0.89^2, divided by our Keck J filter
  curve to make it filter-free (design 5.3.4), smoothed with a 51-sample
  running median.
  - The ratio is used only over 11700-13400 A. `Jeff.sm` is smoothed and
    its cut-on does not match the Keck J curve, so the ratio collapses at
    the filter edges: it is still falling at 11605 A, where F_J first
    reaches 0.85, and my first build with an F_J >= 0.85 cut gave 0.157 at
    the J2 blue end. It is held constant outside that range.
  - Result: 0.201 at <= 11700 A, 0.246 at 12000, 0.287 at 12500, 0.333 at
    13000. Median 0.218 over the J2 window and 0.287 over J. For context,
    LDS749B gives 0.18 in J2 with the filter included.
- **The regression fixtures are frozen against this provisional
  product.** S10 must replace it and regenerate them, with a `CHANGES.md`
  line.

**Code:**

- `keck_etcs/etc.py`:
  - **`validate(inputs) -> (filled, warnings)`:** the schema check first
    (an `InputError` names every field), then defaults filled recursively
    from `etc_input.json`. Semantic warnings: CDS with n_reads != 1; unused
    `line` or user arrays; `snr_reference = line` without a line; an
    extended source without `length_arcsec`; `snr_reference` without
    `target_snr`. A user `wave_A`/`flux` length mismatch raises.
  - **`compute(inputs) -> dict`:** every field of `etc_output.json`, and
    the output validates against it.
    - Fine grid: the sky grid's 0.5 A vacuum samples over the window ± 10
      LSF FWHM.
    - N0 x T_atm x T_sys (the filter-free era curve x the band filter x
      `scale`) is convolved with the LSF and then sampled. The product is
      convolved, not each factor, which is correct for a line on a telluric
      feature and identical for a smooth source; noted in the docstring.
    - Sky: `sky_scale` x B x T_sys convolved, without T_atm (N6).
    - The source is normalized on the filter's own grid, so the whole
      filter is covered.
    - Line mode uses the new `core.source.gaussian_line_binned`
      (cell-integrated, so flux is conserved below the grid step), plus an
      optional flat-f_nu continuum.
    - Extended sources: SB x pi D^2/4 x `extended_fraction`; in line mode
      the line flux is per arcsec^2, with a warning.
    - `seeing_wave_um` gives per-pixel slit fractions, interpolated from 7
      nodes.
    - Target S/N: pixel and resel use `solve_exptime_median`; line uses the
      window sums. Solved times below 1.455 s or above 3600 s warn; an
      unreachable target warns and keeps `exptime_s`.
    - Saturation peak, plus the persistence warning when the flag is not
      `ok`.
    - A warning whenever the LSF width comes from the interim rule rather
      than a measured slit.
    - `meta`: `keck_etcs_version`; `calib_version` and `pypeit_version` from
      the throughput's `index.yaml` entry (no PypeIt import); `era`;
      `inputs`.
- `keck_etcs/instruments/base.py`: `throughput(era)` (the S10 file
  `mosfire_thru_{era}.ecsv` if present, else the provisional one) and
  `index()`. `mosfire.py` sets both paths.
- `keck_etcs/core/slitloss.py`: the extended-source sampling step is now
  `min(FWHM/4, max(0.01", FWHM/20, D/200))`, since the disk is smoothed by
  the PSF. A 2" disk dropped from 0.15 s to 0.02 s with the same fraction
  to 1e-4, and the S7 tests pass unchanged.
- `bin/keck_etc`: JSON file (or `-`) in; JSON to stdout or `-o`.
  `--summary` prints:
  - versions, calib and era;
  - window, LSF and R;
  - slit and aperture fractions;
  - exptime x frames;
  - band-median S/N per pixel and per resel;
  - the line S/N;
  - the per-frame peak ADU, e- and flag;
  - the warnings.

  Invalid input gives exit 2 and names the fields. `setup.py` already globs
  `bin/`.
- `examples/J_point.json`: the S9 case (J = 20 AB, 0.7"/0.7", 4 x 120 s,
  MCDS-16, ABBA, X 1.2, PWV 1.6).
- `examples/J2_point.json`: J2, 19 AB with alpha = -1, 1" slit, 0.9"
  seeing, 4 x 150 s, X 1.075, date 2022-04-09.
- `examples/J_line.json`: 5e-17 cgs at 12820 A, 150 km/s, continuum 23 AB,
  target line S/N 10 → 8 x 137 s, not saturated. The first draft at 1e-17
  needed 8 x 1700 s and saturated on the 12906 A OH line.
- Fixtures `keck_etcs/tests/data/reference_{J,J2,line}.json` (250, 163 and
  253 kB): the inputs plus the full output, floats rounded to 10
  significant digits. The helpers are in `keck_etcs/tests/regression.py`;
  `meta.keck_etcs_version` is excluded, so a version bump alone does not
  fail.
  - `test_regression.py` fails on any relative change above 1e-6 and checks
    that each fixture's inputs are its example.
  - `scripts/regen_regression_fixtures.py` only reports by default (exit 1
    on a difference). `--regen` needs `--note`, which is appended to
    `CHANGES.md` with the date, version and throughput `calib_version`.
- `CHANGES.md` (design 5.5) is new: a calibration-release section (none
  yet; the provisional throughput is called out) and the fixture log, whose
  first line is the S9 freeze.
- **Tests:** `test_etc.py` adds 15:
  - validation, schema-valid output, the window, LSF and aperture;
  - the noise budget (ABBA variance identity);
  - stare against ABBA; throughput and sky scaling;
  - Vega = AB + offset;
  - a hand photon count for J = 20 AB (2%);
  - target-S/N round trips for pixel and resel (1e-6);
  - line mode: the window width; line-flux conservation (3%); the line
    target round trip; an out-of-band warning;
  - the extended-source SB x w x L limit (2e-3);
  - clipping and era-gap warnings; seeing scaling;
  - user-spectrum normalization;
  - `etc` running with sockets blocked and without PypeIt, boto3 or
    requests.

  The suite has **82 passed**.

**Verification:**

- `bin/keck_etc examples/J_point.json --summary`: band-median S/N per
  pixel 4.334 (per resel 6.890); per-frame peak 3986 ADU at 12905.7 A, an
  OH line; flag `ok`.
- **XTcalc by hand** (`scripts/mosfire/xtcalc_hand_snr.py`): a
  re-implementation of XTcalc v2.3's magnitude mode from `XTcalc.pro` on
  its own files (`Jeff.sm` x 0.89^2, the May 2012 MOSFIRE sky
  `Jsky_cal_pA`, `mktrans_zm`; 75 m^2; RN 15/sqrt(16) = 3.75 e-; dark
  0.005; 1.31 A/pix; R = 3310; no slit loss; 2-point dither x2).
  - Same case: XTcalc gives **7.39** (theta 0.7", airmass 1.0; 7.33 at
    1.5; 6.15 with theta 1.05"). Ours is 4.33, a **ratio of 0.59, within
    the factor of 2**.
  - The gap comes from our slit and aperture loss (0.561; XTcalc assumes
    none), the measured read noise (5.8 against 3.75 e-) and 6 spatial
    pixels against 3.9. It is partly offset by the Gemini interline
    continuum, which is **2.7x lower** than XTcalc's 2012 MOSFIRE-measured
    sky (median 0.81 against 2.2 ph/s/arcsec^2/nm/m^2 over 11700-13300 A
    and in the 12440-12480 A low-OH window; the OH-line means agree, 8.2
    against 8.8).
  - That continuum difference decides faint-source S/N. It is the D14
    question for S11 (the default `sky_scale`, and whether to scale the
    lines and the continuum separately).
  - My first pass gave XTcalc 17.4 (ratio 0.25) because of an extra 1e4
    in my conversion of XTcalc's sky units: its `10^(loghc+4)` is already
    h·c in erg·um. Fixed before the numbers above.
  - S12 does the full grid of magnitudes and slits.
- `keck_etcs.core` and `keck_etcs.etc` import and run without PypeIt,
  boto3 or network access (tested).

**Choices for review:**

1. The provisional throughput's constant extension below 11700 A (J2's
   blue 530 A) and above 13400 A.
2. The source is convolved as a product with T_atm and T_sys rather than
   factor by factor.
3. Extended sources in line mode take the line flux per arcsec^2.
4. Fixtures are stored rounded to 10 significant digits (about 670 kB in
   git).

**Learned:**

- XTcalc's magnitude mode:
  - takes the median S/N over pixels where the convolved filter exceeds
    0.1 (1.145-1.361 um), wider than our half-power window;
  - its `theta` is the object's extent along the slit and sets both the
    sky area and the read-noise pixels;
  - `Jsky_cal_pA` is MOSFIRE-measured and flux-calibrated per spatial row
    of a 0.7" slit;
  - it has no slit loss and uses 75 m^2.
- `conda run` does not forward stdin, so the CLI's `-` input was checked
  only through a file.
