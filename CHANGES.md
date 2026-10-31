# Changes

Code versions follow `keck_etcs.__version__`; calibration releases are tagged
`mosfire-YYYY.MM`, one tag for all band groups (design 5.5, D28, D49;
`mosfire-J-YYYY.MM` before `mosfire-2026.10`). A calibration release is one
commit touching only `keck_etcs/data/` and this file, with a section listing
the standards added, the era medians before and after, any detector-table
change, and the image tags (with digests) of the Nautilus reductions that
fed it.

## Code (unreleased, after 0.2.5)

- **H sensfunc parameters, the A0V model in H, the H pilot (S24a; D51,
  D53; "Other bands" part H prompt 5):**
  - `scripts/mosfire/sensfunc_perturbation_test.py --polyorders 4 5 6 8
    --tell-npca 2 3 4 5 --band H --jobs N`: the D53 parameter test (the
    1e-5 perturbation stability, the rms difference to the next value up
    over the band's common window and within 100 A of its edges; the
    lowest value passing 1, 1 and 2 percent is chosen; tables and JSON).
    **H: polyorder 4, tell_npca 2** (`keck_mosfire_H.sens`, tables in its
    header; design 9.3) on `longslit_3x0.7_H` (HIP 17971, 0.7") and the
    brightest 2017-2025 `long2pos_specphot` A0V night, HD 79108
    2024-12-24 (downloaded and reduced locally at the pin; gates PASS,
    median throughput 0.32 through the 4" bar).
  - `scripts/mosfire/build_sensfunc.py`, for Y, H and K (J keeps PypeIt's
    defaults so the released J products stay reproducible): the
    **filter-edge mask** (spec1d copies with `OPT_MASK`/`BOX_MASK` false
    where the band's filter transmission is below half its peak, before
    the per-frame fits and the coadd) and the **telluric resolution
    guess** (`[[IR]] resln_guess` from the band's LSF rule at the smaller
    of the slit width and the star's spatial FWHM). Both came out of the
    test: a star in an off-centre 4" bar sees 300 A beyond the filter's
    half-maximum, where the steep zero point pulls a low-order polynomial
    off by 10-30 percent inside the window, and PypeIt's sampling-based
    resolution guess (R about 3300, bounded to 0.6-1.4x) pins a 4"-bar fit
    at its lower bound. `sens/<NAME>_<DATE>_sens_setup.json` records both.
  - The A0V model takes the band's own 2MASS magnitude (D51): the night
    manifests carry `hmag_2mass` and `kmag_2mass` beside `jmag_2mass`
    (`make_night_manifest.py`, `status_row.py`, `night_failures.py`), the
    pod exports them, `reduce_standard.py --mag` and `build_sensfunc.py
    --mag` default to the band's column (`standards.mag_column`), `--jmag`
    stays the J cross-check; `run_manifest.json` `standard` gains
    `mag_2mass` and `mag_band_2mass`.
  - `make_night_manifest.py pilot --band H` writes
    `nautilus/manifests/nights_pilot_H.csv` (H-2: the H white dwarf
    Feige 110 2014-06-01, the brightest 2017-2025 A0V HD 79108 2024-12-24,
    HD 159008 2015-09-17, HD 133772 2017-06-15); `night_job.yaml`
    `completions: 4`. `check_std_peaks.py --band`; `check_pypeit_pin.py
    --image` takes a bare tag.
  - **Image 0.2.7**
    (`sha256:46e80edaf6eef0469530dae0d57fd756a8d6de64d221bbf873e2e07a16509dc2`,
    keck-etcs `c5c8e53`, PypeIt pin unchanged at `b0447b7`) carries all of
    the above; the 2012-11-28 H and K references were rebuilt with the
    final settings and re-staged, so a 0.2.6 pod would fail `zp_agree`.

- **Reference reductions, footprints, multi-band layout and gates (S23d;
  D52, D55, D56, D59, D60; "Other bands" part H prompt 4):**
  - the dev-suite reference nights `longslit_3x0.7_H`, `longslit_3x0.7_K`,
    `K_long` and `long2pos1_H` reduced with `reduce_standard.py` inside the
    0.2.5 image (PypeIt at the pin; the `pypeit14b` checkout is on another
    branch), with the current repository mounted. The **H and K
    footprints** are measured and frozen (`H_FOOTPRINT_A` 14650.5-17970.7 A,
    1.6284 A/pix; `K_FOOTPRINT_A` 19535.9-23991.1 A, 2.1850 A/pix; the
    K_long night gives 19529.7-23957.1 A), the LSF rows for H and K at 0.7"
    (2.560 and 2.613 pix, against the J rule's 2.627) and K at 1.5" (5.370
    against 5.249) are in `lsf_measurements.ecsv` (columns `ref_wave_A`,
    `fwhm_A_ref`, `R_ref` replace the J-specific `fwhm_A_1250`, `R_1250`),
    and the first K thermal-continuum fits exist (`scripts/mosfire/fit_thermal_continuum.py`:
    `eps_eff` 0.47 on 2012-11-28 at 1.6 C and 0.23 on 2019-10-13 at 4.8 C
    against the provisional XTcalc throughput, with a spectral shape
    flatter than a 275 K grey body; D60 to be revisited in part K).
  - **PypeIt defect at the pin** (`nautilus/patches/pypeit_mosfire_slitrange_spec1d.patch`):
    `pypeit_sensfunc` crashes on a spec1d of a short long slit
    (`LONGSLIT-3x0.7`) because `config_specific_par` splits a `slitrange`
    that the spec1d header cannot yield; the patch reads the header's
    `SLITRANGE` card. Committed on `etc-fixes` as `b0447b7` (on top of the
    S17 read-noise fix `38bb1b7`) and pinned by **image 0.2.6**
    (`sha256:c9e01c3415afe8d5b5739e022c90600ebc7aa809275a9d89a4120dca49cc3f92`,
    keck-etcs `d34a000`); the reference reductions and sensfuncs above
    were rerun in it, so the staged H and K references carry the new pin.
    The 0.2.6 image is the first with the CDS read noise of 21 e- (S17).
  - **D52 check:** PypeIt's IR algorithm does not use `hydrogen_mask_wid`
    (only UVIS does), and the Vega model leaves no Brackett residual on
    HIP 17971 in H (`scripts/mosfire/brackett_mask_check.py`: data-minus-fit
    rms 0.019 mag at Br10-18 against 0.018 in the continuum), so the H and
    K `.sens` files (`keck_mosfire_{H,K}.sens`, provisional: polyorder 5,
    `tell_npca` 3) carry no mask line.
  - **Layout (D55):** `keck_etcs.paths.night_dir`/`s3_prefix` take `band`;
    Y, H and K products live under `mosfire/<night>/<band>/`, the raw
    frames are shared, J is unchanged. `reduce_standard.py` (also:
    standards as their own OH arcs when no other on-sky frame exists;
    lamp-calibrated `long2pos`; PypeIt's object-finding defaults on
    `long2pos`; `pypeit_setup` run in `redux/`), `build_sensfunc.py`
    (per-band `.sens`), `gates.py` (windows and throughput range from
    `mosfire.gate_windows`), `harvest_sens.py`, `measure_lsf.py`,
    `stage_reference.py`, `verify_nights.py`, `status_table.py` and the
    status rows take `--band`/`$BAND`. Manifests gain a `band` column, one
    row per (night, band) (`make_night_manifest.py`; `nights_dryrun_HK.csv`
    for the 2012-11-28 H and K dry runs); `download_mosfire_night.py`
    merges a night's bands into one `raw/manifest.ecsv` (`--bands`);
    `validate_job.yaml` gates each row against its own reference
    (`GATES_REFERENCE=auto`). New `scripts/mosfire/measure_footprint.py`.

- **KOA census per band (S23c; D50; "Other bands" part H prompt 3):**
  `scripts/koa/search_mosfire_standards.py --filters` (band groups `Y`,
  `J` = J/J2/J3, `H`, `K`, or KOA filter names; default `J` reproduces the
  S14 census from its cache) queries KOA once per group, records 2MASS H
  and Ks beside J for every A0V star (`hmag_2mass`, `kmag_2mass`; D51),
  and writes all bands into the one table
  `keck_etcs/data/mosfire/koa_standards_candidates.ecsv` (a `filter`
  column; instrument-neutral columns and `meta`, H-1). The report adds a
  per-band block (candidate nights, usable wide-slit nights, WD / archive
  / A0V, era coverage, nights holding both a white dwarf and an A0V star
  for D52) and recomputes the design 9.2 TAP counts from the cached
  frames. `scripts/koa/find_validation_targets.py` reads every cached
  band, reports per band whether the Hennawi/Yang/Wang nights carry a
  same-night wide-slit standard, names the design 9.7 dev-suite fallbacks,
  and keeps `nights_validation.csv` to the J group until the multi-band
  manifests of S23d. The J rows of the census are unchanged.
  `check_docs.py` lists products rebuilt after a release (`<tag>-dev`)
  instead of failing on them.

- **Band-neutral refactor, part 2 (S23b; D49; "Other bands" part H
  prompt 2):** throughput products are named per band group,
  `mosfire_thru_<group>_<era>.ecsv` (`Instrument.throughput_pattern` must
  carry `{group}`; the S23a `legacy_throughput_group` stop-gap is gone),
  and one tag covers all groups (`mosfire-YYYY.MM`). New scripts:
  `scripts/mosfire/migrate_standards_table.py` (one-off: the J table's
  `zp_1200/1250/1300`, `thru_median_1117_*` columns recomputed from the
  committed curves as `zp_lo/mid/hi`, `thru_median_common`),
  `scripts/mosfire/stamp_release.py` (stamps a release tag into every
  non-provisional `index.yaml` entry) and `scripts/compare_release_outputs.py`
  (`compute()` on every example and fixture in this tree and in an old
  release tree, a table of the maximum relative difference per output
  field). `combine_throughput.py` writes one file per group and era with
  `bands` in the file `meta` and the `index.yaml` entry;
  `combine.combine_era` reports rows an earlier run flagged
  `excluded_3mad` as excluded again (a rerun reproduces the `meta`).
  `verify_release.py` checks every group (names, `bands`, `compute` per
  band, XTcalc per group, `zp_mid` against airmass); `verify_harvest.py`
  accepts the pin of any image in the operator guide, compares the curve
  `meta.row` without the combine-time flag, and re-harvests with the
  night's filter; `check_docs.py` accepts both tag forms and checks the
  per-group names. The trend and report scripts read `zp_mid`. The build
  scripts' development tag is `mosfire-2026.10-dev`.

- **Band-neutral refactor, part 1 (S23a; design 9, D49-D59; "Other bands"
  part H prompt 1):** the ETC and the calibration code no longer hard-code
  J. `Band` gains `group`, `order`, `zp_nodes_A`, `common_window_A`,
  `pwv_window_A`, `pwv_weak`, `edge_trim_frac`, `a0v_min_wave_A`, `lsf`
  and `footprint_provisional`; the MOSFIRE module defines **Y, H and K**
  (Y footprint measured on the dev suite's `Y_long`; H and K nominal and
  flagged provisional); `band` accepts `Y`, `J`, `J2`, `H`, `K`. A band
  group without a reduced standard runs on a **provisional placeholder**
  curve (`mosfire_thru_<group>_provisional.ecsv`, XTcalc 2012 efficiency
  with the filter divided out, `calib_version = provisional-xtcalc-2012`,
  `scripts/mosfire/build_provisional_throughput.py`) and every provisional
  item (footprint, LSF rule, throughput) is a `PROVISIONAL` warning.
  Harvest rows carry `zp_lo`, `zp_mid`, `zp_hi`, `thru_median_common`,
  `zp_nodes_A`, `common_window_A` instead of `zp_1200/1250/1300` and
  `thru_median_1117_1260/1250` (the committed J table is regenerated under
  the new names at the next release, S23b); `combine_era` and `trend` read
  the common window, edge trim and A0V cut per band from the instrument
  module (J values unchanged); `standards.a0v_model(band, mag)` scales the
  Vega model to the band's own 2MASS magnitude (J, H, Ks; D51) and records
  the J/band offset; `lsf_fwhm_pix(slit, band)` prefers measured rows of the
  band's group. J outputs are unchanged (regression fixtures identical).
  New examples `Y_point`, `H_point`, `K_point`.

- **Packaging (S18):**
  - `install_requires` is now what `keck_etcs.core` and `keck_etcs.etc`
    import: numpy, scipy, astropy, jsonschema and pyyaml;
  - PypeIt, matplotlib, IPython and boto3 move to the `calib` extra, and
    pytest to `test`;
  - `package_data` now also ships the per-standard curves
    (`keck_etcs/data/mosfire/throughput/standards/`), so a wheel holds all
    40 files of `keck_etcs/data/`.
- **PypeIt (S17):** `KeckMOSFIRESpectrograph.get_detector_par` takes
  `ronoise` from `SAMPMODE`/`NUMREADS` (Keck table; CDS 21 e-, was 5.8 for
  every frame).
  - Committed on `etc-fixes` as `38bb1b747d55a5b9205cbeb62734b0e870223990`;
    the patch is `nautilus/patches/pypeit_mosfire_ronoise.patch`.
  - Pinned by image 0.2.6 (S23d; pin `b0447b7` includes it). No released
    product uses it yet.
  - A CDS lamp-off flat pair gives 21.4 e- (`measure_read_noise.py`).
- **Docs (S18):**
  - `README.md` usage;
  - `nautilus/README.md` as the operator guide;
  - `docs/wmko_api_note.md`;
  - the design document "as built" (v0.5);
  - `scripts/check_docs.py`, which checks that the docs agree.
- **Continuous integration (PR #2):** `.github/workflows/ci.yml` with
  three jobs: the ETC without PypeIt on Python 3.11-3.14 (tests, the CLI
  on `examples/`, `scripts/check_docs.py`); the calibration pipeline with
  PypeIt installed at `nautilus/pypeit_pin.txt`; and the Sphinx build with
  warnings as errors plus `scripts/check_docs_build.py`.
  `keck_etcs/tests/test_standards.py` now skips without PypeIt instead of
  failing.
- **Developer docs (PR #2):** `docs/developer/calculations.md` (the
  calibration and ETC chains, equation by equation, with the PypeIt code
  each step uses) and `docs/developer/testing.md` (the suite and CI).

## Calibration releases

### mosfire-2026.10 (2026-10-27, plan S23b; J-only: the mosfire-J-2026.10 products under the per-group names and columns)

**No number changed.** Design D49 (Q50, Q68) organises the throughput
products by band group (grating order) and uses one calibration tag per
release for all groups. This release carries the J products of
`mosfire-J-2026.10`, from the same 20 standards with the same exclusions,
under the new names and columns, before any Y, H or K product exists, so
the rename is not held under the H and K timeline. The Y, H and K
placeholders (`mosfire_thru_{Y,H,K}_provisional.ecsv`, `calib_version =
provisional-xtcalc-2012`) are registered but are not part of the release.

**Era curves** (`keck_etcs/data/mosfire/throughput/mosfire_thru_J_<era>.ecsv`,
were `mosfire_thru_<era>.ecsv`; `scripts/mosfire/combine_throughput.py`
per group): pixel-wise identical to the mosfire-J-2026.10 files
(`wave`, `thru_median`, `thru_mad`, `n_std` differ by 0; same standards and
exclusions in `meta`). The `meta` gains `band_group`, `bands` and
`common_window_A`; the `index.yaml` entries carry `bands: [J, J2]`.

| Era | Standards used | Range [A] | Curve median 11900-12450 A | Before |
|---|---|---|---|---|
| 2012-04..2016-09 | 4 | 11633-13457 | 0.257 | 0.257 |
| 2017-02..2025-02 | 9 | 11172-13457 | 0.255 | 0.255 |
| 2025-04.. | 1 | 11171-12462 | 0.270 | 0.270 |

**Standards table** (`standards.ecsv`, 20 rows, 14 in the era curves):
the columns `zp_1200`, `zp_1250`, `zp_1300`, `thru_median_1117_1260` and
`thru_median_1117_1250` are replaced by `zp_lo`, `zp_mid`, `zp_hi` (the
zero point at the band's own nodes, `zp_nodes_A`: J 12000/12500/13000 A,
J2 11500/12000/12500 A) and `thru_median_common` (median of the
filter-free curve over `common_window_A` = 11900-12450 A, the quantity the
trend analysis calls `thru_common`). The values were recomputed from the
committed curves with the harvest's own functions
(`scripts/mosfire/migrate_standards_table.py`; the synced in-pod harvest
files carry the old columns and a local re-harvest could not reproduce
every `excluded_nonlinear` flag without all raw frames): for every J row
`zp_lo/mid/hi` equal the old `zp_1200/1250/1300` exactly, and for every J2
row `zp_mid` and `zp_hi` the old `zp_1200` and `zp_1250`. Every other
column is unchanged; each curve's `meta.row` carries the new columns.

**Standards added:** none. **Excluded:** as mosfire-J-2026.10 (four
nonlinear nights; 55 Dra 2014-10-05 and GD153 2025-01-25 by 3 MAD).

**Method changes:** none. **Detector table:** unchanged.

**Regression** (`scripts/compare_release_outputs.py` against `git archive`
of the mosfire-J-2026.10 tree; the table is in the part-H prompt log of
2026-10-27): `compute()` on the six examples and three fixtures. The six
J/J2 inputs agree on all 36 output fields with a largest relative
difference of 0; the only text differences are `meta.calib_version` and
the renamed file inside one warning. The Y, H and K examples have no
counterpart in the old release. The regression fixtures were regenerated
for the tag and that warning (same numbers).

**Checks:** `scripts/mosfire/verify_release.py` ALL CHECKS PASS (2012-2016
x J filter against XTcalc 2012: -2.9 percent; `zp_mid` against airmass in
J: 1.88 sigma); `scripts/mosfire/verify_harvest.py --reharvest` on LDS749B
2022-04-09: PASS; `scripts/check_docs.py` ALL CHECKS PASS.

**Reductions used** (image | digest | PypeIt pin; unchanged):

- `keck-etcs:0.1.6` | sha256:0c5e88fd838e24f9e658be3a01ffee276d80546df772a9da19da9c0ce912a357 | 8017f47997d6417d797be6d0a0358d7acb8918b5
- `keck-etcs:0.2.2` | sha256:920bd25f80483fe1c47ae70605bbd299229e6ecb593ca29f31fe5ebdfd746138 | fb4790520e4ccd49d39d42ed8438a614f307030b
- `keck-etcs:0.2.3` | sha256:99cc0d6379326b165270eba073a8b12ac716d71965a406781fe8a9293da42adf | fb6fb62c46383b09c5c13f1edcad97d3367fa0cd
- `keck-etcs:0.2.4` | sha256:258e52f474676199e52a9a3969861445c542fcc6790940792e9de5ccac31d13b | fb6fb62c46383b09c5c13f1edcad97d3367fa0cd
- `keck-etcs:0.2.5` | sha256:69591fcbdb595ca0b24438f9b4cf803d0ad48dedbe36141a8d211e3b3a4daed4 | bc18a3ba46d1d331da0875424c63999e578a4937

All images are under `gitlab-registry.nrp-nautilus.io/profx/`.

### mosfire-J-2026.10 (2026-10-08, plan S16; first release)

**Era curves** (`keck_etcs/data/mosfire/throughput/mosfire_thru_<era>.ecsv`,
`scripts/mosfire/combine_throughput.py`; filter-free, pixel-wise median):

| Era | Standards used | Range [A] | Curve median 11900-12450 A | Before |
|---|---|---|---|---|
| 2012-04..2016-09 | 4 | 11633-13457 | 0.257 | none (used 2017-2025) |
| 2017-02..2025-02 | 9 | 11172-13457 | 0.255 | 0.273 (LDS749B only, S10) |
| 2025-04.. | 1 | 11171-12462 | 0.270 | none (used 2017-2025) |

- 2017-02..2025-02 at 11600 / 12000 / 12400 A: 0.186 / 0.244 / 0.273 before,
  0.185 / 0.251 / 0.264 now; it now also covers 12462-13457 A.
- The ETC (`compute`) completes an era's curve over the band window from
  the nearest era that measured the rest, scaled by the median ratio over
  11900-12450 A (`Instrument.throughput_for_window`; 2025-04.. over J:
  12462-13457 A from 2017-2025 x 1.024; 2012-2016 over J2: 11172-11633 A
  x 1.005).
- The default (latest) era is now 2025-04.., one standard.

**Standards added:** 15 nights over S15a-S15b (`standards.ecsv` now has 20
rows; 14 enter the era curves).

- 2012-04..2016-09: Feige110 2014-06-01, HD95126 2014-11-23, HD18571
  2015-09-04, HD54601 2015-10-22.
- 2017-02..2025-02: HD74721 2017-11-05 and 2017-11-06, HD65158 2020-11-26,
  HD21379 2021-09-30, HD210501 2021-10-27, Feige110 2024-07-21, GD153
  2024-12-29 (J) and 2024-12-30 (J2), with LDS749B 2022-04-09 (S10).
- 2025-04..: GD153 2025-07-23.
- **Excluded:**
  - by the 26k ADU nonlinearity flag (harvest): HD159008 2015-04-28,
    HD74721 2016-04-17, HD133772 2017-06-15, HD21379 2021-09-28;
  - by 3 MAD on 11900-12450 A (D22): 55 Dra 2014-10-05 (0.196, J = 6.2 in
    1.45 s frames) and GD153 2025-01-25 (0.285; the J2 nights sit about
    5 percent above J, below).

**Method changes** (S16; Q&A S16-1 to S16-3):

- J rows only where the J filter is >= 0.9 of its peak; A0V rows only
  redward of 11900 A (`combine.EDGE_TRIM_FRAC`, `A0V_MIN_WAVE`). Reasons:
  - the J curve of the same white dwarf falls below its J2 curve by
    10 percent at 11650 A (the tabulated J cut-on is too high);
  - every A0V curve is depressed blueward of about 11900 A.
- The 3-MAD exclusion compares nights over 11900-12450 A, inside both
  filters.
- **D25 LSF:** `FWHM = sqrt((w / 0.292)^2 + 1.08^2)` pix (was
  `max(w / 0.277, 2.2)`); +3.9 percent at 0.7", -0.6 percent at 1.0"
  (measured 1" widths still take precedence).
- **D14 `sky_scale`:** unchanged (1.0); OH lines over Gemini per night
  0.43-0.91 (median 0.82), continuum not monitored.

**Known systematics:**

- J/J2 offset of about 5 percent in 11900-12450 A (filter curves agree
  with the measured J2/J ratio to 3-9 percent).
- The J cut-on and A0V blue depression above.
- 55 Dra low but unflagged.
- `zp_1250` against airmass in J: 1.9 sigma (limit 2).
- 2012-2016 x J filter is 2.9 percent below XTcalc's 2012 curve
  (x 75 / 72.37 m^2; -13 to +13 percent in 250 A bins).
  - *Corrected 2026-10-09.* The release first gave +3.6 percent. That
    compared our filter-free curve with XTcalc's efficiency, which includes
    the filter (`verify_release.py`, check 2).

**Detector table:** unchanged.

**Validation against this release** (S18, 2026-10-09;
`scripts/mosfire/validate_j0841.py` on the unchanged 0.1.6 products):

- J0841+3814 2022-04-09, ETC/measured S/N: 0.982 over the band and 0.990
  between OH lines. Both pass (20 and 10 percent); they were 0.996 and 1.003
  with the S10 curve.
- XTcalc comparison (`compare_xtcalc.py`): ratios 0.895-1.013 (0.7") and
  1.078-1.291 (1.0"); they were 0.891-1.005 and 1.067-1.271.

**Reductions used** (image | digest | PypeIt pin):

- `keck-etcs:0.1.6` | sha256:0c5e88fd838e24f9e658be3a01ffee276d80546df772a9da19da9c0ce912a357 | 8017f47997d6417d797be6d0a0358d7acb8918b5
- `keck-etcs:0.2.2` | sha256:920bd25f80483fe1c47ae70605bbd299229e6ecb593ca29f31fe5ebdfd746138 | fb4790520e4ccd49d39d42ed8438a614f307030b
- `keck-etcs:0.2.3` | sha256:99cc0d6379326b165270eba073a8b12ac716d71965a406781fe8a9293da42adf | fb6fb62c46383b09c5c13f1edcad97d3367fa0cd
- `keck-etcs:0.2.4` | sha256:258e52f474676199e52a9a3969861445c542fcc6790940792e9de5ccac31d13b | fb6fb62c46383b09c5c13f1edcad97d3367fa0cd
- `keck-etcs:0.2.5` | sha256:69591fcbdb595ca0b24438f9b4cf803d0ad48dedbe36141a8d211e3b3a4daed4 | bc18a3ba46d1d331da0875424c63999e578a4937

All images are under `gitlab-registry.nrp-nautilus.io/profx/`. Checks:
`scripts/mosfire/verify_release.py` (ALL CHECKS PASS).

### mosfire-J-2026.10-dev (development products, not a release)

- 2026-10-05 (S10): first per-era throughput,
  `keck_etcs/data/mosfire/throughput/mosfire_thru_2017-2025.ecsv` (era
  2017-02..2025-02), from one standard: LDS749B on 2022-04-09 (J2, 5" slit,
  MF.20220409.55932+MF.20220409.56084), reduced in-pod with image
  `gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.1.6`
  (`sha256:0c5e88fd838e24f9e658be3a01ffee276d80546df772a9da19da9c0ce912a357`,
  keck-etcs `b2883b6`), PypeIt pin `8017f47997d6417d797be6d0a0358d7acb8918b5`.
  It covers 11172-12462 A (J2 half-power band); band median 0.227
  (filter-free). Eras 2012-04..2016-09 and 2025-04.. have no standards yet
  and use it with a warning. It replaces the provisional XTcalc 2012 curve
  (`provisional-xtcalc-2012`, part 3 S9), which is removed.

## Regression fixtures

- 2026-10-27: regression fixtures regenerated (keck_etcs 0.2.5, throughput mosfire-2026.10): S23b release mosfire-2026.10 (J-only, D49): same numbers; calib_version tag and the throughput file name in one warning changed (mosfire_thru_2025-on.ecsv -> mosfire_thru_J_2025-on.ecsv); compare_release_outputs.py against mosfire-J-2026.10: largest relative difference 0
- 2026-10-08: regression fixtures regenerated (keck_etcs 0.2.5, throughput mosfire-J-2026.10): S16 first calibration release mosfire-J-2026.10: era curves for 2012-04..2016-09, 2017-02..2025-02 and 2025-04.. from 14 standards (combine cuts S16-1(b): J rows T >= 0.9 peak, A0V rows >= 11900 A; 3-MAD on 11900-12450 A); the default (latest) era is now 2025-04.., completed over J from 2017-2025 (Instrument.throughput_for_window); D25 LSF quadrature refit sqrt((w/0.292)^2 + 1.08^2) pix (+3.9 percent at 0.7 arcsec)
- 2026-10-04: regression fixtures regenerated (keck_etcs 0.1.6, throughput mosfire-J-2026.10-dev): S10: throughput mosfire_thru_2017-2025.ecsv (mosfire-J-2026.10-dev) replaces provisional-xtcalc-2012; LDS749B 2022-04-09 row from image keck-etcs:0.1.6 (sha256:0c5e88fd...2a357), PypeIt pin 8017f47; era names now 2017-02..2025-02 style
- 2026-10-04: regression fixtures regenerated (keck_etcs 0.1.6, throughput provisional-xtcalc-2012): first freeze (S9): examples J_point, J2_point, J_line against the provisional XTcalc throughput
