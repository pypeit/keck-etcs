# Keck MOSFIRE implementation, part K: the K band and the thermal background (Phase 7, S25)

## Goals

Build the K band of the MOSFIRE ETC on the band-neutral code of part H
(`keck_mosfire_prompt_H.md`, S23-S24). This doc is plan step **S25**
(`docs/keck_mosfire_implementation.md` v0.5):

1. **K sensfunc parameters** by the measured polyorder test (design D53),
   the A0V model scaled to 2MASS Ks (D51), Br gamma masked at 30 A (D52).
2. **The thermal background term** (D60): a grey body `eps_eff *
   Planck(T_amb)` added to the sky, the ambient temperature from the
   header card `TUBETEMP`, the monitor columns and the per-night fit, the
   ETC input `ambient_temp_C` and output `thermal_e`.
3. **The K time series** on Nautilus (pilot, batches, harvest, throughput
   product, trend, the K sky-excess curve), the K examples, fixtures and
   XTcalc comparison, and the K validation night including the thermal
   continuum.

Part H must be complete (S23 and S24 logged, the J-only tag cut). The Y
doc (`keck_mosfire_prompt_Y.md`) follows and holds the final release.

## Context

- **Design and decisions:** `docs/keck_mosfire_design.md` v0.7, section 9
  (9.2 facts, 9.5 P13 for the thermal term, 9.6 monitor), D48-D62, and
  the Q&A Q60, Q65 (thermal and `TUBETEMP`), Q61/Q66 (excess curve) in
  `keck_mosfire_prompts.md`.
- **K facts (9.2):** order 3, 2.169 A/pix, filter 19215-24046 A (2227
  pix, wider than the detector: the centred long slit sees about
  19540-23970 A, measured in S23d and frozen in `BANDS`), AB-Vega 1.845,
  86 OH lines (sparse beyond 2.3 um), Ne 59 and Ar 20 lines for lamp
  nights, XTcalc 2012 median throughput 0.317 (gate 0.16-0.51), mirror
  reflectivity 0.95 per surface in XTcalc. Nodes 2.05/2.15/2.30 um, common
  window 1.98-2.37 um, PWV windows 1.95-2.00 and 2.38-2.40 um (water; the
  CO2 bands at 2.01 and 2.06 um are not water). The brightest OH line
  (2.001 um) reaches 26k ADU in about 7 min through a 0.7" slit. KOA: 72
  `long2pos_specphot` nights with star-like names, 372 on any long-slit
  mask. CALSPEC white dwarfs are faint in K (GD153 Ks ~ 14.1), so the A0V
  series dominates.
- **The thermal term (9.5 P13 = D60; `scripts/mosfire/survey_other_bands.py`
  section 4):** the May-2012 MOSFIRE K sky (XTcalc
  `MosfireSkySpec/Ksky_cal_pA.sav`) exceeds the Gemini model smoothed to
  the 0.7" LSF by 2.7 / 5.2 / 9.1 / 12.8 / 21 ph/s/arcsec^2/nm/m^2 at
  2.15 / 2.25 / 2.30 / 2.35 / 2.40 um, i.e. a 275 K grey body with
  `eps_eff` 0.15 / 0.12 / 0.14 / 0.13 / 0.15 (flat); the fit moves to 0.09
  at 280 K and 0.21 at 270 K. The term is

  ```
  B_th(lam) = eps_eff * P_ph(lam, T_amb)        [ph/s/arcsec^2/nm/m^2]
  P_ph      = 2 c / lam^4 / (exp(h c / (lam k T)) - 1) * (arcsec^2 in sr) * 1e-9
  B_eff     = sky_scale * [B_gemini + E_band] + B_th      (5.3.8; B_th before T_sys, not attenuated by T_atm)
  ```

  `eps_eff` is referred to above the telescope (it absorbs the mirrors'
  transmission). Defaults `eps_eff = 0.15`, `T_amb = 275 K`; the term is
  negligible outside K (at 1.80 um, 0.05 against a continuum of 0.4) and
  `thermal_e` is reported for every band.
- **`TUBETEMP` (Q65, D60):** every MOSFIRE frame we hold carries
  `TUBETEMP` ("tube temperature", degrees C): 238 frames on 30 nights,
  2012-09-10 to 2025-07-23, median 1.6 C, range -3.4 to +4.9 C, per-night
  spread usually below 0.5 K (`scripts/mosfire/inspect_raw_headers.py
  --stat TUBETEMP --by-night`). No dome or mirror temperature card exists;
  the dewar cards `DWRTMP1-8` are the cold instrument. The night's median
  `TUBETEMP` is held fixed while `eps_eff` is fitted (the two are
  degenerate, about 50 percent in `eps_eff` per 5 K). The ETC default for
  `ambient_temp_C` is the median `TUBETEMP` of the K throughput sample
  (2 C provisionally); the documentation states the spread (-3.4 to +4.9 C
  moves the term by about -40 to +35 percent). If the fitted per-night
  `eps_eff` correlates with `TUBETEMP`, the model is wrong and T belongs
  to something else (the instrument's warm window), to be reported, not
  forced.
- **What part H left for K:** `BANDS['K']` with the measured footprint and
  provisional LSF; `MONITOR['K']` without frozen lines;
  `fit_thermal_continuum.py` (S23d) with the 2012 and 2019 `eps_eff`
  values from `longslit_3x0.7_K` and `K_long`; a provisional
  `keck_mosfire_K.sens`; `measure_sky_excess.py --band`; the `--polyorders`
  mode of `sensfunc_perturbation_test.py`; `a0v_model(band, mag)`;
  manifests with `band`; `validate_j0841.py` generalised; the K dry run
  passed on 2012-11-28.
- **Monitor (9.6):** every on-sky row in every band gains `tube_temp_C`;
  K adds `sky_continuum` (e-/s/arcsec^2/A at the detector and the same
  above the instrument) over 2.30-2.40 um per frame. Rows are flags, not
  gates (D47).
- **Validation (9.7):** one K night at 20 percent with the 6.1 method,
  plus the thermal continuum at 2.30-2.40 um within 30 percent;
  `find_validation_targets.py` (S23c) says whether a quasar night has a
  same-night wide-slit standard; the fallback is Per-emb 25 (2019-10-13,
  `K_long`, a bright embedded source: good for the continuum, not for the
  faint-source regime).
- **Rules (CLAUDE.md and the plan):** the user runs git; Python via
  `conda run -n pypeit14b`; calculations are scripts on disk; nothing
  under `KECK_ETCS_DATA` is committed; provenance `meta` on every data
  file; no secret value anywhere; image pushes and Jobs beyond the pilot
  are confirmed with the user; PypeIt defects go to a PypeIt branch; each
  prompt ends with a Log entry below.

## Prompts

1. **S25a: the thermal term in the ETC and the monitor.** Add the Planck
   term to `keck_etcs/core/sky.py` (`thermal_background(wave_A, eps_eff,
   T_K)` in Gemini units, unit-tested against the 275 K numbers above to
   5 percent), the instrument-module constants `THERMAL = {'eps_eff':
   0.15, 'T_amb_K': 275.15, 'provenance': ...}`, the input
   `ambient_temp_C` (float or null, -10..20, K only in effect; null = the
   default) in `keck_etcs/schema/etc_input.json`, the output `thermal_e`
   (electrons per spectral pixel from the term; zero outside K to within
   the 1.80 um estimate) in `etc_output.json`, the 5.3.8 sum in `etc.py`
   (before `T_sys`, not attenuated by `T_atm`, outside the `sky_scale`
   bracket), and the warnings. In `keck_etcs/calib/monitor.py` add
   `tube_temp_C` to every on-sky row (from `TUBETEMP`) and the K metric
   `sky_continuum` over 2.30-2.40 um (10th percentile of PypeIt's sky
   model per frame, converted with the night's `T_sys` as the excess curve
   is); extend `fit_thermal_continuum.py` to take a night's harvest and
   monitor rows, hold T at the night's median `TUBETEMP`, fit `eps_eff`
   alone, and write `eps_eff`, `tube_temp_C` and the fit residual into the
   night's monitor file. Verify: `pytest` passes; the J, J2 and H fixtures
   are unchanged (`regen_regression_fixtures.py` report mode); `compute()`
   with `band = K` returns a finite `thermal_e` that reproduces the 2012
   and 2019 reference continua within 30 percent at the default
   constants; `check_docs.py` passes once the WMKO note lists the two new
   fields. Log your work.

2. **S25b: the K sensfunc parameters, the A0V model in Ks, the pilot.**
   Run the polyorder test (`sensfunc_perturbation_test.py --polyorders 4
   5 6 8`) on `longslit_3x0.7_K` and on the first wide-slit K standard
   from the census; K may need `tell_npca` above 3 for the CO2 bands and
   the water at both edges, so test 3, 4 and 5 as well. Write
   `keck_etcs/data/pypeit_par/keck_mosfire_K.sens` (lowest passing order,
   `hydrogen_mask_wid = 30` for Br gamma 2.166 um, the result table in the
   header). The A0V model is scaled to 2MASS Ks (`a0v_model('K', ks)`;
   PypeIt's `TMASS-K` curve, half-maximum 2.028-2.299 um) with the J-scaled
   value as the cross-check column. Write `nautilus/manifests/nights_pilot_K.csv`
   (3-5 wide-slit nights across eras, at least one WD if the census has
   one bright enough), ask the user to rebuild and push the image, and with
   the go-ahead run the pilot. Sync, harvest, merge; freeze the K monitor
   lines (`select_monitor_lines.py --band K`, including Ne/Ar lines for
   lamp nights) and re-run the monitor step for the pilot. Verify: as
   S24a, plus: every pilot night has `tube_temp_C`, `sky_continuum` and a
   fitted `eps_eff` in its monitor file, and the pilot's `eps_eff` values
   are listed against `TUBETEMP`. Log your work with the polyorder and
   `tell_npca` tables, the status table and the image tag/digest/pin.

3. **S25c: K batches, product, the thermal defaults, the excess curve,
   validation.** Batches as part H (Indexed Jobs, sweeps, backup, sync,
   merge; launches confirmed; one log entry per batch). Then
   `mosfire_thru_K_<era>.ecsv`, the trend table and plot, and the thermal
   defaults: the era median `eps_eff` and the sample median `TUBETEMP`
   written into the instrument module with provenance (the `ambient_temp_C`
   default and its documented spread), plus the `eps_eff`-against-`TUBETEMP`
   correlation (slope, scatter) reported; if `eps_eff` is not constant at
   fixed `TUBETEMP` to within the 3-MAD rule, say so in the design and
   keep the ETC's spread statement honest. The K sky-excess curve
   `sky/mosfire_sky_excess_K.ecsv` from all non-twilight frames with the
   thermal term subtracted first (so the curve is the non-thermal
   excess), `examples/K_point.json` as a fixture, `compare_xtcalc.py` for
   K (XTcalc's own K thermal handling noted), and the K validation night
   (20 percent on the object S/N; the 2.30-2.40 um continuum within 30
   percent; Per-emb 25 as the fallback). Verify: >= 10 wide-slit standards
   over >= 2 eras; era medians within 0.16-0.51; the other bands' fixtures
   unchanged; validation PASS or analysed; `check_docs.py` passes. Log
   your work, batch by batch, then the product, the thermal defaults, the
   curve, the validation and the 9.8 checklist lines for K.

## Q&A

Please answer with ">A." lines before prompt 1 is run (a default is
proposed for each):

- **K-1. One `eps_eff` for all eras, or one per era.** The mirrors'
  emissivity changes with recoating. (a) one value per era (the J eras,
  D6), with the ETC using the era of the requested date, as it does for
  throughput (recommended); (b) one value overall.
- **K-2. `ambient_temp_C` for the other bands.** The term is computed for
  every band and is negligible outside K. (a) accept the input for every
  band and report `thermal_e` everywhere (recommended: one code path, no
  band special-casing); (b) reject it outside K with a schema error.
- **K-3. Pilot size.** (a) 4 nights, `parallelism` 4 (recommended); (b)
  other.

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
