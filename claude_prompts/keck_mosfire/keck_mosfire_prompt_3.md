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
   filter. Log your work.

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
