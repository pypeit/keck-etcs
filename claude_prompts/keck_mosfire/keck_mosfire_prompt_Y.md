# Keck MOSFIRE implementation, part Y: the Y band and the Y/H/K release (Phase 7, S26-S27)

## Goals

Build the Y band of the MOSFIRE ETC and cut the calibration release that
carries all four bands. This doc covers two plan steps
(`docs/keck_mosfire_implementation.md` v0.5):

1. **S26, Y band:** the Y sensfunc parameters (design D53), the A0V model
   scaled to 2MASS J (D51), the Moon by ephemeris in the monitor for every
   band and the Y-only cut on the sky-excess curve (D61), the Y time
   series on Nautilus, the Y throughput product, examples, fixtures, the
   XTcalc comparison and the Y validation.
2. **S27, release and documentation:** one calibration tag
   `mosfire-YYYY.MM` for Y, J, H and K, the documents and the Read the
   Docs pages updated, and the design doc "as built" for the new bands.

Parts H and K must be complete (S23-S25 logged). Y goes last because it
has the smallest sample (D57); its batches may start as soon as part H
is done, but the release waits for K.

## Context

- **Design and decisions:** `docs/keck_mosfire_design.md` v0.7, section 9
  (9.2 facts, 9.5 P14 for the excess curve and the Moon, 9.7, 9.8 the
  definition of done), D48-D62, and the Q&A Q61/Q66 (Moon) and Q63 in
  `keck_mosfire_prompts.md`.
- **Y facts (9.2):** order 6, 1.082 A/pix, filter 9719-11243 A (1410 pix,
  narrower than the detector), centred long-slit footprint **9255-11471
  A measured** from the dev suite's `Y_long` `WaveCalib` (= the J2
  footprint x 5/6 to 0.1 percent: Y shares the J grating tilt, so the
  ETC window is the filter's), AB-Vega 0.655, 82 OH lines, Ne 9 and Ar 9
  lines (few: lamp nights are weak calibrators in Y), PypeIt
  `tweak_standard` clean window 9520-11256 A, XTcalc 2012 median
  throughput 0.237 (gate 0.12-0.38), mirror reflectivity 0.85 per surface
  in XTcalc. Nodes 1.00/1.05/1.10 um, common window 0.98-1.11 um, no PWV
  window (`pwv_weak`), second-order light outside 0.952-1.126 um already
  masked by PypeIt. The 2012 measured sky agrees with the Gemini model
  (0.8-1.0x between lines). The brightest OH line (1.083 um) reaches 26k
  ADU in about 19 min through a 0.7" slit. KOA: 13 `long2pos_specphot`
  nights with star-like names, 230 on any long-slit mask, so the "done"
  threshold is **5 wide-slit standards over 2 eras** (9.8).
- **The Moon (Q66, D61):** no MOSFIRE header carries a Moon card. The
  monitor already computes the Sun's altitude per frame
  (`keck_etcs/calib/monitor.py`, `sun_altitude(mjd_mid, site)`, astropy
  `get_sun` and `AltAz`, the site dict in `instruments/mosfire.py`); the
  Moon is the same code path with `get_body('moon')`, plus the
  illuminated fraction from the Sun-Moon elongation and the separation
  from the target's `RA`/`DEC`. Record `moon_alt_deg`, `moon_illum` and
  `moon_sep_deg` for every on-sky row in every band. A frame is "moonlit"
  when the Moon is above the horizon and more than 30 percent
  illuminated. **Only the Y excess curve applies a cut:** dark frames if
  they number at least 20 over at least 3 nights, otherwise all frames
  with `moon_included = true` in the file's `meta` and the
  dark-minus-moonlit difference reported. J, H and K use all frames (the
  user: the Moon should not matter there).
- **What parts H and K left for Y:** `BANDS['Y']` with the measured
  footprint and provisional LSF; `MONITOR['Y']` without frozen lines; a
  provisional `keck_mosfire_Y.sens` (polyorder 6); the `--polyorders`
  mode of `sensfunc_perturbation_test.py`; `a0v_model(band, mag)`;
  `measure_sky_excess.py --band`; manifests with `band`;
  `validate_j0841.py` generalised; the Y reference reduction
  (`Y_long`: GD71 2019-11-18 through a 1" slit, the quasar J2132-1434 on
  2019-11-20); the Nautilus layout and gates per band; the thermal term
  (zero in Y); the saturation fraction.
- **Validation (9.7):** one Y night at 20 percent; `find_validation_targets.py`
  (S23c) says whether a quasar night carries a same-night wide-slit
  standard; the fallback is J2132-1434 with GD71 two nights earlier
  through a 1" slit, where slit loss enters the flux calibration and the
  test is weaker (say so in the result).
- **Release (D49, D28, 5.5):** the tag `mosfire-YYYY.MM` covers every
  group; a calibration release is one commit touching only
  `keck_etcs/data/` and `CHANGES.md`, with a section listing the standards
  added per band, the era medians before and after, any detector-table
  change, the `.sens` parameters per band and the image tags (with
  digests) of the reductions that fed it; `nautilus/README.md` section 10
  is the procedure; `scripts/mosfire/verify_release.py` the check. The
  J-only tag of S23b is the previous release.
- **Documents to bring "as built" (S27):** `README.md`,
  `docs/wmko_api_note.md` (every schema field: the `band` values,
  `ambient_temp_C`, `thermal_e`, `saturation.frac_pix_nonlinear_1pct`),
  the developer docs on the calculations (`docs/developer/`: the thermal
  term, the excess curve, the per-band LSF, the band groups), the
  examples page and the interactive page (`docs/`; band selector and the
  new fields), `nautilus/README.md` (multi-band manifests and layout),
  `CHANGES.md`, `CITATION.cff` if the version changes, and
  `docs/keck_mosfire_design.md` v0.8 with 9.2 filled in (measured
  footprints, LSFs, `eps_eff`, excess curves) and section 9 marked "as
  built" for the bands delivered. `scripts/check_docs.py` and the `-W`
  Sphinx build (`KECK_ETCS_DOCS_ALLOW_PYPEIT=1` in `pypeit14b`) are the
  checks.
- **Rules (CLAUDE.md and the plan):** the user runs git (the tag above
  all); Python via `conda run -n pypeit14b`; calculations are scripts on
  disk; nothing under `KECK_ETCS_DATA` is committed; provenance `meta` on
  every data file; no secret value anywhere; image pushes and Jobs beyond
  the pilot are confirmed with the user; PypeIt defects go to a PypeIt
  branch; each prompt ends with a Log entry below.

## Prompts

1. **S26a: the Moon in the monitor, the Y sensfunc parameters, the A0V
   model, the pilot.** Add `moon_altitude_illum_sep(mjd_mid, site, ra,
   dec)` beside `sun_altitude` in `keck_etcs/calib/monitor.py` and the
   three columns to every on-sky row (unit test against a known full and
   new Moon date); the merged `calib_monitor.ecsv` gains them for the J,
   H and K rows at the next merge (a re-run of the monitor step on the
   synced nights, locally; say how many). Run the polyorder test on
   `Y_long` (GD71) and on the first wide-slit Y standard from the census
   (`--polyorders 4 5 6`); write `keck_etcs/data/pypeit_par/keck_mosfire_Y.sens`
   (6 unless the test says lower; `hydrogen_mask_wid = 10`; `tell_npca` by
   the test; the result table in the header). The A0V model is scaled to
   2MASS J (`a0v_model('Y', j)`). Write `nautilus/manifests/nights_pilot_Y.csv`
   (3 wide-slit nights if the census has them, across eras), ask the user
   to rebuild and push the image, and with the go-ahead run the pilot.
   Sync, harvest, merge; freeze the Y monitor lines
   (`select_monitor_lines.py --band Y`) and re-run the monitor step for
   the pilot. Verify: as S24a; the Moon columns are present and plausible
   on every row (altitude against an independent ephemeris for one
   night). Log your work with the polyorder table, the status table and
   the image tag/digest/pin.

2. **S26b: Y batches, product, the Y excess curve with the Moon rule,
   validation.** Batches as parts H and K (small: 13 candidate nights at
   most). Then `mosfire_thru_Y_<era>.ecsv`, the trend table and plot (with
   5 standards the 3-MAD test is weak; report medians and ranges instead
   where `MIN_NIGHTS` is not met), the Y excess curve
   `sky/mosfire_sky_excess_Y.ecsv` by the Moon rule above (count the dark
   frames and nights first and log the decision; write `moon_included`
   and the dark-minus-moonlit difference in `meta`), `examples/Y_point.json`
   as a fixture, `compare_xtcalc.py` for Y, and the Y validation night (20
   percent; the J2132-1434 fallback with its weaker test stated). Verify:
   >= 5 wide-slit standards over >= 2 eras; era medians within 0.12-0.38;
   the other bands' fixtures unchanged; validation PASS or analysed;
   `check_docs.py` passes. Log your work, batch by batch, then the
   product, the curve and its Moon decision, the validation and the 9.8
   checklist lines for Y.

3. **S27: the Y/H/K release and the documents "as built".** Run
   `verify_release.py` over all groups and fix what it finds; complete
   `index.yaml` (every new file with `bands`, script, sha256, provenance);
   write the `CHANGES.md` release section for `mosfire-YYYY.MM` (per band:
   standards added, era medians, `.sens` parameters, the thermal defaults,
   the excess curves and their Moon decision, image tags and digests) and
   ask the user to tag. Bring the documents listed in Context "as built":
   README, the WMKO API note (every field; `check_docs.py` enforces it),
   the developer docs on the calculations, the examples page and the
   interactive page (band selector; `ambient_temp_C` as an optional
   input; `thermal_e` and the saturation fraction in the output), the
   Nautilus operator guide, and `docs/keck_mosfire_design.md` v0.8 (title
   "Y, H, K as built"; 9.2 filled with the measured footprints, LSFs,
   `eps_eff` per era, excess-curve provenance; section 9 and the *Other
   bands* pointers reworded from "proposed/decided" to "as built"; a
   change note; 9.8 ticked with the numbers). Verify: `check_docs.py` and
   the `-W` Sphinx build pass; the interactive page computes for Y, J, H
   and K with the released calibration (Pyodide check script of part 7);
   the regression fixtures of every band pass at the tagged data; the 9.8
   checklist holds line by line, or the log says which line does not and
   why. Log your work with the checklist.

## Q&A

Please answer with ">A." lines before prompt 1 is run (a default is
proposed for each):

- **Y-1. Moonlit threshold.** "Moonlit" = Moon above the horizon and more
  than 30 percent illuminated. (a) agree (recommended); (b) above the
  horizon at any phase; (c) also require the separation from the target
  below 60 degrees.
- **Y-2. Y batches before K is done.** The Y code needs only part H.
  (a) run the Y pilot and batches as soon as part H is logged, in
  parallel with the K work, to use the cluster time (recommended); (b)
  strictly after K.
- **Y-3. Design doc version for "as built".** (a) v0.8, title "(Y, H, K
  as built)", section 9 kept as the record of the extension with its
  measured values (recommended); (b) fold section 9 into sections 3-6 and
  retire it.

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
