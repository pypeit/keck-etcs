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
   column (H-1: one table per instrument, all bands in it; other Keck
   instruments will later get their own table under
   `keck_etcs/data/<instrument>/` from their own census script, so keep
   the column names and the `meta` block instrument-neutral and put
   nothing MOSFIRE-specific into the table's schema that a `filter` or
   `instrument` column cannot carry). Apply the J rules unchanged (wide slit >= 3",
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
   brightest A0V `long2pos_specphot` night of the 2017-2025 era that the
   census returns (H-3; download it with `download_mosfire_night.py`),
   fit each order, report the perturbation
   stability and the rms difference to the next order up over 1.49-1.78 um
   and within 100 A of the edges, and take the lowest order passing both
   thresholds (1 percent; 2 percent at the edges); likewise `tell_npca`.
   Write `keck_etcs/data/pypeit_par/keck_mosfire_H.sens` with the result
   table in its header. Make `reduce_standard.py --jmag` general
   (`--mag` plus the band's 2MASS column from the manifest; `a0v_model(band,
   mag)`). Write `nautilus/manifests/nights_pilot_H.csv` (4 wide-slit
   nights across eras, WD and A0V; H-2), ask the user to rebuild the
   image, and with the go-ahead run the pilot as one Indexed Job with
   `parallelism` 4, sized from the J pilot's memory. Sync, harvest,
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
   schema, `etc.py` and the WMKO note (D62; built here, not in K, per
   H-4); `examples/H_point.json`
   made a fixture (`regen_regression_fixtures.py --regen --note`);
   `compare_xtcalc.py` for H; the H validation night (6.1 method, 20
   percent; `validate_j0841.py` generalised to a band and target). Verify:
   >= 10 wide-slit standards over >= 2 eras; era medians within 0.17-0.54;
   J fixtures unchanged; validation PASS or the failure analysed;
   `check_docs.py` passes. Log your work, batch by batch, then the
   product, the curve, the validation and the 9.8 checklist lines for H.

## Q&A

Please answer with ">A." lines before prompt 1 is run (a default is
proposed for each). *Answered 2026-10-26; folded into the prompts above
(H-1 in prompt 3, H-2 and H-3 in prompt 5, H-4 in prompt 6) and into
design 9.3 and 9.10.*

- **H-1. Where the per-band candidate rows live.** (a) one table
  `koa_standards_candidates.ecsv` with a `filter` column (recommended:
  one census, one provenance block); (b) one file per band.
>A. I agree with (a).  Note that we will eventually have different Keck instruments included in the analysis.  
- **H-2. Pilot size and parallelism for H.** (a) 4 nights, `parallelism`
  4, sized from the J pilot's memory (recommended); (b) other.
>A. (a)
- **H-3. The first wide-slit H standard for the polyorder test.** (a)
  the brightest A0V `long2pos_specphot` night in the 2017-2025 era that
  the census returns (recommended: brightest means the cleanest test);
  (b) a WD night if one exists, so the test has no Brackett issue.
>A. (a)
- **H-4. Saturation fraction here or in K.** Q67 listed the output under
  S25 (K); this doc builds it in S24b because H is the band that needs it.
  (a) agree (recommended); (b) keep it for K.
>A. (a)

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-10-26 (Q&A H-1..H-4 answered; prompts and design updated)

The user answered all four questions with (a), with a note on H-1 that
other Keck instruments will eventually join the analysis. Folded in,
without editing the answers:
- Prompt 3 (S23c): one candidate table per instrument with a `filter`
  column, under `keck_etcs/data/<instrument>/`, column names and `meta`
  instrument-neutral so the later instruments follow the same layout.
- Prompt 5 (S24a): the pilot is 4 nights at `parallelism` 4 (H-2); the
  polyorder test's KOA night is the brightest A0V `long2pos_specphot`
  night of the 2017-2025 era (H-3).
- Prompt 6 (S24b): the saturation fraction is built here (H-4), the
  hedge removed.
- Design doc (`docs/keck_mosfire_design.md`, still v0.7): 9.3 P3 records
  the single per-instrument table and the multi-instrument note; 9.10 now
  places the saturation fraction under S24, matching the plan (S24 already
  said so). No other document changed; the plan needed nothing.

What I learned: the data layout is already per instrument
(`keck_etcs/data/mosfire/`, `keck_etcs/data/sky/` shared), so the H-1
note is met by the existing directory convention; what the census and
harvest code must avoid is hard-coding `mosfire` in column names or
`meta` keys that another instrument's table would reuse.

### 2026-10-26 (Prompt #1 / S23a: instrument module, schema and calibration code made band-neutral; Y, H, K run on provisional data; J unchanged)

The prompt asked for Opus 5.5; this session ran on Claude Fable 5.1. No git
commands were run other than `git status`, `git diff` and `git log`.
Everything is uncommitted: 26 files modified, 7 new (three examples, three
provisional curves, one script).

**Instrument module** (`keck_etcs/instruments/base.py`, `mosfire.py`):
- `Band` gains `group`, `order`, `zp_nodes_A`, `common_window_A`,
  `pwv_window_A` (a tuple of windows), `pwv_weak`, `edge_trim_frac`,
  `a0v_min_wave_A`, `lsf` (dict: slope, floor, form, provisional,
  provenance) and `footprint_provisional`; the old positional fields are
  unchanged, so every existing `Band(...)` call still works.
- `Instrument` gains `group_of`, `group_bands`, `common_window(group)`,
  `throughput_provisional_pattern`, `legacy_throughput_group`,
  `lsf_rule(band)`; `throughput_file(era, group)`, `throughput(era,
  group)` and `throughput_for_window(..., group)` are per group, the splice
  window is the group's common window (`SPLICE_WINDOW` stays as the
  default), the era completion only ever reads the same group, and the
  cache key is `('throughput', group, era)`. `lsf_fwhm_pix(slit, band)`
  restricts measured rows to the band's group (the 2022-04-09 J2 row
  serves J and J2, nothing else) and appends `(provisional)` to the rule
  text when the band's rule was fitted on another band.
- **A trap found and closed:** the J files are still named
  `mosfire_thru_<tag>.ecsv` (the rename is prompt 2), so a pattern without
  `{group}` would have let Y, H and K silently read the J curve, and the
  first test run showed exactly that. `throughput_file` now returns None
  for any group other than `legacy_throughput_group` (`'J'` in the MOSFIRE
  module) while the pattern has no `{group}` placeholder; prompt 2 drops
  the attribute with the rename.
- MOSFIRE `BANDS`: Y (footprint 9255-11471 A measured on the dev suite's
  `Y_long`, 1.087 A/pix, order 6, nodes 10000/10500/11000, common window
  9800-11100, `pwv_weak`), H (nominal 14680-18040 A, `footprint_provisional`,
  1.627 A/pix, order 4, nodes 15500/16500/17500, common 14900-17800, PWV
  at the band edges only, `pwv_weak`) and K (nominal 19540-23970 A,
  provisional, 2.169 A/pix, order 3, nodes 20500/21500/23000, common
  19800-23700, PWV windows 19500-20000 and 23800-24000). J and J2 carry
  group `J`, order 5, the as-built common window 11900-12450, PWV window
  11170-12600, `edge_trim_frac` 0.9 (J) and None (J2), `a0v_min_wave_A`
  11900, and the measured LSF rule; Y, H, K carry the same rule flagged
  provisional (D59). `MONITOR` has `fwhm_nodes`, `flat_nodes` (Y 6, H 14,
  K 18 nodes), `band_windows`, empty `monitor_lines` and a new
  `lsf_ref_waves` dict per band (`monitor.line_widths` prefers it over the
  scalar `lsf_ref_wave`).
- **One deliberate departure from the design wording:** design 9.3 says
  "`EDGE_TRIM_FRAC` 0.9 of the filter peak for every band", but J2 rows
  are not trimmed in the shipped products (the 2025-on curve spans the full
  J2 half-power band 11171-12462 A), and trimming them would change the J
  numbers this prompt must preserve. J2 therefore keeps `edge_trim_frac =
  None` "as built"; the new bands get 0.9. Worth a line in the design at
  the next revision.

**Provisional data for Y, H and K.** `compute()` must run for every band,
and D1 forbids using XTcalc curves as calibration. As the J ETC did before
S10 (`provisional-xtcalc-2012`), each new group gets a placeholder
`mosfire_thru_<group>_provisional.ecsv` from the new
`scripts/mosfire/build_provisional_throughput.py`: XTcalc's 2012 efficiency
(`MosfireSpecEff/<band>eff.sm.dat`) times KMRef^2 (0.85, 0.94, 0.95) with
the shipped filter divided out, over the filter half-power band, with full
provenance (source sha256, filter sha256) and `calib_version =
provisional-xtcalc-2012`, registered in `index.yaml`. Filter-free medians:
Y 0.257, H 0.348, K 0.343 (end-to-end 0.237, 0.338, 0.317). XTcalc's H
efficiency ends at 17991 A, 49 A short of the nominal H window, so the ETC
holds the edge value there with its usual warning. `Instrument.throughput`
uses the placeholder only when no era of the group has a curve, with a
`PROVISIONAL` warning; `throughput_for_window` never splices it;
`meta.calib_version` reports `provisional-xtcalc-2012`, `meta.era` the
date's era. `scripts/check_docs.py` now excludes `provisional-*` entries
from its "index.yaml versions == latest release" check (it listed them and
failed).

**ETC** (`etc.py`, `schema/etc_input.json`): `band` enum `Y, J, J2, H, K`
(J3 rejected, D48; `test_core_schema` now uses J3 as its rejected value);
`compute()` takes the group from the band, passes the band to the LSF, and
warns once per provisional item, each warning starting with `PROVISIONAL`:
footprint (H, K), LSF rule (Y, H, K), throughput (Y, H, K). J and J2 carry
no `PROVISIONAL` warning (asserted by the existing test). Per band at the
defaults (J = 20 AB, 0.7", 4 x 120 s): Y 9718-11242 A, S/N 3.9; J 4.47
(unchanged); H 14680-18040 A, 2066 px, S/N 5.0 and the 1 percent
nonlinearity flag at 15833.5 A after 120 s (the OH saturation of design
9.2); K 19540-23969 A, S/N 3.4. New `examples/{Y,H,K}_point.json` (the J
example with the band changed; not fixtures).

**Calibration code:**
- `harvest.py`: row columns `zp_lo`, `zp_mid`, `zp_hi`, `thru_median_common`,
  `zp_nodes_A` (`'12000/12500/13000'`), `common_window_A` (`'11900-12450'`)
  replace `zp_1200/1250/1300` and `thru_median_1117_1260/1250`; the nodes,
  window and PWV windows come from `band_of(manifest)` (instrument +
  filter); `thru_median_common` is the median of the filter-free `thru`
  (masked for `nofilter` rows), the same quantity as `trend.curve_common_median`;
  `estimate_pwv` takes one window or several and reports them; `pwv_weak`
  bands get `flag = pwv_weak`. J2 rows now use the J2 nodes (design 9.3),
  which is why the committed J table is regenerated in prompt 2 rather than
  renamed in place. Smoke test on the local 2022-04-09 LDS749B sensfunc:
  the row carries `zp_lo/mid/hi` 19.23/19.63/18.60 at 11500/12000/12500 A
  and `common_window_A` 11900-12450.
- `combine.py`: `rules_for(filter, bands)` and `combine_era(..., bands=None,
  group=None)`; without `bands` the J constants apply (the unit tests), with
  `MOSFIRE.bands` the J2 rules are identical (asserted). `trend.py`:
  `common_window(filter, bands)`. `combine_throughput.py` passes the bands
  and `group='J'`.
- `standards.py`: `TMASS` (J, H, Ks zero points and Vega magnitudes from
  Cohen et al. 2003), `tmass_band(band)` (Y/J/J2/J3 -> J, H -> H, K -> K),
  `tmass_response`, `synthetic_tmass`, `vega_tmass`, `v_equivalent(mag,
  band)`, **`a0v_model(band, mag)`** (the D51 signature; the old one-argument
  call is gone and the tests updated), `jhk_offset_mag`, and
  `sens_par_lines(mag, band, j_mag)` / `write_sens_par(text, mag, band,
  j_mag)` whose record carries `band_2mass`, `a0v_scaled_to`, `mag_2mass`,
  `j_2mass` and `a0v_jhk_offset_mag`. `build_sensfunc.py` still calls
  `write_sens_par(text, jmag)` and so still scales in J; prompt 5 makes it
  band-aware. PypeIt's Vega spectrum gives synthetic 2MASS H and Ks within
  0.06 mag of Cohen's values (asserted).
- `monitor.py`: `lsf_ref_waves` per band. `harvest_sens.py --merge` masks
  a column a row file lacks (pre-S23a row files); `verify_harvest.py`
  reads `zp_nodes_A` from the row and accepts the pre-S23a table (legacy
  columns) until prompt 2 regenerates it.

**Docs:** `docs/wmko_api_note.md` band row; `docs/developer/calculations.md`
harvest columns; `CHANGES.md` "Code (unreleased)" entry for S23a.

**Verification:** `pytest keck_etcs/tests`: 121 passed, 3 deselected (new
tests: band groups and windows, per-band LSF, provisional throughput,
per-band combine rules, trend common window, `band_of` and row strings,
`median_in` with masks, Y/H/K `compute()` warnings and outputs, examples
per band, per-band A0V round trip);
`scripts/regen_regression_fixtures.py` (report mode): J, J2 and line
fixtures **unchanged**; `scripts/check_docs.py` ALL CHECKS PASS;
`sphinx-build -W` exit 0; `bin/keck_etc examples/H_point.json --summary`
runs. `verify_harvest.py` on the committed table reports two FAILs that
predate this work: `pypeit_version` fb6fb62c4 against the pin bc18a3ba4
(the pin moved with image 0.2.5 after those rows were harvested) and the
`excluded_3mad` flags that `combine_throughput.py` writes into the table
but not into the curve meta (by design). Not touched: the J throughput
files (prompt 2), `gates.py`, the manifests, `reduce_standard.py`,
`search_mosfire_standards.py` (prompts 3 and 4).

What I learned about the repository:
- `Instrument.throughput` caches by era name; a second axis (the group)
  had to go into the cache key, and the tests that pop the cache
  (`test_throughput_falls_back_to_nearest_era`) needed the new key.
- `scripts/check_docs.py` requires every `index.yaml` entry to carry the
  latest release tag of `CHANGES.md`; placeholders therefore need an
  explicit exemption, which now exists for `provisional-*`.
- The J2 half-power band is what the 2025-on era file covers, i.e. J2 rows
  were never edge-trimmed; the design's "0.9 for every band" has to be read
  as "every new band".
- `verify_harvest.py` compares the table row with the curve's `meta.row`
  over all columns, so any later flag edit of the table (the 3-MAD
  exclusion) shows as a FAIL there; that check should compare everything
  but `flag`, or the combine step should update the curve meta too (a
  prompt-2 cleanup when the table is regenerated).
- XTcalc's efficiency files span 2048 samples per band at the detector
  sampling and the H file stops 49 A before the nominal H coverage; the
  2012 curves exclude the Keck mirrors (hence KMRef^2).

### 2026-10-27 (Prompt #2 / S23b: J files renamed per group, standards table migrated, J-only release mosfire-2026.10 prepared; compute() identical to mosfire-J-2026.10)

The prompt asked for Opus 5.5; this session ran on Claude Fable 5.1. No
git command other than `git status`, `git diff`, `git log` and `git
archive HEAD` (read-only, extracted into the scratch directory as the
"old release" tree) was run. No new Q&A answers since the previous entry.
Everything is uncommitted, on top of the uncommitted S23a work.

**Rename (D49).** `MOSFIRE.throughput_pattern` is now
`mosfire/throughput/mosfire_thru_{group}_{tag}.ecsv`;
`Instrument.throughput_file` raises if a pattern has no `{group}` (a
pattern without it would let every group read one file), and the S23a
`legacy_throughput_group` stop-gap is gone from `base.py` and
`mosfire.py`. `combine_throughput.py` (with `CALIB_VERSION =
mosfire-2026.10`) loops over the band groups that have rows and wrote
`mosfire_thru_J_{2012-2016,2017-2025,2025-on}.ecsv`: `wave`,
`thru_median`, `thru_mad` and `n_std` differ from the old files by
exactly 0 (checked with a scratch script), the `meta` lists the same
standards and exclusions and gains `band_group`, `bands` (J, J2) and
`common_window_A`; the `index.yaml` entries carry `bands`. The old files
are still on disk, unregistered (their index entries are dropped);
`verify_release.py` prints them as a WARN until they are removed. **Git is
yours:**

```
git rm keck_etcs/data/mosfire/throughput/mosfire_thru_2012-2016.ecsv
git rm keck_etcs/data/mosfire/throughput/mosfire_thru_2017-2025.ecsv
git rm keck_etcs/data/mosfire/throughput/mosfire_thru_2025-on.ecsv
git add keck_etcs/data/mosfire/throughput/mosfire_thru_J_*.ecsv keck_etcs/data/mosfire/throughput/mosfire_thru_*_provisional.ecsv
```

**Standards table: which path and why.** All 20 nights are synced under
`$KECK_ETCS_DATA/mosfire/<night>/`, but their `harvest/*_row.ecsv` are the
in-pod outputs with the old columns, and a local re-harvest from the sens
files would not reproduce every row: the raw frames behind the
`excluded_nonlinear` flag are only partly local (1-5 frames per night),
so `harvest.standard_peak_adu` would drop that flag on some nights. The
table was therefore migrated by the new one-off
`scripts/mosfire/migrate_standards_table.py`, which recomputes the four
metrics from the committed curves with the harvest's own functions
(`zp_at` on `zeropoint`, `median_in` on `thru`), copies every other
column unchanged, rewrites each curve's `meta.row` (new columns, the
harvest-time flag, `band_group`) without touching the curve data
(asserted line by line), stamps the table and its index entry, and drops
the old era-file index entries. Checks printed per row: for every J row
`zp_lo/mid/hi` equal the old `zp_1200/1250/1300` exactly; for every J2 row
`zp_mid` and `zp_hi` equal the old `zp_1200` and `zp_1250`;
`thru_median_common` equals `trend.curve_common_median`. All 20 PASS. J2
rows now carry `zp_lo` at 11500 A (19.23, 19.20, 19.27, 19.23 for the four
J2 nights), which the old table did not have. `thru_median_common` values
(0.164-0.285) are the `thru_common` of the report.

**Release tag.** New `scripts/mosfire/stamp_release.py <tag>` writes the
tag into every non-provisional `index.yaml` entry (14 stamped, 3
`provisional-xtcalc-2012` placeholders kept); the build scripts'
development tag is now `mosfire-2026.10-dev`. `check_docs.py` accepts
`mosfire-YYYY.MM` and checks that every throughput entry is named per
group with `bands`.

**Regression.** New `scripts/compare_release_outputs.py`: runs
`compute()` on every example and fixture input in this tree and in an
old tree (`--old DIR`, or `git archive REF` by itself), each in its own
subprocess, and tabulates the maximum relative difference per output
field (nested `meta`, `summary` and `saturation` flattened; strings as
`=`/`!=`; allowed text fields printed element by element). Result against
the mosfire-J-2026.10 tree (`git archive HEAD`): **largest relative
difference 0 over every numeric field of the six J/J2 inputs**; the only
text differences are `meta.calib_version` and the file name inside one
warning; the Y, H and K examples have no counterpart in the old release
(`band: 'H' is not one of ['J', 'J2']`). The table:

| field | example:J2_point | example:J_line | example:J_point | fixture:J | fixture:J2 | fixture:line |
|---|---|---|---|---|---|---|
| `meta.keck_etcs_version` | = | = | = | = | = | = |
| `meta.pypeit_version` | = | = | = | = | = | = |
| `meta.calib_version` | != (allowed) | != (allowed) | != (allowed) | != (allowed) | != (allowed) | != (allowed) |
| `meta.era` | = | = | = | = | = | = |
| `meta.inputs` | = | = | = | = | = | = |
| `wave_A` | 0 | 0 | 0 | 0 | 0 | 0 |
| `dispersion_A_per_pix` | 0 | 0 | 0 | 0 | 0 | 0 |
| `lsf_fwhm_A` | 0 | 0 | 0 | 0 | 0 | 0 |
| `resolving_power` | 0 | 0 | 0 | 0 | 0 | 0 |
| `n_spec_per_resel` | 0 | 0 | 0 | 0 | 0 | 0 |
| `slit_fraction` | 0 | 0 | 0 | 0 | 0 | 0 |
| `aperture_fraction` | 0 | 0 | 0 | 0 | 0 | 0 |
| `n_spatial_pix` | 0 | 0 | 0 | 0 | 0 | 0 |
| `fwhm_arcsec_band` | 0 | 0 | 0 | 0 | 0 | 0 |
| `throughput` | 0 | 0 | 0 | 0 | 0 | 0 |
| `atm_transmission` | 0 | 0 | 0 | 0 | 0 | 0 |
| `filter_transmission` | 0 | 0 | 0 | 0 | 0 | 0 |
| `signal_e` | 0 | 0 | 0 | 0 | 0 | 0 |
| `sky_e` | 0 | 0 | 0 | 0 | 0 | 0 |
| `dark_e` | 0 | 0 | 0 | 0 | 0 | 0 |
| `read_noise_e` | 0 | 0 | 0 | 0 | 0 | 0 |
| `noise_e` | 0 | 0 | 0 | 0 | 0 | 0 |
| `snr_pixel` | 0 | 0 | 0 | 0 | 0 | 0 |
| `snr_resel` | 0 | 0 | 0 | 0 | 0 | 0 |
| `summary.snr_pixel_median` | 0 | 0 | 0 | 0 | 0 | 0 |
| `summary.snr_resel_median` | 0 | 0 | 0 | 0 | 0 | 0 |
| `summary.snr_line` | = | 0 | = | = | = | 0 |
| `summary.line_window_A` | = | 0 | = | = | = | 0 |
| `summary.exptime_s` | 0 | 0 | 0 | 0 | 0 | 0 |
| `summary.n_frames` | 0 | 0 | 0 | 0 | 0 | 0 |
| `summary.total_time_s` | 0 | 0 | 0 | 0 | 0 | 0 |
| `saturation.peak_e_per_frame` | 0 | 0 | 0 | 0 | 0 | 0 |
| `saturation.peak_adu_per_frame` | 0 | 0 | 0 | 0 | 0 | 0 |
| `saturation.wave_A` | 0 | 0 | 0 | 0 | 0 | 0 |
| `saturation.flag` | = | = | = | = | = | = |
| `warnings` | 0 | != (allowed) | != (allowed) | != (allowed) | 0 | != (allowed) |

The fixtures were regenerated for the tag and that warning
(`regen_regression_fixtures.py --regen --note`; the line is in
`CHANGES.md`); report mode now says unchanged.

**Verification.** `verify_release.py` (rewritten per group: names and
`bands` in the index, `compute` per era and band of every released group,
XTcalc per group with its KMRef, `zp_mid` against airmass, provenance):
ALL CHECKS PASS (XTcalc -2.9 percent, J 1.88 sigma, the same five image
triplets as the first release). `verify_harvest.py` (no legacy columns;
check 3 accepts the pin of any image in the operator guide's table and
says whether it is the current one; check 4 compares the curve `meta.row`
without the combine-time `excluded_3mad`; the re-harvest divides out the
night's shipped filter as the night job does): VERIFY PASS over 20 rows,
with `--reharvest` of LDS749B 2022-04-09 reproducing the table row.
`pytest keck_etcs/tests`: 124 passed (new: `{group}` placeholder required,
prior `excluded_3mad` rows reported, shipped table columns and nodes,
shipped era file `bands`); `check_docs.py` ALL CHECKS PASS;
`sphinx-build -W` exit 0.

**Docs.** `CHANGES.md`: header (tag format), a code entry for S23b and the
release section `mosfire-2026.10`; `README.md` (current tag, the README
example outputs, the refresh steps); `nautilus/README.md` section 10
(tag format, stamp and compare steps); `docs/wmko_api_note.md`,
`docs/citing.md`, `docs/developer/calculations.md` (names and tag
format). The report under `reports/` is historical and keeps `zp_1250`.

**Ask: please tag.** As `nautilus/README.md` section 10 step 8: commit
the code, then the release (`keck_etcs/data/` and `CHANGES.md`), then
`git tag mosfire-2026.10`; step 9 (`backup_products.py --run --release
mosfire-2026.10`) is outward-facing and was not run.

What I learned about the repository:
- A rerun of `combine_throughput.py` on a table that already carries
  `excluded_3mad` flags used to write an empty `meta.excluded` (the
  flagged rows were skipped before the statistics); `combine_era` now
  reports such rows as excluded again, so the regenerated files have the
  same `meta` as the originals.
- `compute()` takes `calib_version` from `index.yaml`, not from the file
  `meta`, so a release is stamped in the index alone; the ECSV `meta` of
  the dev products keeps the `-dev` tag they were built under.
- The regression fixtures compare `warnings` and `meta.calib_version` as
  strings, so any release, even one with identical numbers, regenerates
  them; `compare_release_outputs.py` is the check that the numbers did
  not move.
- `Table(rows=[...])` gives fixed-width string columns: a test that
  assigns a longer flag must widen the column first (`astype('U32')`), or
  the value is silently truncated.
- The 2022-04-09 night is the only one with all raw frames local, which
  is why it is the re-harvest check.
