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

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
