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

### 2026-10-27 (Prompt #3 / S23c: KOA census for Y, H and K in the one candidate table; validation targets per band)

The prompt asked for Opus 5.5; this session ran on Claude Fable 5.1. No
git command other than `git status`, `git log`, `git tag` and `git show
HEAD:<file>` (the committed J table, for the comparison) was run. No new
Q&A answers. The S23b commits are in (`b0fc83c`, `c334e35`); `git tag`
lists no tag on this checkout.

**Census script.** `scripts/koa/search_mosfire_standards.py --filters`
takes band groups (`Y`, `J` = J/J2/J3 as in S14, `H`, `K`) or KOA filter
names; the default `J` reproduces the S14 census from its cache
(`koa_mosfire_J_longslit_frames.xml`, kept under its old name; the other
groups cache as `koa_mosfire_<group>_longslit_frames.xml`). `BASE_WHERE`
is now `base_where(filters)`; the frames of every group are stacked and
run through the unchanged rules (archive and SIMBAD A0 matches within
60", wide slit >= 3", flats in the band and on the same mask kind, OH
frames >= 55 s or long2pos arcs in the band). 2MASS is queried for J, H
and Ks (`tmass_mags`, cache `tmass_jhk.json`; columns `hmag_2mass`,
`e_hmag_2mass`, `kmag_2mass`, `e_kmag_2mass` after `e_jmag_2mass`). The
`meta` carries `instrument`, `filters`, `filter_groups`, `koa_queries` and
`koa_rows` per group and the command line; nothing MOSFIRE-specific is in
the column names (H-1). `report()` gains the per-band block and
`design_counts()` recomputes the 9.2 TAP counts from the cached frames.
The committed table was built with `--filters J Y H K` (the Y/H/K frame
queries and 2MASS cones ran in about ten minutes).

**Verification.** A scratch comparison of the new table's J-group rows
with the committed one (`git show HEAD:...`): the same 594 (night,
standard, mask, filter) keys and **every one of the 43 common columns
unchanged**; the four 2MASS columns are new. The 9.2 TAP counts from the
cached frames: Y 11317 / 230 / 13, J2 714 / 14 / 2, H 15409 / 415 / 92
and K 27575 / 372 / 72 equal design 9.2; J gives 12051 / 332 / 50 against
12052: the J cache is from 2026-10-05 and the survey ran later, when one
more frame had become public (KOA's public set only grows). `pytest
keck_etcs/tests`: 125 passed (new: every band in the table, 2MASS H and
Ks finite for > 95 percent of the A0V rows, `expand_filters`,
`base_where`); `check_docs.py` ALL CHECKS PASS after letting it list,
instead of fail on, products rebuilt after a release (`mosfire-2026.10-dev`
on the three census files until the next release stamps them).

**Per-band census** (usable = WD/archive/A0V with flats on a wide slit;
reducible = also a wavelength calibrator; "WD+A0V" = nights holding both
classes, on a wide slit and, in brackets, on any slit):

| | Y | J | J2 | H | K |
|---|---|---|---|---|---|
| Candidate rows / nights | 451 / 272 | 570 / 364 | 24 / 18 | 758 / 464 | 722 / 414 |
| Usable wide-slit rows / nights | 23 / 21 | 43 / 38 | 9 / 8 | 87 / 72 | 77 / 60 |
| of which reducible nights | 12 | 16 | 4 | 35 | 55 |
| WD / archive / A0V rows (usable wide) | 9 / 0 / 14 | 3 / 1 / 39 | 7 / 0 / 2 | 1 / 1 / 85 | 1 / 1 / 75 |
| Distinct stars (usable wide) | 11 | 26 | 4 | 45 | 40 |
| Reducible nights per era 2012-16 / 2017-25 / 2025- | 0 / 8 / 4 | 7 / 9 / 0 | 0 / 3 / 1 | 16 / 19 / 0 | 19 / 36 / 0 |
| WD+A0V nights, wide (any slit) | 0 (10) | 0 (7) | 0 (0) | 0 (6) | 0 (9) |

Whole table: 2525 rows on 716 nights; 239 usable wide-slit rows on 101
nights (WD 21, archive 3, A0V 215), 144 of them reducible on 77 nights
(OH 15, lamp arcs 129); 42 percent of candidate nights have matching
lamp arcs (20 percent in J alone: the H and K `long2pos_specphot`
nights usually carry Ne/Ar arcs). The 2022-04-09 LDS749B check passes.

What this means for the H and K plan: H and K each have more usable
wide-slit nights than J (72 and 60 against 38), nearly all A0V stars on
`long2pos_specphot` with arcs, and only one white dwarf and one archive
star each on a wide slit, so **D52's cross-tie in H and K has no night
with both classes on a wide slit**; it will compare a white dwarf night
with A0V nights of the same era, or use the 6 (H) and 9 (K) nights that
hold both classes on narrow slits. No H or K wide-slit night falls in era
2025-04.. yet. Y has 9 white-dwarf rows (GD153, LDS749B) on wide slits
and no 2012-2016 wide-slit night.

**Validation targets.** `scripts/koa/find_validation_targets.py` reads
every cached band group (`--filters` to restrict), keeps the J-only
rules, prints a per-band summary with the 9.7 fallbacks, and writes the
table for all bands (202 program targets on 24 nights, 107 validation
points on 15 nights). `nights_validation.csv` stays the J-group manifest
(4 nights, unchanged) until S23d adds the `band` column; the Y/H/K
validation nights are only listed. Per band: Y 15 validation nights, 9 of
them with a same-night wide-slit standard (LDS749B 2022-04-09, GD153
2024-12-29/30, 2025-01-08/25, 2025-07-17/18/22/23), so Y does not need
the J2132-1434 fallback; H one point (J1532+2237, 2022-01-11, GD153 on a
1" slit); K two (J0313-1806, 2020-12-09, GD153 1"; J1342+0928,
2021-04-18, P330E 1"); no H or K program night has a wide-slit standard,
so those validations flux with a narrow-slit standard (slit loss enters,
as the design notes for the Y fallback) or use Per-emb 25 in K
(2019-10-13, thermal continuum only). The design doc records both
results (9.3 P3 and 9.7).

**Docs:** `CHANGES.md` code entry; design 9.3 and 9.7 result paragraphs.
`docs/keck_mosfire_design.md` section 4.1 keeps its "Other bands" note.

What I learned about the repository:
- `conda run` drops stdin: a heredoc-piped `python -` under it runs
  nothing and prints nothing (the memory note was right; the scratch
  analyses had to be files).
- KOA's long2pos nights in H and K carry Ne/Ar arcs far more often than
  in J, which is why their reducible fractions are high.
- `check_docs.py` treated any `-dev` entry after a release as a failure,
  which would have blocked every census or monitor rebuild between
  releases; it now lists them as pending.
- A `(align)` mask name (`LONGSLIT-46x1 (align)`) is grouped separately
  from the science mask in the validation table, so some nights appear
  twice for one target.

### 2026-10-27 (Prompt #4 / S23d: reference reductions at the pin in the image, H and K footprints and LSFs frozen, Brackett and thermal checks, the multi-band layout and gates, the dry runs prepared)

The prompt asked for Opus 5.5; this session ran on Claude Fable 5.1. No
git command other than `git status`, `git log`, `git tag`, `git rev-parse
HEAD` and `git diff --stat` was run. No new Q&A answers. The S23c commit
(`654092c`) is in. Everything below is uncommitted.

**Where "at the pin" was.** `scripts/check_pypeit_pin.py` FAILS in
`pypeit14b`: its PypeIt is `/mnt/tank/Astronomy/PypeIt/PypeIt` at
`53f64bb85` on the branch `speed_up_arcfit`, which does not contain the pin
(`bc18a3b`), with `keck_mosfire.py`, `wavecalib.py` and 70 other files
differing. I did not touch that checkout (git is yours). The 0.2.5 image
(PypeIt at the pin, digest `69591fcb...`) is in the workstation's Docker,
so every reference reduction ran inside it with this repository mounted
read-only at `/opt/src/keck-etcs` and first on `PYTHONPATH`, the data root
mounted at its host path, `KECK_ETCS_GIT_SHAS` set to the pin and this
HEAD, `KECK_ETCS_IMAGE=local` (the products are not pod products) and a
final `chown` to my user (the image runs as root; its PypeIt cache is not
readable otherwise). The pin check inside runs in image mode and PASSES.
The helper is in my scratch directory
(`/tmp/claude-1000/-mnt-tank-Astronomy-PypeIt-keck-etcs/40acd4df-f2ae-49c4-84d6-43f9c4578882/scratchpad/run_in_image.sh`);
it is not repository material.

**Reference reductions (D56),** raw frames copied from the dev suite into
`mosfire/20121128/raw/` (H and K share it), `20191013/raw/`, `20180718/raw/`;
products under `mosfire/<night>/<band>/` (D55):

| Setup | Night, band | Driver changes it needed | Result |
|---|---|---|---|
| `longslit_3x0.7_H` | 2012-11-28 H | the 2.9 s HIP 17971 frames typed `arc,standard,tilt` (their own OH lines; no other on-sky frame) as the dev-suite file does; `pypeit_setup` run in `redux/` (it logs into the cwd, read-only in the mount) | success, 150 s; wave RMS 0.066 pix; S/N 151-160 per frame |
| `longslit_3x0.7_K` | 2012-11-28 K | the same | success, 184 s; RMS 0.037 pix; S/N 133-139 |
| `K_long` | 2019-10-13 K | none | success, 483 s; RMS 0.091 pix; HIP 17971 S/N 140-144, Per-emb 25 S/N 7-12 |
| `long2pos1_H` | 2018-07-18 H | lamp-calibrated long2pos path (Ne/Ar arcs typed `arc,tilt`, `[[wavelengths]]` from `keck_mosfire_arcs_H.fits`); PypeIt's object-finding defaults instead of the J2 template's `find_trim_edge = 10,10` (the star sat 10 pixels from the edge of a 41-pixel slit and was discarded, "no trace") | success, 142 s; arcs RMS 0.21 and 0.17 pix; **HIP 61138 extracted at S/N 2-9 only** |

The long2pos star: the dev-suite `keck_mosfire_long2pos1_h.pypeit`, run
as-is in the same image, extracts the same faint objects (S/N 2-6 at the
same positions), so the driver reproduces PypeIt's reduction of that
night and the weak extraction is PypeIt's long2pos handling (or the data),
not the driver. The lamp-calibrated path itself works. Left for S24a; the
H A0V sample is `long2pos_specphot`, the bar-split path of S15.

**A PypeIt defect at the pin.** `pypeit_sensfunc` on the HIP 17971 spec1d
crashed in `keck_mosfire.config_specific_par`: it splits
`get_meta_value(header, 'slitrange')`, which is None for a product header
of a short long slit (`LONGSLIT-3x0.7`: `find_longslit_pos` needs the CSU
bar cards; the spec1d header carries `SLITRANGE` = `971:1099` instead).
`LONGSLIT-46x` and long2pos masks return without those cards, which is
why every J night passed. Fix: `nautilus/patches/pypeit_mosfire_slitrange_spec1d.patch`
(the `slitrange` branch of `compound_meta` returns the header's
`SLITRANGE` when present); a unified diff against the pin's file, applied
with `patch -p1` inside the image for the sensfunc runs below (not to your
checkout). **Please** commit it on `etc-fixes` and move the pin, as the
earlier patches went.

**Measured (all from the image reductions):**

- Footprints (`scripts/mosfire/measure_footprint.py`, new; frozen in
  `mosfire.py` with file and sha256):
  - H: `mosfire/20121128/H/redux/Calibrations/WaveCalib_A_1_DET01.fits`
    (sha256 `6243190f...8bf26`): pixels 0-2039, **14650.5-17970.7 A**,
    1.6284 A/pix. The nominal 14680-18040 was 30 A too narrow at the blue
    end and 70 A too wide at the red. ETC window 14660.9-17970.7 A: the
    filter sets the blue end, the detector the red (105 A of the filter
    band fall off).
  - K: `mosfire/20121128/K/redux/Calibrations/WaveCalib_A_1_DET01.fits`
    (sha256 `6e9bbfd2...c54c5f`): **19535.9-23991.1 A**, 2.1850 A/pix
    (nominal 19540-23970). `K_long` (46x1.5, 2019-10-13, sha256
    `16070c6b...feb35b`): 19529.7-23957.1 A, 2.1713 A/pix: the K tilt
    reproduces to about 35 A (16 pixels) at the red end between nights,
    recorded as `K_FOOTPRINT_2019_A`. ETC window = the footprint (375 A of
    the filter band fall off).
  - `footprint_provisional` is off for H and K; `MONITOR['band_windows']`
    updated; the ETC no longer warns about the H and K footprints.
- LSF (`measure_lsf.py --band --record`; the script's `--record` had lost
  its `sha256sum` import in the S6b refactor and never worked since, fixed):
  H 0.7" **2.560 pix** (4.15 A, R 3976; 8 clean of 28 OH lines, the H
  lines blend), K 0.7" **2.613 pix** (5.65 A, R 3803; 5 clean lines), K
  1.5" (`K_long`) **5.370 pix** (11.6 A, R 1850; 17 lines). The J
  quadrature rule gives 2.627 and 5.249 pix: -2.6, -0.5 and +2.3 percent,
  so the rule holds in H and K to a few percent and the predicted 5
  percent narrowing is not seen. `lsf_measurements.ecsv` now has one row
  per (filter, date, slit): `ref_wave_A` (the band's middle node),
  `fwhm_A_ref`, `R_ref` replace `fwhm_A_1250`, `R_1250` (J row values
  unchanged). `lsf_fwhm_pix(0.7, 'H'|'K')` and `(1.5, 'K')` now return the
  measured rows; the LSF warning for H and K stays only at other widths.
- Sensfuncs of HIP 17971 (J-scaled A0V model, `--jmag 8.005`, 2MASS H
  7.981 and Ks 7.887 recorded in the census; the band-scaled model is
  prompt 5), provisional `keck_mosfire_{H,K}.sens` (polyorder 5, tell_npca
  3): H zero point finite over 14651-17972 A, median end-to-end throughput
  over 14900-17800 A **0.241** (0.7" slit, slit loss included; gate 0.17-0.54),
  telluric PWV 1.0 mm; K finite over 19537-24007 A, **0.247** over
  19800-23700 A (gate 0.16-0.51), PWV 0.6 mm. `gates.py --band H|K` on the
  references: all four local gates PASS.
- **Brackett mask (D52)** (`scripts/mosfire/brackett_mask_check.py`, new;
  two `pypeit_sensfunc` runs on the H coadd with `hydrogen_mask_wid` 10
  and 30): the two sensfuncs are identical to 1e-4 mag, because PypeIt's
  **IR algorithm never uses `hydrogen_mask_wid`** (only
  `flux_calib.standard_zeropoint`, the UVIS path, does); and the Vega
  model leaves no Brackett residual: the per-pixel zero point minus the
  fit has rms 0.019 mag within +-40 A of Br10-18 against 0.018 mag in the
  continuum (ratio 1.08; per line 0.010-0.027). The H and K `.sens` files
  carry no mask line (the header says why); design 9.3 records it.
- **K thermal continuum (D60)** (`scripts/mosfire/fit_thermal_continuum.py`,
  new; sky from the raw frames divided by the flat and the exposure time,
  the Gemini model at the frame's airmass and 1.6 mm, both as 10th
  percentile floors per 100 A over 2.15-2.40 um; T_sys the provisional
  XTcalc curve; T = the night's median `TUBETEMP`):

  | Night | Frames | TUBETEMP | floor measured 2.155 / 2.395 um | x model | eps_eff at T (275 K) | eps per bin 2.155 -> 2.395 |
  |---|---|---|---|---|---|---|
  | 2012-11-28 | 4 x 2.9 s HIP 17971, 0.7" | 1.59 C | 20.4 / 40.6 ph/s/arcsec^2/nm/m^2 | 35-40 | 0.468 (0.457) | 1.09 -> 0.27 |
  | 2019-10-13 | 2 x 119 s Per-emb 25 + 2 x 2.9 s HIP 17971, 1.5" | 4.79 C | 8.8 / 38.6 | 13-18 | 0.226 (0.287) | 0.34 -> 0.19 |

  The 2019 floor rises 4.4x across the band (XTcalc's 2012 spectrum: 2.7
  to 21, 7.8x; a 275 K grey body: 7.8x); the 2012 short frames carry a
  flat ~20 component at 2.15-2.25 um (a pedestal or read floor of a 2.9 s
  frame: 35 e-) on top of the thermal rise. In both nights the excess is
  flatter than a 275 K Planck, so one `eps_eff` at the tube temperature
  does not describe the blue end of K: the D61 continuum excess and the
  D60 thermal term overlap there and part K must fit them together, with
  the measured T_sys. The red-end values (0.19-0.20 in 2019, 0.27-0.33 in
  2012) sit 1.3-2x above the design's 0.12-0.15. Outputs:
  `mosfire/<night>/K/thermal/thermal_<night>.{ecsv,json}`.

**Nautilus side (D55).** `keck_etcs.paths.night_dir`/`s3_prefix` take
`band` (`LEGACY_BANDS`: J, J2, J3 stay at the night level; `raw` shared);
`reduce_standard.py` resolves the band from `--filter`/`$BAND`/`$FILTER`
or the raw headers and writes under `mosfire/<night>/<band>/` with `band`
and `raw_s3_prefix` in the manifest; `build_sensfunc.py --band` picks the
band's `.sens` (`mosfire.sens_par_file`); `gates.py --band` reads the
windows from `mosfire.gate_windows` (J keeps its S4b windows exactly;
`LEGACY_GATE_WINDOWS`), the throughput range from `THRU_GATE_RANGE`
(0.5-1.6x XTcalc per group) and passes the band to `inspect_sensfunc`
(whose `inspect`, `compare` and `estimate_pwv` take a window and the
band's PWV windows); `harvest_sens.py`, `measure_lsf.py`,
`stage_reference.py`, `verify_nights.py`, `status_table.py`,
`status_row.py`, `night_failures.py` know the band. `make_night_manifest.py`
writes a `band` column and one row per (night, band) with the band's
`s3_prefix`; `download_mosfire_night.py` takes `--bands`, fetches each
row's band into the shared `raw/` and merges the manifests by KOA id. The
Job scripts export `$BAND` with the other columns, log it, and
`GATES_REFERENCE=auto` means the row's own `s3://keck-etcs/<s3_prefix>/reference`
(`validate_job.yaml` now says `auto`; `night_job.yaml` unchanged in
effect; the two blocks stay identical, `validate_manifests.py` OK).
`nights_dryrun_HK.csv` (new; `make_night_manifest.py dryrun_HK`) holds
the 2012-11-28 H and K rows; `nights_dryrun.csv` was rewritten with the
`band` column (same row). References staged locally:
`mosfire/20121128/{H,K}/reference/` (MANIFEST.txt, 10 files each).

**Not done here, for you (outward-facing, as the prompt says):**
1. the PypeIt fix on `etc-fixes` and the new pin (`nautilus/pypeit_pin.txt`,
   `build_image.sh` already allows that branch);
2. bump `keck_etcs/__init__.py` to 0.2.6 and `CITATION.cff`, `bash
   nautilus/build_image.sh --push`, then point the three Job manifests at
   0.2.6 (image line, digest comment, `KECK_ETCS_IMAGE`) and run
   `validate_manifests.py`; record the tag in the README table;
3. once the image exists I should re-run the four reference reductions
   and the two sensfuncs in it (10 minutes; the references must carry the
   new pin for the `ref_pin` gate, since the current ones record `bc18a3b`
   plus the patch) and re-stage; then you push:
   `s3_sync.py push mosfire/20121128/raw`, `stage_reference.py 20121128
   --band H --push`, `--band K --push`;
4. the dry runs: the ConfigMap from `nights_dryrun_HK.csv`,
   `validate_job.yaml` with `completions: 2`, and `GATES: PASS` twice. KOA
   has no H or K flats on 2012-11-28, so the raw directory is the dev
   suite's, as the manifest notes say.

**Verification:** `pytest keck_etcs/tests`: 128 passed (new:
`test_paths.py`, `test_gate_windows_and_sens_files`, the measured LSF
rows and footprints; `test_other_bands_run_on_provisional_data` now
expects the LSF warning for Y only); `regen_regression_fixtures.py`
report: J, J2, line unchanged; `check_docs.py` ALL CHECKS PASS;
`validate_manifests.py` MANIFESTS OK; `gates.py` PASS on both references.
Nothing J-related changed: the J gate windows are the S4b ones, the J
layout is the night level, `lsf_fwhm_pix(w, 'J')` is unchanged, the J
rows of the LSF table carry the same numbers under the new column names.

**Docs:** `nautilus/README.md` (layout with band directories, the `band`
column, the per-band dry run with the 2012-11-28 steps, the gate
windows); `CHANGES.md` code entry; design 9.2 (footprints measured), 9.3
(the D52 result), 9.4 (reference results, the PypeIt defect), 9.5 (the
LSF measurements, the first `eps_eff` values and their caveat).

What I learned about the repository:
- The `pypeit14b` checkout is the user's working PypeIt and moves; the
  pinned image is the reproducible place, and mounting the repository into
  it with `PYTHONPATH` gives "PypeIt at the pin, keck_etcs current"
  without a rebuild. Its cache is root-owned, so the container runs as
  root and the products are chowned back.
- `pypeit_setup` and `pypeit_sensfunc` write logs into the working
  directory; the driver now runs the former in `redux/` (the latter was
  already in `sens/`).
- `Spec2DObj.skymodel` of an A-B reduction is the residual sky, so sky
  levels must come from the raw frames (`monitor.process_raw`), as the
  monitor already does.
- PypeIt's `hydrogen_mask_wid` is a UVIS-only parameter; the IR telluric
  fit has no hydrogen mask.
- A `Table(rows=...)` of the night manifests is written by `csv`; the
  `band` and `filter` columns carry the same value on purpose (the pod
  exports both; older manifests have only `filter`).
- `measure_lsf.py --record` was broken since S6b (a missing import); the
  2022-04-09 row predates the refactor.

### 2026-10-30 (Prompt #4 / S23d, closing: image 0.2.6 at the new pin, reference reductions rerun in it, references re-staged)

Session on Claude Fable 5.1 (the prompt asks for Opus 5.5), continuing
the 2026-10-27 entry. You committed the `SLITRANGE` fix on PypeIt
`etc-fixes` as `b0447b74ea01ac0ba8496817afaa336e573791c0` (on top of the
S17 read-noise fix `38bb1b7`), moved the local `pypeit14b` checkout to it,
and built and pushed **image 0.2.6**
(`gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.2.6`, digest
`sha256:c9e01c3415afe8d5b5739e022c90600ebc7aa809275a9d89a4120dca49cc3f92`,
keck-etcs `d34a000`, PypeIt `2.0.2.dev1223+gb0447b74e`, keck_etcs 0.2.6).
The first build attempt failed in the build script's own secret scan:
`scripts/check_docs.py` carried the literal patterns the scan greps for;
its patterns are now split literals, as the build script's are.

**Done here:**

- The three Job manifests (`night_job.yaml`, `validate_job.yaml`,
  `koa_download_job.yaml`) point at 0.2.6 (image line, digest comment,
  `KECK_ETCS_IMAGE`, `KECK_ETCS_IMAGE_DIGEST`); `validate_manifests.py`
  MANIFESTS OK. `nautilus/README.md` section 3 has the 0.2.6 row
  (**Current**) and section 4 loses its "Pending" read-noise bullet (the
  pin carries it). `check_pypeit_pin.py --image 0.2.6`: all three checks
  PASS (the checkout is at the pin with an empty diff, the image's
  `KECK_ETCS_GIT_SHAS.pypeit` equals it); a bare tag now resolves to the
  Nautilus image, as the usage line always said.
- **The four reference reductions and the two sensfuncs rerun in 0.2.6**
  (no patch needed; the 0.2.5 products are kept aside under
  `$KECK_ETCS_DATA/mosfire_products_image0.2.5/`, not in the layout, until
  you discard them): all four `success` (152, 185, 490, 206 s), every
  `run_manifest.json` records pin `b0447b7`, keck-etcs `d34a000` and the
  0.2.6 digest, pin check PASS in image mode. Against the 0.2.5 products:
  the H, K and K_long **footprints are identical to 0.1 A** and the
  wavelength RMS to three decimals (`measure_footprint.py`; the WaveCalib
  files differ in bytes, so their sha256 in `mosfire.py` and in
  `lsf_measurements.ecsv` are the new ones); the **LSF rows re-recorded
  with `measure_lsf.py --record` are numerically identical** (H 0.7"
  2.5597, K 0.7" 2.6135, K 1.5" 5.3704 pix); the extracted **S/N per frame
  is 5 percent lower** (H 144-151 for 151-160, K 125-129 for 133-139,
  K_long HIP 17971 132-136 for 140-144) with the median counts within 0.5
  percent, which is the CDS read noise of 21 e- now in the variance (the
  first products with the S17 fix); the long2pos star is as faint as
  before (S/N 2-7). Sensfunc medians: H **0.2397** over 14900-17800 A
  (0.2414 before), K **0.2459** over 19800-23700 A (0.2472); `gates.py
  --band H|K`: all four gates PASS for both. Brackett check rerun: line
  rms 0.0187 against continuum 0.0184 (ratio 1.02), masks 10 and 30 A
  identical to 1e-4 mag, same verdict. Thermal fits rerun: 2012-11-28
  eps_eff 0.468 (0.457 at 275 K), 2019-10-13 0.226 (0.287): unchanged.
- References re-staged: `stage_reference.py 20121128 --band H` and
  `--band K` (10 files each, MANIFEST.txt rewritten; the
  `run_manifest.json` inside carries the 0.2.6 provenance for the
  `ref_pin` gate).
- `CHANGES.md` (S23d entry: the image, the pin, the rerun; the S17
  read-noise note says "pinned by 0.2.6"), design 4.8.2/9.4 and the
  settled-questions list name the new pin and image; `mosfire.py`'s
  footprint comment records the rerun.

**Verification:** `pytest keck_etcs/tests` 128 passed; `check_docs.py`
ALL CHECKS PASS; `validate_manifests.py` MANIFESTS OK;
`check_pypeit_pin.py --image 0.2.6` PASS.

**Dry run (done by you the same day, logs parsed here):** after the
commit (`e0340bb`), `s3_sync.py push mosfire/20121128/raw` and
`stage_reference.py 20121128 --band H|K --push`, the ConfigMap from
`nights_dryrun_HK.csv` and `validate_job.yaml` with `completions: 2`
(`parallelism: 2`; the manifest now says so). Both pods, image 0.2.6,
`KECK_ETCS_GIT_SHAS` pypeit `b0447b7` / keck_etcs `d34a000`:

| index | band | reduce | gates | agreement with the staged reference | harvest row | push |
|---|---|---|---|---|---|---|
| 0 (`keck-etcs-validate-0-fsn8q`) | H | success, 352 s | **PASS** (8/8; thru 0.2397, RMS 0.066) | spec1d counts ratio 1.000000 x4, zp median 1.00004, S/N to 0.00 % | `thru_median_common` 0.243, PWV 1.14 mm, flags `pwv_weak,narrow` | 107 files, 0 failed; 9.3 min wall, 3.7 GB peak |
| 1 (`keck-etcs-validate-1-vt9gb`) | K | success, 288 s | **PASS** (8/8; thru 0.246, RMS 0.037) | 1.000000 x4, zp median 1.00017, S/N to 0.00 % | 0.262, PWV 0.58 mm, flags `pwv_extrapolated,narrow` | 108 files, 0 failed; 8.9 min wall, 3.7 GB peak |

`ref_pin` PASS in both (reference and pod at `b0447b7`), monitor 56 and 64
rows with 0 failures, status rows under `runs/keck-etcs-validate/status/`,
`NIGHT_DONE` twice. The pod products are now on the bucket under
`mosfire/20121128/{H,K}/`; the two logs are kept under
`$KECK_ETCS_DATA/runs/keck-etcs-validate/logs/20261030_dryrun_HK_index{0_H,1_K}.log`
(not committed). The per-band layout, `GATES_REFERENCE=auto` and the
band-aware gates work in the pods as they do locally; **prompt 4 is
closed.** Next is prompt 5 (the H and K standards and their models).

**Learned:** the image's secret scan reads every file of the build
context, the checker included, so a pattern that must appear in the tree
is written as split literals. The read-noise change moves the extracted
S/N by 5 percent at these count levels without touching the wavelength
solutions, the LSF or the footprints; the throughput medians move by 0.5
percent through the extraction weights. A `cd DIR && (a) & (b) &` line
runs `b` in the old directory: two logs landed in the repository root and
were moved.

### 2026-10-30 (Prompt #5 / S24a, part 1: the H sensfunc parameters measured, the A0V model in the band's own 2MASS magnitude, the H pilot manifest; pilot BLOCKED on the image rebuild)

Session on Claude Fable 5.1 (the prompt asks for Opus 5.5). No new Q&A
answers (H-1..H-4 as folded in). Everything below ran locally in
`pypeit14b`, which is at the pin `b0447b7` (the 0.2.6 image's) with a
clean tree, so "at the pin" holds without the image.

**The D53 test** (`scripts/mosfire/sensfunc_perturbation_test.py`, extended:
`--band` sets the common window, `--polyorders` and `--tell-npca` loop over
the parameter with `--n` 1e-5 perturbations per value, `--jobs` runs the
fits in parallel; per value the stability, the rms and max difference to
the next value up over the window and within 100 A inside its edges; the
lowest value passing 1 / 1 / 2 percent is chosen; JSON and tables). Nights:
the reference `longslit_3x0.7_H` (HIP 17971, 0.7", S/N 150) and, per H-3,
the brightest reducible 2017-2025 `long2pos_specphot` A0V of the census,
**HD 79108 on 2024-12-24** (H = 6.16, 1.45 s frames, airmass 1.49; KOA
download of 25 frames with `download_mosfire_night.py 20241224 --bands H`,
reduced with `reduce_standard.py` in 392 s: two frames with the star in a
4" bar, S/N 260, wavelength RMS 0.058 px on both bars, raw peaks 12-14k
ADU so linear; gates PASS, median throughput 0.32 through the 4" bar).

The first run on HD 79108 failed everything (chi2 5500, orders 10-30
percent apart) and exposed two things PypeIt's defaults do wrong for a
star in an off-centre wide bar, both fixed on the keck-etcs side in
`build_sensfunc.py` for Y, H and K (J untouched: its release must stay
reproducible until the next J re-reduction):

1. **Filter-edge mask.** The 4" bar at spat 946 covers 14350-18267 A, 300 A
   beyond the H filter's half-maximum at both ends; the zero point rises
   steeply there and a polynomial fitted across it overshoots by 10-30
   percent inside 15000-15300 A. Pixels with filter transmission below half
   the peak (outside 14664-18075 A) are now masked in spec1d copies
   (`sens/spec1d_*_fmask.fits`) before the per-frame fits and the coadd.
   chi2 5500 -> 1040.
2. **Telluric resolution guess.** PypeIt guesses R from the sampling (3
   px per element, R about 3300) and bounds the fit to 0.6-1.4 of it; the
   wide-bar fit sat at the lower bound. `[[IR]] resln_guess` is now the
   band's LSF rule at the effective slit width (the smaller of the bar
   width and the star's spatial FWHM) and `resln_frac_bounds` 0.4-1.5.
   The wide-bar fit still runs to the bounds (and to 0.2x / -25 px when
   opened that far, at the same chi2): on a 1.45 s A0V coadd the H
   tellurics do not constrain resolution and shift, and the throughput
   medians do not feel them (0.317-0.319 across every setting). The
   reference night's fit also sat at 0.6x (its star is 0.41" FWHM in the
   0.7" slit). `sens/<NAME>_<DATE>_sens_setup.json` records both.

With those, **polyorder 4 and tell_npca 2 pass on both nights** (reference:
stability 0.65 percent, next-order rms 0.63, edges 0.41; HD 79108: 0.30 /
0.92 / 1.01 percent; tell_npca 3 passes too, 0.2-0.4 percent from 2;
orders 5 and 6 fail the 1 percent step on one night each; the highest
order tried, 8, is the reference only). Written to
`keck_etcs/data/pypeit_par/keck_mosfire_H.sens` with both tables in the
header (polyorder 4, tell_npca 2, no hydrogen mask line); design 9.3 has
the result paragraph. The tables and JSON are under
`mosfire/<night>/H/sens/polyorder_test/` (the pre-mask runs under
`polyorder_test_nomask/`, the 0.6x-bounds run under
`polyorder_test_bounds06/`).

**The A0V model in the band's own 2MASS magnitude (D51):** the night
manifests carry `hmag_2mass` and `kmag_2mass` beside `jmag_2mass`
(`make_night_manifest.py`, `status_row.py`, `night_failures.py`; the pod
exports every column); `reduce_standard.py --mag` and `build_sensfunc.py
--mag` default to the band's column (`standards.mag_column`,
`mag_from_env`), `--jmag` stays the J cross-check; `run_manifest.json`
`standard` records `mag_2mass` and `mag_band_2mass`;
`nights_dryrun_HK.csv` regenerated with the two columns. **Cross-check
finding:** on HIP 17971 the band-scaled model is 0.022 mag brighter than
the J-scaled one in H (median throughput 0.2397 -> 0.2349 with the final
file) and **0.120 mag brighter in K (0.2459 -> 0.2205)**: 2MASS J - Ks =
+0.118 for a star that should have about 0; reddened (it sits in Perseus)
or not a clean A0V. The band's own magnitude is the right flux level
either way; design 9.3 asks the K doc to check the star's colour against
the K white dwarf before the K release. HD 79108: +0.023 mag offset.

**Pilot manifest** (`make_night_manifest.py pilot --band H`,
`nautilus/manifests/nights_pilot_H.csv`, H-2; the J pilot rules are now
confined to the J group so that `pilot` reproduces `nights_pilot.csv` from
the all-band census table): Feige 110 2014-06-01 (the one H white dwarf
on a wide slit with a calibrator, 2012-2016), HD 79108 2024-12-24
(the test night), HD 159008 2015-09-17 (2012-2016 A0V, 44 flats), HD
133772 2017-06-15 (second 2017-2025 A0V, another program; also the J
pilot's A0V night). `night_job.yaml` `completions: 4`, `parallelism: 4`
(the J pilot peaked at 7.6-11.7 GiB on 16 Gi).

**Also:** `check_std_peaks.py --band`; the per-night sens parameter copy
is now written for archive standards too (`<NAME>_<DATE>_std.sens`) when
it carries the resolution lines; the reference sensfuncs of 2012-11-28 H
and K were rebuilt with the final file and settings and **re-staged**
(`stage_reference.py 20121128 --band H|K`; gates PASS, H 0.2349, K 0.2205);
the version is bumped to **0.2.7** (`__init__`, `CITATION.cff`, `README.md`,
`docs/wmko_api_note.md`).

**Verification:** `pytest keck_etcs/tests` 133 passed (new: the band
magnitude column and environment, the driver's record per band, the
builder's edge mask / resolution guess / slit width, the H pilot and HK
dry-run manifests); `check_docs.py` ALL CHECKS PASS;
`validate_manifests.py` MANIFESTS OK; gates PASS on the three local
nights.

**For you, before the pilot (outward-facing):**
1. commit; `bash nautilus/build_image.sh --push` (the `.sens` file, the
   driver and `build_sensfunc.py` changed; the pin stays `b0447b7`), and
   give me the 0.2.7 digest: I then update the three Job manifests and
   the README table as for 0.2.6;
2. `stage_reference.py 20121128 --band H --push` and `--band K --push`
   (the staged references changed with the sensfunc settings; a pod on
   0.2.7 reproduces them, a pod on 0.2.6 would fail `zp_agree`);
3. the pilot, with your go-ahead: the KOA download Job on
   `nights_pilot_H.csv` (`koa_download_job.yaml`, 4 rows; 2024-12-24 is
   already local, `s3_sync.py push mosfire/20241224/raw` would spare its
   download) and `night_job.yaml` (completions 4, parallelism 4). Then I
   sync, harvest, merge, freeze the H monitor lines and write part 2 of
   this entry with the status table.

**Learned:** PypeIt's IR sensfunc fits the zero point over every unmasked
pixel, filter edges included, and guesses the telluric resolution from the
pixel sampling; neither is a defect (they are parameters), but a standard
in a wide bar of an off-centre long2pos position needs both set from the
keck-etcs side. The `pilot` rules of `make_night_manifest.py` silently
drew from every band once the census table held them all. `conda run`
buffers a script's output until it exits, so a running reduction's log
looks empty from outside; the night's own `run.log` shows progress.

### 2026-10-31 (Prompt #5 / S24a, part 2: the H pilot, two long2pos fixes, the H monitor lines frozen)

Session on Claude Fable 5.1 (the prompt asks for Opus 5.5).

**Image 0.2.7** (`gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.2.7`,
`sha256:46e80edaf6eef0469530dae0d57fd756a8d6de64d221bbf873e2e07a16509dc2`,
keck-etcs `c5c8e53`, PypeIt pin `b0447b7`; `check_pypeit_pin.py --image
0.2.7` PASS): the three Job manifests, the README table (section 3) and
CHANGES carry it. The user pushed the re-staged H and K references.

**The pilot.** The first launch ran both Jobs against the ConfigMaps'
previous content (the 19-row J batch 1): the download Job re-skipped 19 J
nights and the four night pods skipped their J rows in seconds; nothing on
the bucket changed. The ConfigMaps were re-created from
`nights_pilot_H.csv`, the KOA download Job (4 rows, 3 min) and then the
night Job (4 completions, parallelism 4) ran; `koa_download_job.yaml` now
says 4 completions. Monitored every 30 min (`/loop`); done in 18 min:

| Index | Night | Standard | Mask | Pod (0.2.7) | Wall [s] | Peak [GiB] | Gates | Frames in 4" bars | Median thru | zp_mid (16500 A) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 20140601 | Feige 110 (WD) | long2pos_specphot (align) | `no trace` (exit 13) | 532 | - | - | 0 | - | - |
| 1 | 20241224 | HD 79108 (A0V, H 6.163) | long2pos_specphot | success | 332 | 8.20 | PASS | 2 | 0.318 | 19.778 |
| 2 | 20150917 | HD 159008 (A0V, H 6.800) | long2pos_specphot | `sens failed` (exit 14) | 1053 | - | - | 1 (crash) | - | - |
| 3 | 20170615 | HD 133772 (A0V, H 7.225) | long2pos_specphot | success | 830 | 8.20 | PASS | 2 | 0.323 | 19.791 |

The two successes are verified (`verify_nights.py 20241224 20170615 --band
H --digest ... --pin b0447b7`: ALL OK; 20241224 needed a forced pull first,
because the night's earlier local products had the same sizes as the pod's).
Scratch 0.73 and 1.36 GB.

**What failed, and the fixes.** Both failures are the long2pos bar
geometry in H, not the sensfunc settings:

1. *2014-06-01 (`no trace`)*: six slits traced for seven bars (bar 26, a
   0.7" posC bar, not traced; the posC 4" bar 25 traced as slit 943 but
   its own wavelength fit failed, so it was flagged bad and the two frames
   with the star in it had no object); the posA 4" bar 21 (slit 1120) had
   its own fit at RMS 1.08 px. PypeIt's `transfer_wavecal` requires one
   traced slit per bar and refused the whole mask.
2. *2015-09-17 (`sens failed`)*: eight slits traced for seven bars (a
   spurious 847-pixel slit at 1187-2034, above the mask), the same
   refusal; the arc-FWHM fallback of `specphot_wide_slits` found only one
   wide bar and left `specphot.bars = None`, on which
   `build_sensfunc.slit_width_of` crashed. Underneath: two of the night's
   four Ne/Ar arcs (m150917_0472/0473) were taken through the plain
   `long2pos` mask, whose bars 21 and 25 are 0.7" wide, so the combined arc
   mixed 3-px and 17-px lines in those bars and their fits followed the
   narrow lines (FWHM "1.3 px", cross-correlation with the neighbours 0.3).
3. **PypeIt (`etc-fixes`, uncommitted; the pin moves with image 0.2.8):**
   `KeckMOSFIRESpectrograph.long2pos_match_bars` and `long2pos_bar_slits`
   match the bars to the traced slits by position: bar 23 (posB) sits at
   `CRPIX2`, bar n is `23 - n` CSU pitches (CSU length plus gap, 44 px)
   above it; a bar takes the slit within a third of a pitch (the three
   observed layouts agree to 4 px; `test_long2pos_match_bars`).
   `transfer_wavecal` skips a bar without a slit, ignores a slit without a
   bar, and keeps a bar's own fit when the transferred one is worse (the
   mixed-mask night gave RMS 1.5 and 5.9 px against its own 0.3 and 0.2).
4. **`reduce_standard.py`:** `specphot_wide_slits` uses the same matcher
   (`bars` with `spat_id` None for an untraced bar, `bars_without_slit`;
   the arc-FWHM rule stays the fallback for a PypeIt without it); on a
   long2pos_specphot night, calibration frames whose CSU mask differs from
   the standard's (`mask_of`, the `(align)` tag dropped) are left out with
   a note. `build_sensfunc.slit_width_of` takes 4.0" from `wide_slit`
   when the bar table has no entry. Tests
   `test_driver_specphot_bars_by_position` (a synthetic
   `Mechanical_Slit_List`) and the extended builder test.
5. **Local reruns** (PypeIt working tree, `--skip-pin-check`, the pod's
   steps without the push): 2014-06-01 PASS with 4 wide-bar frames
   (0364/0376 in bar 21, 0367/0379 in bar 25; transfers at cc 0.90-0.91,
   RMS 0.050 and 0.062 px; 436 s; median throughput 0.322, harvest 0.327,
   zp_mid 19.790); 2015-09-17 PASS with 3 frames (0248/0256 in bar 21,
   0259 in bar 25, RMS 0.059 and 0.078 px; the posB frame 0247 drops out
   at RMS 0.505 against `SPECPHOT_RMS_PIX` 0.5; 932 s; 0.305, harvest
   0.310, zp_mid 19.738). The failed pod products are parked locally as
   `mosfire/<night>/H_pod_0.2.7_failed/`; the bucket still holds the failed
   manifests (status table: `no trace`, `sens failed`), to be replaced by
   the pod rerun.

**A0V against the white dwarf (D2, S15a criterion):** zero points at
16500 A through 4" bars, Feige 110 2014-06-01 19.790; HD 159008 2015-09-17
(same era) -0.052 mag (5 percent fainter); HD 133772 2017-06-15 +0.001;
HD 79108 2024-12-24 -0.012 mag (the 2017-2025 era has no H white dwarf
night; the two eras agree to 1 percent here). All within 20 percent: PASS.
No A0V frame is saturated (raw peaks 12-14k ADU). The reference HIP 17971
at 0.7" gives 0.238 (zp_mid 19.471), slit losses included, as in the
sensfunc test.

**H monitor lines frozen** (`select_monitor_lines.py 20121128 20140601
20150917 20170615 20241224 --band H --nlines 5`; the script now takes
`--band` for the per-band layout, the band's dispersion for the isolation
window, rule 1 over the nights with OH arcs only and rule 3 from the
narrowest slit of the first night): the four long2pos_specphot nights are
Ne/Ar-calibrated (12-16 percent of their identified lines fall on OH
wavelengths) and are left out of rule 1, which the 2012-11-28 reference
alone decides; 91 OH_R24000 lines are at least 100 A inside 14650-17971 A,
23 pass rule 1, 27 rule 2, 79 rule 4, 7 all three, all 7 rule 3 (0.7"
fluxes 500-2200 e-/s/arcsec^2, raw peak 4.8k ADU); the brightest per
sub-window: **15240.788, 15654.833, 16234.899, 16903.502 A** (the reddest
sub-window, 17247-17871 A, has none). File
`keck_etcs/data/mosfire/monitor/monitor_lines_H.ecsv`, sha256
`041aa1c266bb7b8f4e9fb1ca6dc4eb17d21c1a414f090ad6c5eaa51c073cf7e4`;
`MONITOR['monitor_lines']['OH']['H']` set; `test_mosfire_config` checks
it. The monitor was rerun on the five H nights: `monitor.line_fluxes` had
no slit width for a long2pos frame (`TypeError`); it now measures the OH
lines in the mask's 0.7" bars (`bar_widths` from `specphot.bars`), 137-265
rows per night, no `monitor_failed`.

**Merge:** `harvest_sens.py --merge` of the five H harvests (the reference
harvested first: `harvest 20121128 --band H --standard HIP17971`):
`standards.ecsv` 20 -> 25 rows, five curves under `throughput/standards/`,
`calib_monitor.ecsv` 3307 rows. The monitor merge replaced rows per night
only, so the J pod rows of 2014-06-01 blocked its H rows; it now keys on
night and band.

**Verification:** `pytest keck_etcs/tests` 134 passed (two shipped-table
tests now expect the H rows: the J era file's provenance is checked
against its own bands' rows, `standards.ecsv` carries the H nodes and
window; plus the PypeIt `test_keck_mosfire.py`, 3 passed); `check_docs.py` ALL CHECKS PASS;
`validate_manifests.py` MANIFESTS OK; `verify_nights.py` ALL OK on the two
pod nights; `status_table.py` written (27 nights on the bucket).

**The pin and the version.** The user committed PypeIt `etc-fixes`
`5e92ff9` (the matcher) and keck-etcs `0f2c5bc`/`bf0b499`, then re-pushed
the tag **0.2.7** at `bf0b499` (digest
`sha256:e6c69cb7ffd438aebffcd95069542a80c921075d63181cff438b538dbdb76a79`)
before the pin had moved: that image still installs PypeIt `b0447b7` and
cannot reduce the two nights. `nautilus/pypeit_pin.txt` is now `5e92ff9`
(`check_pypeit_pin.py` PASS locally), the version is **0.2.8**, the three
Job manifests say 0.2.8 with the digest marked PENDING, and the README
table notes the re-push. `check_docs.py` fails on purpose until the 0.2.8
row with its digest exists (the manifests must use the README's current
image); `validate_manifests.py` is OK.

**Image 0.2.8** pushed by the user:
`sha256:780dbaf68d96c8b650599a00932750abb26511fdf9031c1d2b1a6fbcefdd51ef`,
keck-etcs `78e2058`, PypeIt pin `5e92ff9` (image label checked;
`check_pypeit_pin.py --image 0.2.8` PASS); the three Job manifests, the
README table (**Current**), CHANGES and the design doc carry it;
`check_docs.py` passes again.

**The rerun on 0.2.8** (night Job on the pilot manifest, 4 completions;
monitored every 30 min, done in 26 min): indices 1 and 3 skipped as done
on the bucket (3-5 s); index 0, 2014-06-01 Feige 110, `GATES: PASS` with
the 4 wide-bar frames (slits 943 and 1120 at RMS 0.062 and 0.050 px),
median throughput 0.3224, 853 s, 7.9 GiB peak, 1.34 GB scratch; index 2,
2015-09-17 HD 159008, `GATES: PASS` with 3 frames (RMS 0.078 and 0.059 px),
0.3052, 1535 s, 12.5 GiB peak, 1.07 GB scratch. The pod results equal the
local ones. Products pulled (`--force`; the local products parked as
`H_local_fixed/`), `verify_nights.py --band H` ALL OK for all four nights
(20140601 and 20150917 against the 0.2.8 digest and pin `5e92ff9`,
20241224 and 20170615 against 0.2.7 and `b0447b7`, the pin of their
image), `status_table.py`: the four H nights `success` with passed gates.
The merge replaced the two local rows and their monitor rows by the pod
ones (`standards.ecsv` H rows: Feige 110 0.3267 and zp_mid 19.789 on
0.2.8/`5e92ff9`, HD 159008 0.3105 and 19.738, the two 0.2.7 rows
unchanged, HIP 17971 local). `pytest` 134 passed, `check_docs.py` ALL
CHECKS PASS.

**Final status table** (bucket, `status_table.py`):

| Night | Standard | Image | PypeIt | Gates | Wall [s] | Peak [GiB] | Frames in 4" bars | Median thru | zp_mid |
|---|---|---|---|---|---|---|---|---|---|
| 20140601 | Feige 110 (WD) | 0.2.8 | `5e92ff9` | PASS | 853 | 7.9 | 4 | 0.322 | 19.789 |
| 20150917 | HD 159008 (A0V) | 0.2.8 | `5e92ff9` | PASS | 1535 | 12.5 | 3 | 0.305 | 19.738 |
| 20170615 | HD 133772 (A0V) | 0.2.7 | `b0447b7` | PASS | 830 | 8.2 | 2 | 0.323 | 19.791 |
| 20241224 | HD 79108 (A0V) | 0.2.7 | `b0447b7` | PASS | 332 | 8.2 | 2 | 0.318 | 19.778 |

The two 0.2.7 nights stay on their image: the matcher changes nothing on a
night whose seven bars were all traced. S24a is complete; the next step is
prompt 6 (S24b, the H batches).

**Next (for the user):** commit (the merged tables, the log).

**Learned about the repository:** the Jobs read their manifest from a
ConfigMap, so "apply the Job" without re-creating the ConfigMap runs the
previous batch, harmlessly (the skip check) but silently; the README now
says so. `s3_sync.py pull` skips same-size objects, so a night reduced
locally before its pod run keeps stale local products until `--force`.
The CSU bar geometry is fixed (bar 23 at `CRPIX2`, 44 px per bar) and
holds to 4 px on every long2pos night seen, which is a better key than
slit counts. A KOA night's lamp arcs can come from a different CSU mask
than its standard (the plain `long2pos` beside `long2pos_specphot`), and
PypeIt combines them into one arc. The monitor's OH fluxes never ran on a
long2pos night before, because J has no frozen lines (`'J': ()`).

### 2026-11-02 (Prompt #6 / S24b, batch 1: 35 H nights launched, 12 new successes merged, 19 failures diagnosed and fixed, sweep manifest and image 0.2.9 prepared)

Session on Claude Fable 5.1 (the prompt asks for Opus 5.5).

**Batch 1.** `make_night_manifest.py batch1_H --band H --usable-wide`
wrote `nights_batch1_H.csv`: 35 nights, every reducible public wide-slit H
night of usable class (census: 122 wide public H rows with flats, 42
reducible rows on 35 nights, all `long2pos_specphot` with lamp arcs; the
four pilot nights included and skipped as done). The user launched the
download Job (35/35 in 47 min) and the night Job at parallelism 4 (image
0.2.8); it ended `Failed` after 81 min with 16 completed indexes and 19
failed. Outcomes (`nautilus/README.md` section 6):

- 12 new `success`, gates PASS, verified (`verify_nights.py --band H`,
  0.2.8 digest and pin, ALL OK): 20140606 HD128039 (1250 s), 20141005
  *55Dra (502 s), 20160226 HD128039 (1113 s), 20160417 HD74721 (796 s),
  20170418 HD99966 (601 s), 20180109 HD47944 (543 s), 20180602 BD+252478
  (2177 s, 14.9 GiB peak), 20230410 HD74721 (1279 s), 20241226 HD44128
  (760 s), 20241227/28/30 HD21875 (757/836/874 s). 1 to 4 frames with the
  star in a 4" bar each. Median throughput 0.30-0.36; five rows
  `excluded_nonlinear` (HD 128039 twice, HD 74721 2023, HD 21875 twice).
- 18 `no calibs` ("no lamp-on flats with filter H") in 15-80 s each and
  one `reduce failed` (20160108). Not a download problem: the flats are
  there. On these nights every flat and Ne/Ar arc was taken through the
  plain `long2pos` mask while the standard sits on `long2pos_specphot
  (align)`, and the S24a rule that drops another CSU mask's calibration
  frames discarded all of them (the pilot nights all had specphot flats).
  The raw headers of 20141123 show the two masks have identical bar
  centres (`Mechanical_Slit_List` `Position_of_Slit`), only the widths
  differ (0.7" for 4.0"), so those frames are valid calibrations.

**Fixes (uncommitted here; PypeIt committed by the user as `b8a6a19`).**

1. `reduce_standard.py other_mask_calibs(tbl)`: another mask's flats, or
   arcs, go only when the standard's mask has its own frames of that type
   (2015-09-17 keeps its fix); otherwise they are kept with a note.
   `test_driver_other_mask_calibs_per_type`.
2. With the flats kept, 20141123 reached `no trace`: the plain-`long2pos`
   flats illuminate the whole CSU (every bar open, 10^4 counts across the
   detector), so the edge trace gives four slits for seven bars ([7,
   1007], bar 23, bars 20-22 merged, [1186, 2033]) and `split_merged_bars`
   refused ("46 slits for 7 bars"). Replaced by `bar_slit_edits(edges,
   bar_centers, pitch, gap, row)`: the trace is shifted onto the mask by
   the median offset of traced edges near nominal bar edges (-3.5 px
   here), a slit holding one bar centre is kept, any other slit is removed
   and each bar inside it added back as its nominal extent clipped to the
   slit; untraced bars are listed and left alone. 20141123 then: seven
   bars, 2 of 6 frames with the star in a 4" bar (the ±7" dither moves it
   into the 0.7" neighbours, as on the pilot nights), gates PASS, 0.330,
   zp_mid 19.82, 266 s. `test_driver_bar_slit_edits` (open-CSU flats,
   clean trace, spurious slit beside an untraced bar, merged positions).
3. 20160108 crashed inside `run_pypeit`: `autoid.full_template` on a
   spurious eighth slit over the open CSU measured an arc FWHM of 0.3 px,
   so `arc.fit_arcspec` called `curve_fit` on one pixel and scipy raised
   `TypeError` (only `RuntimeError` was caught). PypeIt `etc-fixes`
   `b8a6a19`: a fit window under three pixels is skipped and
   `TypeError`/`ValueError` are caught; `test_fit_arcspec_tiny_fwhm`.
   20160108 re-run locally: gates PASS, 0.337, 398 s (the carve left the
   trace alone there: bar 26 untraced, six bars kept, and with that rule
   the spurious slit now also goes).
4. `night_failures.py`: the status prefix `runs/keck-etcs-nights/status/`
   spans every Job of that name (61 rows, J batches included), so the
   sweep had two J nights and lacked six H nights ("data failure, not
   retried": their J runs had failed `no calibs` too). Rows are now keyed
   by (night, band); `--manifest <batch>.csv` restricts the sweep to the
   batch and `--retry-data` retries data failures after a driver change.
   `sweep_batch1_H.csv`: the 19 nights. Test added.
5. `status_table.py` gains a `band` column (and ignores `reference/`
   copies); `check_standards_table.py` keys nights by (night, band), lists
   success products of bands not yet harvested (the K reference) instead
   of failing, and accepts the empty `job_name` of the locally harvested
   HIP 17971 row. ALL CHECKS PASS.
6. **Curve-file collision.** `harvest_sens.py --merge` of the 12 H nights
   changed the committed J curves `*55Dra_20141005.ecsv` and
   `HD74721_20160417.ecsv`: the J and H rows of a night both named their
   curve `<standard>_<night>.ecsv`, so each merge overwrote the other
   band's file. The S24a H merge had already overwritten the committed
   `Feige110_20140601.ecsv` and `HD133772_20170615.ecsv` (HEAD holds H
   curves under J names). `harvest.curve_name` now adds `_<band>` for a
   multi-band product (D55); the merge renames on merge (pod rows need no
   re-harvest), restores a kept row's curve when missing, removes stale
   unreferenced curves, keeps the table row when the same harvest is
   merged again (the J row files predate S23a; re-merging them had masked
   the band metrics, now filled from the curve by `heal_band_metrics`).
   The four J curves are restored from the local J harvests (two differ
   from HEAD only in the curve `meta['row']`, which the S23b migration had
   rewritten: `git checkout -- keck_etcs/data/mosfire/throughput/standards/{*55Dra_20141005,HD74721_20160417}.ecsv`
   keeps the richer copies), the five pilot H curves carry `_H`, and
   `*55Dra` J lost its `excluded_3mad` flag, which `combine_throughput.py`
   sets (to be checked when the H era files are built). The 20170615 J
   monitor rows (51) were likewise gone from `calib_monitor.ecsv` since
   the S24a merge; re-merged.

**Products.** `standards.ecsv` 37 rows (17 H, 11 usable wide-slit over
both eras: era 1 Feige 110, *55 Dra, HD 159008, HD 74721; era 2 HD 99966,
HD 133772, HD 47944, BD+25 2478, HD 79108, HD 44128, HD 21875),
`calib_monitor.ecsv` 5916 rows, 17 `_H` curves. Backup
(`backup_products.py --run`) and the sweep launch are the user's.

**Image 0.2.9 built and pushed** (by the user, from keck-etcs `c3e6df6`
with PypeIt `etc-fixes` at `b8a6a19cc5e8a54899ea318065a41333c8ef7163`):
digest
`sha256:6e0c5801a3c83f20adddcc407a779a3a46db8521c6f529b063e0eea52b28f34a`
(confirmed read-only with `docker manifest inspect`; the image label
`org.opencontainers.image.revision` records both commits). Filled into the
three Job manifests, the `nautilus/README.md` image table (0.2.9
**Current**, 0.2.8 "Ran H batch 1"), the README current-code line and the
design 9.6 as-built list. `validate_manifests.py` MANIFESTS OK,
`check_docs.py` ALL CHECKS PASS, `check_pypeit_pin.py --image 0.2.9` PASS
(the PypeIt checkout is back on `etc-fixes` at the pin), pytest 139
passed, 3 deselected. The sweep recipe of `nautilus/README.md` section 7
was dry-run locally (`kubectl apply --dry-run=client`: Job
`keck-etcs-nights-sweep1`, 19 completions, parses); the launch is the
user's. Note: a ConfigMap `keck-etcs-nights-sweep1` from the J sweep
(S15c) still exists and the recipe's `apply` replaces it; the bucket's
`runs/keck-etcs-nights-sweep1/status/` therefore holds J rows too, which
the (night, band) keys of `status_table.py`, `night_failures.py` and
`check_standards_table.py` keep apart.

**Backup script fixed for the band layout.** A dry run of
`backup_products.py --prefix mosfire/20140606` matched only the root
`manifests/**` and `runs/**` (161 objects, 0.2 MB): its filters knew the
night level only, so no H product (pilot or batch 1) had ever reached
`AIOcean:keck-etcs/`. `filter_rules` now adds every pattern under the band
directories (`[A-Z]*/`, D55) and accepts `mosfire/<night>/<band>`;
`pod.log`, `gates.json` and `pypeit_pin_check.json` join the set;
`release_prefixes()` replaces `release_nights()` (the old
`split('/')[-1]` would have returned `H` for an H row). Dry run of one H
night: 71 files (40 `sens/`, 23 `redux/`, 3 `harvest/`, the JSON/log files,
`raw/manifest.ecsv`); of the whole set: 2331 objects, 366 MB, 1303 files to
copy. `test_backup_products.py` (2 passed). The `--run` is the user's.

**Learned.** The installed PypeIt is an editable checkout: while the user
works on another branch (`speed_up_B` at the end of this session) the
keck-etcs tests skip the bar-matcher test and local reductions must not be
run; `etc-fixes` must be checked out for the next local run or test pass.
`conda run` buffers a script's stdout, so a running reduction's launcher
log is empty until exit (read the night's `run.log`). The KOA
`long2pos` flats of 2014-2016 (and of seven 2017-2024 nights) are full-CSU
flats; `pypeit_trace_edges` finds gaps only where neighbouring bars sit at
different CSU positions. A J-era status row has no `band`; astropy writes
an empty string as a masked `--`, so band keys must normalise it.

### 2026-11-02 (Prompt #6 / S24b, sweep 1: 19 nights on image 0.2.9, 16 successes merged, 3 failures diagnosed, two fixes, image 0.2.10 prepared)

Session on Claude Fable 5.1 (the prompt asks for Opus 5.5).

**Image 0.2.9 and sweep 1.** The user built and pushed 0.2.9 (keck-etcs
`c3e6df6`, PypeIt `b8a6a19`; digest
`sha256:6e0c5801a3c83f20adddcc407a779a3a46db8521c6f529b063e0eea52b28f34a`,
filled in; `check_docs.py` ALL CHECKS PASS, `check_pypeit_pin.py --image
0.2.9` PASS) and launched the sweep from the README section 7 recipe (Job
`keck-etcs-nights-sweep1`, ConfigMap from `sweep_batch1_H.csv`, 19
completions, parallelism 4). Monitored read-only every 15 min (cron,
progress in the scratchpad `p6/sweep1_progress.txt`). Job `Failed` after
79 min: 16 completed, 3 indexes exhausted (`backoffLimitPerIndex: 1`).

| outcome | nights |
|---|---|
| success, gates PASS | 20141123 HD95126 0.334, 20150428 HD159008 0.351 (excluded_nonlinear), 20150904 HD18571 0.339, 20151022 HD54601 0.326, 20160107 HD111744 0.245, 20160415 HD149595 0.338, 20160501 V*V836Cyg 0.248, 20170504 HD160512 0.354, 20170908 HD18571 0.329, 20171105 HD74721 0.289, 20171106 HD74721 0.345, 20190319 HD121880 0.349 (excluded_nonlinear), 20201126 HD65158 0.351, 20210930 HD21379 0.335, 20230205 HD98884 0.356, 20241110 HD24000 0.331 (excluded_nonlinear) |
| reduce failed (x2) | 20160106 HD9485, 20160108 HD111744 |
| gate failed (thru_median 0.043) | 20160530 HD111744 |

Wall clocks 8-33 min (20170908: 1991 s). The carve was applied on every
night: the full-CSU `long2pos` flats (`rm 3, add 6`) on ten nights, bars
merged in a position (`rm 2, add 6`) on the others.

**Failures.**
- 2016-01-08 (`reduce failed`, `run_pypeit` exit 1 in 30 s): the carve
  removed the spurious slit at 1610 and had nothing to add back, and the
  driver wrote `add_slits = ` (empty). PypeIt's parser turns that into one
  empty item and `int('')` raises (`parse.py:466`). Fixed:
  `slitedges_block(rec)` writes only the non-empty keys
  (`test_driver_slitedges_block_omits_empty_keys`). The local re-run of
  batch 1 had not caught it because the final carve rule (remove a slit
  with no bar) came after that run.
- 2016-01-06 (`reduce failed`, the same error): the carve removed all four
  traced slits and added none, because the standard frame's
  `Mechanical_Slit_List` read as bars `['', '0', '0', '0', '0']`. The FITS
  ASCII tables of every frame of that night (flats, arcs, standards) have
  their bytes one 80-byte card further into the data block than the header
  says (`scripts/mosfire/dump_csu_bars.py --raw`: two blank rows, then
  `   20 posA ...` shifted by 2 characters, the last row in the padding).
  PypeIt's `long2pos_bar_widths` reads the same table, so the bar matcher
  would have failed too. Fixed in PypeIt on `etc-fixes`
  (`54e68d7767acee2f9ca4ee8d0f36c4f890bb8b38`, committed by the user):
  `read_slit_list(hdu, extname)` in `keck_mosfire.py` returns the table as
  stripped strings and, when the parsed `Slit_Number`/`Slit_width` columns
  are not integers/floats, re-reads the rows from the raw data block
  (padding included, `_get_raw_data`) at the byte shift where the most rows
  parse (ties broken by the characters read, so `20` beats `2`); used by
  `long2pos_bar_widths` and `get_slitmask`; binary tables (a test's) pass
  through. `test_read_slit_list_shifted[0|80]`. The driver's
  `split_merged_bars` uses it when present. With the recovered bars the
  local re-run reduced the night but found no star in a 4" bar: the six
  "standard" frames have `OBJECT = 'MIRA PMFM 350'`, defocused
  mirror-alignment exposures. Data failure; the night stays out.
- 2016-05-30 (`gate failed`): the star in a 4" bar in 1 of 16 frames (FWHM
  0.58", S/N 68), 12 frames with no object at all: clouds. Excluded by the
  gate; no retry.

**Low nights.** 2016-01-07 HD111744 0.245 (the same star at the same
airmass gives 0.333 on 2016-01-08: transparency; 12 frames of 2.9 and
14.5 s) and 2016-05-01 V* V836 Cyg 0.248 (a variable star; its 2MASS H is
not a stable reference). Both are below median - 3 MAD of era 1 (median
0.326, MAD 0.013), as is 2017-11-05 HD74721 0.289 in era 2 (0.329, 0.010);
`combine_throughput.py` will flag them `excluded_3mad`.

**Products.** Synced (`s3_sync.py pull mosfire/<night>/H`, `--calibs`),
`verify_nights.py --band H --digest sha256:6e0c58... --pin b8a6a19...` ALL
OK (16 nights), `status_table.py` 57 night/bands (H: 16 `success` on 0.2.9,
2 `reduce failed`, 1 `gate failed`), `harvest_sens.py --merge` of the 16
harvests: `standards.ecsv` 53 rows (33 H; 24 usable wide-slit H over 2
eras: 10 in 2012-04..2016-09, 14 in 2017-02..2025-02; 8
`excluded_nonlinear`), 16 new `<standard>_<night>_H.ecsv` curves,
`calib_monitor.ecsv` 8721 rows (monitor_failed 0), `index.yaml` updated;
`check_standards_table.py` ALL CHECKS PASS; pytest 141 passed, 1 skipped
(the PypeIt checkout is on `speed_up_arcfit`, so the bar-matcher test
skips), 3 deselected.

**Image 0.2.10 prepared** for sweep 2 (`nautilus/manifests/sweep2_H.csv`:
2016-01-08 only; 2016-01-06 and 2016-05-30 are data failures):
`__version__`/`CITATION.cff`/README 0.2.10, `pypeit_pin.txt` `54e68d7...`,
the three manifests at 0.2.10 with `sha256:PENDING_PUSH`, README image
table row (0.2.9: "Ran H sweep 1"), design 9.6 as-built list.
`validate_manifests.py` MANIFESTS OK; `check_docs.py` has the four expected
FAILs until the digest is filled in. Sweep 2 recipe: README section 7
(`sweep1` -> `sweep2`, `completions: 1`). The build/push, the launch and
`backup_products.py --run` are the user's. `backup_products.py` was also
fixed this session (band directories; see the batch-1 entry).

**Learned.** KOA MOSFIRE frames can carry FITS ASCII tables whose data
block starts one card late; astropy parses them silently into shifted
columns, so a bar list of blanks and zeros is a data defect, not a mask
without bars. `MIRA PMFM` frames are mirror-alignment exposures that KOA
lists under the standard's name: a future manifest builder should drop
frames whose `OBJECT` starts with `MIRA`. The Job's `backoffLimitPerIndex:
1` retries a `reduce failed` night once, uselessly when the failure is
deterministic; the retry costs about 90 s per night. The user's PypeIt
checkout moves between branches during a session; the pin check, not the
checkout, is the reference for the image.

### 2026-11-03 (Prompt #6 / S24b: image 0.2.10 pushed and pinned, sweep 2 ready to launch)

Session on Claude Fable 5.1.

The user committed the sweep-1 work (`6a51d43`) and built and pushed image
0.2.10 (PypeIt pin `54e68d7`; digest
`sha256:672a59c4e70c30e9cf0f23adf4d6efdef67fc894ee5ea8e9be7dd7d806075a2f`).
Filled in: the three Job manifests (digest comment and
`KECK_ETCS_IMAGE_DIGEST`), the README image table row (keck-etcs
`6a51d43`). `validate_manifests.py` MANIFESTS OK; `check_docs.py` ALL
CHECKS PASS after one false positive was removed: the 40-character path
`mosfire/20140606/H/redux/Science/spec1d` (with its leading slash) in
`test_backup_products.py` matched the AWS secret-like pattern (mixed case,
digits and slashes, exactly 40 characters), so the assertion now uses
`endswith` on the shorter tail. `check_pypeit_pin.py --image 0.2.10` FAILs
only because the local PypeIt checkout is on `speed_up_arcfit` (138 files
differ from the pin); the image was built from `etc-fixes` at the pin.
Sweep 2 (`sweep2_H.csv`, 2016-01-08) is the user's to launch; the
post-sweep steps are the sweep-1 ones with the 0.2.10 digest and the
`54e68d7` pin.

**Learned.** The secret scan in `check_docs.py` has no notion of paths:
any 40-character run of mixed-case letters, digits and slashes trips it,
and a MOSFIRE night path with a band directory is exactly that length when
the mask-less pattern ends in `spec1d`. Keep long literal paths out of test
assertions, or split them.

**H product, trend, saturation fraction, sky-excess machinery, XTcalc,
validation prepared (same day).**

- `combine_throughput.py --group H --dev` (new flags: one group without
  rewriting the released J files; `--dev` stamps `mosfire-2026.10-dev`,
  the `check_docs.py` convention for a product pending the next release):
  `mosfire_thru_H_2012-2016.ecsv` (8 standards; `excluded_3mad` HIP 17971
  2012-11-28 on the 0.7" slit, HD 111744 2016-01-07, V* V836 Cyg
  2016-05-01) and `mosfire_thru_H_2017-2025.ecsv` (13; excluded HD 74721
  2017-11-05); band medians 0.326 and 0.329 over 14900-17800 A; nodes
  15500/16500/17500 A: 0.336/0.353/0.284 (era 1), 0.336/0.352/0.277 (era 2).
  No H standard after 2025-04, so `compute` uses 2017-2025 there with a
  warning (`test_h_throughput_from_its_era_curves`); the provisional tests
  now cover Y and K only. Milestone 9.8 item 1 met for H (21 standards over
  2 eras, medians inside 0.17-0.54).
- `plot_throughput_trend.py --group H` (figure
  `docs/figures/mosfire_throughput_trend_H.png`): era medians of
  `thru_common` 0.330 and 0.330, MAD 2.4 and 2.5 percent, slopes -2.8 +- 2.5
  and +0.2 +- 0.5 percent per year; zp_mid 19.807 and 19.804; residuals
  against PWV 2.1 sigma (r = +0.46, 21 rows; the H PWV comes from the band
  edges only, `pwv_weak`), airmass 0.7 sigma. The J run is unchanged except
  that the H rows no longer leak into its first block.
- `saturation.frac_pix_nonlinear_1pct` (D62): `snr.saturation_peak`, the
  output schema (required), `docs/wmko_api_note.md`, the generated field
  reference (37 output leaves), design 5.3.11; `test_core_snr` extended.
  The regression comparer treats a new key as a difference, so the four
  fixtures were regenerated with a `CHANGES.md` note (J, J2, line numbers
  unchanged) and `reference_H.json` added (`examples/H_point.json`; on the
  H era curves, no sky excess yet).
- Sky continuum excess (D61): `Instrument.sky_excess(band)` and
  `sky_excess_pattern`, `Band.sky_excess_warn` (H, K),
  `sky.sky_background(..., excess=)`, `compute` adds the curve inside the
  `sky_scale` bracket and warns for H and K without one.
  `scripts/mosfire/measure_sky_excess.py --band H` (new; the K and Y docs
  reuse it): per frame, the raw-frame sky in the 0.7" bars of a long2pos
  mask (or the one long slit), objects masked, the Sun and Moon by
  ephemeris, the night's `pwv_fit`, T_sys from the band's era curve, the
  Gemini model smoothed to the slit's LSF, 10th-percentile floors per
  100 A. Two things learned on the way: (1) a short CDS frame carries an
  electronic pedestal (about -100 e- per pixel in 1.45 s, the same value
  in the closed bars, 13 ADU above the reference pixels in 1.45 s and in
  2.9 s frames alike, so not light), which the script measures per
  spectral row in the closed-bar columns next to each slit and subtracts;
  (2) the inter-line H floor is about 1 Gemini unit (the Maihara
  continuum; the Gemini model's own floor is 0.5), while a 1-5 s standard
  frame measures it with a noise of several units per bin, and a
  percentile of noise is biased low by 1.3 sigma per frame. The shipped
  curve is therefore the floor of the exposure-weighted stack of all
  frames (split-half error), with the D61 per-night statistic kept beside
  it; the standards' frames alone (about 2000 s in 40 columns) cannot
  resolve the floor, so **no H curve is shipped yet**: it comes from the
  validation night's 8 x 179 s science frames through the 1" long slit.
  The trial (`--no-write`) over the 37 local H nights: 20 nights have only
  twilight frames (Sun above -18 deg; 172 frames), 3 have no products
  (20160106, 20160108, 20160530), 20180718 has no slit width for its
  long2pos decker. On the rest, the floor depends on the exposure time:
  the 1.45-s frames sit at -110 units even after the pedestal subtraction
  (their closed bars read -50 e-/s, the slit columns lower still), the
  2.9-s frames at +10 to +15, the 3.6-s at +5, while frames of 7 s and
  longer give 0.1-2.7 units (one Moon-lit night at 8.5). So the
  closed-bar estimate does not remove the pedestal of the shortest
  frames, and the script now skips frames shorter than `--min-texp`
  (default 5 s; `min_exptime_s` in the meta). With the cut, 6 nights
  (20140606, 20160417, 20180109, 20180602, 20241110, 20241226; 50 frames
  of 7.3-24.7 s, 40000 column-seconds, pedestals +2.5 to +5 e-/s) give a
  stacked floor excess of 1.90 +- 1.03 units (measured floor 2.37, model
  0.46; night median 0.87; dark minus Moon-lit +0.78, the 20160417
  outlier is the Moon at 72 deg and 79 % lit): consistent with the
  Maihara continuum of about 1 unit, but the error is as large as the
  signal, which is why the curve waits for the 8 x 179 s science frames.
- `compare_xtcalc.py --band H` (`xtcalc_comparison_H.ecsv`,
  `xtcalc_attribution_H.ecsv` under `external/xtcalc/comparison/`): H,
  flat f_nu, 4 x 120 s MCDS-16, seeing 0.7": ours/XTcalc 0.70-0.72 through
  the 0.7" slit and 0.81-0.86 through 1.0" (J was 0.6-0.8 in S12). The
  attribution at H = 20, 0.7": sky x1.64 (XTcalc's May-2012 MOSFIRE sky is
  brighter than Gemini between the lines, the very excess D61 will add
  back), detector x0.88, extraction x0.83, slit and aperture loss x0.58,
  sampling x1.05. XTcalc's IDL `interpol` extrapolates linearly, and in H
  its efficiency file ends at 1.7991 um inside the band and the
  transmission file short of the band edge, so both are clipped at zero
  now (before, the plain band median was NaN for bright H sources). The J
  tables were regenerated for the check: the XTcalc side is bit-identical
  to the 2026-10-05 tables, the keck-etcs column is 0.5-1.8 % higher
  because the J throughput product was rebuilt since (S22-S24), and the
  regenerated tables replace the old ones under
  `external/xtcalc/comparison/` (the old pair is in the session
  scratchpad only).
- Validation: `validate_j0841.py` takes `--band --date --target
  --standard --frames` (`config()`: science frames from the band's run
  manifest, `sens_<standard>_<date>.fits`, the band window as the D18
  range, slit width and reads from the headers, outputs
  `validation_<target>_*`); the S11 defaults are unchanged.
  `make_night_manifest.py validation --band H` writes
  `nautilus/manifests/nights_validation_H.csv` (2022-01-11, GD153
  LONGSLIT-46x1, `spec2d = 1`, J1532+2237 8 x 179 s in the notes; the
  frames are not on the bucket). The launch recipe (download Job, then a
  night Job) is in `nautilus/README.md` section 7. The reduction, the
  validation run and the sky-excess curve wait for it.
- Checks: pytest 144 passed, 1 skipped (PypeIt checkout on
  `speed_up_arcfit`); `check_docs.py` ALL CHECKS PASS (8 `-dev` products
  pending the next release, 3 provisional placeholders); design 9.8 has an
  "H as built" paragraph; `CHANGES.md` S24b bullets.

**For the user.** Commit; launch sweep 2 (`sweep2_H.csv`) and the H
validation night (`nights_validation_H.csv`, download Job then night Job);
then I sync, verify (0.2.10 digest, pin `54e68d7`), merge, run
`validate_j0841.py --band H ...` and `measure_sky_excess.py --band H`,
regenerate `reference_H.json` (a `CHANGES.md` note) and close prompt 6.
