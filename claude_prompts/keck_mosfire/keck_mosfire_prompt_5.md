# Keck MOSFIRE implementation, part 5: time series (Phase 4)

## Goals

Reduce the KOA standard-star nights in batch on Nautilus as Indexed Jobs,
back up the high-level products after each batch, harvest their zero points,
run the throughput trend analysis across the instrument eras, and cut the
first calibration release. These are steps S15 and S16 of the plan (v0.3).
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
  releases), 7 (definition of done: >= 10 standards over >= 2 eras).
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
   Risks: PypeIt `develop`'s hook for custom standards; run time; nights
   with the standard at a different slit position than the flats. Log your
   work, with the status table and the image tag/digest/pin.

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
   over all synced `harvest/` directories; narrow-slit standards get
   `flag = narrow` and keep their `seeing_fwhm_pix` for the slit-loss sample.
   Verify: the number of `success` nights equals the number of new rows in
   `keck_etcs/data/mosfire/throughput/standards.ecsv`; every row has the six
   provenance columns filled; the count of wide-slit rows and their spread
   over eras is reported against the milestone target (>= 10 standards over
   >= 2 eras); every processed night is either a row or a recorded failure;
   `git status` shows only the ECSV files. Log your work.

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
   Log your work.

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
