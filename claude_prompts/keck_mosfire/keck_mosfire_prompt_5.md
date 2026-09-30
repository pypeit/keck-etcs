# Keck MOSFIRE implementation, part 5: time series (Phase 4)

## Goals

Reduce the KOA standard-star nights in batch, harvest their zero points, run
the throughput trend analysis across the instrument eras, and cut the first
calibration release. These are steps S15 and S16 of the plan. The KOA search
itself (S14) is in its own prompt doc, `claude_prompts/koa_search_prompts.md`,
which must have produced the candidate table and the first downloads before
this doc starts.

Run order: after `koa_search_prompts.md` (candidates and downloads) and part
2 (the reduction and harvest scripts). S15 -> S16. S15 will span several
sessions; split it by year or by batch and log each batch. Part 6 step S18
needs S16.

## Context

- Design: `docs/keck_mosfire_design.md`, sections 2 (D2-D6, D22, D28, N3),
  4.1 (selection criteria), 4.2 (workflow), 4.4 (per-standard table), 4.5
  (per-era combination), 4.6 (trend analysis), 4.7 (uncertainties), 5.5
  (calibration releases), 7 (definition of done: >= 10 standards over >= 2
  eras).
- Plan: `docs/keck_mosfire_implementation.md`, steps S15, S16 and the risks
  section.
- Inputs: `keck_etcs/data/mosfire/koa_standards_candidates.ecsv` (from the
  KOA doc: date, KOA ID, `MASKNAME`, filter, `SAMPMODE`, `NUMREADS`,
  airmass, program, standard class, 2MASS J for A0V stars); downloads under
  `$KECK_ETCS_DATA/mosfire/<YYYYMMDD>/raw/`; `scripts/mosfire/reduce_standard.py`
  and `scripts/mosfire/harvest_sens.py` (part 2); `keck_etcs/calib/{harvest,
  combine}.py`; `keck_etcs/data/pypeit_par/keck_mosfire_J.sens`.
- A0V standards (decision N3): build the model spectrum by scaling PypeIt's
  Vega spectrum (`vega_tspectool_vacuum.dat`) so that its synthetic 2MASS J
  magnitude equals the star's 2MASS J; implement in
  `keck_etcs/calib/standards.py` and pass it to PypeIt's sensfunc as a
  user-supplied standard (check how `pypeit_sensfunc` / `SensFunc` accepts a
  custom standard spectrum in PypeIt 2.0: `pypeit/core/standard.py`
  `get_standard_spectrum(spectral_type=..., V_mag=...)` returns a Vega model
  scaled by V only, so a J-scaled model needs either a V-equivalent magnitude
  or a direct hook). PypeIt masks Paschen lines automatically.
- Eras (design D6): 2012-04-04 to 2016-09-15; 2017-02-13 to 2025-02-11;
  2025-04-29 onward.
- Rules (CLAUDE.md): the user runs git; `conda run -n pypeit14`; scripts on
  disk; nothing under `KECK_ETCS_DATA` is committed; a calibration release is
  one commit touching only `keck_etcs/data/` and `CHANGES.md` (the user makes
  the commit); log each batch.

## Prompts

1. **S15a: A0V standard support and the batch driver.** Extend
   `keck_etcs/calib/standards.py` with the Vega + 2MASS J model (N3) and
   classification of a candidate as WD (PypeIt archive) or A0V; extend
   `scripts/mosfire/reduce_standard.py` to loop over nights from the
   candidate table, skip nights without dome flats (record `no calibs`),
   handle `long2pos` and `long2pos_specphot` masks with PypeIt's settings,
   and write a per-night status table
   (`$KECK_ETCS_DATA/mosfire/batch_status.ecsv`: night, standard, slit,
   status in {success, no calibs, fit failed, no trace}). Run it on the first
   batch (the wide-slit standards and the Hennawi/Yang/Wang nights first).
   Verify: every night in the batch has a status; each `success` night has a
   `sens_*.fits`; at least one A0V sensfunc was built with the J-scaled Vega
   model and its zero point at 1.25 um is within 20 percent of a WD night in
   the same era (or the difference is explained). Risks: PypeIt 2.0's hook
   for custom standards; run time; nights with the standard at a different
   slit position than the flats. Log your work, with the status table
   summary.

2. **S15b: remaining batches and harvest.** Continue the batch over all
   candidate nights (several sessions if needed, one log entry per batch),
   then run `scripts/mosfire/harvest_sens.py` on every `sens_*.fits` to fill
   `keck_etcs/data/mosfire/throughput/standards.ecsv` and the per-standard
   curve files; narrow-slit standards get `flag = narrow` and keep their
   `seeing_fwhm_pix` for the slit-loss sample. Verify: the number of
   wide-slit rows and their spread over eras is reported against the
   milestone target (>= 10 standards over >= 2 eras); every processed night
   is either a row or a recorded failure; `git status` shows only the ECSV
   files. Log your work.

3. **S16: trend analysis and first calibration release.** Implement
   `keck_etcs/calib/trend.py` (per-era median, MAD, linear slope in percent
   per year with uncertainty, correlations of `zp_1250` with airmass, PWV
   and slit width) and `scripts/mosfire/plot_throughput_trend.py` (zero
   point and band-median throughput versus date with era boundaries;
   figures under `docs/figures/`). Run `combine.py` to write
   `mosfire_thru_<era>.ecsv` for every era with data, apply the 3-MAD
   whole-night exclusion and list the excluded nights, bump `index.yaml` to
   `calib_version = mosfire-J-YYYY.MM`, write the `CHANGES.md` section
   (standards added, era medians before and after), regenerate the
   regression fixtures deliberately, and update `docs/keck_mosfire_design.md`
   section 4.6 with the results. Verify: `compute` with `throughput.date` in
   each era returns that era's curve and `meta.era`; the 2012-2016 era
   median is within about 10 percent of XTcalc's 2012 curve after the 75 vs
   72.4 m^2 aperture correction, or the discrepancy is discussed; no residual
   correlation of `zp_1250` with airmass at more than 2 sigma; the release
   diff touches only `keck_etcs/data/`, `CHANGES.md`, the fixtures and the
   design doc. Log your work.

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
