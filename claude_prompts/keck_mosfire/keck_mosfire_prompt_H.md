# Keck MOSFIRE implementation, part H: band-neutral refactor and the H band (Phase 7, S23-S24)

## Goals

Extend the MOSFIRE ETC from J to the other bands, starting with H. This
doc covers two plan steps (`docs/keck_mosfire_implementation.md` v0.5):

1. **S23, band-neutral refactor.** Everything the J work hard-codes
   (zero-point nodes, windows, edge trims, gates, file names, the S3
   layout, the census filter) becomes per-band data, with the J numbers
   unchanged, verified by a `compute()` regression to 1e-6 and released as
   a **J-only calibration tag** (design D49, Q68). The KOA census is re-run
   for Y, H and K, the dev-suite reference nights of every band are
   reduced locally, and the H and K footprints are measured and frozen.
2. **S24, H band.** The H sensfunc parameters chosen by a measured test
   (D53), the A0V model scaled to 2MASS H (D51), the pilot and batches on
   Nautilus, the H throughput product, the H sky-excess curve (D61), the
   saturation-fraction output (D62), examples, fixtures, the XTcalc
   comparison and the H validation night.

H goes first because it has the largest wide-slit sample and no new
physics (D57). The K doc (`keck_mosfire_prompt_K.md`) and the Y doc
(`keck_mosfire_prompt_Y.md`) follow in that order; the Y doc also holds
the final release step S27.

## Context

- **Design and decisions:** `docs/keck_mosfire_design.md` v0.7, section 9
  (per-band facts in 9.2; D48-D62 in section 2; the questions and answers
  under "Q&A / Other bands" in `keck_mosfire_prompts.md`, Q49-Q68). Read
  section 9 before prompt 1. The numbers in 9.2 come from
  `scripts/mosfire/survey_other_bands.py` and
  `scripts/mosfire/inspect_raw_headers.py`.
- **What J built, and what generalises** (log of "Other bands" prompt #1):
  - `keck_etcs/instruments/base.py`: `Band` (name, filter file, dispersion,
    footprint), `Instrument` (`throughput_pattern` with `{tag}`,
    `SPLICE_WINDOW = (11900, 12450)`, `lsf_fwhm_pix(slit)` without a band,
    `band_window`, `vega_offset`);
  - `keck_etcs/instruments/mosfire.py`: `BANDS` J and J2 only, `MONITOR`
    keyed by band (`fwhm_nodes`, `flat_nodes`, `band_windows`,
    `monitor_lines`, `lsf_ref_wave`), `LSF_SLOPE`/`LSF_FLOOR_PIX`
    (quadrature rule, D25), `NONLINEAR_ADU = 26000`, `site`;
  - `keck_etcs/calib/harvest.py`: `ZP_WAVES` (`zp_1200/1250/1300`),
    `MEDIAN_WINDOWS` (`thru_median_1117_1260`, `_1250`), `estimate_pwv`
    window, `WIDE_SLIT_ARCSEC = 3.0`, `ROW_COLUMNS`;
  - `keck_etcs/calib/combine.py` and `trend.py`: `COMMON_WINDOW =
    (11900, 12450)`, `EDGE_TRIM_FRAC = {'J': 0.9}`, `A0V_MIN_WAVE`;
  - `keck_etcs/calib/standards.py`: the Vega model scaled to 2MASS J only;
  - `nautilus/gates.py`: `THRU_RANGE` (0.15-0.45), `COUNTS_WINDOW`
    (11700-12400) hard-coded;
  - `scripts/koa/search_mosfire_standards.py`: `BASE_WHERE` is J-only;
    `--refresh` is its only option; the SAMPMODE census lives there too;
  - `scripts/koa/make_night_manifest.py`, `nautilus/manifests/*.csv`
    (columns `night, instrument, s3_prefix, standard, slit, spec2d, notes,
    std_class, jmag_2mass, std_ra, std_dec, filter`);
  - `scripts/koa/download_mosfire_night.py` (`--manifest`, `--index`,
    `--lamp-arcs`, `--to-s3`), `nautilus/koa_download_job.yaml`,
    `nautilus/night_job.yaml`, `nautilus/validate_job.yaml`;
  - `scripts/mosfire/reduce_standard.py` (already `--filter`, `--sens`,
    `--std-class`, `--jmag`; products to `mosfire/<night>/{redux,sens,harvest}`);
  - `scripts/mosfire/harvest_sens.py` (`harvest`, `monitor`, `--merge`),
    `combine_throughput.py`, `plot_throughput_trend.py`, `verify_release.py`,
    `select_monitor_lines.py --band`, `measure_lsf.py --record`,
    `sensfunc_perturbation_test.py COADD --levels --n --sens`,
    `compare_xtcalc.py`, `scripts/regen_regression_fixtures.py`;
  - data: `keck_etcs/data/mosfire/throughput/mosfire_thru_<era>.ecsv`
    (three J files, no band in the name), `standards.ecsv`,
    `filters/mosfire_{Y,J,J2,J3,H,K}.ecsv` (all six already shipped),
    `lsf_measurements.ecsv` (has a `filter` column),
    `monitor/monitor_lines_J2.ecsv`, `monitor/calib_monitor.ecsv`,
    `pypeit_par/keck_mosfire_J.sens`, `index.yaml` (calib_version
    `mosfire-J-2026.10`), `keck_etcs/schema/etc_input.json` (`band` enum
    `J`, `J2`), `examples/{J_point,J2_point,J_line}.json`,
    `keck_etcs/tests/data/` fixtures.
- **Dev-suite reference nights** (design 9.4, D56; raw frames under
  `$PYPEIT_DEV/RAW_DATA/keck_mosfire/`, PypeIt files under
  `pypeit_files/keck_mosfire_*.pypeit`; `$PYPEIT_DEV` defaults to
  `~/Projects/PypeIt/PypeIt-development-suite`): `Y_long` (reduced;
  footprint 9255-11471 A), `longslit_3x0.7_H` and `longslit_3x0.7_K`
  (HIP 17971, 2012-11-28, 0.7"), `K_long` (HIP 17971 and Per-emb 25,
  2019-10-13, 1.5"), `long2pos1_H` (HIP 61138, 2018-07-18, Ne/Ar arcs).
  Only `Y_long` has a `REDUX_OUT` on this workstation.
- **H facts (9.2):** order 4, 1.627 A/pix, filter 14661-18076 A (2099
  pix, wider than the detector: the centred long slit sees about
  14680-18040 A, to be measured), AB-Vega 1.365, 110 OH lines, XTcalc 2012
  median throughput 0.338 (gate 0.17-0.54), between-line sky 2.4-3.5x the
  Gemini model, the brightest OH line (1.583 um) reaches 26k ADU in
  1.5-2 min through a 0.7" slit. Nodes 1.55/1.65/1.75 um, common window
  1.49-1.78 um, PWV weak. KOA: 92 `long2pos_specphot` nights with
  star-like names, 415 on any long-slit mask.
- **Rules (CLAUDE.md and the plan):** the user runs git (every tag, every
  push); Python via `conda run -n pypeit14b`; calculations are scripts on
  disk; nothing under `KECK_ETCS_DATA` is committed; provenance `meta`
  on every data file (design 5.4, D36); no secret value in any file or
  log; outward-facing infrastructure (image push, Jobs larger than the
  pilot, anything touching the bucket's access) is confirmed with the
  user first; PypeIt defects are fixed in PypeIt on a branch, not worked
  around here; each prompt ends with a Log entry below.
- **Nautilus:** `nautilus/README.md` is the operator guide (image build and
  push, the pin, bucket layout, `kubectl` idioms, batches, sweeps, sync,
  backup, releases). The image is rebuilt and re-tagged whenever
  `keck_etcs.calib`, a `.sens` file or the pin changes; every batch logs
  tag, digest and pin.

## Prompts

1. **S23a: instrument module, schema and the calibration code made
   band-neutral.** Generalise, without changing any J number:
   - `keck_etcs/instruments/base.py`: `Band` gains `group`, `order`,
     `zp_nodes_A`, `common_window_A`, `pwv_window_A` and an `lsf` entry
     (slope, floor, provenance; `None` means "use the instrument rule with
     a warning"); `throughput_pattern` takes `{group}` and `{tag}`;
     `SPLICE_WINDOW` becomes the group's `common_window_A`;
     `throughput_for_window` completes a window from another era of the
     same group only; `lsf_fwhm_pix(slit, band)` prefers a measured row of
     that band in `lsf_measurements.ecsv`.
   - `keck_etcs/instruments/mosfire.py`: `BANDS` for Y, H and K from design
     9.2 (footprints for H and K marked provisional until prompt 4 measures
     them; Y's is measured), `MONITOR` entries per band (FWHM nodes = the
     zero-point nodes; flat nodes every 250 A; `band_windows`; empty
     monitor-line tuples until frozen), `LSF` per band (J's rule with
     `provisional = True` for Y, H, K; D59).
   - `keck_etcs/calib/harvest.py`: `zp_lo`, `zp_mid`, `zp_hi`,
     `thru_median_common`, plus `zp_nodes_A` and `common_window_A` in the
     row, all read from the band; `estimate_pwv` uses the band's PWV window
     and sets `flag = pwv_weak` where 9.3 says so. `combine.py` and
     `trend.py`: `COMMON_WINDOW`, `EDGE_TRIM_FRAC` (0.9 for every group)
     and `A0V_MIN_WAVE` per group from the module. `standards.py`:
     `a0v_model(band, mag)` with PypeIt's `TMASS-J/H/K` curves (D51), the
     J-scaled model kept as `a0v_scaled_to`/`a0v_jhk_offset_mag` columns.
   - `keck_etcs/schema/etc_input.json`: `band` enum adds `Y`, `H`, `K`
     (J3 stays out, D48); `keck_etcs/etc.py` and the core must run for
     every band with the provisional data and warn once per provisional
     item. Add `examples/{Y,H,K}_point.json` (not yet fixtures).
   - Tests: extend `test_instruments.py`, `test_harvest.py`,
     `test_combine.py`, `test_trend.py`, `test_etc.py` to a non-J band;
     `test_regression.py` must still pass on the J fixtures unchanged.
   Verify: `pytest keck_etcs/tests` passes; `scripts/regen_regression_fixtures.py`
   (report mode) shows no difference on J; `check_docs.py` passes. Do not
   rename the J throughput files yet (prompt 2). Log your work.

2. **S23b: the J rename, the regenerated J table and the J-only tag.**
   Rename `keck_etcs/data/mosfire/throughput/mosfire_thru_<era>.ecsv` to
   `mosfire_thru_J_<era>.ecsv` (git `mv` is the user's; prepare the new
   files and say which old ones to remove), regenerate `standards.ecsv`
   from the existing harvest files (`harvest_sens.py --merge` on the
   synced nights, or a one-off script that maps the old columns to the new
   ones if the harvest files are not all local; say which) and
   `combine_throughput.py` with the new names; `index.yaml` entries with
   `bands` per file; `verify_release.py` extended to groups and the new
   names; `nautilus/README.md` section 10 and `CHANGES.md` updated for the
   tag format `mosfire-YYYY.MM` (D49, D28). Then the regression: run
   `compute()` on every example and fixture with the old release and the
   new files (`scripts/compare_release_outputs.py`, new: writes a table
   of max relative differences per output field) and require 1e-6. Write
   the `CHANGES.md` release section for `mosfire-2026.MM` (J-only: same
   standards, same numbers, new names and columns) and ask the user to
   tag. Verify: the comparison table is all below 1e-6; `verify_release.py`
   passes; `pytest` passes; `check_docs.py` passes. Log your work with the
   comparison table.

3. **S23c: the KOA census for Y, H and K and the validation targets.**
   Add `--filters` to `scripts/koa/search_mosfire_standards.py` (default
   `J` so the J census is reproducible), generalise `BASE_WHERE`, record
   2MASS H and Ks beside J, and write the per-band candidate rows into
   `keck_etcs/data/mosfire/koa_standards_candidates.ecsv` with a `filter`
   column (or one file per band if the schema of the existing table makes
   that cleaner; say which). Apply the J rules unchanged (wide slit >= 3",
   a wavelength calibrator on the night, flats in the band, SIMBAD and
   2MASS matches). Report per band: candidate nights, usable wide-slit
   nights, WD and A0V counts, era coverage, and whether any H or K night
   has both a white dwarf and an A0V star (D52's check). Re-run
   `scripts/koa/find_validation_targets.py` for Y, H and K and report
   whether the Hennawi/Yang/Wang nights carry same-night wide-slit
   standards (9.7). Note the dev-suite fallbacks (J2132-1434 in Y,
   Per-emb 25 in K). Verify: the J rows of the table are unchanged; the
   TAP counts of design 9.2 are reproduced or the difference explained.
   Log your work with the per-band table.

4. **S23d: reference reductions, footprints, manifests with `band`, gates
   and the dry runs.** Locally in `pypeit14b` at the pin
   (`scripts/check_pypeit_pin.py` first), reduce `longslit_3x0.7_H`,
   `longslit_3x0.7_K`, `K_long` and `long2pos1_H` with
   `reduce_standard.py --filter <band>` (or the dev-suite PypeIt files
   where the driver does not yet cover the mask; say which) and from their
   `WaveCalib`: the centred long-slit footprint of H and K (freeze into
   `BANDS`, provisional flag off, with the file and its sha256 as
   provenance), `measure_lsf.py --record` per band and slit (0.7", 1.5"),
   the H Brackett-mask check on HIP 17971 (`hydrogen_mask_wid` 10 versus
   30 A: zero-point smoothness across Br 10-18; D52), and the K
   between-line continuum of 2012 and 2019 against the Gemini model over
   2.15-2.40 um with `TUBETEMP` from the headers (the first `eps_eff`
   values, D60; a script `scripts/mosfire/fit_thermal_continuum.py` that
   the K doc reuses). Then the Nautilus side (D55): `band` column in the
   manifests and `make_night_manifest.py` (one row per night and band),
   `download_mosfire_night.py` fetching each listed band's flats and arcs
   into the shared `mosfire/<night>/raw/`, products of Y/H/K under
   `mosfire/<night>/<band>/`, `gates.py` reading its windows and the
   0.5-1.6x XTcalc range from the instrument module, `reduce_standard.py`
   choosing the band's `.sens` file (a provisional H and K `.sens` with
   polyorder 5, `tell_npca` 3, `hydrogen_mask_wid` 30 for now). Ask the
   user to rebuild and push the image (tag recorded), then run
   `validate_job.yaml` on the 2012-11-28 H and K nights as the dry runs
   against the local reference (the 1 percent gate of 4.8.7). Verify:
   footprints and LSF rows in the data files with provenance; the dry-run
   gates pass for H and K; `pytest` passes; nothing J-related changed.
   Log your work with the measured footprints, LSFs, the Brackett result
   and the first `eps_eff` values.

5. **S24a: the H sensfunc parameters, the A0V model in H, the pilot.**
   Extend `scripts/mosfire/sensfunc_perturbation_test.py` with
   `--polyorders 4 5 6 8` (D53, Q64): on `longslit_3x0.7_H` and on the
   first wide-slit H standard from the census (download it with
   `download_mosfire_night.py`), fit each order, report the perturbation
   stability and the rms difference to the next order up over 1.49-1.78 um
   and within 100 A of the edges, and take the lowest order passing both
   thresholds (1 percent; 2 percent at the edges); likewise `tell_npca`.
   Write `keck_etcs/data/pypeit_par/keck_mosfire_H.sens` with the result
   table in its header. Make `reduce_standard.py --jmag` general
   (`--mag` plus the band's 2MASS column from the manifest; `a0v_model(band,
   mag)`). Write `nautilus/manifests/nights_pilot_H.csv` (3-5 wide-slit
   nights across eras, WD and A0V), ask the user to rebuild the image, and
   with the go-ahead run the pilot as one Indexed Job. Sync, harvest,
   merge; freeze the H monitor lines (`select_monitor_lines.py --band H` on
   the reference plus pilot nights; D45) and re-run the monitor step for
   the pilot. Verify: as S15a (one status per night; `run_manifest.json`
   image digest and pin; an A0V zero point within 20 percent of a WD night
   in the same era or explained; wall-clock and memory recorded; the
   frozen list meets the 4.9.4 rules). Log your work with the polyorder
   table, the status table and the image tag/digest/pin.

6. **S24b: H batches, product, excess curve, saturation fraction,
   validation.** Batches as S15b/S15c (Indexed Jobs, sweeps,
   `backup_products.py`, sync, `harvest_sens.py --merge`, monitor merge;
   launches confirmed; one log entry per batch). Then:
   `combine_throughput.py` writes `mosfire_thru_H_<era>.ecsv`; the trend
   table and plot (`plot_throughput_trend.py`, `trend.py`, 3-MAD flags);
   the H sky-excess curve `keck_etcs/data/sky/mosfire_sky_excess_H.ecsv`
   (D61: all non-twilight frames, no object in the window, PypeIt's sky
   model per frame over the night's `T_sys`, 10th percentile per 100 A,
   median over nights, in Gemini units; a script
   `scripts/mosfire/measure_sky_excess.py --band H` the K and Y docs
   reuse) and its use in `keck_etcs/core/sky.py` inside the `sky_scale`
   bracket (5.3.8); `saturation.frac_pix_nonlinear_1pct` in the output
   schema, `etc.py` and the WMKO note (D62; Q67 listed it under K, it is
   built here because H is where it matters); `examples/H_point.json`
   made a fixture (`regen_regression_fixtures.py --regen --note`);
   `compare_xtcalc.py` for H; the H validation night (6.1 method, 20
   percent; `validate_j0841.py` generalised to a band and target). Verify:
   >= 10 wide-slit standards over >= 2 eras; era medians within 0.17-0.54;
   J fixtures unchanged; validation PASS or the failure analysed;
   `check_docs.py` passes. Log your work, batch by batch, then the
   product, the curve, the validation and the 9.8 checklist lines for H.

## Q&A

Please answer with ">A." lines before prompt 1 is run (a default is
proposed for each):

- **H-1. Where the per-band candidate rows live.** (a) one table
  `koa_standards_candidates.ecsv` with a `filter` column (recommended:
  one census, one provenance block); (b) one file per band.
- **H-2. Pilot size and parallelism for H.** (a) 4 nights, `parallelism`
  4, sized from the J pilot's memory (recommended); (b) other.
- **H-3. The first wide-slit H standard for the polyorder test.** (a)
  the brightest A0V `long2pos_specphot` night in the 2017-2025 era that
  the census returns (recommended: brightest means the cleanest test);
  (b) a WD night if one exists, so the test has no Brackett issue.
- **H-4. Saturation fraction here or in K.** Q67 listed the output under
  S25 (K); this doc builds it in S24b because H is the band that needs it.
  (a) agree (recommended); (b) keep it for K.

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
