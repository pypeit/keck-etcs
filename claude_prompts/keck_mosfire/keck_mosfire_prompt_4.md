# Keck MOSFIRE implementation, part 4: validation (Phase 3)

## Goals

Turn the first sensfunc into the first throughput product, validate the ETC
against the measured S/N of the J0841+3814 frames, and compare with the
Keck XTcalc calculator as a sanity check. These are steps S10, S11 and S12 of
the plan. Everything here runs locally on products synced from the private
bucket (design D38).

Run order: after parts 2 and 3. S10 needs part 2's harvest (S6); S11 needs
S10, part 2's reductions (the in-pod products of S4b synced to the data
root, or the local S4 reference as fallback) and part 3's `compute()` (S9);
S12 needs only S9 and can run in parallel with S10 and S11. After S10, rerun
part 3's regression fixtures against the real throughput (see prompt 1).

## Context

- Design: `docs/keck_mosfire_design.md` (v0.3), sections 2 (D14, D16, D18,
  D22, D32, D36, D39, N5, N6), 4.5 (per-era combination), 5.2
  (`spectrum.shape = user`, `throughput.date`), 5.3.8 (sky per pixel), 5.5
  (versioning), 6.1 (validation procedure and the 20 percent criterion), 6.2
  (slow test and the XTcalc script), 8 (open items: `sky_scale`, effective
  aperture).
- Plan: `docs/keck_mosfire_implementation.md` (v0.3), steps S10, S11, S12.
- Data root `KECK_ETCS_DATA` (local mirror of `s3://keck-etcs`; the bucket
  is private, so every pull uses the user's AWS profile through
  `scripts/nautilus/s3_sync.py`): `mosfire/20220409/redux/Science/spec1d_*`
  (four J0841+3814 frames, 150 s each, ABBA +/-2", 1" slit, airmass 1.075,
  MCDS-16) and, for the fluxing and coadd, the `spec2d_*` files if needed:
  the dry run pushed them (`SPEC2D=1`) but they are not in the backup set
  (design 4.8.9), so pull them with `s3_sync.py pull mosfire/20220409
  --spec2d` while the night is on S3; `mosfire/20220409/sens/sens_LDS749B_20220409.fits`
  (the in-pod sensfunc; the local reference is the fallback);
  `external/xtcalc/XTcalc_dir/` (XTcalc data files: `mosfire/mosfire_J.txt`
  filter, `MosfireSpecEff/Jeff.sm.dat` throughput, `MosfireSkySpec/Jsky_cal_pA.sav`
  measured 2012 sky in erg/s/cm^2/A per spatial pixel through a 0.7" slit,
  `Mauna_Kea_sky/mktrans_zm_*.sav` transmission).
- Repo inputs from earlier parts: `keck_etcs/data/mosfire/throughput/standards.ecsv`
  and the per-standard curve (part 2, S6, with the six provenance columns);
  `keck_etcs/etc.py`, `bin/keck_etc`, the schemas and fixtures (part 3); the
  LSF measurement table (part 2, S13).
- PypeIt (the laptop checkout on `orig-hires-fixes`, MOSFIRE-equivalent to
  the pin `nautilus/pypeit_pin.txt`; run `scripts/check_pypeit_pin.py`
  first): `pypeit_flux_calib FLUX_FILE` with a
  `flux read ... flux end` block pairing spec1d files with the sensfunc;
  spec1d fields `OPT_WAVE`, `OPT_FLAM`, `OPT_FLAM_IVAR`, `OPT_COUNTS_SKY`,
  `OPT_COUNTS_SIG_DET`, `FWHM`, `FWHMFIT`, `S2N`; `pypeit_coadd_1dspec` for
  the four-frame coadd.
- XTcalc formulas (Prompt #1 log of `keck_mosfire_prompts.md`, and
  `XTcalc.pro` in the tarball): area 75 m^2; RN 15/sqrt(N_reads) e-; dark
  0.005; pixel 0.18" spatial and 0.24" dispersion; no slit losses; sky =
  measured 2012 spectrum scaled by slit width x object extent; two-point
  dither doubles background variance; S/N per spectral pixel, median over
  the band; Vega to AB offset +0.91 in J; worked example in
  `docs/MOSFIRE_XTcalc.pdf`: K band, 0.7" slit, 16 reads, m = 18.6 AB, 1000 s.
- Rules (CLAUDE.md): the user runs git; `conda run -n pypeit14`; scripts on
  disk; regression fixtures are regenerated only deliberately with a
  `CHANGES.md` line; log each prompt.

## Prompts

1. **S10: throughput product v0.** Implement `keck_etcs/calib/combine.py`
   following design 4.5: per era, the pixel-wise median of the per-standard
   telescope+spectrograph+detector curves on the common 1 A grid, the MAD,
   the count of standards, and whole-night exclusion beyond 3 MAD in band
   median; the per-era `meta` lists the distinct `image` and
   `pypeit_git_sha` values of the contributing rows (design D36). Run it on
   the one standard we have to write
   `keck_etcs/data/mosfire/throughput/mosfire_thru_2017-2025.ecsv`
   (`wave, thru_median, thru_mad, n_std` with `n_std = 1`, `thru_mad = NaN`)
   and register it in `index.yaml` as `calib_version = mosfire-J-2026.10-dev`.
   Then replace part 3's provisional XTcalc product: regenerate the
   regression fixtures with `scripts/regen_regression_fixtures.py`, add the
   `CHANGES.md` line (naming the image tag and pin behind the row), and
   remove the provisional warning. Verify: the file loads through
   `instruments/mosfire.py`; `compute` with `throughput.date =
   2022-04-09` echoes `meta.era = 2017-02..2025-02` and `meta.calib_version =
   mosfire-J-2026.10-dev`; `meta.images` in the era file equals the set of
   `image` values of the contributing rows; all tests pass. Log your work.

2. **S11: validation against J0841+3814.** Sync first: `s3_sync.py pull
   mosfire/20220409 --spec2d` (and confirm the products' `pypeit_git_sha`
   in `run_manifest.json` equals the pin). Write
   `scripts/mosfire/validate_j0841.py` that (a) fluxes the four science
   spec1d files with the LDS749B sensfunc (`pypeit_flux_calib`) and coadds
   them; (b) measures the S/N per pixel per frame and for the coadd as
   `OPT_FLAM * sqrt(OPT_FLAM_IVAR)`, the spatial FWHM from `FWHMFIT` times
   0.1798"/pix, and the fluxed sky spectrum from `OPT_COUNTS_SKY`; (c) runs
   `compute` with `spectrum.shape = user` on the smoothed fluxed spectrum,
   `slit_width_arcsec = 1.0`, the measured FWHM, `exptime_s = 150`,
   `n_frames = 4`, MCDS-16, ABBA, airmass 1.075, PWV from the telluric fit,
   `throughput.date = 2022-04-09`; (d) writes a comparison ECSV in 50 A bins
   and a figure of measured versus predicted S/N and of measured versus
   Gemini sky, each carrying the provenance of the products used. Add
   `keck_etcs/tests/test_validation_j0841.py` marked `slow` and skipped
   without `KECK_ETCS_DATA`. Two further checks belong here: the second test
   of decision N5 (compare the OH-line positions of the Gemini grid with the
   measured J2 sky from PypeIt, which is in vacuum), and the sky-level test
   of D14 (ratio of measured to Gemini sky in OH lines and between them, to
   set a default `sky_scale` if it is not 1). Verify: the median
   ETC/measured S/N ratio is within 20 percent over 1.117-1.260 um and
   within 10 percent between OH lines; record the fitted effective aperture
   factor and any `sky_scale` in `instruments/mosfire.py` with provenance,
   and append a results subsection to `docs/keck_mosfire_design.md` section
   6.1. Risk: the quasar is faint, so use the four-frame coadd and 50 A
   bins; if the criterion fails, diagnose (throughput, sky level, aperture,
   LSF) before changing any constant; if the in-pod and local reference
   spec1d differ (part 2 prompt 6), validate against the in-pod products,
   since those feed the calibration. Log your work.

3. **S12: XTcalc sanity comparison.** Write
   `scripts/mosfire/compare_xtcalc.py` that re-implements XTcalc's S/N
   formula in Python using XTcalc's own data files from the tarball (its
   filter, throughput x 0.89^2, measured 2012 sky, Gemini transmission at
   PWV 1.6 and airmass 1) and its constants, then tabulates XTcalc-mode S/N
   against ours for J magnitudes 17-23 AB, slits 0.7" and 1.0", 4 x 120 s
   MCDS-16 ABBA, 0.7" seeing, airmass 1.2. Verify: in XTcalc mode the script
   reproduces the PDF's K-band example within 10 percent (or the J example if
   you construct one from the PDF's stated inputs); each difference from our
   ETC is attributed to a known cause (throughput era, RN model 3.75 vs 5.8
   e-, slit loss, sky model, aperture 72.4 vs 75 m^2). Append the table and
   attribution as an appendix to `docs/keck_mosfire_design.md`. This is a
   script, not a CI test. Log your work.

4. **XTcalc bug?** Write a report of the possible XTcalc bug.  Include figures 
   if you can.  Be quantitative and stick to the facts.
   Write it to `docs/XTcalc_bug.md` and I will share it.
   Use Opus 5.5. Log your work

## Q&A

### S12 (2026-10-05)

1. **Can you confirm XTcalc's band-median quirk by running XTcalc itself?**
   The context:
   - Reading `XTcalc.pro`, its magnitude-mode "median S/N" uses
     `filt_index`, which is computed on the full 3072-pixel grid but applied
     to the 1650-pixel band arrays.
   - IDL clips the 729 out-of-range subscripts to the last (red-edge)
     pixel, so the reported value is about the 28th percentile of the
     band's S/N.
   - My Python port reproduces the manual's K-band line example (8.85
     against 9.1). That example is line mode, which the quirk does not
     touch, so the magnitude mode is unverified.

   One run of the IDL program (the IDL Virtual Machine, `run_XTcalc.sav`)
   would settle it. In the GUI, choose J band, slit 0.7", angular extent
   0.7", 4 exposures, 16 Fowler reads, "Use Magnitude" with 20.0 AB and
   Flat F_nu, "Determine Signal to Noise" with total time 480 s, and the
   default airmass and water vapour.

   The port predicts **S/N = 4.44** with the quirk, or 7.39 without it.
   *Default:* if you cannot run it, Appendix A keeps the quirk as "inferred
   from the source, not confirmed by running IDL".
>A. I have run the XTcalc GUI at WMKO with your config.  The S/N reported is 4.4 per spectral pixel

2. **Default `sky_scale`, given S11 and S12.** The numbers so far:
   - The sky model is the largest single input difference between the two
     calculators (step 6 of Appendix A: x1.09-1.45 in S/N).
   - On 2022-04-09 the measured sky is 0.86x Gemini in the OH lines and
     1.15-1.33x between them (design 6.1.1).
   - XTcalc's 2012 sky is 2.7x Gemini between the lines.

   The options:
   - (a) keep 1.0 until the part-5 sky-limited nights;
   - (b) adopt about 1.2 now, a continuum compromise, with a warning that
     the lines are overestimated;
   - (c) add separate `sky_scale_lines` and `sky_scale_continuum` to the
     schema (a design change, D14).

   *Default:* (a), with (c) proposed to you after S16 if the
   continuum-to-line ratio holds over many nights.
>A. use your default

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-10-05 (Prompt #1 / S10: throughput product v0 from LDS749B; the provisional XTcalc curve is removed; fixtures regenerated)

**Code:**

- `keck_etcs/calib/combine.py` (design 4.5, D22, D36). `combine_era(rows,
  curves, era, filters)`:
  - selects the era's rows (`start <= date < end`; rows already flagged
    `excluded` are skipped);
  - takes each row's filter-free curve: the harvest's `thru` when the
    filter was divided there, or else `thru_raw` / the band filter here
    (rows flagged `nofilter`). Either way it keeps only the filter's
    half-power band, where the division is stable;
  - applies the whole-night 3-MAD cut on band medians, only with >= 3
    nights;
  - takes the pixel-wise median, the MAD (NaN for one curve) and `n_std` on
    the 1 A grid;
  - writes `meta`: era, standards used and excluded, filter handling,
    `valid_range_A`, `band_median_era`, and the distinct `images`,
    `image_digests`, `pypeit_git_shas`, `keck_etcs_git_shas` and
    `pypeit_versions` of the contributing rows (D36). No PypeIt import.
- `scripts/mosfire/combine_throughput.py`: runs every era of
  `instruments/mosfire.py` and writes `mosfire_thru_<tag>.ecsv` for eras
  with standards. It registers each file in `index.yaml` (`calib_version
  mosfire-J-2026.10-dev`, `pypeit_version`, provenance) and adds
  `excluded_3mad` to the `flag` of excluded rows in `standards.ecsv`
  (updating that file's sha256).
- **Eras renamed** to the prompt's form, now that files are named by era:
  - `Era` gained a `tag`: `2012-04..2016-09` (tag `2012-2016`),
    `2017-02..2025-02` (`2017-2025`), `2025-04..` (`2025-on`);
  - `meta.era` echoes the name; the file is
    `mosfire_thru_{tag}.ecsv`, as the prompt asks for 2017-2025.
- `Instrument.throughput(era)`:
  - takes an `Era` and returns the era actually used, `valid_range_A` and
    warnings;
  - **an era without a curve uses the nearest era that has one** (the
    earlier on a tie), with the warning `no throughput curve yet for era
    X; using era Y`;
  - the provisional fallback and `provisional_throughput` are gone.
- `etc.compute`:
  - `meta.era` and `meta.calib_version` / `pypeit_version` come from the
    era actually used;
  - **new warning** when the band window extends more than one LSF FWHM
    beyond the curve's measured range ("held constant at the edge value");
  - the provisional warning is removed.

**Product:** `keck_etcs/data/mosfire/throughput/mosfire_thru_2017-2025.ecsv`.

- One standard: LDS749B, 2022-04-09, J2, 5" slit, image 0.1.6
  (`sha256:0c5e88fd…`), PypeIt pin 8017f47, keck-etcs b2883b6.
  `n_std = 1`, `thru_mad = NaN`.
- The row was harvested in-pod before S8 (`flag = nofilter`), so the J2
  filter was divided in `combine`. Coverage is 11172-12462 A, the J2
  half-power band.
- Filter-free throughput: 0.115 (11200 A), 0.165 (11500), 0.244 (12000),
  0.273 (12400), 0.301 (12462). Band median 0.227.
  - The XTcalc 2012 curve over the same window had a median of 0.218, so
    the level agrees within 4%.
  - Ours falls toward the blue: XTcalc's provisional curve was held flat at
    0.20 below 11700 A, while ours is 0.12-0.16 at 11200-11500 A. That is
    either a real loss at the J2 blue edge or a filter-curve and
    instrument cut-on mismatch where the J2 filter is steep (the air/vacuum
    assumption shifts the curve by 3.4 A). More standards, and J-filter
    nights, will tell.
- `index.yaml`: the new entry. **Removed:** the provisional file
  `mosfire_thru_provisional-xtcalc-2012.ecsv`, its index entry and
  `scripts/mosfire/build_provisional_throughput.py`; all three remain in
  git history.

**Fixtures:** the dry run showed 9242 differences in `reference_J`
(throughput -14% at the J blue end, meta era and calib). I regenerated them
with `scripts/regen_regression_fixtures.py --regen --note …`, which added
the CHANGES.md line naming image 0.1.6, its digest and pin 8017f47.
`CHANGES.md` also gains a "mosfire-J-2026.10-dev (development products)"
entry describing the curve and the replacement of the provisional one.

**Tests** (87 pass):

- `test_combine.py`, 4 tests:
  - one nofilter standard: the filter is divided, the curve is masked to
    the half-power band, MAD is NaN;
  - five standards with an outlier: the 3-MAD exclusion, median, MAD and
    `meta.images` = the set of images of the contributing rows;
  - no clipping below 3 nights; era boundaries;
  - the shipped era file's `meta.images` and `pypeit_git_shas` equal those
    of its rows in `standards.ecsv`.
- `test_instruments.py`: new era names; the era file and the fallback.
- `test_etc.py`: the era used, calib and pypeit versions, the fallback and
  coverage warnings, no provisional warning.

**Verify:**

- The file loads through `instruments/mosfire.py`.
- `compute` with `throughput.date = 2022-04-09` echoes `meta.era =
  2017-02..2025-02` and `meta.calib_version = mosfire-J-2026.10-dev`. J2
  with a 1" slit: no warnings, since a 2.5 A edge gap is under one LSF.
- `meta.images` = `['…/keck-etcs:0.1.6']` = the set of the contributing
  rows.
- All tests pass.
- `examples/J_point.json` (default date → era 2025-04.. → falls back to
  2017-02..2025-02): S/N per pixel 4.381 (4.334 with XTcalc). It now warns
  that J's 12462-13523 A is held at 0.301.

**For review:**

1. The era naming: name `2017-02..2025-02` plus file tag `2017-2025`. The
   prompt used both forms; the open era's tag `2025-on` is my choice.
2. Defaulting the latest era to the nearest era with a curve (with a
   warning) rather than failing.
3. Dividing the filter in `combine` for `nofilter` rows, restricted to the
   half-power band. Design 4.5 does not say this yet.
4. **J above 12462 A has no measured throughput**: it is a constant
   extrapolation until a J-filter standard is reduced (part 5). For J
   targets this matters more than any other open item.
5. Deleting, rather than archiving, the provisional product.

### 2026-10-05 (Prompt #2 / S11: validation against J0841+3814 — PASS: ETC/measured 0.996 band, 1.003 between OH lines)

**Inputs:**

- The in-pod products of image 0.1.6 (`sha256:0c5e88fd…`), already in the
  mirror from S6b's `s3_sync.py pull mosfire/20220409 --force --include
  'redux/*' …`. That pull includes all six `spec2d_*`, so no new pull was
  needed.
- `run_manifest.json`: `pypeit_git_sha` = `pypeit_pin` = 8017f47.
  `scripts/check_pypeit_pin.py`: PASS.
- **The target is J0841+3814_OFF, the bright blind-offset star** (J2 =
  15.9 AB intrinsic; S/N 51 per pixel in one frame), not the faint quasar
  the prompt anticipated.
- PypeIt paired the frames A–B (`bkg_id` 36↔37, 38↔39), so each spec1d is
  a difference frame, which matches the ETC's ABBA variance.

**`scripts/mosfire/validate_j0841.py`** (outputs in
`<night>/validation/`, never in `redux/`):

- **(a)** Copies the four spec1d to `validation/work/`, fluxes them
  (`pypeit_flux_calib`, a flux file with the LDS749B sensfunc) and coadds
  them (`pypeit_coadd_1dspec`) → `J0841_coadd_20220409.fits`.
- **(b)** Measured quantities:
  - S/N per frame = `OPT_FLAM*sqrt(OPT_FLAM_IVAR)`;
  - 4-frame S/N from the coadd (its grid is 1.3027 A against the native
    1.2922, so it is rescaled by sqrt(dlam ratio)) and as sqrt(sum of the
    frames' S/N^2), which agree to 0.7%;
  - FWHM = median `FWHMFIT` over the band, x 0.1798: 4.98, 5.04, 5.63,
    5.55 px → 0.952";
  - **the sky from the raw frames**: flat-fielded e-/s per (spatial pix,
    spectral pix), the objects masked (±3 FWHM), the central half of the
    slit, each column resampled with its own `waveimg`, the median of 1017
    columns and of the 4 frames. That is the ETC's b(lam).
  - PypeIt's `OPT_COUNTS_SKY` is the profile-weighted sky (from
    `extract_optimal`: the per-pixel sky x N_eff = 1/sum P^2), so it is not
    a sky level and was not used for D14.
- **(c)** The ETC input:
  - the coadd / the ETC's own convolved T_atm (masked below 0.3) / the model
    slit fraction (0.678 at 0.952"), with a 51-px running median;
  - `source.mag` = its own J2 AB magnitude, 15.933;
  - the tellurics, slit loss and normalization all cancel inside `compute`,
    so the signal is a closure and the test is the noise model, as design
    6.1 intends;
  - other inputs: 1" slit, FWHM 0.952", exptime 149.84 s (TRUITIME, not
    the nominal 150), 4 frames, MCDS-16, ABBA, airmass 1.076 (the mean of
    the four), PWV 1.616 mm (the standard's telluric fit, 9 h later),
    date 2022-04-09.
- **(d)** Writes `validation_j0841_bins.ecsv` (50 A bins: S/N measured,
  frames and ETC, ratios overall and between lines, sky measured and ETC,
  sky ratios, counts), `validation_j0841_summary.json` and
  `validation_j0841.png` (S/N, ratio, sky). Each carries the image, digest,
  PypeIt SHA, pin, keck-etcs SHA, sensfunc sha256, spec1d names, coadd
  sha256, keck_etcs version, `calib_version` and era.

**Results:**

- S/N per pixel, 1.117-1.260 um: measured 81.92 (coadd; 82.52 from the
  frames in quadrature), ETC 82.03.
- **ETC/measured: band 0.996, between OH lines 1.003. Both pass** (20% and
  10%).
  - Against the frames in quadrature: 0.991.
  - Per frame: 0.937, 0.950, 1.037, 1.056. The ETC used the median FWHM,
    and frames 0038/0039 had 5.6 px seeing.
  - Every 50 A bin is within ±10% except the telluric blue edge (0.908 at
    11170 A).
- Signal closure, counts in the slit ETC/measured: 0.999.
- **D14 sky:**
  - measured / (Gemini x T_sys): **0.859 in OH lines** (the S6b monitor
    gave 0.91); **1.332 between them**;
  - the between-line value is contaminated by OH wings: the cleanest bins
    (11370, 11720, 11820 A) give 1.14-1.19, and bins beside bright lines
    give 1.5-2.3 (the real LSF wings exceed the Gaussian model);
  - dark (0.008) is negligible against the 0.1-0.5 e-/s/pix excess, and
    MCDS has no bias pedestal;
  - with `sky_scale` = 1.33 the ratios become 0.968 and 0.978.
- **N5 (second test):** OH centroids measured − Gemini = **−0.070 A** (MAD
  0.098, 26 isolated lines), 0.05 px. The grid is vacuum-consistent.
- **D16:** scanning `length_fwhm` 0.6-3.0, the band ratio goes from 0.75
  to 1.01; the best value is 2.22. Within 1% for 1.48-2.44, within 2% for
  1.32-2.64. The default 1.5 gives 0.996.
- **Noise budget** (`scripts/mosfire/validation_noise_budget.py`):
  - between lines, this star's variance is 70% source, 16% sky, 13% read
    noise and 0.5% dark. **So the sky level and aperture are only weakly
    tested here.**
  - At J2 = 17.9/19.9/21.9 AB the sky share is 39/51/53%. A x1.33
    continuum would lower the S/N by 6/7.5/8%, and length_fwhm 2.22 changes
    it by 6/8/9%.

**Recorded** in `keck_etcs/instruments/mosfire.py`, with provenance:

- `VALIDATION_J0841` (all the numbers above);
- `SKY_SCALE_DEFAULT = 1.0`;
- `APERTURE_LENGTH_FWHM_DEFAULT = 1.5`.

**The schema defaults are unchanged**:

- One night gives lines x0.86 and continuum x1.15-1.33, which no single
  `sky_scale` reconciles.
- The bright star does not fix the aperture.
- The part-5 sky-limited quasar nights should decide both.
- `test_instruments.py` now checks that the recorded defaults equal the
  schema's and that 1.5 lies in the allowed aperture range.

**Docs:** design 6.1.1 "Results, 2022-04-09" (table and reading) is new;
section 8's sky-model item gets the S11 result, and an effective-aperture
item is added.

**Tests:**

- `keck_etcs/tests/test_validation_j0841.py`, three tests: the D18
  criterion; signal closure ±2% and N5 < 0.5 A; validation against the
  in-pod products (image, digest, pin).
- They are marked `slow`, skipped without `KECK_ETCS_DATA`, and excluded
  by default (`pytest.ini`: `addopts = -ra -m "not slow"`, marker
  registered).
- The run command is `KECK_ETCS_DATA=… pytest -m slow --run-slow`. The
  installed pytest-astropy plugin owns a `--run-slow` switch, and without
  it the tests were skipped. Result: **3 passed** (7 s, reusing the coadd).
- Default suite: 88 passed, 3 deselected.

**For review:**

1. Keep `sky_scale` = 1.0 for now, or adopt 0.86 (lines) or 1.2-1.3
   (continuum), or add separate line/continuum scales to the schema
   (a design change)?
2. The slow-test convention: `-m "not slow"` by default plus
   pytest-astropy's `--run-slow`.
3. The validation target is the offset star. For a sky-limited test,
   include the quasar itself if it was extracted on other nights (it was
   not detected here: one object per frame).

**Learned:**

- MOSFIRE spec1d `OPT_COUNTS_SKY` is the profile-weighted sky (x N_eff).
- `pypeit_coadd_1dspec` resampled to 1.3027 A/pix.
- pytest-astropy, installed in `pypeit14b`, skips `slow` tests unless given
  `--run-slow`.
- `conda run` does not forward stdin; inline Python must be written to a
  file.

### 2026-10-05 (Prompt #3 / S12: XTcalc comparison — port reproduces the manual's example to 3%; every difference attributed)

**`scripts/mosfire/compare_xtcalc.py`** (a script, not a CI test; about 4 s;
outputs `xtcalc_comparison.ecsv` and `xtcalc_attribution.ecsv` in
`$KECK_ETCS_DATA/external/xtcalc/comparison/`, with meta):

- A line-by-line Python port of XTcalc v2.3 on its own files (filter,
  `<band>eff.sm.dat` x KMRef^2, the `<band>sky_cal_pA` 2012 sky,
  `mktrans_zm_16_10`).
  - `mosfire_resolution` is reproduced: a 1 km/s velocity grid; IDL
    `interpol`, i.e. linear with linear extrapolation; a Gaussian of c/R;
    IDL `convol` edges set to 0; a 3072-pixel grid centred on the band.
  - The band is where the convolved filter exceeds 0.1. Line and magnitude
    modes are both ported, with XTcalc's constants (75 m^2, 0.18"/pix,
    15/sqrt(N) e-, dark 0.005, zp 48.59, J 1.31 / K 2.10 A/pix, R = rt x
    0.7 / slit) and the two-point dither.
- **Manual check.** `MOSFIRE_XTcalc.pdf` has no magnitude-mode example in
  its text. Its worked example is the Figure 1 GUI screenshot, a **line**
  case:
  - inputs (read at 300 dpi; the source FWHM is 30 km/s, not 90 as it first
    looked at low resolution, and the dark and RN values confirm it): K,
    0.7"/0.7", 1 exposure, 16 reads, 9e-18 at 6563 A, z = 2.3, 1000 s;
  - the port gives **S/N 8.85 against 9.1 (0.972) — within 10%, PASS**;
  - dark 58.92 and RN 12.87 are exact; signal 0.955, sky 0.963,
    throughput 0.989;
  - the GUI is v1.8 beta, from before the 2012-06-26 switch to the measured
    throughput and sky in the v2.3 files.
- **XTcalc magnitude-mode quirk** (found by reading the source):
  - `sn_index = filt_index = NONzero_index` is computed on the full grid
    (2379 indices, 1.049-1.360 um, since the extrapolated sky stays
    positive), but subscripts the band-cut arrays (1650 px). There is no
    `compile_opt strictarrsubs`, and IDL clips 729 (31%) of them to the
    red-edge pixel;
  - the "median" is therefore about the 28th percentile. At J = 20, 0.7",
    XTcalc displays 4.44, against a true band median of 7.39. The 7.39
    matches S9's independent hand calculation, which took the plain median;
  - not confirmed by running IDL: **Q&A item 1** asks you to run it once.
- **Table** (J 17-23 AB, 0.7" and 1.0", 4 x 120 s MCDS-16 ABBA, 0.7"
  seeing; XTcalc theta 0.7" at airmass 1; ours at airmass 1.2, PWV 1.6, the
  2017-02..2025-02 curve): keck_etcs / XTcalc-as-coded = 0.89-1.01 (0.7")
  and 1.07-1.27 (1.0"); keck_etcs / XTcalc's true median = 0.58-0.77.
- **Attribution** (cumulative swaps on one S/N engine; XTcalc's noise
  formula equals ours):
  - the quirk x1.34-1.74;
  - area and zp x0.97;
  - throughput x1.00-1.03;
  - atmosphere grid x1.000 (same Gemini source);
  - airmass 1.0→1.2 x0.99-1.00;
  - **sky model (2012 MOSFIRE → Gemini) x1.09-1.45**;
  - RN 3.75→5.8 and dark x0.84-0.97;
  - extraction 3.89→6 pixels x0.81-0.94;
  - **slit loss x0.56-0.76**;
  - sampling (dispersion, LSF, window) x1.04-1.12;
  - `compute` against the engine: x1.000. The chain closes to <0.1%.
- Every cause on the prompt's list is quantified (throughput era, RN 3.75
  against 5.8, slit loss, sky model, area 72.4 against 75), plus three it
  did not name: XTcalc's quirk, the extraction pixels and the sampling.

**Docs:**

- `docs/keck_mosfire_design.md` **Appendix A** (new): the manual check, the
  quirk, the table, the attribution and a reading.
  - XTcalc's quirk (x0.6) offsets most of what it omits or underestimates
    (slit loss, read noise, aperture), so the two calculators agree to
    0.89-1.27 largely by accident.
  - The sky model is the largest disagreement between the inputs, which
    feeds the `sky_scale` question.
- **Q&A** (S12) added: (1) run XTcalc once to confirm the quirk; (2) the
  default `sky_scale` options, with my default of keeping 1.0 until the
  part-5 nights.

**Notes:**

- `scripts/mosfire/xtcalc_hand_snr.py` (S9) is kept. Its plain-median value
  (7.39) agrees with the port's quirk-free median (7.392), an independent
  cross-check, but the port supersedes it.
- XTcalc's reported S/N for faint sources is set by the low-S/N red-edge
  pixel, so published XTcalc numbers are likely pessimistic by about 40%
  in J magnitude mode. Worth telling WMKO if it is confirmed.

**Learned:**

- XTcalc ships its manual as `XTcalc_dir/MOSFIRE_XTcalc.pdf`;
  `docs/MOSFIRE_XTcalc.pdf` in this repo does not exist (the context line
  is stale).
- `pdftotext` is on the workstation; `pypdf` is not in `pypeit14b`.

### 2026-10-05 (S12 follow-up: XTcalc band-median quirk confirmed by the user's GUI run)

- I wrote `docs/XTcalc_HOWTO.md` (how to run XTcalc with the IDL VM GUI or
  the command line, the test case, the expected values) for the user.
- The user ran the XTcalc GUI at WMKO with the Q&A S12-1 configuration
  (J, 0.7"/0.7", 4 exposures, 16 reads, 20.0 AB flat f_nu, 480 s, default
  airmass and PWV). It reported **S/N 4.4 per spectral pixel**.
  - The port predicted 4.437 with the quirk and 7.392 without it, so the
    quirk is **confirmed**, and the port's magnitude mode reproduces the
    real program to within the 0.1 display precision.
  - Together with the manual's line example (8.85 against 9.1), both modes
    of the port are now checked against XTcalc itself.
- Updated: design Appendix A (from "inferred" to "confirmed"); the
  `compare_xtcalc.py` docstring; `docs/XTcalc_HOWTO.md` (result recorded).
- Worth telling WMKO: XTcalc's magnitude-mode S/N for J continuum sources
  is about 40% below its own band median. It reports roughly the 28th
  percentile, weighted toward the red-edge pixel by the `filt_index`
  subscript clipping in `XTcalc.pro`.
