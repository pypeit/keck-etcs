# Keck MOSFIRE implementation, part 5: time series (Phase 4)

## Goals

Reduce the KOA standard-star nights in batch on Nautilus as Indexed Jobs,
back up the high-level products after each batch, harvest their zero points,
run the throughput trend analysis across the instrument eras, and cut the
first calibration release. Every night also gets its calibration-monitor
table (design 4.9), and the monitor trends join the throughput trends.
These are steps S15 and S16 of the plan (v0.4).
The KOA search (S14) and the in-cluster download Job (S14b) are in their own
prompt doc, `claude_prompts/koa_search_prompts.md`, which must have produced
the candidate table, the night manifests and the first raw frames on S3
before this doc starts.

Run order: after `koa_search_prompts.md` (candidates, manifests, downloads)
and part 2 (the driver, the image, the job templates, the dry run and the
harvest). S15a -> S15b -> S15c -> S16. S15b will span several sessions; one
Indexed Job per batch (by year or by program) and one log entry per batch.
Part 6 step S18 needs S16.

## Context

- Design: `docs/keck_mosfire_design.md` (v0.3), sections 2 (D2-D6, D22,
  D28, D31-D34, D36, D39, N3), 4.1 (selection criteria), 4.2 (workflow and
  S3 layout), 4.4 (per-standard table), 4.5 (per-era combination), 4.6
  (trend analysis), 4.7 (uncertainties), 4.8.4-4.8.7 (jobs, provenance,
  failure handling, gates), 4.8.9 (backup set and timing), 5.5 (calibration
  releases), 7 (definition of done: >= 10 standards over >= 2 eras, and
  item 7, a monitor table for every night), and from v0.4 D40-D47 and 4.9
  (calibration monitor).
- Plan: `docs/keck_mosfire_implementation.md` (v0.3), steps S15 (a, b, c),
  S16 and the risks section.
- Inputs: `keck_etcs/data/mosfire/koa_standards_candidates.ecsv` and
  `nautilus/manifests/nights_<batch>.csv` (from the KOA doc: `night,
  instrument, s3_prefix, standard, slit, spec2d, notes`); raw frames on
  `s3://keck-etcs/mosfire/<YYYYMMDD>/raw/` (KOA doc prompt 2, in-cluster or
  fallback); `scripts/mosfire/reduce_standard.py`, `nautilus/night_job.yaml`,
  `nautilus/gates.py`, `nautilus/night_failures.py`,
  `nautilus/status_table.py`, `scripts/mosfire/harvest_sens.py` (part 2);
  `keck_etcs/calib/{harvest,combine}.py`;
  `keck_etcs/data/pypeit_par/keck_mosfire_J.sens`; the image
  `gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.2.0` or later (rebuilt
  in part 2 prompt 5 after S6, S8 and this doc's S15a code; same PypeIt pin
  `nautilus/pypeit_pin.txt` unless deliberately moved, in which case the
  tag is bumped and the log says so).
- Nautilus: namespace `pypeit`; private bucket `s3://keck-etcs` (every pod
  mounts the credentials secret `KECK_ETCS_S3_SECRET` settled in part 1;
  local pulls use the user's AWS profile through
  `scripts/nautilus/s3_sync.py`); Indexed Jobs with one night per pod,
  `parallelism` from the pilot's measured memory; idempotent pods (skip if
  `run_manifest.json` exists unless `REPLACE=1`); `activeDeadlineSeconds`
  on every Job; sizing from the pilot, not the first pod. Job launches
  beyond the pilot are confirmed with the user first.
- Backup (design D39, 4.8.9): after each batch,
  `scripts/nautilus/backup_products.py` (to be written in S15b; `rclone copy
  nautilus_s3:keck-etcs/ AIOcean:keck-etcs/` with `--include` filters for
  `sens/**`, `harvest/**`, `run_manifest.json`, `run.log`, `redux/*.pypeit`,
  `redux/Science/spec1d_*`, `manifests/**`, `runs/**`, `raw/manifest.ecsv`;
  excludes raw frames, `spec2d_*`, `Calibrations/`, `QA/`; `--dry-run`
  first; idempotent) and `rclone check --one-way` with the same filters.
  Pull `Calibrations/WaveCalib*` locally (S15c) before relying on the
  backup, since it is not in the set.
- A0V standards (decision N3): build the model spectrum by scaling PypeIt's
  Vega spectrum (`vega_tspectool_vacuum.dat`) so that its synthetic 2MASS J
  magnitude equals the star's 2MASS J; implement in
  `keck_etcs/calib/standards.py` and pass it to PypeIt's sensfunc as a
  user-supplied standard (check how `pypeit_sensfunc` / `SensFunc` accepts a
  custom standard spectrum on `develop` at the pin: `pypeit/core/standard.py`
  `get_standard_spectrum(spectral_type=..., V_mag=...)` returns a Vega
  model scaled by V only (read on the local checkout, which differs from the
  pin only in `keck_hires.py`, so this holds at the pin), so a J-scaled
  model needs either a V-equivalent magnitude or a direct hook). PypeIt
  masks Paschen lines automatically.
- Calibration monitor (design 4.9; part 2 prompt 7, S6b): every pod writes
  `harvest/<night>_monitor.ecsv` after the harvest. A monitor failure sets
  `flag = monitor_failed` and never fails a night (D47). The OH line list
  is provisional until the S15a freeze. `harvest_sens.py --merge` builds
  `keck_etcs/data/mosfire/monitor/calib_monitor.ecsv`. If the KOA doc
  downloaded Ne/Ar lamp frames (`lamp_arc` in `raw/manifest.ecsv`), the
  monitor measures them directly. PypeIt still ignores them outside
  `long2pos_specphot`.
- Eras (design D6): 2012-04-04 to 2016-09-15; 2017-02-13 to 2025-02-11;
  2025-04-29 onward.
- Rules (CLAUDE.md): the user runs git; `conda run -n pypeit14`; scripts on
  disk; nothing under `KECK_ETCS_DATA` is committed; no secret value in the
  repo or a log; a calibration release is one commit touching only
  `keck_etcs/data/` and `CHANGES.md` (the user makes the commit); log each
  batch.

## Prompts

1. **S15a: A0V standard support, image rebuild and the pilot batch.** Extend
   `keck_etcs/calib/standards.py` with the Vega + 2MASS J model (N3) and
   classification of a candidate as WD (PypeIt archive) or A0V; extend
   `scripts/mosfire/reduce_standard.py` to read the standard's class and
   2MASS J from the night manifest row, to skip nights without dome flats
   (status `no calibs`), to handle `long2pos` and `long2pos_specphot` masks
   with PypeIt's settings, and to write the status row of design 4.8.6.
   Ask the user to rebuild and push the image (part 2 prompt 5's
   `build_image.sh --push`, tag `0.2.0`; same pin) and record tag, digest
   and pin. Write `nautilus/manifests/nights_pilot.csv` (3-5 wide-slit
   nights, the 2022-04-09 night excluded) and, with the user's go-ahead,
   run it as one Indexed Job (`parallelism` 4, `SPEC2D=0`). Then
   `s3_sync.py pull` the `success` nights' `sens/` and `harvest/`,
   `harvest_sens.py --merge`, and run `nautilus/status_table.py`. Verify:
   every pilot night has exactly one status; each `success` night has a
   `sens_*.fits`, a harvest row and a `run_manifest.json` whose
   `image_digest` and `pypeit_git_sha` match the recorded image; at least
   one A0V sensfunc was built with the J-scaled Vega model and its zero
   point at 1.25 um is within 20 percent of a WD night in the same era (or
   the difference is explained); the per-night wall-clock and peak memory
   are recorded and the `night_job.yaml` header sizing is updated from them.
   Then freeze the monitor lines (design D45, 4.9.4). Run
   `scripts/mosfire/select_monitor_lines.py` on 2022-04-09 plus the
   `success` pilot nights, write the frozen OH list (and Ne/Ar lists, if
   lamp frames exist) into the monitor config with the script output and
   its sha256 as provenance, and drop `lines = provisional`. Ask the user to
   rebuild the image, then re-run the monitor step only (`harvest_sens.py
   monitor`, in a pod or locally on the synced night) for the pilot nights,
   so that every production row uses the frozen list. Verify, in addition:
   - every pilot night has a monitor file;
   - the frozen list meets the five rules, with each line identified on at
     least 80 percent of the nights examined;
   - the per-night dome-flat rates and OH fluxes are listed in the log.

   Risks: PypeIt `develop`'s hook for custom standards; run time; nights
   with the standard at a different slit position than the flats. Log your
   work, with the status table, the frozen line list and the image
   tag/digest/pin.

2. **S15b: remaining batches, sweeps and per-batch backup.** Write
   `scripts/nautilus/backup_products.py` as described in Context (a thin
   wrapper around `rclone copy` and `rclone check --one-way` with the D39
   filters, `--dry-run` by default, `--release TAG` mode for S16, logging
   object counts and bytes). Then, batch by batch (one Indexed Job per
   manifest, `parallelism` from the pilot's memory, launches confirmed with
   the user): apply the Job, follow it, run `nautilus/night_failures.py` to
   write the sweep manifest, apply the sweep Job once, record remaining
   failures with their data reason, run `backup_products.py` for real and
   then `rclone check`, and log the batch (counts per status, wall-clock,
   image tag/digest/pin, backup object count and bytes). Several sessions;
   one log entry per batch. Verify per batch: every night in the manifest
   has exactly one status; no pod ran past `activeDeadlineSeconds`; a failed
   night re-applied via the sweep either succeeds or carries a data reason;
   `rclone check --one-way` reports the backup complete; `git status` shows
   only manifests and the backup script. Log your work.

3. **S15c: sync and harvest merge.** For every `success` night:
   `s3_sync.py pull mosfire/<night>` (sens, harvest, spec1d) and `--calibs`
   for the `WaveCalib*` files (needed by part 2's S13 for more slit widths
   and not in the backup set); then `scripts/mosfire/harvest_sens.py --merge`
   over all synced `harvest/` directories (it also merges the
   `*_monitor.ecsv` files into `calib_monitor.ecsv`); narrow-slit standards get
   `flag = narrow` and keep their `seeing_fwhm_pix` for the slit-loss sample.
   Verify: the number of `success` nights equals the number of new rows in
   `keck_etcs/data/mosfire/throughput/standards.ecsv`; every row has the six
   provenance columns filled; the count of wide-slit rows and their spread
   over eras is reported against the milestone target (>= 10 standards over
   >= 2 eras); every processed night is either a row or a recorded failure;
   every `success` night has monitor rows, and the `monitor_failed` count
   is reported; `git status` shows only the ECSV files. Log your work.

4. **S16: trend analysis, first calibration release and release backup.**
   Implement `keck_etcs/calib/trend.py` (per-era median, MAD, linear slope
   in percent per year with uncertainty, correlations of `zp_1250` with
   airmass, PWV and slit width) and `scripts/mosfire/plot_throughput_trend.py`
   (zero point and band-median throughput versus date with era boundaries;
   figures under `docs/figures/`). Run `combine.py` to write
   `mosfire_thru_<era>.ecsv` for every era with data, apply the 3-MAD
   whole-night exclusion and list the excluded nights, bump `index.yaml` to
   `calib_version = mosfire-J-YYYY.MM`, write the `CHANGES.md` section
   (standards added, era medians before and after, and the image tags,
   digests and PypeIt pins of the reductions used), regenerate the
   regression fixtures deliberately, and update `docs/keck_mosfire_design.md`
   section 4.6 with the results. Then run `backup_products.py --release
   <calib_version>` to copy the D39 set of every contributing night into
   `AIOcean:keck-etcs/releases/<calib_version>/` and `rclone check` it.
   Verify: `compute` with `throughput.date` in each era returns that era's
   curve and `meta.era`; the 2012-2016 era median is within about 10 percent
   of XTcalc's 2012 curve after the 75 vs 72.4 m^2 aperture correction, or
   the discrepancy is discussed; no residual correlation of `zp_1250` with
   airmass at more than 2 sigma; every row entering an era median has a
   non-empty `image_digest` and `pypeit_git_sha` and `CHANGES.md` lists each
   distinct pair; the release backup check passes; the release diff touches
   only `keck_etcs/data/`, `CHANGES.md`, the fixtures and the design doc.

   Monitor trends (design 4.6, D47): extend `trend.py` with per-era
   medians, MADs and 3-MAD flags for every monitor metric, written into
   `calib_monitor.ecsv`'s `flag` column. Write
   `scripts/mosfire/plot_monitor_trends.py` with four figures in
   `docs/figures/`:
   - FWHM against date;
   - the dome-flat rate at each node against date, with era boundaries;
   - line FWHM against slit width, which refits the D25 slope and floor;
   - the OH-flux to Gemini ratio (an empirical `sky_scale`) against date
     and airmass.

   Report the correlation of the dome-flat rate at 12000/12500 A with
   `zp_1250`. Propose to the user, without applying, any change to the LSF
   constants (D25) or to the default `sky_scale` (D14) that these imply.
   Log your work.

## Q&A

### S15a (2026-10-05)

1. **Blocked: the KOA search has not run.** This doc's goals say
   `koa_search_prompts.md` must first produce the candidate table, the
   night manifests and raw frames on S3, but:
   - its Logs section is empty;
   - there is no `keck_etcs/data/mosfire/koa_standards_candidates.ecsv`;
   - `nautilus/manifests/` holds only `nights_dryrun.csv`;
   - `s3://keck-etcs/mosfire/` holds only `20220409/`.

   I did the S15a work that needs no new nights (the A0V model, the driver
   and the sensfunc changes, tests; see the log). The pilot manifest, the
   0.2.0 image, the pilot Job, the status table, the A0V/WD comparison, the
   sizing and the monitor-line freeze all wait for data.

   *Default:* point me next at `koa_search_prompts.md` prompt 1 (census,
   candidates, manifests including `nights_pilot.csv`), then its prompt 2
   (downloads); then resume S15a here at the image rebuild. Rebuilding
   0.2.0 now is possible, since the code is ready, but it can wait until the
   pilot is ready to run.

>A. Use your default

2. **Zero point of the A0V model (N3).**
   - N3 says to scale PypeIt's Vega spectrum so that its *synthetic* 2MASS
     J equals the star's 2MASS J.
   - With PypeIt's `TMASS-J` response and the Cohen et al. (2003) zero
     point, PypeIt's Vega spectrum comes out at J = **+0.024**
     (photon-counting) or +0.013 (energy-weighted), whereas the 2MASS
     system puts Vega at J = −0.001.
   - Following N3 literally (photon-counting) makes every A0V model 2.3
     percent fainter in J, and so every A0V zero point 2.3 percent higher,
     than scaling relative to Vega's −0.001 would.

   The options:
   - (a) photon-counting synthetic, as implemented;
   - (b) energy-weighted (1.2 percent);
   - (c) scale relative to Vega's −0.001, independent of the response
     curve and the zero point.

   *Default:* (a). The A0V-versus-WD cross-tie on pilot nights with both
   classes (D2) measures the offset directly. The value used is recorded in
   every A0V sensfunc's `<NAME>_<DATE>_std_model.json`
   (`vega_tmass_j_synthetic`).

>A. Use your default

3. **Night-manifest columns for A0V nights.**
   - The driver and `build_sensfunc.py` read four extra columns:
     `std_class`, `jmag_2mass`, `std_ra` and `std_dec` (degrees). The night
     job already exports every column as an environment variable, so
     `night_job.yaml` is unchanged.
   - The KOA doc allows "extra columns the reduction driver reads", so
     `make_night_manifest.py` (KOA prompt 1) should write them. Rows for
     white dwarfs can leave them empty.

   *Default:* as described, unless you prefer them packed into `notes`.

>A. Use your default

4. **(2026-10-07) The shipped 2017-2025 curve is now out of date; one test
   fails.** `harvest_sens.py --merge` added four 2017-2025 rows to
   `standards.ecsv` (HD133772 2017-06-15, Feige110 2024-07-21, GD153
   2024-12-30 and 2025-07-23). `test_shipped_era_file_provenance_matches_its_rows`
   requires `mosfire_thru_2017-2025.ecsv` to be built from exactly the
   era's non-excluded rows, so it fails until the curve is rebuilt
   (`combine.py`, an S16 step). Two rows should not enter any era curve
   as they stand:
   - HD133772 (A0V, 2017-06-15) is saturated: 99.9th-percentile raw counts
     of about 40k ADU against the 26k linearity limit
     (`scripts/mosfire/check_std_peaks.py`), so its zero point is 0.35 mag
     too faint.
   - The J-filter long2pos Feige110 nights give a median throughput of
     about 0.24 against about 0.18 for the J2 LONGSLIT nights. The filters
     account for only 8 percent of that (median transmission 0.93 against
     0.86), so about 25 percent is not yet understood.

   The options:
   - (a) flag the HD133772 row `excluded_nonlinear`, and teach the harvest
     to flag any standard above the linearity limit; leave the era curve
     and the failing test for S16, which rebuilds the curve once batch 1
     adds more J and J2 standards;
   - (b) as (a), and also rebuild `mosfire_thru_2017-2025.ecsv` now, with
     LDS749B + GD153 x2 + Feige110 2024, so the tests pass;
   - (c) take the four new rows out of `standards.ecsv` again until S16.

   *Default:* (a). The curve the ETC ships stays the one validated in S10,
   and the failing test documents the pending rebuild.
   >A. Use your default

### S15b (2026-10-05)

1. **May I run the first real backup now?**
   - `backup_products.py` is written and dry-run tested. The bucket's
     backup set today is the 2022-04-09 night only: 60 objects, 6.4 MB.
   - A real run would create `AIOcean:keck-etcs/` on the shared Google
     Drive, copy those files, and then confirm them with
     `rclone check --one-way`. That verifies the copy-and-check path end to
     end before any batch depends on it.

   *Default:* yes, run it once now (`--run`), then after every S15b batch
   as the prompt says.
>A. Yes, go ahead

2. **The batches are blocked on the KOA search, as in S15a-1.** You chose
   the default there: `koa_search_prompts.md` prompts 1-2 come first. S15b's
   batch loop (apply the Job, follow it, sweep, back up, log) starts once
   there are manifests and raw frames, and after the S15a pilot.

   *Default:* point me next at `koa_search_prompts.md` prompt 1.

### S16 (2026-10-08)

1. **Which part of each standard's curve enters the era curves?** S16
   found two systematics blueward of about 11900 A
   (`scripts/mosfire/compare_filter_pair.py` and the per-row values in the
   log):
   - **The J filter's cut-on.** The same white dwarf through J is below
     its J2 curve by 10 percent at 11650 A, 3 percent at 11800 A and 0 at
     12000 A, so the tabulated J transmission on its edge (11530-11800 A)
     is too high. A slightly shifted cold-filter edge would do this.
   - **A depression of every A0V curve blueward of about 11900 A:** 0.10-0.13
     at 11600 A, against 0.14-0.17 for white dwarfs in the same filter and
     0.18-0.19 in J2. They agree at 12000 A. Suspects: the Vega model, or
     the telluric fit in the 1.13-1.16 um water band (all A0V rows are
     `pwv_extrapolated`).

   With the S10 rule (each row's half-power band), 8 of the 9 rows of
   2017-2025 are J and mostly A0V, and the curve at 11600 A falls to 0.138,
   against 0.186 shipped now and 0.187 from the independent J2-only 2025
   era. The options:
   - (a) keep the S10 rule (half-power band for every row);
   - (b) J rows only where the J transmission is >= 0.9 of its peak (from
     about 11620 A); J2 rows keep the half-power band; A0V rows only
     redward of 11900 A. 2017-2025 then gives 0.186 at 11600 A and 0.204
     at 11700 A, against 0.205 for the 2025 J2-only era;
   - (c) as (b), and also the J2 rows only where T >= 0.9 of peak. This
     loses 11170-11550 A, which the J2 band of the ETC needs.

   *Default:* (b), with the cuts in `combine.py` as constants, the reason
   in its docstring, and both systematics listed in `CHANGES.md` and design
   4.6. The 3-MAD exclusion already compares nights over 11900-12450 A
   (done), which then excludes 55 Dra (2014-10-05) and HD65158
   (2020-11-26).
>A. Ok, use (b)

2. **A remaining J/J2 offset of about 5 percent in 11900-12450 A.**
   - In 2017-2025 the J2 nights' filter-free throughput is 0.262-0.285,
     the J nights' 0.247-0.272 (GD153: 0.248 in J, 0.262 in J2 the next
     night). The filter curves agree with the measured J2/J ratio to
     3-9 percent.
   - The era curves take the pixel-wise median of both, so the offset adds
     about 2-3 percent of scatter, not a bias.

   *Default:* accept it for this release and list it in `CHANGES.md` as a
   known systematic. Measuring the cold filter curves (or fitting an edge
   shift to J/J2 pairs of the same star) is a follow-up.
   >A. Use your default

3. **Proposals from the monitor trends (design 4.6; not applied).**
   - **D25 (LSF):** the line FWHM at 12500 A is 3.56-3.61 pix in a 1"
     slit (4 nights) and 2.63 pix in 0.7" (1 night). The current
     `max(slit / 0.277, 2.2)` is +0.5 percent at 1" and -3.8 percent at
     0.7". Proposed: `FWHM = sqrt((slit / 0.292)^2 + 1.08^2)` pix, which
     fits both (only two slit widths so far).
   - **D14 (`sky_scale`):** OH lines over the Gemini model, science-slit
     frames, per night: 0.91, 0.77, 0.86, 0.43 (median 0.82; OH varies
     from night to night by 2x). The continuum between lines is not
     monitored (S11: x1.14-1.33). Proposed: keep `SKY_SCALE_DEFAULT = 1.0`
     until lines and continuum can have separate scales; document 0.8
     (0.4-0.9) as the typical OH-line level.

   *Default:* apply the D25 refit with the release (it changes the ETC's
   LSF by less than 4 percent at >= 0.7", and the regression fixtures are
   regenerated anyway); leave D14 as is.
>A. Use your default

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-10-05 (Prompt #1 / S15a, part 1: A0V standards and driver changes; pilot BLOCKED on the KOA search)

**Prerequisite check:**

- `koa_search_prompts.md` has not run (empty Logs).
- There is no candidate table, only `nights_dryrun.csv` in
  `nautilus/manifests/`, and `s3_sync.py ls mosfire/` shows only
  `20220409/` (162 objects).
- So the pilot batch, the 0.2.0 image, the status table, the A0V/WD
  zero-point comparison, the sizing and the monitor-line freeze cannot run
  yet (Q&A S15a-1).
- I did the code part of S15a, which needs no new nights, and tested it on
  2022-04-09.

**`keck_etcs/calib/standards.py`** (new; PypeIt imported inside functions):

- **N3 model:** PypeIt's `vega_tspectool_vacuum.dat` scaled so that its
  synthetic 2MASS J equals the star's.
  - Synthetic J is photon-counting with PypeIt's `TMASS-J` response
    (`flux_calib.load_filter_file`) and the Cohen et al. (2003) zero point
    3.129e-10 erg/s/cm^2/A.
- **The PypeIt hook needs no PypeIt change.** `[sensfunc] star_type = A0`
  and `star_mag = V` give `VegaStandard(V)` = Vega x 10^(0.4 (0.03 − V)), so
  the J-scaled model is exactly PypeIt's model at
  **V_eq = 0.03 + J − J_synth(Vega) = J + 0.0058**.
  - Verified to 1e-10 against `VegaStandard` flux.
  - `write_sens_par` inserts the two lines under `[sensfunc]`.
- **Vega's synthetic J is +0.024** (photon) or +0.013 (energy), against the
  2MASS system's −0.001, a 2.3% systematic on A0V zero points.
  Documented, recorded per sensfunc, and put to the user (Q&A S15a-2).
- `classify(ra, dec, sptype, std_class)` returns `archive` (PypeIt has the
  spectrum; LDS749B → calspec), `A0V` or `unknown`. A measured archive
  spectrum beats a manifest's A0V label.

**`scripts/mosfire/build_sensfunc.py`:**

- `--std-class` and `--jmag` (defaults `$STD_CLASS`, `$JMAG_2MASS`). For
  A0V it writes `sens/<NAME>_<DATE>_A0V.sens` (base `.sens` plus `star_type
  = A0`, `star_mag = V_eq`) and `sens/<NAME>_<DATE>_std_model.json`.
- An A0V night without J fails with exit 1, so the job records `sens
  failed`.

**`keck_etcs/calib/harvest.py`, a bug found by the hook check:**

- PypeIt records `std_cal = std_name = None` (and no coordinates) for a
  model standard, so `std_class_of` would have labelled every A0V row
  **WD**.
- Now `std_class_of(std_cal, model)` returns A0V when `build_sensfunc.py`'s
  model record exists (`std_model_record`) or `std_cal` names Vega, WD for
  an archive file, and **unknown** (never WD) otherwise.
- `std_model` reads `vega_tspectool_vacuum.dat J=… (V_eq …)` for A0V rows.

**`scripts/mosfire/reduce_standard.py`:**

- Standard record from `--std-class/--std-name/--std-ra/--std-dec/--jmag`
  (defaults `$STD_CLASS`, `$STANDARD`, `$STD_RA`, `$STD_DEC`,
  `$JMAG_2MASS`, which the night job exports from manifest columns
  automatically), written to `run_manifest.json['standard']`. An A0V night
  without coordinates or J fails as `setup failed`.
- Frame typing:
  - frames within 60" of an A0V position are `standard`;
  - **Ne/Ar lamp frames** (`PWSTATA7/8 == 1`, PypeIt's `arclamp`) were
    being typed `lampoffflats`, a latent bug for any night whose lamp arcs
    are downloaded for the monitor. They are now `arc,tilt` on
    `long2pos_specphot` nights and dropped from the PypeIt file otherwise
    (kept in `raw/` for the monitor).
- **long2pos / long2pos_specphot:** nod pairing from PypeIt's
  `keck_mosfire.get_comb_group` (B–A pairs; for specphot the narrow-slit
  frame is the background of the wide one) instead of our A/B time-order
  pairing. Untested on a real long2pos night until the pilot.
- The "no calibs" skip (no lamp-on flats) already existed. Design 4.8.6's
  status row is already written by the night job (`status_row.py`) on
  every outcome; it now also records the optional columns `std_class`,
  `jmag_2mass`, `std_ra` and `std_dec`.
- **Regression:** `--setup-only` on 2022-04-09 (scratch, linked raw) gives
  a PypeIt data table **identical** to the pod's; the standard record is
  `archive`.

**`scripts/mosfire/check_a0v_sensfunc_hook.py`** (mechanics; LDS749B treated
as an A0V, outputs in `<night>/a0v_hook_check/`):

- `pypeit_sensfunc` accepts the A0V `.sens`.
- The zero point rises by +1.0017 mag for +1 mag in J (the IR telluric
  refit makes it 0.17% non-linear).
- With the model record the class is A0V; without it, unknown → **PASS**.

**Other:**

- `nautilus/Dockerfile` import guard: + `keck_etcs.calib.standards`.
- `keck_etcs/tests/test_standards.py` (7 tests):
  - Vega's J and the model round trip; the model = PypeIt's
    `VegaStandard` at V_eq (1e-10);
  - classification, the `.sens` insertion and the harvest classes;
  - the driver's typing (lamp arc, flat, A0V within 60" and beyond,
    archive);
  - long2pos pairing through PypeIt (`bkg_id` [2, 1, 4, 3]).
- Suite: **95 passed**, 3 slow deselected.

**Still to do in S15a, once the KOA doc has produced data:**

1. `nights_pilot.csv` (3-5 public wide-slit nights with flats; not
   2022-04-09; with the A0V columns).
2. The user rebuilds and pushes `0.2.0` (same pin 8017f47). This also
   brings S8's filter curves and the harvest's default filter into the
   pods.
3. The pilot Job (`parallelism` 4, `SPEC2D=0`), with the go-ahead.
4. Pull, merge, `status_table.py`.
5. The A0V/WD zero-point comparison.
6. Wall-clock and memory into the `night_job.yaml` header.
7. `select_monitor_lines.py` on 2022-04-09 plus the pilot → freeze →
   rebuild → monitor re-run.

**Questions:** Q&A S15a-1 (the KOA doc must run first), S15a-2 (the Vega
zero point of the A0V model), S15a-3 (the A0V manifest columns).

### 2026-10-05 (Prompt #2 / S15b, part 1: backup script and sweep fix; batches BLOCKED on the KOA search)

**Q&A read:** the user chose the defaults for S15a-1 (the KOA doc first),
S15a-2 (photon-counting synthetic J for the A0V model) and S15a-3 (extra
manifest columns). No code change was needed for 2 and 3; they are what
S15a implemented.

**Blocked:** there are still no batch manifests and no raw frames beyond
2022-04-09, and the S15a pilot has not run. So no Job, no sweep, no
per-batch backup and no batch log entry. I did the parts of S15b that need
no new nights.

**`scripts/nautilus/backup_products.py`** (new):

- A thin wrapper around `rclone copy nautilus_s3:keck-etcs/
  AIOcean:keck-etcs/` and `rclone check --one-way`, with one filter set
  (written to a temporary `--filter-from` file).
  - Included, per night: `sens/**`, `harvest/**`, `run_manifest.json`,
    `run.log`, `redux/*.pypeit`, `redux/Science/spec1d_*` and
    `raw/manifest.ecsv`; at the root, `manifests/**` and `runs/**`.
  - Everything else is excluded.
- `sens/**` follows the prompt's Context, a superset of design 4.8.9's
  `sens/sens_*.fits` plus QA. It also keeps the A0V `.sens` and
  `*_std_model.json` (S15a), which the harvest needs to classify an A0V
  row.
- Modes:
  - dry run (default): `rclone size` objects and bytes, plus the count a
    copy would transfer;
  - `--run`: copy, then check, counting =, −, * and ! from `--combined`;
  - `--prefix mosfire/<night> …`: per-batch subsets;
  - `--release TAG [--nights …]`: copy to `releases/TAG/`; the nights
    default to the non-excluded rows of `standards.ecsv` (S16);
  - `--check-only`.
- Each run writes a JSON summary to `$KECK_ETCS_DATA/runs/backup/` (local)
  and prints the line for the log. No credentials are printed: the rclone
  remotes hold them.
- **Tested (dry runs only):**
  - whole set: 60 objects, 6.4 MB, 60 to copy, `AIOcean:keck-etcs/` absent;
  - release dry run: picks night 20220409 from `standards.ecsv`;
  - filter audit (`rclone lsf` with the rules): 60 of the bucket's 163
    objects (40 `sens`, 3 `harvest`, 12 spec1d `.fits`/`.txt`, the
    `.pypeit`, `run.log`, `run_manifest.json`, `raw/manifest.ecsv`, 1
    `runs` status row), and 0 spec2d, raw FITS, `Calibrations/` or `QA/`.
- **No real copy yet:** it writes to the shared Drive, so I asked first
  (Q&A S15b-1).

**`nautilus/night_failures.py`, a gap fixed:**

- The sweep manifest kept only the 7 design columns, so an A0V night
  swept after a failure would lose `std_class`, `jmag_2mass`, `std_ra` and
  `std_dec`, and fail again as `setup failed`.
- It now adds those columns when any status row carries them (which
  `status_row.py` records since S15a), empty where a row lacks them.
- `keck_etcs/tests/test_night_failures.py`: one A0V row and one older row
  without the columns; the sweep keeps the A0V values and leaves the white
  dwarf's empty.
- Suite: **96 passed**, 3 slow deselected.

**Incident:**

- While checking which rclone remotes exist, an `awk` filter on
  `rclone.conf` matched "type" inside `token_type` and printed the OAuth
  tokens of the three Google Drive remotes (GDrive, AIOcean, RoB) into the
  session transcript. Nothing was written to any file, log or repo.
- The access tokens shown had expired; the refresh tokens are long-lived.
  I told the user and suggested `rclone config reconnect <remote>:` if they
  want them rotated.
- Lesson: list remotes with `rclone listremotes` and types with
  `rclone config show <remote> | grep '^type'`, never by grepping the
  config file.

**Verify (S15b):** `git status` shows the backup script, the
`night_failures.py` fix, its test and this doc; no manifests yet. The other
per-batch checks wait for batches.

**Next:** `koa_search_prompts.md` prompt 1 (Q&A S15b-2), then its prompt 2,
then S15a's pilot, then S15b's batches.

### 2026-10-05 (S15b: first real backup, approved in Q&A S15b-1)

- `python scripts/nautilus/backup_products.py --run` copied the bucket's
  backup set (night 20220409: 60 objects, 6.4 MB) to the new
  `AIOcean:keck-etcs/`.
- `rclone check --one-way`: 60 match, 0 missing, 0 differ, 0 errors
  (COMPLETE).
- A dry run afterwards would transfer 0 files (idempotent).
- Summaries are in `$KECK_ETCS_DATA/runs/backup/`.
- Also this session (KOA doc prompt 2): the KOA probe passed, and the
  batch-1 download manifest (19 reducible nights) and Job are ready, waiting
  for image 0.2.0 and the user's go-ahead. Pilot changes (20250722 →
  20250723, 20131225 → 20140601) are explained in `koa_search_prompts.md`.

### 2026-10-07 (Prompt #1 / S15a, part 2: pilot batch, three PypeIt/driver fixes, monitor-line freeze)

**Result:** all five pilot nights are `success` with passed gates, verified
against their manifests; the J2 OH monitor lines are frozen. It took four
images (0.2.1 to 0.2.3) and three rounds of fixes.

**Images** (registry `gitlab-registry.nrp-nautilus.io/profx/keck-etcs`):

| Tag | Digest | keck-etcs | PypeIt pin (`etc-fixes`) | Change |
|---|---|---|---|---|
| 0.2.1 | sha256:1a8e8291...1cce3 | 31488fa | 8017f47 | first pilot run |
| 0.2.2 | sha256:920bd25f80483fe1c47ae70605bbd299229e6ecb593ca29f31fe5ebdfd746138 | 09e9eee | fb47905 | long2pos bars, OH-arc cap, align-box fix, frozen lines |
| 0.2.3 | sha256:99cc0d6379326b165270eba073a8b12ac716d71965a406781fe8a9293da42adf | fdfb1d7 | fb6fb62 | 4" bar wavelength transfer, object filter |

**Status table** (`nautilus/status_table.py`; one status per night; products
checked by the new `nautilus/verify_nights.py`, ALL OK):

| Night | Standard | Mask, filter | Image | Gates | Wall [s] | Peak [GiB] | Median thru | zp_1250 |
|---|---|---|---|---|---|---|---|---|
| 20140601 | Feige110 | long2pos_specphot (align), J | 0.2.3 | PASS | 2617 | 11.74 | 0.248 | 19.76 |
| 20170615 | HD133772 (A0V) | long2pos_specphot, J | 0.2.3 | PASS | 587 | 7.74 | 0.172 | 19.42 |
| 20240721 | Feige110 | long2pos_specphot, J | 0.2.3 | PASS | 330 | 7.63 | 0.233 | 19.77 |
| 20241230 | GD153 | LONGSLIT-46x5, J2 | 0.2.3 | PASS | 1702 | 8.68 | 0.176 | 18.46 |
| 20250723 | GD153 | LONGSLIT-46x5, J2 | 0.2.2 | PASS | 4819 | 11.22 | 0.181 | 18.50 |

20250723 stays on 0.2.2: pin fb47905 lacks only the long2pos transfer, which
does not apply to a LONGSLIT night. Every `run_manifest.json` carries its
image digest and `pypeit_git_sha` equal to the pin of that image.

**What failed, and the fixes** (in order):

1. *Pilot on 0.2.1: the three long2pos nights failed `no trace`, and the two
   GD153 nights were killed.*
   - Each long2pos_specphot position is three CSU bars, 0.7" | 4.0" | 0.7"
     (`Mechanical_Slit_List`); the star sits in the 4.0" bar in some dither
     positions (2017: YOFFSET 0; 2014 align mask: +-14").
   - PypeIt's mask-design matching merged or dropped the bars (2017-06-15
     kept one two-bar slit; 2024-07-21's kept slit was fully masked).
   - Fix in `reduce_standard.py`: `use_maskdesign = False` (one slit per
     bar); the 4.0" bars from the mask table, checked against the arc line
     widths; only frames whose brightest object is in a 4.0" bar count
     (`specphot_use`), so `no trace` means no such frame.
   - The Job's global `backoffLimit: 4` was used up by the long2pos
     retries and the Job then deleted the healthy GD153 pods. Fix in
     `night_job.yaml`: `backoffLimitPerIndex: 1` and a `podFailurePolicy`
     (data outcomes exit 2 -> FailIndex, not retried; evictions ignored).
2. *20250723 was OOM-killed at 16 GiB three times.* All 36 science frames
   were typed as OH arcs and combined into one arc image. Fix: at most
   `MAX_OH_ARCS = 16` arc frames (longest, then nearest the standard); the
   rest are `science` only. Locally the night then peaked at 8.4 GB.
3. *20241230 failed `wave_rms` (0.85 px).* Its science frames are on
   `LONGSLIT-46x1 (align)`, whose bar 23 is a 4" alignment box in the
   middle of the slit; PypeIt extracted the arc there, where the OH lines
   are 16 px wide instead of 4. **PypeIt fix (fb47905):**
   `Spectrograph.get_arc_extract_center` gets the arc frames, and MOSFIRE
   moves the extraction to the adjacent bar
   (`KeckMOSFIRESpectrograph.alignment_box_rows`). Result: cc 0.52 -> 0.88,
   RMS 0.85 -> 0.13 px.
4. *20240721 and 20140601 failed `wave_rms` in the 4.0" bars (0.7-1.5 px).*
   Flat-topped 22-px arc lines defeat `full_template`. **PypeIt fix
   (fb6fb62):** a new `Spectrograph.transfer_wavecal` hook; MOSFIRE refits
   the identified lines of the two 0.7" neighbours, moved by their
   cross-correlation shifts (1.5-3.6 px, cc 0.90-0.93). RMS 0.05-0.11 px.
   The posB 4" bar has no neighbours, so `specphot_use` also requires a
   wavelength RMS below 0.5 px (`SPECPHOT_RMS_PIX`).
5. *20140601 frame 0357 counted as a wide-bar frame* because of a bogus
   12-px "object". Fix: objects with FWHM outside 0.5-2x the night's median
   are not candidates.
6. *Gates:* the spec1d gate now requires objects only in standard frames
   (faint validation targets may have none); the long2pos wave gate checks
   the used 4" bars against 0.5 px.
7. *`build_sensfunc.py`:* frames of different exposure times are no longer
   refused; the exposure time with the largest total is coadded
   (20140601: 11.6 and 21.8 s). A single frame's sensfunc is the night's.
8. *Stale products on the bucket* (found by `verify_nights.py`): a night
   whose earlier run failed kept that run's same-size `sens`/`WaveCalib`
   objects, because the success path pushed without `--force` and
   `s3_sync` skips equal sizes. Fix: products are always force-pushed.
   20240721, 20140601, 20241230 (and 20170615, to move it to 0.2.3) were
   rerun with `REPLACE=1`. Two harmless leftovers remain on S3, not in any
   manifest: `sens_Feige110_20240721_0089.fits`,
   `sens_Feige110_20140601_0357.fits`.

**A0V check (D2): failed, difference explained.** HD133772's zero point at
1.25 um is 0.35 mag (38 percent) fainter than Feige110's in the same era and
filter. The A0V frames are saturated: 99.9th-percentile raw counts of
39.9k-40.1k ADU (peak 41.5k) against the 26k linearity limit, where every
WD frame is below 6k (`scripts/mosfire/check_std_peaks.py`). The A0V sensfunc
was built with the J-scaled Vega model (V_eq 7.248 from J = 7.242,
`HD133772_20170615_std_model.json`), but this star at 8.7 s cannot test it.

**Open: J against J2.** The J-filter Feige110 nights give about 0.24, the
J2 LONGSLIT nights about 0.18 (LDS749B 2022 included: 0.180). The archive
spectra agree with CALSPEC to 2-3 percent in J
(`scripts/mosfire/compare_std_spectra.py`); read mode and exposure time are
not the cause; the filters explain 8 percent. Batch 1 adds both kinds. The
merge makes the shipped 2017-2025 curve stale and one test fails; Q&A
S15a-4 asks how to proceed.

**Monitor-line freeze** (`select_monitor_lines.py 20220409 20241230 20250723
--band J2`, the three J2 OH nights; the long2pos nights have no OH frames):

- 74 candidate lines; 15 pass rules 1, 2 and 4, all identified on 3/3
  nights; rule 3 passes (raw p99.9 5.6k ADU).
- Frozen (one per sub-window, one window empty): **11591.847, 11788.495,
  12229.206, 12287.158 A**, the same as the provisional list.
- Written to `keck_etcs/data/mosfire/monitor/monitor_lines_J2.ecsv`
  (sha256 faedee86e3d2cd9eab6cac04f84ff0ba1b950a7868c8579048146eddc5e332d3,
  in `index.yaml`); `MONITOR['monitor_lines_status'] = 'frozen'`.
- The J band and the Ne/Ar lists are not frozen: no J long-slit night yet.
- The freeze went into 0.2.2, so every pilot monitor file already uses the
  frozen list: no `lines=provisional` flag and no `monitor_failed` row in
  any of them. No separate monitor rerun was needed.

**Dome-flat rates** (`flat_rate_per_arcsec`, e-/s/pix/arcsec, median over
frames, at 11250 11500 11750 12000 12250 12500 A):

- 20220409 (FPOWER 9.0): 877 1431 1988 2493 2854 951
- 20241230 (FPOWER 13.5): 3672 5892 8003 10131 11647 3851
- 20250723 (FPOWER 4.0): 937 1517 2080 2600 2958 986
- 20140601, 20170615, 20240721: flagged `nonlinear` (long2pos flats peak at
  36.8-41.1k ADU in the 4" bars), no rate.

The rates follow the lamp power, so their trend (S16) needs a normalisation
by `FPOWER`.

**OH fluxes** (`line_flux`, e-/s/arcsec^2, median over frames, at the frozen
lines 11591.8 11788.5 12229.2 12287.2 A):

- 20220409: 345 93 600 711
- 20241230: 369 92 654 765
- 20250723: 219 40 444 486

**Merge:** `harvest_sens.py --merge` added five rows to
`keck_etcs/data/mosfire/throughput/standards.ecsv` (six in all) with their
curves, and 1385 rows to `calib_monitor.ecsv`. For long2pos nights the
row's KOA-ID list names every standard frame, not only the 4" frames used,
and `slit_width` is empty; both are follow-ups.

**Sizing:** `night_job.yaml`'s header has the table above. Memory 16 Gi
stays; CPU could drop to 2; parallelism 4 suits batch 1.

**What I learned about the repository:**

- The night job's YAML script is not in the image, so a job fix needs no
  rebuild; driver or PypeIt fixes do.
- PypeIt's MOSFIRE support assumes `use_maskdesign` for long2pos, which
  does not work for `long2pos_specphot`; the bar geometry comes from the raw
  frames' `Mechanical_Slit_List` and `Alignment_Slit_List` extensions, and
  bar 1 is at the top of the detector (`find_longslit_pos` geometry).
- `conda run` does not forward stdin: edit scripts written to a heredoc
  and piped to `conda run python -` never ran (my error early in this
  session; caught when `git status` showed a clean tree).

### 2026-10-07 (S15a follow-up: Q&A S15a-4 answered (a), nonlinear standards flagged at harvest)

- `keck_etcs/calib/harvest.py`: new `standard_peak_adu(manifest, files,
  raw_dir)`, the largest 99.9th-percentile raw count in a 15-pixel band
  around the standard's trace, over the frames the sensfunc used
  (`specphot_use` on long2pos_specphot nights). `harvest()` adds
  `excluded_nonlinear` to the row's `flag` when it exceeds
  `NONLINEAR_ADU` (26k ADU); `combine.py` already skips `excluded` rows.
  A unit test is in `keck_etcs/tests/test_harvest.py`.
- The five pilot nights were re-harvested locally (rows keep the pod's
  image provenance, from `run_manifest.json`) and re-merged. Only
  HD133772 2017-06-15 is flagged
  (`pwv_extrapolated,excluded_nonlinear`); no zero point changed.
- Lesson: a local harvest needs `raw/manifest.ecsv` (KOA IDs, read mode)
  or every standard frame's header in `raw/`; pull the manifest first.
- As agreed, `mosfire_thru_2017-2025.ecsv` is not rebuilt, and
  `test_shipped_era_file_provenance_matches_its_rows` fails until S16
  rebuilds the era curves; 103 other tests pass.
- The in-pod harvest gets the flag with the next image (0.2.4), which batch
  1 (S15b) should use.

### 2026-10-08 (Prompt #2 / S15b, batch 1: 19/19 nights success after one sweep; two more fixes; backup complete)

**Batch 1** (`nautilus/manifests/nights_batch1.csv`, 19 reducible wide-slit
nights; Job `keck-etcs-nights`, image 0.2.4, parallelism 4, launched by the
user 2026-10-07):

- 4 new success (20141005, 20160417, 20241229, 20250125); 5 skipped (the
  pilot nights, already success); 9 `no trace` and 1 `reduce failed`, all
  long2pos_specphot.
- **`no trace` (9 nights):** on these nights the flats show no gap between
  the three bars of a position, so `use_maskdesign = False` traced 3 slits
  (about 127 pixels each) for 7 bars and the 4.0" bars could not be told
  apart. Raising the edge sensitivity does not help (`edge_thresh` 50 to 5
  on 2015-09-04: still 3 slits).
  Fix (`reduce_standard.py`, `split_merged_bars`): a pre-pass runs
  `pypeit_trace_edges`. If there are fewer slits than mask bars, each slit
  holding k bars (width plus one bar gap over the CSU pitch, 44 px) is
  replaced through PypeIt's `rm_slits`/`add_slits` by k equal bars; the
  record goes in `run_manifest.json` (`specphot_bar_split`). Tested locally
  on 2015-09-04: 7 slits, 4" bars RMS 0.06/0.04 px, gates PASS.
- **`reduce failed` (20150428):** the KOA target `HIP85871/7.25` became part
  of PypeIt's output file name, and the `/` made it a missing directory.
  **PypeIt fix (bc18a3b):** `outputfiles.construct_basename` replaces `/` and
  `\` in the target name by `-`; a test is in `test_outputfiles.py`.
- Image **0.2.5**: digest
  sha256:69591fcbdb595ca0b24438f9b4cf803d0ad48dedbe36141a8d211e3b3a4daed4,
  keck-etcs 10a469f, PypeIt pin bc18a3b.
- **Sweep:** `night_failures.py keck-etcs-nights` first also listed
  20240721 and 20140601, from the pilot's stale `gate failed` rows under the
  same Job name. Fixed: only each night's latest status row counts. The
  sweep (`sweep_batch1.csv`, 10 nights, Job `keck-etcs-nights-sweep1`, image
  0.2.5): **10/10 success, gates PASS**; every night needed the bar split.

**Verify:**

- Every batch-1 night has exactly one latest status: **19 success** (14 new,
  5 pilot). No data failures remain.
- `verify_nights.py` on the 14 new nights: ALL OK (products match their
  sha256; images 0.2.4/0.2.5 with their pins).
- No pod near `activeDeadlineSeconds` (21600 s): the longest night is
  4819 s (20250723).
- Peak memory 6.1-13.6 GiB (13.55 GiB on 20211027, 85 percent of the
  16 Gi limit; watch it).
- Backup (`backup_products.py --run`): 1010 files copied; `rclone check
  --one-way`: 1070 match, 0 missing, 0 differ, 0 errors, COMPLETE (177.7 MB;
  summary `runs/backup/backup_20261008T141541Z_run.json`).
- `git status`: besides the manifests (`sweep_batch1.csv`) it shows code
  fixes (`reduce_standard.py`, `night_failures.py`), the merged tables and
  this doc. The fixes are part of this batch.

**Status table** (`status_table.py`; image, PypeIt sha, wall-clock s, peak GiB):

| Night | Image | PypeIt | Wall | Peak |
|---|---|---|---|---|
| 20140601 | 0.2.3 | fb6fb62 | 2617 | 11.74 |
| 20141005 | 0.2.4 | fb6fb62 | 636 | 9.41 |
| 20141123 | 0.2.5 | bc18a3b | 332 | 6.76 |
| 20150428 | 0.2.5 | bc18a3b | 761 | 6.64 |
| 20150904 | 0.2.5 | bc18a3b | 416 | 6.75 |
| 20151022 | 0.2.5 | bc18a3b | 1399 | 6.76 |
| 20160417 | 0.2.4 | fb6fb62 | 1182 | 7.79 |
| 20170615 | 0.2.3 | fb6fb62 | 587 | 7.74 |
| 20171105 | 0.2.5 | bc18a3b | 321 | 7.71 |
| 20171106 | 0.2.5 | bc18a3b | 607 | 7.78 |
| 20201126 | 0.2.5 | bc18a3b | 403 | 7.69 |
| 20210928 | 0.2.5 | bc18a3b | 680 | 7.87 |
| 20210930 | 0.2.5 | bc18a3b | 402 | 7.68 |
| 20211027 | 0.2.5 | bc18a3b | 464 | 13.55 |
| 20240721 | 0.2.3 | fb6fb62 | 330 | 7.63 |
| 20241229 | 0.2.4 | fb6fb62 | 1052 | 6.06 |
| 20241230 | 0.2.3 | fb6fb62 | 1702 | 8.68 |
| 20250125 | 0.2.4 | fb6fb62 | 2212 | 8.81 |
| 20250723 | 0.2.2 | fb47905 | 4819 | 11.22 |

**Science notes** (from the merged `standards.ecsv`, 20 rows; for S16):

- **The A0V model works.** The 9 unsaturated A0V nights in J give zp_1250
  19.77-19.83 mag, against 19.76/19.77 (Feige110) and 19.90 (GD153) for the
  WDs in J. So the S15a A0V/WD check is met once saturated nights are
  excluded.
- `excluded_nonlinear` (harvest flag, 26k ADU) marks 4 nights: 20150428,
  20160417, 20170615, 20210928 (zp 19.28-19.50, except 20150428 at 19.82).
- **Not flagged but low:** 55 Dra (20141005, J = 6.2, 1.45 s frames) at
  19.52. Possibly nonlinearity below 26k ADU, or the timing of the minimum
  exposure; to look at in S16.
- **J against J2 is a filter effect:** GD153 on consecutive nights gives
  median throughput 0.224 in J (2024-12-29) and 0.176 in J2 (2024-12-30),
  same star and slit. The J2 filter curve divided out at harvest (or J2's
  real throughput) is the place to look; the curves' median transmissions
  (0.93 against 0.86) explain only 8 of the 27 percent.
- Most J-filter rows carry `pwv_extrapolated`: the PWV fit runs to the edge
  of the grid for these short-exposure standards.

**What I learned about the repository:**

- Reusing a Job name keeps earlier status rows under
  `runs/<JOB_NAME>/status/`. Every consumer must take each night's latest
  row (now `night_failures.py`; `status_table.py` reads the manifests and
  was already right).
- The long2pos_specphot bar gaps are visible in the flats on some nights
  (2014-06-01, 2017, 2024) and not on others (2014-11 to 2021). The traced
  slit count, not the date, decides whether the split is needed.

### 2026-10-08 (Prompt #3 / S15c: sync of the 20 success nights, re-harvest and merge; all checks pass, milestone met)

**Sync.** For each of the 20 `success` nights in `status_table.py` (batch 1
plus 2022-04-09):

- `s3_sync.py pull mosfire/<night> --include 'sens/*' 'harvest/*'
  'redux/Science/spec1d_*' run_manifest.json gates.json raw/manifest.ecsv
  --calibs`.
- The raw standard frames the sensfunc used (the harvest's saturation check
  reads them).
- Everything is under `$KECK_ETCS_DATA/mosfire/<night>/`; every night has
  its sens, harvest files and one `WaveCalib`.
- New: `s3_sync.py pull --calibs` adds `redux/Calibrations/WaveCalib*` to
  `--include`. The prompt named the option, but it did not exist.

**Harvest changes** (`keck_etcs/calib/harvest.py`, tests in `test_harvest.py`):

- `slit_of_night(manifest, frames)`: a `long2pos_specphot` row now records
  the 4.0" bar the standard was in (width from the manifest's `specphot`
  bar table) and a length of one CSU bar. These rows had an empty
  `slit_width`, so the narrow-slit rule could not apply to them.
- `flag = narrow` below `WIDE_SLIT_ARCSEC = 3.0` (the census's
  `WIDE_SLIT`).

**Re-harvest and merge.**

- All 20 nights were re-harvested locally (rows keep the pod's provenance
  from `run_manifest.json`), then `harvest_sens.py --merge` ran over the 20
  `harvest/` directories.
- Differences from the table before:
  - the 15 long2pos rows gained `slit_width = 4.0`, `slit_length = 1`;
  - LDS749B 2022-04-09 lost the stale `nofilter` flag (harvested before
    filter division existed);
  - no zero point or throughput changed;
  - all four `excluded_nonlinear` flags are kept.

**Verify** (`scripts/mosfire/check_standards_table.py`, new and re-runnable):

- 20 `success` nights, 20 rows, one per night; no recorded failures remain
  (every processed night is a row).
- Provenance: 120/120 cells filled (`image`, `image_digest`,
  `pypeit_git_sha`, `keck_etcs_git_sha`, `job_name`, `s3_prefix`).
- Wide-slit rows: 20 of 20 (no narrow-slit standard was reduced, so no
  `narrow` row yet). Usable for era curves: 16 rows, 11 distinct
  standards:
  - 2012-04..2016-09: 5 rows (Feige110, 55 Dra, HD95126, HD18571, HD54601;
    all J);
  - 2017-02..2025-02: 10 rows (HD74721 x2, HD65158, HD21379, HD210501,
    Feige110, GD153 in J; LDS749B, GD153 x2 in J2);
  - 2025-04..: 1 row (GD153, J2).
- **Milestone (>= 10 standards over >= 2 eras): met** (11 over 3).
- Flags: `pwv_extrapolated` 13, `excluded_nonlinear` 4, `ok` 5.
- Monitor: 2456 rows on all 20 nights; `monitor_failed` 0.
- `git status`: the ECSV files (`standards.ecsv`, `calib_monitor.ecsv`,
  the 20 curves, `index.yaml`) plus the code of this step (`s3_sync.py`,
  `harvest.py` and its test, the check script) and this doc. That is more
  than "only the ECSV files", because the slit-width/`narrow` support and
  `--calibs` had to be added.
- Tests: 104 pass; `test_shipped_era_file_provenance_matches_its_rows`
  still fails, as agreed in Q&A S15a-4, until S16 rebuilds the era curves.

**For S16:**

- Both filters are now in each era: the J-against-J2 offset (about
  25 percent at the same star) must be resolved before an era median mixes
  them.
- 55 Dra at zp 19.52, unflagged.
- `pwv_extrapolated` on most short J exposures.
- The `*55Dra` file names (the KOA target name kept its `*`).

### 2026-10-08 (Prompt #4 / S16, part 1: trend analysis and monitor trends; the release waits for Q&A S16-1..3)

Done so far (nothing of the release is written yet: no era files, no
`calib_version` bump, no `CHANGES.md`, no fixtures, no release backup):

**The "J against J2" offset was a summary-column artefact.**

- `harvest.median_in` defaults to `thru_raw`, so a row's
  `thru_median_1117_1260` includes the filter, over a window that crosses
  both filters' edges. Likewise `zp_1250` sits on J2's red cut-off (half
  power 12463 A).
- The filter-divided curves agree:
  - `scripts/mosfire/compare_filter_pair.py` (new) on GD153 in J
    (2024-12-29) and J2 (2024-12-30): measured `thru_raw` J2/J 0.944
    against 0.915 from the filter curves over 11536-12452 A (3 percent);
    with the other J2 nights 5-9 percent.
- Two real systematics blueward of about 11900 A, and a 5 percent J/J2
  offset: Q&A S16-1 and S16-2.

**New code:**

- `keck_etcs/calib/trend.py` (tests `test_trend.py`):
  - `curve_common_median` gives `thru_common`, the filter-free median over
    `COMMON_WINDOW` = 11900-12450 A;
  - `era_stats` (median, MAD, slope %/yr with error);
  - `correlation` (Pearson; residuals after era medians);
  - `monitor_flags` (per-era 3-MAD night flags `trend_3mad`; rows flagged
    `nonlinear`/`monitor_failed` skipped; dome-flat series split by lamp
    `FPOWER`).
- `keck_etcs/calib/combine.py`: the 3-MAD exclusion compares nights over
  `COMMON_WINDOW`, not over each row's own band.
- `scripts/mosfire/plot_throughput_trend.py` writes
  `docs/figures/mosfire_throughput_trend.png`.
- `scripts/mosfire/plot_monitor_trends.py` writes the flags into
  `calib_monitor.ecsv` (169 rows `trend_3mad`, 19 group/era sets) and the
  figures `docs/figures/mosfire_monitor_{fwhm,flat_rate,lsf,sky_scale}.png`.

**Throughput trend** (16 usable rows):

| Quantity | 2012-04..2016-09 | 2017-02..2025-02 | 2025-04.. |
|---|---|---|---|
| `thru_common` median (MAD) | 0.253 (4.3 %) | 0.258 (3.3 %) | 0.270 (1 night) |
| `thru_common` slope | +5 +- 10 %/yr | +0.2 +- 0.6 %/yr | - |
| `zp_1250` in J | 19.79 mag | 19.81 mag (MAD 0.3 %, +0.4 +- 0.6 %/yr) | - |

- Residual correlations of `thru_common` (era medians removed): airmass
  0.6 sigma, PWV 0.9 sigma, slit width 1.1 sigma.
- `zp_1250` against airmass in J: 2.4 sigma, but driven by 55 Dra
  (airmass 1.44, 0.3 mag low), which the 3-MAD rule excludes once the
  combine runs. To recheck then (release check).

**Monitor trends:**

- FWHM: 20 nights, median 0.74" (0.39-1.35").
- Dome-flat rate at 12000 and 12500 A against `zp_1250`: only the J2
  nights have unsaturated flats (4 nights, FPOWER 4/9/9/13.5): r = -0.78,
  1.2 sigma. That is not meaningful while the lamp power changes.
- The 19 flagged group/era sets are listed by the script; I have not yet
  checked each one, so they are flags to look at, not findings.
- D25 and D14 proposals: Q&A S16-3.

### 2026-10-08 (Prompt #4 / S16, part 2: first calibration release mosfire-J-2026.10)

Applied the answers to Q&A S16-1 (b), S16-2 (accept) and S16-3 (D25 refit;
D14 unchanged), then built the release.

**Code:**

- `keck_etcs/calib/combine.py`: J rows only where the J filter is >= 0.9
  of its peak (`EDGE_TRIM_FRAC`); A0V rows only redward of 11900 A
  (`A0V_MIN_WAVE`); rows without `std_class` are tolerated. Test
  `test_edge_trim_and_a0v_cut`.
- `keck_etcs/core/lsf.py`, `instruments/base.py`, `instruments/mosfire.py`:
  D25 as `sqrt((w / 0.292)^2 + 1.08^2)` pix (new `Instrument.lsf_form`,
  `'max'` stays the default for other instruments). The monitor's own LSF
  constants are unchanged; they define its fixed measurement windows.
- `Instrument.throughput_for_window` (used by `etc.compute`): an era's
  curve is completed over the band window from the nearest era that
  measured the rest, scaled by the median ratio over 11900-12450 A, with a
  warning.
  - Needed because the 2025-04.. curve comes from one J2 night
    (11171-12462 A), so the default J calculation would otherwise hold the
    throughput constant over 12462-13457 A.
  - Scales applied: 2025-on over J x 1.024; 2012-2016 over J2 x 1.005.
  - Tests: `test_throughput_for_window_splices_uncovered_wavelengths`; the
    era fallback is now tested by monkeypatching a missing file.
- `scripts/mosfire/combine_throughput.py`: `CALIB_VERSION =
  mosfire-J-2026.10`.
- `scripts/mosfire/verify_release.py` (new): the S16 checks.

**Release products:**

- Era curves (`combine_throughput.py`):
  - 2012-04..2016-09: 4 standards, 11633-13457 A; excluded 55 Dra
    2014-10-05 (3 MAD);
  - 2017-02..2025-02: 9 standards, 11172-13457 A; excluded GD153
    2025-01-25 (3 MAD; 0.285, the J2 nights sit about 5 % high);
  - 2025-04..: 1 standard (GD153 2025-07-23, J2).
- Curve medians over 11900-12450 A: 0.257 / 0.255 / 0.270 (S10's
  2017-2025 curve from LDS749B alone: 0.273).
- `excluded_3mad` written into `standards.ecsv`.
- `index.yaml`: all 18 MOSFIRE entries now `calib_version:
  mosfire-J-2026.10`.
- Regression fixtures regenerated (`regen_regression_fixtures.py --regen`).
  The differences were the version, the default era (now 2025-04..), the
  LSF (+3.9 % at 0.7") and the throughput (about 1 %).
- `CHANGES.md` release section: era curves before and after, the standards
  added and excluded, method changes, known systematics, and the 5 image |
  digest | PypeIt pin triplets.
- `docs/keck_mosfire_design.md` 4.6.1: results.

**Verify** (`verify_release.py`: ALL CHECKS PASS; tests: 111 passed):

- `compute` with `throughput.date` in each era (J and J2) returns that era
  (`meta.era`) and `calib_version mosfire-J-2026.10`.
- 2012-2016 against XTcalc 2012 (x 75 / 72.37 m^2): +3.6 % over
  11633-13457 A (bins -10 to +15 %), within the 10 % target.
- No residual correlation of `zp_1250` with airmass beyond 2 sigma: J
  1.88 sigma (n = 11); J2 untestable (n = 3).
- Every row in an era curve has `image_digest` and a 40-character
  `pypeit_git_sha`; `CHANGES.md` lists the 5 distinct triplets.
- Final trend (14 rows): `thru_common` 0.258 (MAD 2.2 %, -1.0 +- 2.7 %/yr)
  and 0.257 (2.7 %, -0.3 +- 0.5 %/yr); residual correlations airmass
  1.8 sigma, PWV 0.2, slit width 0.6. No era-to-era change beyond the
  scatter.
- Release backup (`backup_products.py --run --release mosfire-J-2026.10`):
  801 files (126.2 MB, the D39 set of the 14 nights in the era curves)
  copied to `AIOcean:keck-etcs/releases/mosfire-J-2026.10/`; `rclone check
  --one-way`: 801 match, 0 missing, 0 differ, 0 errors, COMPLETE (summary
  `runs/backup/backup_20261008T151511Z_run.json`).
- Release diff: the data, `CHANGES.md`, fixtures and design doc form the
  release commit. The code changes above must go in a separate, earlier
  commit, so the release commit touches only `keck_etcs/data/`,
  `CHANGES.md`, `keck_etcs/tests/data/` and `docs/keck_mosfire_design.md`.

**What I learned about the repository:**

- `harvest.median_in` defaults to `thru_raw`, so the row columns
  `thru_median_*` include the filter. Fine for the gate, misleading across
  filters.
- `band_median_era` in an era file's meta is computed before the 3-MAD
  clipping; quote the curve's own median.
