# Keck/MOSFIRE: sensitivity analysis and exposure-time calculator design (J band as built; Y, H, K decided)

*Version 0.7 (J "as built" plus the Y/H/K extension, decided), 2026-10-26; v0.6 (extension proposed) was 2026-10-26 and v0.5 ("as built") 2026-10-09. Decisions come from the Q&A in
`claude_prompts/keck_mosfire/keck_mosfire_prompts.md` (rounds 1 and 2, all agreed; round
(d) on Nautilus, Q27-Q39, answered 2026-09-30; Calibrations, Q40-Q48,
answered 2026-10-04; Other bands, Q49-Q68, answered 2026-10-26). Readers: the PypeIt/keck-etcs
developers, future implementation sessions, and WMKO staff who will host the
web front end.*

*Change note, v0.2 (Prompt #5):* the PypeIt reductions now run as Kubernetes
Jobs on the NRP Nautilus cluster instead of on the workstation (new decision
D30; new section 4.8; section 4.2 rewritten; provenance fields added in 4.4
and 5.4; eight flagged decisions and new open items in section 8). The ETC
library design (section 5) is unchanged except for the provenance fields.
Conventions follow the user's PAB project (`Oceanography/python/PAB/nautilus/`)
and the PypeIt dev suite (`PypeIt-development-suite/nautilus/`).

*Change note, v0.3 (Prompt #6):* the user answered Q27-Q39. The eight
flagged decisions of v0.2 are now settled decisions D31-D38, with three
changes from the recommended defaults folded in: the bucket `keck-etcs`
exists and is **private** (D32: every read and write, local or in-pod, needs
the user's credentials; products are distributed through git, not S3 URLs);
PypeIt is pinned to a commit on **`develop`**, not `orig-hires-fixes` (D31,
D35: the local reference reduction must run on PypeIt code equivalent to
the pin for MOSFIRE); and the backup set is defined as the high-level
products only (new D39). Sections 4.2, 4.3, 4.8 and 8 updated accordingly;
the residual items in section 8 are verifications, not decisions.

*Change note, v0.3.1 (2026-09-30, follow-up):* the user will not switch the
laptop's PypeIt checkout to `develop`; it stays on `orig-hires-fixes` in
`pypeit14`, and no PypeIt development happens on this laptop. Checked
read-only: `git merge-base HEAD origin/develop` is the pin `f3a1f1d27`, HEAD
is exactly one commit ahead and none behind, and `git diff --stat
origin/develop...HEAD` touches only `pypeit/spectrographs/keck_hires.py`
(+131/-33). So the local MOSFIRE code path is identical to the pin. D35 and
the S0 check are therefore relaxed from "local checkout *is* the pin" to
"local checkout *contains* the pin and differs from it only in files
irrelevant to MOSFIRE J reductions"; the reference reduction records both
SHAs and the check result, and the S4b gate compares pins, not SHAs. The
registry project, deploy token, `docker login` and the S3 credentials are
confirmed done by the user (section 8). D31, D32, D39 unchanged.

*Change note, v0.4 (2026-10-04, Prompt #7/#8):* a **calibration monitor**
is added. Per night it records the spatial FWHM of the standard stars and
science objects, the brightness of the flat lamps at fixed wavelengths, and
the width and brightness of the calibration lines. The decisions come from
the user's answers to Q40-Q48 (all recommendations accepted) and are D40-D47.
The detail is in the new section 4.9. Also touched: 4.2 (layout), 4.4 (the
FWHM columns), 4.6 (monitor trends), 4.8.9 (the backup set already covers
the new file), 5.1 (package layout), 7 (definition of done, item 7) and 8
(open items). Two points matter for the design. MOSFIRE has no internal
flats, so its *dome* flats stand in for them. Its J band is
wavelength-calibrated on OH sky lines, not lamps, so the OH lines act as
the "arc" for widths and serve as a sky monitor for brightness. The Ne/Ar
lamp lines are an instrument monitor, but only on nights with lamp frames.

*Change note, v0.5 (2026-10-09, plan S18, "as built"):* this version
describes what was built for the MOSFIRE J milestone. It runs to keck_etcs
0.2.5, image 0.2.5 and the first calibration release, `mosfire-J-2026.10`
(`CHANGES.md`; results in the report). Changes from v0.4:

- **LSF (D25, 5.3.6):** quadrature form, `sqrt((w / 0.292)^2 + 1.08^2)` pix,
  fitted on 1" and 0.7" OH lines.
- **Combine (4.5):**
  - J rows are kept only where the J filter is >= 0.9 of its peak;
  - A0V rows only redward of 11900 A;
  - the 3-MAD test runs over 11900-12450 A;
  - an era curve is completed over a band window from the nearest era
    that measured the rest of it.
- **Pin (D31, 4.8.2):** on PypeIt `etc-fixes` (`bc18a3b`; `b0447b7` since
  image 0.2.6, S23d), not `develop`.
- **Workstation (D35):** the reference reduction and the local checks run
  on the Linux workstation, in `pypeit14b`, with the checkout at the pin.
- **Jobs (4.8.1, 4.8.4, 4.8.6):** per-index retries and exit-2 data
  outcomes.
- **PypeIt `ronoise` fix (D19):** done (S17).
- **Results** (validation, XTcalc comparison, throughput and monitor
  trends) moved to the report `reports/Keck_MOSFIRE_report_20261009.md` (2026-10-09); this document keeps
  the design.
- **Definition of done:** status in the report; section 8 updated.

The operator guide is `nautilus/README.md`, the WMKO interface
`docs/wmko_api_note.md`. `scripts/check_docs.py` checks that they agree with
the schemas, `index.yaml`, `CHANGES.md` and the outputs.

*Change note, v0.6 (2026-10-26, "Other bands" prompt #1):* the design is
extended to the **Y, H and K bands** in the new section 9. Nothing in
sections 1-8 is changed in substance; each section that the extension
touches carries a short *Other bands (v0.6)* pointer to the matching part
of section 9. The extension is written as **proposals P1-P15**, each tied
to a question (Q49-Q63) under "Q&A / Other bands" in
`claude_prompts/keck_mosfire/keck_mosfire_prompts.md`; they become settled
decisions (D48 on) once answered, and the implementation plan is written
after that. The numbers in section 9 come from
`scripts/mosfire/survey_other_bands.py` (PypeIt's wavelength templates, the
dev suite's Y long-slit reduction, the shipped filter curves, the Gemini
grid, the May-2012 MOSFIRE sky spectra and 2012 efficiency curves that ship
with Keck's XTcalc, and a KOA TAP count per filter). The two findings that
shape the extension: **K needs a thermal background term** (the measured
2012 sky exceeds the Gemini model by a 275 K grey body of effective
emissivity about 0.15, 10-20x the model at 2.3-2.4 um), and **H and K are
detector-limited** (their filter bands are wider than the 2048-pixel
footprint), so their ETC windows depend on the slit position.

*Change note, v0.7 (2026-10-26, "Other bands" prompt #3):* the user answered
Q49-Q68 (fifteen proposals, all agreed, three with notes; five follow-ups,
all agreed). The proposals P1-P15 of section 9 are now **decisions
D48-D62**, listed in section 2 and kept under their P numbers in section 9
with the answers folded in: the H and K `polyorder` starts at 5 and is set
by a measured test (D53, Q53/Q64); the ambient temperature of the K
thermal term comes from the header card `TUBETEMP`, present in every frame
we hold (D60, Q65); the Moon is computed by ephemeris and excluded only
from the Y sky-excess measurement (D61, Q61/Q66); the band-neutral refactor
ends with a J-only calibration tag before any H product exists (D49, Q68).
The work is plan Phase 7 (S23-S27, `docs/keck_mosfire_implementation.md`
v0.5) and three prompt docs, one per band
(`claude_prompts/keck_mosfire/keck_mosfire_prompt_{H,K,Y}.md`, run in that
order). Section 9.9 keeps the two items still to verify. The *Other bands
(v0.6)* pointers in sections 1-8 stand; "P*n*" there now means "D*n+47*".

## 1. Purpose and scope

Two deliverables share one code base:

- **(A) Sensitivity analysis.** Measure MOSFIRE's end-to-end throughput in the
  J band from spectrophotometric and telluric standard stars that we reduce
  ourselves with PypeIt, and track it over the instrument's life
  (2012-present) so that changes are seen rather than assumed.
- **(B) Exposure-time calculator.** A Python library, `keck_etcs`, with a
  single JSON-in, JSON-out entry point that predicts signal, noise, S/N and
  saturation for MOSFIRE spectroscopy from the measured throughput, the Gemini
  Maunakea sky model and the measured detector properties. WMKO will wrap it in
  a web page later; the core therefore has no plotting and no file-system side
  effects at call time.

Scope of the first milestone: MOSFIRE long-slit spectroscopy in the **J and J2**
filters, CDS and MCDS readout, point and extended sources, ABBA and stare
sequences. Out of scope for the milestone: Y/H/K (the code is band-agnostic
and they follow as standards are reduced), up-the-ramp readout, multi-slit
masks, imaging, and the other Keck instruments (which will reuse
`keck_etcs.core`).

*Other bands (v0.6):* the second milestone adds Y, H and K long-slit
spectroscopy, designed in section 9 (scope in 9.1; J3 and Ks stay out,
P1).

## 2. Settled decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Throughput is derived from standards we reduce ourselves; archived PypeIt sensfuncs and the 2012 XTcalc curves are cross-checks only. | Project-wide rule; provenance must be reproducible. |
| D2 | Two classes of standard: CALSPEC white dwarfs (GD71, GD153, G191-B2B, Feige 110, LDS749B, others in CALSPEC) as absolute anchors; A0V (HIP) telluric stars, fluxed as a Vega model scaled to their 2MASS J magnitude, as the dense time series. Cross-tie on nights with both. | WDs are rare in KOA; A0V stars were taken by almost every program. 2MASS J has a 0.02-0.03 mag floor. |
| D3 | LDS749B is used for 2022-04-09 but down-weighted in the long-term zero point. | It is faint (J ~ 15.0 Vega); its CALSPEC NIR segment is NICMOS at 23-310 A sampling. As a DBQ4 it has no Paschen lines, so it is a clean continuum. |
| D4 | Throughput is measured only from slits >= 3" wide (LONGSLIT-46x3, 46x5, `long2pos_specphot`). Narrow-slit standards are used to calibrate the slit-loss model. | Slit loss is negligible at >= 3" for typical seeing; narrow-slit standards would fold seeing into throughput. |
| D5 | Metrics: telluric-corrected zero point at 1.20, 1.25, 1.30 um and the band-median throughput over 1.117-1.260 um, each with airmass and fitted PWV. J, J2 and J3 are combined after dividing out the filter curves. | Same grating and detector; only the filter differs. |
| D6 | Instrument eras: 2012-04 to 2016-09 (original optics), 2017-02 to 2025-02 (after collimator repair), 2025-04 onward (after CSU repair). No discrete recoat epoch is modeled. | From the MOSFIRE news page. Keck I segments are recoated a few at a time. |
| D7 | Tellurics and PWV are fitted per standard by PypeIt's `IR` sensfunc; the zero point is defined at airmass 1 with the telluric model divided out; NIR continuum extinction is ignored. | No PWV in headers. The J continuum extinction is a few hundredths of a magnitude and mostly water, which the telluric model carries. |
| D8 | Sensfunc `polyorder` 5-7 (not PypeIt's default 13) for the J2 window; red trim at 1.260 um checked against the fluxed standard. | 13 is high for a 1400 A window. |
| D9 | The Hennawi/Yang/Wang quasar program nights are prioritized in the KOA search. | Same setup as our data, many nights, likely HIP A0V standards, and quasar spectra for validation. |
| D10 | Band-agnostic core; J and J2 first. | Same grating; Y/H/K follow. |
| D11 | JSON inputs and outputs as in section 5.2. | Web front end. |
| D12 | Read noise from the Keck table interpolated in log N_reads; dark 0.008 e-/s/pix; linearity flags at 26k, 37k, 43k ADU. The header `SATURATE=33000` is noted but not used. | Measured values beat 15/sqrt(N). |
| D13 | Readout modes CDS and MCDS-N in v1; schema fields ready for UTR; UTR added only if the KOA `SAMPMODE` census shows it above a few percent of science frames. | MCDS-16 is the default and recommended mode; PypeIt does not distinguish modes. |
| D14 | Sky from the Gemini Maunakea `mk_skybg_zm` grid with a user `sky_scale`; validated against the sky measured in our J0841+3814 frames. | Project decision for the NIR; OH varies by 2x through a night. |
| D15 | ABBA doubles the background, dark and read-noise variance per frame. | Each frame is differenced against a sky frame of equal exposure. |
| D16 | Moffat beta = 3.5 slit loss; extraction aperture 1.5 x FWHM along the slit; the factor is calibrated in validation. | PypeIt optimal extraction behaves like ~1.2 x FWHM; validation sets the effective value. |
| D17 | S/N per spectral pixel is the headline; S/N per resolution element is also returned. | Comparable with XTcalc. |
| D18 | Validation: reproduce PypeIt's measured S/N on J0841+3814 within 20 percent over the band. | Measured S/N, not another ETC, is the target. |
| D19 | PypeIt fix: `ronoise` from `NUMREADS`/`SAMPMODE`, drafted as a PypeIt branch. *As built (S17, 2026-10-09):* committed on `etc-fixes` as `38bb1b7` (patch in `nautilus/patches/pypeit_mosfire_ronoise.patch`, test `pypeit/tests/test_keck_mosfire.py`). It is not yet in the image pin. A CDS flat pair measures 21.4 e-. | PypeIt hard-codes 5.8 e-. |
| D20 | Package layout of section 5.1. | Instrument-agnostic core for the other Keck ETCs. |
| D21 | ECSV for 1-D tables under ~1 MB; FITS for grids; every file carries provenance metadata; `keck_etcs/data/index.yaml` indexes products. | Diff-able in git; provenance for WMKO. |
| D22 | "Current" throughput = pixel-wise median of the latest era's standards, with MAD; `date` selects an era; `throughput_scale` is a free factor; nights beyond 3 MAD in band median are excluded whole. | Robust to a bad night; era-aware. |
| D23 | Gemini grid rebinned (flux-conserving) to 0.05 nm over 0.95-2.45 um, one FITS file of ~3 MB committed to git. No git-lfs, no download on first use. | MOSFIRE's narrowest LSF is ~0.36 nm; the native 45 MB is too large for git. |
| D24 | Data root `KECK_ETCS_DATA` (default `~/Projects/PypeIt/keck-etcs-data`) with `mosfire/<YYYYMMDD>/{raw,redux,sens}`; only harvested tables and combined products are committed. | Raw KOA data and PypeIt outputs are large. |
| D25 | Gaussian LSF, FWHM = max(slit / 0.277"/pix, 2.2 pix) x dispersion; floor and slope measured from OH lines. *Revised 2026-10-04 (S13, user):* the slope was 0.24"/pix (XTcalc); OH lines of the 2022-04-09 1" slit give FWHM 3.61 px, R 2677 at 1.25 um, i.e. 0.277"/px. Interim until other slit widths (part 5) separate slope and floor. *As built (S16, 2026-10-08):* `FWHM = sqrt((w / 0.292)^2 + 1.08^2)` pix x dispersion, fitted on the 1" (3.56-3.61 px, 4 nights) and 0.7" (2.63 px) OH widths (`lsf_form = 'quadrature'`); a measured width for the slit still takes precedence. | Anamorphic factor 1.48 makes the dispersion-direction pixel 0.24", but the measured slit-limited LSF is 15% narrower than slit / 0.24". |
| D26 | Moffat beta 3.5; seeing FWHM quoted at the observing band, optional `seeing_wave_um` with lambda^-0.2 scaling; 2-D integral over the slit x aperture rectangle; extended sources are a top-hat convolved with the Moffat. | Standard practice. |
| D27 | Tests: analytic unit tests, a frozen JSON regression fixture, the XTcalc comparison as a script (not CI), the J0841 validation as a `slow` test. | See section 6. |
| D28 | Semantic versions for code, date tags for calibration products (`mosfire-J-2026.10`), both echoed in every output with `pypeit_version`; `CHANGES.md`; a calibration release touches only `keck_etcs/data/` and `CHANGES.md`. | WMKO can diff releases. |
| D29 | Definition of done in section 7. | |
| D30 | All PypeIt reductions (`pypeit_setup`, `run_pypeit`, `pypeit_sensfunc`, the per-night harvest) and the KOA raw-data downloads run as Kubernetes Jobs on the NRP Nautilus cluster, following the conventions of the user's PAB project and the PypeIt dev suite; the ETC library, its tests, the combine/trend/validation analyses and the KOA metadata search stay local. Section 4.8. | User decision, Prompt #5 (2026-09-30). Tens of KOA nights do not belong on a laptop; the user already runs PypeIt and PAB on Nautilus, and Nautilus S3 already hosts PypeIt's telluric grids. |
| D31 | Container image `gitlab-registry.nrp-nautilus.io/profx/keck-etcs:<semver>` (public registry, same as `profx/pab`), base `python:3.12`, built on the user's Linux workstation. PypeIt is installed from GitHub at a pinned commit on **`develop`** (recorded in `nautilus/pypeit_pin.txt`; `f3a1f1d27` = `origin/develop` on 2026-09-30, re-pinned only deliberately with an image tag bump; *as built:* the pin is `bc18a3b` on the PypeIt branch `etc-fixes` = `develop` + the MOSFIRE fixes found in reduction, a recorded exception until it merges, 4.8.2); `keck_etcs` installed from this repo; the PypeIt cache populated at build time (`pypeit_cache_github_data keck_mosfire`, `pypeit_install_telluric` on `TellPCA_3000_26000_R10000.fits`, `XDG_CACHE_HOME` pinned); PypeIt and keck_etcs SHAs baked in as `KECK_ETCS_GIT_SHAS` (ENV + label). Section 4.8.2. | Q29, Q30, Q31, Q38. `orig-hires-fixes` is not needed for this work; `develop` is PypeIt's integration branch. 3.12 is what the dev suite and PAB use; switch to 3.14 only if the dry run shows a numerical difference. |
| D32 | Storage: the **private** bucket `s3://keck-etcs` on Nautilus S3 (Ceph RGW; created by the user 2026-09-30; only the user has read/write) is the canonical store of raw and reduced data, laid out as in 4.2. Every access, local (`scripts/nautilus/s3_sync.py`) or in-pod (a mounted credentials secret in namespace `pypeit`), uses the user's credentials; nothing is public. Pods work on `emptyDir` scratch; no PVC. `$KECK_ETCS_DATA` is the local mirror. Products reach WMKO and collaborators through the committed ECSV/FITS files in git, not through S3 URLs. | Q27, Q28, Q35. A private bucket needs no policy work and cannot be overwritten by others; the committed products were always the primary record (D21, D28). |
| D33 | One night per pod as an Indexed Job over a night manifest (`completions = n_nights`, `parallelism` 4 to start); each pod idempotent (a night whose `run_manifest.json` exists on S3 is skipped unless `REPLACE=1`). Section 4.8.4. | Q34. PypeIt nights share no writer, so fan-out is safe; PAB's single pod protected a single SQLite writer. |
| D34 | Each night job harvests its own `sens_*.fits` (`keck_etcs.calib.harvest`) and pushes the per-standard row and curve to `mosfire/<night>/harvest/`; the local `scripts/mosfire/harvest_sens.py --merge` builds `standards.ecsv`. Harvesting a synced sens file locally gives the same row. | Q36. |
| D35 | *As built:* the local work moved to the Linux workstation (`pypeit14b`), whose PypeIt checkout sits at the pin itself, so the check passes with an empty diff. As designed: the 2022-04-09 night is reduced once locally in `pypeit14`, whose PypeIt checkout stays on `orig-hires-fixes` (user, 2026-09-30) and must be **MOSFIRE-equivalent to the image pin**: `scripts/check_pypeit_pin.py` (plan step S0) passes only if (1) the pin is an ancestor of the local HEAD and (2) the diff from the pin to HEAD, plus any uncommitted changes, touches only an allow-list of paths irrelevant to MOSFIRE J reductions (other spectrographs' `pypeit/spectrographs/*.py`, excluding `keck_mosfire.py`, `spectrograph.py`, `util.py` and `__init__.py`; `doc/`; `*.rst`; tests). It reports both SHAs and the file list; anything else fails with the offending files named. The reference reduction records `pypeit_git_sha` (its actual commit, `017bece06` today), `pypeit_pin` (`f3a1f1d27`) and the check result. That reduction gates the Nautilus dry run: `gates.py --reference` first requires the reference's recorded pin to equal the image pin with a passed check, then the in-pod LDS749B zero point must agree to 1 percent over 1.117-1.260 um. Every other night is reduced on Nautilus only. If the pin later moves to a commit that changes MOSFIRE code, the local check fails by design until the user brings the laptop checkout up to date or the reference is redone elsewhere. | Q37, Q38, follow-up 2026-09-30. On that date the local diff from the pin is `keck_hires.py` only (+131/-33), so the MOSFIRE code path is identical; requiring equal SHAs would force a branch switch the user does not want. |
| D36 | Reduction provenance on every product: `image`, `image_digest`, `pypeit_git_sha`, `keck_etcs_git_sha`, `job_name`, `s3_prefix`, in the per-standard table (4.4), the per-night `run_manifest.json`, the curve and era `meta` (5.4) and `CHANGES.md` (5.5). A locally harvested row carries `image = local`. | Q38. |
| D37 | KOA raw-frame downloads run as a Nautilus Job writing to `mosfire/<night>/raw/` on S3 with a manifest; the KOA metadata search stays local; fallback is a local download and `s3_sync.py push` if pods cannot reach KOA anonymously (checked first in plan step S14b). The 2022-04-09 dev-suite frames are pushed from the workstation. | Q33. |
| D38 | Stays local, in `pypeit14`, on synced products: `keck_etcs.core`, `etc.compute`, the schemas, tests, the Gemini grid build, combine, trend, the J0841 validation, the XTcalc comparison, the KOA metadata search, the PypeIt `ronoise` branch (off `develop`) and the documentation. Pods never call `compute()`; the core keeps its no-I/O rule. | Q39. |
| D39 | Backup (Nautilus is not backed up): only the high-level products needed for the sensitivity analysis and the ETC are copied from `s3://keck-etcs` to the Google shared drive `AIOcean:keck-etcs/` with `rclone`, after each successful batch of plan step S15 and again, under the calibration tag, at each release (S16). The set is defined in 4.8.9: `sens/`, `harvest/`, `run_manifest.json`, `run.log`, the pypeit file, `Science/spec1d_*`, `manifests/`, `runs/`. Excluded: raw frames (re-downloadable from KOA), `spec2d_*`, `Calibrations/`, PypeIt `QA/`. | Q32. The excluded items are large and re-derivable by re-running a night; the included ones are what the analysis reads and what a re-run would have to reproduce. |
| D40 | A **calibration monitor**: the instrument-agnostic module `keck_etcs/calib/monitor.py` (PypeIt imported only inside functions, like `harvest.py`) takes a night's PypeIt products (`Flat`, `WaveCalib`, `Tilts`, spec1d) and raw frames plus a per-instrument monitor config (wavelength nodes, lines, spatial region) and returns rows. The MOSFIRE J config is implemented now; LRIS gets its own config when LRIS starts. Section 4.9. | Q40. The four items apply to every Keck spectrograph; LRIS is next. |
| D41 | **Spatial FWHM** per extracted object and frame (standards and science objects): PypeIt's scalar `FWHM` in pixels and arcsec (x 0.1798), and the median of `FWHMFIT` within ±100 A of the zero-point nodes (J2: 1.15, 1.20, 1.25 um; J: 1.20, 1.25, 1.30 um), plus a `slitloss_gt1pct` flag where the D26 Moffat model predicts more than 1 percent slit loss at the frame's slit width. `seeing_fwhm_pix` in the standard row stays the median scalar FWHM. | Q41. Tests the lambda^-0.2 scaling (D26) and the "no slit loss at >= 3 arcsec" assumption (D4) on data; S11 needs the science FWHM anyway. |
| D42 | **Flat brightness.** Instruments without internal flats use their dome flats, tagged `flat_kind = dome` and read as a trend only. Metric: the lamp-on minus lamp-off rate in e-/s/pix, i.e. the median of `pixelflat_raw` divided by the per-frame exposure time, over the central 50 percent of the slit length, in ±50 A boxes at fixed vacuum wavelengths; also given per arcsec of slit width. Recorded with it: the lamp cards (MOSFIRE: `FLAMP1`, `FLAMP2`, `FPOWER`, `FLATSPEC`), `TRUITIME`, `SAMPMODE`, `NUMREADS`, slit width, filter, and the peak raw ADU of the lamp-on frames against the 1 percent non-linearity limit. | Q42. Dome-flat light passes through the telescope, so it is a throughput proxy that also carries lamp ageing. |
| D43 | Flat wavelength nodes are listed explicitly in each instrument's monitor config. MOSFIRE: every 250 A (J2: 1.125-1.250 um, 6 nodes; J: 1.150-1.325 um, 8 nodes). Generic default for the optical instruments: every 500 A. | Q43. 500 A gives J2 only two or three points. |
| D44 | **Calibration-line widths.** For MOSFIRE the OH lines in each night's `WaveCalib` are the "arc". The S13 fit (`measure_lsf.py`) moves into `keck_etcs.calib.monitor` and runs in-pod for every night and every slit with a wavelength solution, recording per (night, slit) the median Gaussian FWHM in pixels and A, its scatter, the slope with wavelength, the number of clean lines and `arc_source = OH`. Where Ne/Ar lamp frames exist (all `long2pos_specphot` nights, and afternoon arcs on a mask and filter that also has a wavelength image that night), the same fit runs on the lamp lines with `arc_source = lamp`. Lamp frames are downloaded from KOA only if the S14 census shows they are common for the relevant masks. | Q44. Wide-slit nights mostly measure the slit width, but that constrains the D25 slope and floor at other widths. |
| D45 | **Calibration-line brightness**, two metrics. (a) OH lines on every on-sky frame are a **sky monitor**: line flux in e-/s/arcsec^2, and in photons/s/arcsec^2/m^2 above the instrument (divided by that night's throughput where a sensfunc exists; the Gemini model's unit), with the frame's UT, airmass and the night's fitted PWV, plus the summed flux of all clean OH lines in the band. (b) Ne/Ar lines on lamp nights are an **instrument monitor**: line flux in e-/s per arcsec of slit width. Lines are chosen by explicit rules (4.9.4) by `scripts/mosfire/select_monitor_lines.py` on 2022-04-09 and the S15a pilot nights, then frozen in the monitor config with the script output as provenance. Lines may be added but are never removed. | Q45. OH varies about 2x through a night, so it does not measure the instrument, but it is the measurement D14 needs. |
| D46 | Monitor rows go to `harvest/<night>_monitor.ecsv`, written by the in-pod harvest. The file is part of the D39 backup set through `harvest/**`, which matters because `Calibrations/` is not backed up. `harvest_sens.py --merge` builds the committed `keck_etcs/data/mosfire/monitor/calib_monitor.ecsv` with the D36 provenance columns, registered in `index.yaml` and covered by the calibration-release rule (D28). `compute()` never reads it; only the LSF rows feed the instrument module, through `lsf_measurements.ecsv` as now. | Q46. Inside the package keeps it under `index.yaml` and D28. |
| D47 | Monitor metrics produce **flags, not gates**. In S16 each metric gets a per-era median and MAD, and nights beyond 3 MAD are flagged in the table, not failed. The only existing gate that touches calibrations, wavelength RMS, is kept. The flat-brightness trend is plotted beside the throughput trend with a correlation test. | Q47. If the dome-flat rate falls but the standards' throughput does not, the lamps are the cause; if both fall, the optics or the coatings are. |
| D48 | **Band set:** Y, H and K long-slit spectroscopy are built; J3 and Ks are not. | Q49 (P1). 4 and 10 public long-slit frames in KOA; Ks is an imaging filter. |
| D49 | **Band groups and one tag per release.** Throughput products are organised by grating order (`Y`, `J` = J/J2/J3, `H`, `K`): one era file per group, `mosfire_thru_<group>_<era>.ecsv`, the J files renamed `mosfire_thru_J_<era>.ecsv`; per-group common window, edge trim (0.9 of the filter peak) and A0V blue cut; one calibration tag per release for all bands, `mosfire-YYYY.MM`. The band-neutral refactor (S23) ends with a **J-only tag** whose products carry the current numbers under the new names and columns, checked by a `compute()` regression to 1e-6, so the rename is not held under the H and K timeline. | Q50 (P2), Q68. The filter-free throughput is a property of the grating order; a rename is a calibration-release change (D28). |
| D50 | **KOA census per band:** `search_mosfire_standards.py --filters Y,H,K` under the J reducibility and wide-slit rules, recording 2MASS H and Ks beside J. | Q51 (P3). The first TAP count gives 92 (H), 72 (K) and 13 (Y) wide-slit nights against 50 in J. |
| D51 | **A0V model scaled to the band's own 2MASS magnitude** (J for Y and J, H for H, Ks for K; PypeIt's `TMASS-J/H/K` curves), the J-scaled model kept as a cross-check column. | Q51 (P4). Avoids relying on the Vega model's colours over 1 um. |
| D52 | **Hydrogen-line mask** `hydrogen_mask_wid = 30` A in the H and K `.sens` files, 10 A in Y and J; checked on a night with both a white dwarf and an A0V star in H if the census finds one. No PypeIt change. | Q52 (P5). A0V Brackett lines at R ~ 3000 are 50-100 A wide. |
| D53 | **Sensfunc parameters per band:** one `.sens` file per band; `polyorder` 6 for Y; for H and K the **lowest order that passes a measured test**, starting at 5: `sensfunc_perturbation_test.py` extended to loop over orders 4-8 on each band's dev-suite reference night and on the first wide-slit KOA standard, taking the lowest order whose 1e-5 perturbation stability is below 1 percent and whose zero point differs from the next order up by less than 1 percent rms over the common window and 2 percent within 100 A of the edges; `tell_npca` by the same test (default 3); `extrap` 0; filter edges handled by the combine edge trim. The chosen order and the test table go into the `.sens` header and 9.3. | Q53 (P6), Q64. The user prefers a lower order for H and K if it holds; the test decides rather than a guess. |
| D54 | **Band-neutral metric columns:** `zp_lo`, `zp_mid`, `zp_hi` and `thru_median_common`, with the nodes and the common window in the row and in the instrument module (Y 1.00/1.05/1.10 um over 0.98-1.11; H 1.55/1.65/1.75 over 1.49-1.78; K 2.05/2.15/2.30 over 1.98-2.37; J as built); the J table regenerated under the new names at the S23 tag; PWV recorded where weak with `flag = pwv_weak`. | Q54 (P7). |
| D55 | **S3 layout and gates for multi-band nights:** manifests gain a `band` column, one row per (night, band); raw frames shared under `mosfire/<night>/raw/`; products under `mosfire/<night>/<band>/` for Y, H and K, J unchanged; idempotency per row; gate windows from the instrument module; throughput gate 0.5-1.6x XTcalc's 2012 median per band (Y 0.12-0.38, H 0.17-0.54, K 0.16-0.51). | Q55 (P8). |
| D56 | **Reference reductions from the dev suite** (`Y_long`, `longslit_3x0.7_H` and `_K`, `K_long`, `long2pos1_H`), locally first and then in-pod as each band's dry run; they give the H and K footprints, the per-band LSF, the K thermal continuum and the Brackett-mask test, and stay out of the throughput sample (D4). | Q56 (P9). |
| D57 | **Order of work:** H, then K, then Y, after the band-neutral refactor. | Q57 (P10), Q67. H has the largest wide-slit sample and no new physics. |
| D58 | **Schema and instrument module:** `band` adds `Y`, `H`, `K`; `Band` gains group, order, nodes, windows and LSF entries; `throughput_pattern` takes `{group}`; the era completion splices only within a group; per-band examples, fixtures and XTcalc comparisons. The ETC models the centred long slit; H and K are detector-limited, so an off-centre slit loses one band edge, which the ETC states but does not model. | Q58 (P11). |
| D59 | **LSF per band:** the J quadrature rule in pixels for Y, H and K with a warning until the monitor's OH widths give per-band slope and floor; `lsf_fwhm_pix(slit, band)` prefers a measured row of the band. | Q59 (P12). XTcalc's resolving powers imply a 0.7" image 5 percent narrower in H and K. |
| D60 | **Thermal background in K:** `eps_eff * Planck(T_amb)` added to the sky before `T_sys`, unattenuated by the atmosphere; defaults `eps_eff = 0.15`, `T_amb = 275 K`. The ambient temperature is the header card **`TUBETEMP`** (telescope tube, degrees C; present in all 238 frames we hold, 2012-2025, median 1.6 C, range -3.4 to +4.9): the monitor records `tube_temp_C` per frame in every band; the per-night K fit holds T at the night's median `TUBETEMP` and fits `eps_eff` alone (the two are degenerate, about 50 percent per 5 K); the ETC input `ambient_temp_C` defaults to the K sample's median `TUBETEMP` (2 C provisionally) and the output gains `thermal_e`. If the fitted `eps_eff` correlates with `TUBETEMP`, the model is wrong and T belongs to something else (the instrument's warm window). | Q60 (P13), Q65. The 2012 K sky exceeds the Gemini model by a 275 K grey body of emissivity 0.12-0.15, 10-20x the model at 2.3-2.4 um. |
| D61 | **Sky continuum excess per band:** an additive curve `E_band(lam)` measured from our own reduced frames (Sun below -18 deg, no object in the window, 10th percentile per 100 A, median over nights), shipped as `sky/mosfire_sky_excess_<band>.ecsv`, scaled with the Gemini sky by `sky_scale`; zero with a warning until measured. **Moon:** no header card exists; `moon_alt_deg`, `moon_illum` and `moon_sep_deg` are computed by ephemeris (as the Sun's altitude already is) and recorded for every band, and a cut is applied **only to the Y curve**: dark frames (Moon below the horizon or illuminated less than 30 percent) when at least 20 of them over at least 3 nights exist, otherwise all frames with `moon_included = true` in the metadata and the dark-minus-moonlit difference reported. J, H and K use all frames. | Q61 (P14), Q66. The user: the Moon should not matter in H or K; avoid it only in Y if enough exposures remain. |
| D62 | **Saturation output** `saturation.frac_pix_nonlinear_1pct`, the fraction of spectral pixels whose brightest spatial pixel exceeds 26k ADU per frame. **Validation and done:** one validation night per band at 20 percent (K: thermal continuum within 30 percent); done means >= 10 wide-slit standards over >= 2 eras per band (Y >= 5), `compute()` with fixtures and examples per band, the thermal term and the saturation fraction, one release tag, and this design "as built". | Q62 (P15), Q63. In H the brightest OH lines reach 26k ADU in about 1.5-2 min through a 0.7" slit. |

Decisions made while writing this document (not in the Q&A; flagged for
review):

- **N1.** Keck effective collecting area 72.3674 m^2, PypeIt's `KeckTelescopePar`
  value; XTcalc uses 75 m^2. The 3.5 percent difference moves the throughput,
  not the predicted counts, so it must be consistent between analysis and ETC.
- **N2.** Per-band wavelength window = filter half-power bandpass intersected
  with the 2048-pixel detector window at the LONGSLIT-46 position. PypeIt's
  wavelength templates span 2600-3000 pixels because they are stitched across
  CSU slit positions; they are not the footprint of one slit.
- **N3.** A0V stars are fluxed by scaling PypeIt's Vega spectrum
  (`vega_tspectool_vacuum.dat`) so that its synthetic 2MASS J magnitude
  matches the star's 2MASS J. PypeIt's `VegaStandard` scales by V only, so this
  lives in `keck_etcs.calib`.
- **N4.** Sky-grid interpolation is linear in airmass and linear in log(PWV);
  values outside 1.0-2.0 airmass or 1.0-5.0 mm are clipped with a warning.
- **N5.** All wavelengths are vacuum, PypeIt's convention. The Gemini/ATRAN
  grids are treated as vacuum.
- **N6.** Atmospheric transmission is applied to the source only, not to the
  sky emission, which the Gemini model already gives as seen from the ground.
- **N7.** Exposure-time mode solves the per-frame time for a target S/N at
  fixed `n_frames` (quadratic, section 5.3.9), as XTcalc does.
- **N8.** The KOA search will live in `claude_prompts/koa_search_prompts.md`
  (to be created).

The eight decisions flagged in v0.2 while moving the reductions to Nautilus
were put to the user as Q27-Q39 and are now settled as D31-D38 above (with
the bucket, PypeIt branch and backup answers folded in, and D39 added for
the backup set). Section 4.8 carries the detail.

*Other bands (v0.6; decided v0.7):* the proposals P1-P15 of section 9 are flagged the
same way and put to the user as Q49-Q63. None is settled yet.

## 3. Instrument facts and sources

| Quantity | Value | Source |
|----------|-------|--------|
| Telescope area | 72.3674 m^2 (eff. aperture) | PypeIt `telescopes.py` |
| Detector | Teledyne H2RG HgCdTe, 2048x2048, 2.5 um cutoff; never replaced | Keck MOSFIRE pages; Kulas et al. 2012 |
| Plate scale | 0.1798 "/pix spatial (header `PSCALE` 0.1799); 0.24 "/pix in dispersion (anamorphic 1.48, header `FCANAMOR`) | PypeIt; XTcalc; headers |
| Gain | 2.15 e-/ADU (`SYSGAIN`) | Keck detector page; headers |
| Read noise (e- rms) | CDS 21; MCDS-4 10.8; -8 7.7; -16 5.8; -32 4.2; -64 3.5; -128 3.0 | Keck detector page. Lab values (Kulas+12): 17.2, 8.9, 6.5, 4.9, 3.8, 3.3 |
| Dark current | < 0.008 e-/s/pix (PypeIt: 28.8 e-/pix/hr) | Keck detector page; PypeIt |
| Linearity | 1% to 26k ADU (56k e-); 5% to 37k ADU (80k e-); saturation 43k ADU (97k e-) | Keck detector page. Header `SATURATE=33000` differs; not used |
| Persistence | ~0.04%, time constant ~600-660 s | Keck detector page; Kulas+12. Not modeled |
| Minimum integration | 1.455 s (`READTIME` 1.45479 s) | Keck detector page; headers |
| Readout modes | `SAMPMODE` 1 Single, 2 CDS, 3 MCDS, 4 UTR; `NUMREADS` = reads per group | Headers; Kulas+12 (MCDS recommended for spectroscopy) |
| Dispersion (A/pix) | Y 1.08; J 1.30; J2 1.30; H 1.63; K 2.17 | PypeIt `reid_arxiv` templates (`scripts/mosfire_band_footprints.py`); XTcalc agrees |
| Filters (center/FWHM, um) | Y 1.048/0.152; J 1.253/0.200; J2 1.181/0.129; J3 1.288/0.122; H 1.637/0.341; K 2.162/0.483; Ks 2.147/0.314 | Keck filters page (ASCII curves available there) |
| J2 clean window | 1.117-1.260 um | PypeIt `keck_mosfire.tweak_standard` (second-order / edge contamination outside) |
| Resolving power | R ~ 3300 at 0.7" in J (XTcalc R-theta 2317"); to be re-measured from OH lines | XTcalc; D25 |
| Eras | 2012-04-04 first light; 2016-09-15 to 2017-02-13 offline, collimator element repaired; 2020-02 guider detector replaced (not science array); 2025-02-11 to 2025-04-29 CSU inoperable (1" long slit only); 2026-08-26 warm for cold-head servicing | MOSFIRE news page |
| Keck mirror reflectance used by XTcalc | 0.89 per surface in J (two surfaces) | XTcalc.pro |
| XTcalc J throughput (2012) | end-to-end peak 0.32, median 0.28 over 1.117-1.373 um | XTcalc `Jeff.sm.dat` x 0.89^2 |

*Other bands (v0.6):* the same facts for Y, H and K (grating order,
dispersion, filter band, footprint, window, AB-Vega offset, calibrators,
sky levels, XTcalc throughput, KOA counts) are tabulated in 9.2.

## 4. Sensitivity analysis (A)

### 4.1 Standards and KOA selection

Search KOA (koa.ipac.caltech.edu) for MOSFIRE spectroscopy with
`MASKNAME LIKE 'LONGSLIT%'` or `long2pos%`, `FILTER` in {J, J2, J3}, and
`GRATMODE = spectroscopy`, then match `TARGNAME` and coordinates (20 arcmin
tolerance, as PypeIt does) against:

1. CALSPEC white dwarfs and other CALSPEC stars with V < 15 (PypeIt's
   `calspec_info.txt`), plus the ESO/X-shooter set (GD71, GD153, Feige 110,
   LTT stars). PypeIt resolves these automatically.
2. A0V stars: any `TARGNAME` matching `HIP`, `HD`, or a SIMBAD A0V within the
   tolerance. For each, record the 2MASS J magnitude and error.

For every candidate record: date, KOA ID, `MASKNAME` (slit width and length),
filter, `SAMPMODE`, `NUMREADS`, `TRUITIME`, airmass, nod pattern and offsets,
program ID, and whether calibrations (dome flats lamp on/off) exist on the
same night. Standards on slits >= 3" enter the throughput sample (D4); the
rest enter the slit-loss sample. The `SAMPMODE` histogram of all science frames
answers the UTR question (D13). The search is its own prompt doc (N8); the
priority nights are the Hennawi/Yang/Wang quasar program (D9). *Settled by
the KOA census (2026-10-05, `scripts/koa/search_mosfire_standards.py`;
the question to Josh Walawender (WMKO) is dropped, user):* the 5" slit was
not routine for standards, so `long2pos_specphot` (its 4" bars) carries the
throughput sample. A night is *reducible* only with a wavelength
calibrator: narrow-slit on-sky frames of >= 55 s that night for the OH
lines, or Ne/Ar arcs on a long2pos mask. The counts are in the report
(`reports/Keck_MOSFIRE_report_20261009.md`, section 1).

*Other bands (v0.6):* the census is re-run per band with the same rules
(P3, 9.3); a first TAP count gives 92 (H), 72 (K) and 13 (Y)
`long2pos_specphot` nights with star-like target names, against 50 in J.

### 4.2 Reduction workflow, S3 layout and data root

Reductions run on Nautilus (D30). The canonical store is the private bucket
`s3://keck-etcs` on Nautilus S3 (D32; endpoint
`https://s3-west.nrp-nautilus.io`, in-cluster
`http://rook-ceph-rgw-nautiluss3.rook`; only the user's credentials can read
or write it, so `s3_sync.py` runs with the user's AWS profile and pods mount
a credentials secret), laid out per instrument and night:

```
s3://keck-etcs/
  mosfire/<YYYYMMDD>/raw/*.fits, manifest.ecsv     # KOA frames (download Job, D37) or pushed from local
  mosfire/<YYYYMMDD>/redux/<night>.pypeit           # the pypeit file actually run
  mosfire/<YYYYMMDD>/redux/Calibrations/            # WaveCalib*, Flat*, Edges*, Tilts* (for S13 and QA)
  mosfire/<YYYYMMDD>/redux/Science/spec1d_*.fits    # spec1d always; spec2d only when SPEC2D=1
  mosfire/<YYYYMMDD>/redux/QA/                      # PypeIt QA PNGs
  mosfire/<YYYYMMDD>/sens/sens_*.fits, *_QA.png     # pypeit_sensfunc output and telluric QA
  mosfire/<YYYYMMDD>/harvest/<standard>_<date>.ecsv # per-standard row + curve (D34)
  mosfire/<YYYYMMDD>/harvest/<night>_monitor.ecsv   # calibration-monitor rows (D46, 4.9)
  mosfire/<YYYYMMDD>/run_manifest.json, run.log     # provenance and the tee'd pod log (D36)
  manifests/nights_<batch>.csv                      # night manifests that drive the Indexed Jobs
  runs/<job_name>/status.ecsv                       # per-night status written by the job
```

The local data root `KECK_ETCS_DATA` (default
`~/Projects/PypeIt/keck-etcs-data`, never in git) keeps the same
layout and is a *mirror* of the bucket, filled by
`scripts/nautilus/s3_sync.py pull mosfire/<night>` (sens, harvest, spec1d and
`Calibrations/WaveCalib*` by default; raw and spec2d on request). It also
holds the external inputs that never go to S3:

```
$KECK_ETCS_DATA/
  external/xtcalc/XTcalc_dir/          # Keck XTcalc tarball, unpacked (Gemini grids)
  mosfire/<YYYYMMDD>/{raw,redux,sens,harvest}/   # synced from S3 (raw only for 2022-04-09 and on request)
```

Per night, one pod of the Indexed Job (D33) runs `scripts/mosfire/reduce_standard.py`
on `emptyDir` scratch: pull `raw/` from S3; `pypeit_setup -s keck_mosfire -r
raw/ -d redux/ -c all`; patch the generated pypeit file (standards longer
than 20 s must be retyped `standard`, because PypeIt types standards by
`exptime < 20 s`; nod pairs get `comb_id`/`bkg_id` as in
`keck_mosfire_j2_long.pypeit`); `run_pypeit`; `pypeit_sensfunc -s <repo>.sens
spec1d_<standard>.fits -o sens/sens_<standard>.fits`; run the gates
(`nautilus/gates.py`, 4.8.7); run the harvest (D34); write
`run_manifest.json`; push everything listed above to S3. The `.sens`
parameter file is repo-owned (`keck_etcs/data/pypeit_par/keck_mosfire_J.sens`,
one per band) and ships inside the image. The same `reduce_standard.py` runs
locally in `pypeit14` for the 2022-04-09 reference reduction (D35); the only
difference is the `--s3` flags. Locally, `scripts/mosfire/harvest_sens.py
--merge` folds the synced harvest rows into the per-standard table (4.4). Only
the harvested tables and the combined products are committed.

### 4.3 Sensfunc and telluric settings

PypeIt `IR` algorithm (`pypeit_sensfunc --algorithm IR`) with:

```
[sensfunc]
  algorithm = IR
  polyorder = 6          # D8; PypeIt default for MOSFIRE is 13
  extrap_blu = 0.0
  extrap_red = 0.0
  [[IR]]
    telgridfile = TellPCA_3000_26000_R10000.fits
    maxiter = 2
    tell_npca = 3        # PypeIt default 5; see below
```

*`tell_npca = 3` (user, 2026-10-02, S4b).* Over the J2 window the default
5-component telluric PCA is degenerate. The differential-evolution fit
(seed 777) is deterministic, but 1e-5 input changes move the per-pixel zero
point by up to ~5% (5-95 percent range). 3 components are stable to <1%,
with a lower chi^2 (1155 against 1173 on the 2022-04-09 coadd) and the same
telluric residual near 1.13 um and red-edge pattern
(`scripts/mosfire/sensfunc_perturbation_test.py`; log of part 2,
prompt #6).

The telluric grid (6 MB) is fetched by PypeIt from its S3 host into the
astropy cache (`~/.cache/pypeit` on the workstation) on first use. That host
is Nautilus S3 itself: PypeIt's `pypeit/data/s3_url.txt` reads
`s3-west.nrp-nautilus.io`, and the grid is the public object
`s3://pypeit/telluric/atm_grids/TellPCA_3000_26000_R10000.fits`. The image
installs it at build time (D31), so pods never download it. PypeIt's
`tweak_standard` already zeroes J2 outside 1.117-1.260 um and masks Paschen
lines in DA white dwarfs and A0V stars (`mask_recomb`). The telluric fit
returns the model parameters (`TELL_THETA`: pressure, temperature, water,
airmass, resolution, shift, stretch); we record water (PWV) and airmass. For
A0V stars the "standard" spectrum is built as in N3 and passed through the
same machinery.

*Other bands (v0.6; D53):* one `.sens` file per band with `polyorder` 6 (Y)
and a measured choice for H and K starting at 5 (9.3, P6),
`tell_npca` set by the perturbation test per band, and a wider
hydrogen-line mask for the Brackett series in H and K (P5, P6, 9.3).

### 4.4 Metrics

PypeIt's zero point is the AB magnitude of a source producing 1 e-/s/A at the
detector, after dividing out the telluric model, so it refers to airmass 1
(D7). From it,

```
N_lam [e-/s/A]      = 10^(-0.4 (m_AB(lam) - ZP(lam)))
T_sys(lam)          = h * lam * 10^(0.4 (ZP(lam) + 48.6)) / A        (cgs; lam in cm, A = 7.23674e5 cm^2)
```

which is PypeIt's `flux_calib.zeropoint_to_throughput`. `T_sys` is the
end-to-end fraction of photons above the atmosphere that become electrons:
telescope, instrument, filter and QE. Per standard we store, in one ECSV row:

`date, mjd, koa_id, standard, std_class (WD|A0V), std_model (calspec file or "vega+2MASS J=..."), filter, slit_width, slit_length, sampmode, numreads, exptime, airmass, pwv_fit, seeing_fwhm_pix (PypeIt FWHM), zp_1200, zp_1250, zp_1300, thru_median_1117_1260, thru_curve_file, pypeit_version, keck_etcs_version, image, image_digest, pypeit_git_sha, keck_etcs_git_sha, job_name, s3_prefix, flag`

(the six columns from `image` to `s3_prefix` are the reduction provenance of
D36; a row harvested from a local reduction carries `image = local`)

*As implemented in S6 (2026-10-04; `keck_etcs.calib.harvest`):*
- **Extra column `thru_median_1117_1250`,** after `thru_median_1117_1260`:
  the same median over the window S5 found free of red-edge artefacts.
- **`zp_*` masked where the zero-point fit does not reach;** for J2 that
  is `zp_1300`.
- **`pwv_fit`** is the PWV at which the Gemini grid (N4, at the sensfunc's
  airmass, smoothed to the fitted resolution) best matches PypeIt's fitted
  telluric transmission. The PCA telluric model fits no PWV.
- **`seeing_fwhm_pix`** is the median PypeIt spatial FWHM of the
  standard's extracted objects. *From v0.4 (D41)*, the per-frame scalar
  FWHM, the `FWHMFIT` medians at the zero-point nodes and the slit-loss
  flag go in the monitor table (4.9.1), not in this row.
- **`koa_id`** joins the KOA IDs of the standard's frames with `+`.
- **`slit_length`** is in CSU bars (from `LONGSLIT-<bars>x<width>`).
- **`flag`** is comma-separated: `ok`, `nofilter` (no filter curve
  divided; the curve's `thru` is masked) or `pwv_extrapolated`.
- **The per-night harvest writes two files to `harvest/`:**
  `<standard>_<date>_row.ecsv` and `<standard>_<date>.ecsv`. The curve has
  columns `wave` (1 A grid, 9000 + k A), `zeropoint`, `thru_raw`,
  `filter_trans` and `thru`, with the row and the provenance in its
  `meta`.

and the full `T_sys(lam)` curve on a common 1 A vacuum grid in a per-standard
ECSV under `keck_etcs/data/mosfire/throughput/standards/`. Filter curves are
divided out before combining J, J2 and J3 (D5), so the stored curve is
"telescope + spectrograph + detector" and the filter is re-applied by the ETC.

*Other bands (v0.6):* the zero-point nodes, the band-median window and the
PWV window become per-band values of the instrument module, and the row
columns take band-neutral names (P7, 9.3).

### 4.5 Combining into the per-era "current" curve

For each era (D6), on the common 1 A grid: pixel-wise median of the
individual curves and the median absolute deviation, written to
`keck_etcs/data/mosfire/throughput/mosfire_thru_<era>.ecsv` with columns
`wave, thru_median, thru_mad, n_std`. Nights whose band-median throughput
deviates by more than 3 MAD from the era median are excluded as a whole
(flag set in the per-standard table), not clipped pixel by pixel. The ETC
default is the latest era; a `date` input selects an era; `throughput_scale`
applies a global factor.

*As built (S16; `keck_etcs/calib/combine.py`):*

- Each row's filter-free curve is kept inside the filter's half-power
  band. J rows are further kept only where the J filter is >= 0.9 of its
  peak (`EDGE_TRIM_FRAC`), and A0V rows only redward of 11900 A
  (`A0V_MIN_WAVE`); the report (section 3) gives the reasons.
- The 3-MAD test compares nights over `COMMON_WINDOW` = 11900-12450 A,
  inside both filters. It needs at least 3 nights.
- An era curve covers only what its standards measured (2025-04.. has one
  J2 standard, 11171-12462 A). `Instrument.throughput_for_window`
  completes a band window from the nearest era that measured the rest,
  scaled by the median ratio of the two curves over 11900-12450 A, with a
  warning. In the release that is 2025-04.. over J (x 1.024) and
  2012-2016 over J2 (x 1.005). Beyond every era the edge value is held,
  with a warning.

*Other bands (v0.6):* one era curve per **band group** (grating order: Y;
J = J, J2, J3; H; K), file `mosfire_thru_<group>_<era>.ecsv`, with the
common window, the edge trim and the A0V blue cut per group (P2, 9.3).

### 4.6 Trend analysis

Plot `zp_1250` and `thru_median_1117_1260` against date with the era
boundaries marked; per era report the median, MAD, and a linear slope in
percent per year with its uncertainty; test for correlation with airmass, PWV
and slit width (a residual airmass trend means the telluric division is
incomplete; a slit-width trend at >= 3" would contradict D4). *From v0.4 (D47):* the same per-era
statistics are computed for every monitor metric of 4.9 (FWHM, dome-flat
rate at each node, line widths, lamp-line fluxes, OH fluxes). The dome-flat
rate at 1.20 and 1.25 um is plotted beside `zp_1250` with a correlation test,
and nights beyond 3 MAD are flagged, not excluded. The OH-flux series,
divided by the Gemini model at the frame's airmass and PWV, gives the
empirical `sky_scale` distribution (D14, 8). Compare the
2012-2016 era median with XTcalc's 2012 curve as a sanity check of the whole
chain (they should agree at the 10 percent level once the 75 vs 72.4 m^2
aperture is accounted for).

*Results* of the first release (`mosfire-J-2026.10`, plan S16): see the
report, `reports/Keck_MOSFIRE_report_20261009.md`, sections 2-4. The method changes they led to are in 4.5 and
D25; the trend code is `keck_etcs/calib/trend.py`, with
`scripts/mosfire/plot_throughput_trend.py`, `plot_monitor_trends.py` and
`verify_release.py`.

### 4.7 Uncertainties

Per-standard zero point: CALSPEC NIR models 1-2 percent; Vega + 2MASS J 3-4
percent (2MASS 0.02-0.03 mag, Vega model 1-2 percent); telluric residuals 1-3
percent in the J2 window, larger near 1.13 um water; slit loss < 1 percent at
>= 3" for seeing < 1.2"; flat-field and illumination at the slit position 1-2
percent; photon noise 1-2 percent for a 2 x 120 s WD at J = 15, less for
brighter stars. Expect 3-5 percent scatter per standard, which sets the
smallest era-to-era change we can detect at a few percent with ~10 standards
per era.

### 4.8 Reduction infrastructure on Nautilus

This section records how the reductions of 4.2 are run (D30) and which of
the user's established conventions they inherit. Nothing here changes the
physics or the ETC; it changes where `run_pypeit` executes and where its
products live.

**4.8.1 Conventions carried over.** From `Oceanography/python/PAB/nautilus/`
(HOWTO.md, `build_image.sh`, the `*_job.yaml` manifests and their helper
scripts) and `PypeIt-development-suite/nautilus/` (`gen_kube_devsuite`,
`kube_dev_suite.yaml`):

- One Kubernetes Job (`batch/v1`) per unit of work, `restartPolicy: Never`,
  `backoffLimit: 4` for idempotent, resumable work and `0` for one-shots and
  validation runs (*as built:* the night Job uses `backoffLimitPerIndex: 1`
  and a `podFailurePolicy` instead, 4.8.6), `activeDeadlineSeconds` as a safety net against hung pods,
  `imagePullPolicy: Always` on a semver tag with the image digest noted in a
  comment.
- `command: ["/bin/bash", "-lc"]` with a YAML literal block (`|`, never the
  folded `>`), `set -o pipefail`, a `log()` helper printing
  `=== <stage> <date -Is> ===` tee'd to a durable log, a PROVENANCE block
  first (versions and git SHAs), counts or checks before and after, `du -sh`,
  a `*_DONE` sentinel, and `exit 1` on a failed stage so a broken run stops
  rather than carries on. One-line `python -c` snippets, no here-docs.
- A header comment on every manifest stating purpose, sizing from measured
  rates (never from an early sample), and the three `kubectl` lines to delete,
  apply and follow the job. Helper scripts are mounted as ConfigMaps
  (`kubectl create configmap ... --from-file ... --dry-run=client -o yaml |
  kubectl apply -f -`); anything over the 1 MiB ConfigMap limit goes to S3.
- Secrets are mounted, never copied: `prp-s3-credentials` at
  `/root/.aws/credentials` (subPath `credentials`); `HOME=/root`. No secret
  value ever appears in this repository.
- Storage: Nautilus S3 with path-style addressing, uploads through a boto3
  helper (the image ships no `aws` CLI) that is idempotent by key and size;
  the dev suite instead installs `awscli` in the pod, which is also
  acceptable. PAB's bucket is public-read; ours is private (D32), so the
  credentials secret is mounted for reads as well as writes. Nautilus is not
  backed up, so the high-level products are copied to the Google shared
  drive (`AIOcean:` via rclone; D39, 4.8.9).
- Pilot before production: a tiny validation run with hard gates that exit
  non-zero (`v2_validate_gates.py`), then a subsample, then the full batch.
  Failures are re-run by targeted manifests (the `rediscover_csv.py` /
  `sweep_stalled.csv` pattern), never by re-running everything.
- A throwaway `python:3.12-slim` inspect pod for looking at storage.
- Outward-facing infrastructure (namespaces, buckets, image pushes, large
  jobs) is confirmed with the user first.

**4.8.2 Image (D31).** `nautilus/Dockerfile` and `nautilus/build_image.sh
[--push]`, run on the Linux workstation (Q30; this Mac has `kubectl` and
`rclone` but no `docker`), built from a staged context (this repo plus
nothing else; PypeIt comes from GitHub). The PypeIt pin is the single file
`nautilus/pypeit_pin.txt` holding one full commit SHA on `develop`
(`f3a1f1d274b15ee1358f167819d77f1948fce1bd` = `origin/develop` on
2026-09-30, `git describe` 2.0.1-1216, expected in-image version string
`2.0.2.dev1216+gf3a1f1d27`; plan step S0 checks that the local checkout
contains it and is MOSFIRE-equivalent to it, D35). Re-pinning is a
deliberate edit of that file plus an image tag bump recorded in
`nautilus/README.md` and `CHANGES.md`; `build_image.sh` refuses to build if
the pin is not an ancestor of `origin/develop`. Layers: (1) third-party
dependencies only, so a keck_etcs edit rebuilds a small layer (PAB's
2026-09-26 lesson); (2) `pip install
git+https://github.com/pypeit/PypeIt.git@$(cat nautilus/pypeit_pin.txt)`
and `pip install /opt/src/keck-etcs`; (3) cache population:
`pypeit_cache_github_data keck_mosfire` and `pypeit_install_telluric` on the
TellPCA grid downloaded from the public Nautilus URL
(`s3://pypeit/telluric/atm_grids/`, which *is* public) with a sha256 check
against `nautilus/telluric_grid.sha256`, and `ENV XDG_CACHE_HOME=/opt/cache`
so the cache lands at `/opt/cache/pypeit` regardless of `HOME`; (4) build
guards that fail the build: `pypeit.__version__` ends with the pinned short
SHA, `pypeit.pkg.cache.search_cache('TellPCA')` returns the grid, `run_pypeit
--help`, `pypeit_sensfunc --help`, `python -c "import keck_etcs.calib.harvest"`,
and `KECK_ETCS_GIT_SHAS` has no `unknown`. `MPLBACKEND=Agg`,
`PYTHONUNBUFFERED=1`, `OMP_NUM_THREADS` left to the manifest. Image tags
follow `keck_etcs.__version__`; every tag is recorded with its digest and
its PypeIt pin in `nautilus/README.md`. The registry project and its
`write_registry` deploy token are created once by the user (Q29), who runs
`docker login gitlab-registry.nrp-nautilus.io` on the workstation.

*Exception (user, 2026-09-30, S4a).* At `f3a1f1d` PypeIt's
`pypeit_cache_github_data` crashes: `pypeit/scripts/cache_github_data.py:143`
passes `quiet=True` to `PypeItDataPath.get_file_path()`, which has no such
argument. The user fixed it on the PypeIt branch `etc-fixes`
(`275a012dfcb708d4f0eaeebd56d2513083244b24`, one commit on top of
`f3a1f1d`). Image 0.1.0 pins that commit, and `build_image.sh` accepts a pin
on `develop` *or* `etc-fixes` (`PIN_BRANCHES`).
`pypeit/scripts/cache_github_data.py` is on the pin allow-list (D35).
*Re-pinned 2026-10-02 (S4b)* to `etc-fixes`
`8017f47997d6417d797be6d0a0358d7acb8918b5`. That commit adds the extraction
parameter `refine_trace` (default True) and sets it False for `keck_mosfire`:
the iterative trace refinement in `local_skysub_extract` walked the trace of
m220409_0037 off the star (log of part 2, prompt #6). Image 0.1.3 and later
carry it. When the fixes merge into `develop`, the pin moves to the merge commit, `PIN_BRANCHES`
returns to `develop`, and the image tag is bumped. Layer order as built: the
cache (3) sits *before* `COPY` of keck-etcs and its `pip install`, because it
depends only on PypeIt and the grid checksum. `KECK_ETCS_GIT_SHAS` is
declared last, so that a new commit does not invalidate layers 1-3.
`setup.py` ships `keck_etcs/data/` as package data. Inside the image
`check_pypeit_pin.py` runs in image mode: it passes when
`KECK_ETCS_GIT_SHAS.pypeit` equals the pin.

*As built (2026-10-08):* the pin moved along `etc-fixes` with each
MOSFIRE fix found in reduction:

- `fb47905` (image 0.2.2): `get_arc_extract_center` and
  `alignment_box_rows`;
- `fb6fb62` (0.2.3, 0.2.4): `transfer_wavecal` and `long2pos_bar_widths`;
- `bc18a3b` (0.2.5): `construct_basename`;
- `b0447b7` (0.2.6, S23d): the `ronoise` fix (D19, `38bb1b7`) and
  `SLITRANGE` from product headers in `config_specific_par`
  (`pypeit_sensfunc` on a short long slit).

Image 0.2.6 is current. `nautilus/README.md` has every tag
with its digest, keck-etcs commit and pin. The `--allow-branch` flag
anticipated in plan S17 does not exist: `PIN_BRANCHES` serves the purpose.

**4.8.3 Storage (D32).** Layout in 4.2. The pod's working directory is an
`emptyDir` sized by `ephemeral-storage` (a MOSFIRE night is a few GB of
outputs); nothing is written to a shared file system. Push list per night:
the pypeit file, `Calibrations/`, `Science/spec1d_*`, `QA/`, `sens/`,
`harvest/`, `run_manifest.json`, `run.log`; `spec2d_*` (large) only when the
manifest sets `SPEC2D=1`, which the validation nights do. The bucket is
private (D32): only the user's Nautilus S3 keys can list, read or write it,
so `scripts/nautilus/s3_sync.py` (boto3; endpoint from `ENDPOINT_URL`,
credentials from `AWS_PROFILE` in `~/.aws/credentials` or the `AWS_*`
environment, never from the repo) is the only local access path, pods mount
the credentials secret named in the manifests (`KECK_ETCS_S3_SECRET`,
default `prp-s3-credentials` in namespace `pypeit`; whether that secret
holds keys with access to `keck-etcs` is a verification item for the user in
plan step S1b, otherwise a new secret `keck-etcs-s3-credentials` is created
from the user's `~/.aws/credentials`), and anyone else (WMKO, collaborators)
gets the products from git, not from S3. Only public KOA data are staged in
any case. `s3_sync.py` has `push`, `pull` and `ls` subcommands, skips
objects already present with the same size, and fails loudly on
`AccessDenied` rather than falling back to anonymous access. Widening bucket
access later (a read policy for named users, or pre-signed URLs) is an
optional step, not a deliverable of this plan.

**4.8.4 Jobs (D33).** `nautilus/night_job.yaml` is an Indexed Job
(`completionMode: Indexed`); the pod reads its night from row
`JOB_COMPLETION_INDEX` of the manifest CSV (columns: `night`, `instrument`,
`s3_prefix`, `standard`, `slit`, `spec2d`, `notes`) mounted as a ConfigMap or
pulled from `manifests/`. `parallelism: 4` to start; raise only after the
per-night rate and memory are measured on the pilot. Initial resources per
pod, to be measured in the dry run: requests and limits `cpu: 4`, `memory:
16Gi`, `ephemeral-storage: 30Gi` request / `60Gi` limit; `OMP_NUM_THREADS=4`;
`activeDeadlineSeconds: 21600` (6 h) per job. Other manifests:
`nautilus/koa_download_job.yaml` (D37), `nautilus/inspect_pod.yaml`, and
`nautilus/validate_job.yaml` (the 2022-04-09 dry run with `backoffLimit: 0`).
All manifests use namespace `pypeit` (Q27) and mount the credentials secret
of 4.8.3 at `/root/.aws/credentials` (subPath `credentials`), for reads and
writes alike.

*Other bands (v0.6):* the manifests gain a `band` column; a night observed
in several bands is several rows with products under
`mosfire/<night>/<band>/` and the raw frames shared under
`mosfire/<night>/raw/`; the gate windows and throughput range come from
the instrument module per band (P8, 9.4).

**4.8.5 Provenance (D36).** The pod's PROVENANCE block prints and
`run_manifest.json` records: `image` (tag), `image_digest`, `pypeit_version`,
`pypeit_git_sha`, `pypeit_pin`, `pin_check` (the S0 check result: pass or
fail plus the list of files differing from the pin; inside a pod the SHA
equals the pin and the list is empty), `keck_etcs_version`,
`keck_etcs_git_sha`, `job_name`,
`pod`, `node`, `started`, `finished`, `night`, `s3_prefix`, the sha256 of
every raw frame and of every pushed product, the pypeit file text, and the
gate results. `keck_etcs.calib.harvest` copies these into the per-standard
row (4.4) and into the `meta` of the curve file (5.4). A calibration release
lists in `CHANGES.md` the image tags whose reductions it used.

**4.8.6 Failure handling.**

*As built (S15a, 2026-10-06):* data outcomes exit 2 and infrastructure
failures exit 1.

- **Data outcomes:** `no calibs`, `setup failed`, `no trace`, `sens failed`,
  `gate failed` and `pin check failed`. The Job's `podFailurePolicy` turns
  exit 2 into `FailIndex`.
- **Infrastructure failures:** `pull failed`, `push failed`,
  `reduce failed`, OOM. These are retried once per index
  (`backoffLimitPerIndex: 1`).
- **Evictions** (`DisruptionTarget`) are ignored.
- **Why:** the pilot's global `backoffLimit: 4`, exhausted by three
  `no trace` nights, had deleted healthy pods.
- **Status rows:** one object per pod,
  `runs/<job>/status/<index>_<night>.ecsv`. `night_failures.py` takes each
  night's latest row.
- **Products** are always pushed with `--force`, so a re-reduction
  replaces same-size files.

As designed: a night is `success` only when all gates pass and
the push completes; otherwise the pod writes `status in {no calibs, setup
failed, reduce failed, no trace, sens failed, gate failed, push failed}` with
the exception text to `runs/<job_name>/status.ecsv` and exits non-zero, so the
Job reports the failed index. Pods are idempotent: a night whose
`run_manifest.json` already exists on S3 is skipped unless `REPLACE=1`, so
re-applying a Job after preemption resumes. `nautilus/night_failures.py`
turns `status.ecsv` into a sweep manifest of failed nights;
`nautilus/status_table.py` builds the per-night status table of step S15 from
the `run_manifest.json` objects (store-only, no reduction). A night that fails
twice for a data reason (no flats, standard off-slit) is recorded as such and
not retried.

**4.8.7 Dry run and gates (D35).** Before any batch, `validate_job.yaml`
reduces 2022-04-09 in one pod and `nautilus/gates.py` checks: spec1d files
for both LDS749B traces and all four J0841 frames; wavelength RMS below
PypeIt's threshold; sensfunc zero point finite over 1.117-1.260 um; implied
median throughput 0.15-0.45; and, given the local reference products from
step S4 (`--reference` pointing at a synced-back copy), first that the
reference's recorded `pypeit_pin` equals the image's PypeIt SHA and its
`pin_check` passed (else FAIL before any comparison; D35), then zero-point
agreement and `S2N` agreement to 5 percent. *Revised 2026-10-01 (user, after
the S4b dry run):* the zero-point gate is band-level. The median pod/reference
throughput ratio over 1.117-1.260 um must be within 2 percent, and its
per-pixel 5-95 percentile range within ±5 percent. A reduction-fidelity gate
is added: the median `OPT_COUNTS` ratio per frame must be within 0.1 percent.
The reason: the IR telluric fit (`differential_evolution`, seed 777) is
deterministic and gives bit-identical results in the image and locally on
the same input, but it is chaotic in its input. A 1e-5 perturbation of the
counts moves the per-pixel zero point by up to ~5 percent and the band median
by up to ~1 percent (`scripts/mosfire/sensfunc_perturbation_test.py`). The
first dry run gave a median of 0.990 and a 5-95 percent range of 0.975-0.998,
with S2N within 0.01 percent. This scatter also bounds what a single
standard's per-pixel zero point means (relevant to S10). The same gates run
inside every
production pod (without `--reference`). The pilot after the dry run is a
3-5 night batch (the first wide-slit standards) before the full manifest.

**4.8.8 What stays local (D38).** Everything under `keck_etcs/` that WMKO will
call, and every analysis that reads harvested products: the Gemini grid build
(S3), core, instrument module, `compute()`, tests, `combine`, `trend`, the
J0841 validation (on synced spec1d and sens files), the XTcalc comparison, the
KOA metadata search, the PypeIt `ronoise` branch, and the documentation.
`pypeit14` remains the local environment (*as built:* `pypeit14b` on the
Linux workstation); the image pins the same PypeIt commit so local and
in-pod PypeIt agree.

**4.8.9 Backup (D39).** Nautilus S3 is not backed up and the raw frames are
re-downloadable, so the backup set is the high-level products only, per
night under `mosfire/<YYYYMMDD>/`:

| Included (copied to `AIOcean:keck-etcs/`) | Excluded (re-derivable or re-downloadable) |
|---|---|
| `sens/sens_*.fits` and the telluric QA PNGs | `raw/*.fits` (KOA) |
| `harvest/*.ecsv` (row, curve and, from v0.4, `<night>_monitor.ecsv`) | `redux/Science/spec2d_*.fits` |
| `run_manifest.json`, `run.log`, `redux/<night>.pypeit` | `redux/Calibrations/` (incl. `WaveCalib*`; S13 commits its measurements to `lsf_measurements.ecsv`) |
| `redux/Science/spec1d_*.fits` (standards and validation science frames) | `redux/QA/` |
| `manifests/`, `runs/<job>/status.ecsv`, `raw/manifest.ecsv` | |

Per night this is tens of MB, dominated by spec1d and sens files. Timing:
`scripts/nautilus/backup_products.py` (an `rclone copy nautilus_s3:keck-etcs/
AIOcean:keck-etcs/` with `--include` filters for the set above; idempotent)
runs after every successful S15 batch and, at each calibration release
(S16), once more into a dated, tagged subdirectory
`AIOcean:keck-etcs/releases/<calib_version>/` so the release's inputs are
frozen. The committed products in git remain the primary record; the backup
exists to avoid re-reducing if the bucket is lost. Two judgment calls are
flagged: including *all* spec1d files (the science frames are small and S11
needs them) and excluding `WaveCalib*` (needed only to redo S13, which a
re-reduction regenerates).

**4.8.10 Residual verification items** are listed in section 8 (credentials
secret, registry project and token, local PypeIt checkout on `develop`, KOA
reachability from pods). *All settled by 2026-10-08* (section 8).

### 4.9 Calibration monitor (v0.4; D40-D47)

The throughput series (4.4-4.6) says *whether* the system changed. The
monitor helps say *where*: seeing and guiding (FWHM), lamps versus optics
(dome-flat rate against standard throughput), focus and slit (line widths),
and the sky (OH fluxes, D14). Each metric is one or more rows of a long
table, written per night by the in-pod harvest (D46). None of them gates a
night (D47).

**4.9.1 Spatial FWHM (D41).** For every extracted object in every spec1d of
the night, standards and science alike, the monitor records:

- the scalar `FWHM` (pixels, from object finding) and the same value in
  arcsec (x 0.1798);
- `FWHMFIT` (per spectral pixel, from the profile fit), as a median within
  ±100 A of each zero-point node (J2: 11500, 12000, 12500 A; J: 12000,
  12500, 13000 A), so a chromatic slope can be fitted and compared with
  lambda^-0.2 (D26);
- `slitloss_gt1pct`, true where the D26 Moffat (beta 3.5) at the scalar
  FWHM loses more than 1 percent at the frame's slit width. This is
  computed with the same slit-loss function as `keck_etcs.core.slitloss`
  once S7 exists, and with a local copy of the integral until then, flagged
  `slitloss = provisional`.

Only spec1d fields are used, so this works for any PypeIt spectrograph.

**4.9.2 Flat brightness (D42, D43).** Per calibration group with a `Flat`
file:

```
rate(lam_k) = median over { pixels in the slit's central 50% of rows, |lam - lam_k| <= 50 A }
              of pixelflat_raw / t_frame                                    [e-/s/pix]
rate_per_arcsec(lam_k) = rate(lam_k) / slit_width                           [e-/s/pix/arcsec]
```

Here `pixelflat_raw` is PypeIt's mean-combined, gain-applied, lamp-off
subtracted pixel-flat stack (units to be confirmed in S6b, section 8), and
`t_frame` is the lamp-on frames' `TRUITIME`. The wavelengths come from
`pixelflat_waveimg` or, if it is empty, from `WaveCalib.build_waveimg(Tilts,
Slits)`. The rows are a slit's middle half, away from the CSU bar ends.
Bad-pixel-masked pixels are dropped. The MOSFIRE nodes are every 250 A
(J2: 11250-12500 A, 6 nodes; J: 11500-13250 A, 8 nodes). The generic
optical default is every 500 A. Recorded per group: `flat_kind` (`dome` for
MOSFIRE, `internal` where an instrument has one), the lamp header cards
(MOSFIRE: `FLAMP1`, `FLAMP2`, `FPOWER`, `FLATSPEC`; checked on 2022-04-09,
where the headers carry no lamp voltage or current), `TRUITIME`, `SAMPMODE`,
`NUMREADS`, the number of lamp-on and lamp-off frames, slit width, filter,
`DOMEPOSN`, and the peak raw ADU of the lamp-on frames. A peak above the
1 percent non-linearity limit (26k ADU) sets `flag = nonlinear`. Dome flats
also depend on dome position and screen illumination, so the series is
read as a trend (D42).

**4.9.3 Calibration-line widths (D44).** This is the S13 algorithm, moved
from `scripts/mosfire/measure_lsf.py` into `keck_etcs.calib.monitor`.
`measure_lsf.py` becomes a thin wrapper that keeps its `--record` behaviour
for `lsf_measurements.ecsv`. For every line PypeIt identified in the arc
spectrum (`pixel_fit`, `wave_fit`), it fits a Gaussian plus a linear
baseline within ±8 px. A line is rejected as a blend if a companion with at
least 10 percent of its amplitude, from the resolved line list
(`OH_R24000_lines.dat` for OH; `Ne_IR_MOSFIRE_lines.dat` and
`Ar_IR_MOSFIRE_lines.dat` for lamps), lies within 1.5 expected FWHM. Then a
clipped line is fitted to FWHM against wavelength. Per (night, slit, source)
it records the median FWHM in pixels and A, the scatter, FWHM and R at the
reference wavelength (12500 A for J and J2), the slope in px per 1000 A,
`n_lines`, and `arc_source` (`OH` from the `WaveCalib` of on-sky frames;
`lamp` from Ne/Ar frames). Lamp frames are not used by PypeIt's wavelength
solution except on `long2pos_specphot` masks. On other masks the monitor
measures them directly: it builds a central-rows spectrum from the raw lamp
frame with the wave image of a calibration group with the same `MASKNAME`
and filter that night, and identifies lines against the lamp list with the
wavelength solution held fixed. A lamp frame with no matching group is
skipped and counted.

**4.9.4 Calibration-line brightness (D45).** On-sky frames that PypeIt
reduced as A-B pairs have only residual sky in spec1d, so the OH fluxes are
measured on the processed single frames instead. Each raw on-sky frame
(science and standard) is processed by PypeIt's raw-image steps with the
gain applied, divided by `TRUITIME`, and divided by `pixelflat_norm`. For
each monitor line, the flux is summed over ±1.5 FWHM in the wave image
minus a linear continuum from flanking windows, per spatial row. The median
over the slit's central rows, with every object trace masked to ±3 FWHM,
is divided by `platescale x slit_width`:

```
F_OH(line)       [e-/s/arcsec^2, integrated over the line]
F_OH_above(line) = F_OH / (T_sys(lam_line) * A_m2)    [photons/s/arcsec^2/m^2, integrated over the line]
```

`F_OH_above` is compared with the Gemini `SKYBG` (photons/s/arcsec^2/nm/m^2)
integrated over the same window after LSF convolution (5.3.8). It is filled
only where the night has a sensfunc, and it uses the night's own `T_sys`
(not the era median) so that a throughput change is not read as a sky
change. Each row
carries the frame's MJD/UT, airmass and the night's fitted PWV. One extra
row per frame holds the summed flux of the monitor lines' fixed windows
(below). Lamp
lines use the same sum, without object masking, on the lamp frames, and are
reported as e-/s per pixel row per arcsec of slit width. Line-selection
rules, applied by `scripts/mosfire/select_monitor_lines.py`:

1. in PypeIt's line list for that source, and identified on at least
   80 percent of the nights examined;
2. isolated: no companion of more than 10 percent of its amplitude within
   3 FWHM of a sky line in a **1"** slit (about 4.7 A in J2). *Revised
   2026-10-04 (S6b, user):* the original "3 FWHM of the widest slit in use
   (5")" left 1 of 74 J2 OH lines, because the J2 OH lines blend into
   complexes at 5". At 1", 18 lines are identified and isolated;
3. bright, but below the 1 percent non-linearity limit in a typical frame
   (sky plus line, MCDS-16, the frame's exposure);
4. at least 100 A inside the band window and away from strong telluric
   absorption (Gemini `TRANS` above 0.9 at airmass 1.5, PWV 1.6 mm);
5. 4-6 lines per source per band, spread across the window.

**Fixed windows (S6b, user).** Because lines blend in wide slits, each
monitor line also gets a *fixed* window of ±1.5 x the FWHM of a sky line
in a 5" slit (about ±35 A in J2), measured identically on every frame
whatever its slit (`line_flux_window`, e-/s/arcsec^2; `line_flux_above`
for the same window). `line_flux_sum` is the sum of these windows, so it is
comparable between narrow-slit (science) and wide-slit (standard) frames:
this is the 1" against 5" slit-normalisation check. The per-line
`line_flux` uses the frame's own ±1.5 FWHM and carries `flag = blended` on
slits wider than 1".

**Twilight (S6b, user, 2026-10-04).** Each OH row records the Sun's altitude
at mid-exposure (`cards.sun_alt_deg`), and frames with the Sun above -18 deg
carry `flag = twilight`. On 2022-04-09 the LDS749B frames were taken at
-9.0 and -8.5 deg: their low-OH J2 sky was 12-18 e-/s/arcsec^2/A, 4-7x the
dark frames' and rising 50% in 2.5 min. Twilight frames are excluded from
the 1"/5" slit-normalisation check and from `sky_scale`. That check was
not testable on 2022-04-09 and is re-run in part 5 on dark-sky wide-slit
standards.

The script ranks candidates on 2022-04-09 and the S15a pilot nights. Its
output table, with sha256, is the provenance of the frozen list in the
MOSFIRE monitor config. Lines may be added later but are never removed, so
every series stays continuous. Before the freeze, OH rows carry
`lines = provisional`.

**4.9.5 Table format (D46).** One row per (night, frame or calibration
group, metric, wavelength or line), with columns `night, mjd, instrument,
metric, source (object|dome|internal|OH|Ne|Ar), frame (file, or
`group:<calib_key>` for stacks), target, decker, slit_width, filter,
wave_A, line_id, value, unit, err, n, airmass, pwv_fit, cards (a JSON
string of the instrument's recorded header cards), flag`, plus the D36
provenance columns and `keck_etcs_version`. `metric` takes the values
`fwhm_scalar_pix`, `fwhm_scalar_arcsec`, `fwhmfit_pix`, `slitloss_gt1pct`,
`flat_rate`, `flat_rate_per_arcsec`, `line_fwhm_pix`, `line_fwhm_A`,
`line_R`, `line_fwhm_slope`, `line_flux`, `line_flux_window`,
`line_flux_above`, `line_flux_sum`. The per-night file is
`harvest/<night>_monitor.ecsv`. The merged
`keck_etcs/data/mosfire/monitor/calib_monitor.ecsv` is keyed on (night,
frame, metric, wave_A, line_id), and a re-harvest replaces its own rows.

**4.9.6 Instrument configs.** `keck_etcs/instruments/<inst>.py` (from S8)
gains a `monitor` block: the FWHM nodes, the flat nodes and box half-width,
the slit-row fraction, `flat_kind`, the lamp header cards to record, the
line lists per source and the frozen monitor lines. Until S8 exists, the
MOSFIRE block lives in `keck_etcs/calib/monitor_configs.py` and moves later
without changing the rows. LRIS will set `flat_kind = internal` if it uses
its internal halogen, and lamp sources from its arc lists.

*Other bands (v0.6):* per-band FWHM nodes, flat nodes, band windows and
monitor lines, plus a K-band thermal-continuum metric (9.6).

## 5. ETC design (B)

### 5.1 Package layout

```
keck_etcs/
  __init__.py                 # __version__
  etc.py                      # compute(inputs: dict) -> dict ; validate(inputs)
  schema/etc_input.json       # JSON Schema (draft 2020-12) for inputs
  schema/etc_output.json
  core/                       # instrument-agnostic, pure functions, no I/O
    source.py                 # spectral shapes, AB/Vega, normalization to a filter
    atmosphere.py             # transmission grid lookup and interpolation
    sky.py                    # sky grid lookup, interpolation, scale, per-pixel rates
    slitloss.py               # Moffat, slit x aperture integrals, extended sources
    lsf.py                    # LSF FWHM, R, convolution/resampling to pixels
    detector.py               # RN(N_reads), dark, linearity flags
    snr.py                    # signal/noise/S-N equations, exptime inversion
  instruments/
    base.py                   # Instrument dataclass and data loading
    mosfire.py                # bands, dispersion, windows, filters, RN table, eras, LSF params
  calib/                      # sensitivity analysis (A)
    standards.py              # A0V Vega+2MASS model (N3), standard classification
    harvest.py                # sens_*.fits -> per-standard ECSV rows and curves
    combine.py                # per-era medians (4.5)
    trend.py                  # trend statistics (4.6)
    monitor.py                # calibration monitor (4.9, D40): FWHM, flat rates, line widths and fluxes
  data/
    index.yaml                # product registry with versions
    sky/gemini_mk_sky_grid.fits
    mosfire/filters/*.ecsv
    mosfire/detector.ecsv     # RN table, linearity, gain, dark
    mosfire/throughput/...    # per-era curves and per-standard archive
    mosfire/monitor/calib_monitor.ecsv  # merged monitor table (D46); not read by compute()
    pypeit_par/*.sens
  tests/
scripts/                      # one-off analyses and reduction drivers
  mosfire/                    # reduce_standard.py runs locally (reference) and inside the pods
  nautilus/s3_sync.py         # boto3 push/pull between the bucket and $KECK_ETCS_DATA
nautilus/                     # Dockerfile, build_image.sh, Job manifests, ConfigMap helpers (D30, 4.8)
bin/keck_etc                  # CLI: JSON file in, JSON out
docs/
```

`core` functions take and return numpy arrays and floats; `instruments`
loads data files once and hands arrays to `core`; `etc.compute` is the only
function WMKO calls. `calib` may import PypeIt; `core` and `etc` must not
(PypeIt is a heavy dependency the web service should not need).

### 5.2 The `compute(dict) -> dict` API

Inputs (JSON object). Unlisted fields are rejected; missing fields take the
default. All wavelengths are vacuum Angstroms unless the unit is in the name.

| Field | Type | Default | Range / values | Meaning |
|-------|------|---------|----------------|---------|
| `instrument` | str | `"keck_mosfire"` | fixed | |
| `band` | str | `"J"` | `J`, `J2`; *v0.6 (P11):* `Y`, `H`, `K` | filter |
| `slit_width_arcsec` | float | 0.7 | 0.3-5.0 | CSU long-slit width |
| `source.type` | str | `"point"` | `point`, `extended` | |
| `source.mag` | float | 20.0 | 5-30 | total magnitude (point) or magnitude per arcsec^2 (extended), in the band |
| `source.mag_system` | str | `"AB"` | `AB`, `Vega` | Vega offsets from synthetic photometry of the Vega spectrum |
| `source.size_arcsec` | float | 1.0 | 0.2-20 | extended only: top-hat diameter |
| `spectrum.shape` | str | `"flat_fnu"` | `flat_fnu`, `power_law`, `user`, `line` | |
| `spectrum.alpha` | float | 0.0 | -5..5 | power law f_nu ~ nu^alpha |
| `spectrum.wave_A`, `spectrum.flux` | arrays | none | | user spectrum, f_lambda in any units (normalized to `source.mag`) |
| `spectrum.line.wave_A` | float | none | in band | observed line center |
| `spectrum.line.flux_cgs` | float | none | > 0 | integrated line flux, erg/s/cm^2 |
| `spectrum.line.fwhm_kms` | float | 200 | 10-5000 | intrinsic FWHM |
| `spectrum.line.continuum_mag` | float or null | null | | optional continuum under the line |
| `seeing_fwhm_arcsec` | float | 0.7 | 0.3-3.0 | at the observing band unless `seeing_wave_um` is given |
| `seeing_wave_um` | float or null | null | 0.4-2.5 | if given, FWHM scales as (lambda/seeing_wave)^-0.2 |
| `exptime_s` | float | 120 | 1.455-3600 | per frame |
| `n_frames` | int | 4 | 1-1000 | |
| `readout.mode` | str | `"MCDS"` | `CDS`, `MCDS` (`UTR` reserved) | |
| `readout.n_reads` | int | 16 | 1, 2, 4, 8, 16, 32, 64, 128 | CDS forces 1 |
| `nod` | str | `"ABBA"` | `ABBA`, `stare` | ABBA: each frame is sky-subtracted with a frame of equal time |
| `airmass` | float | 1.2 | 1.0-2.5 (clipped to 1.0-2.0 for the grids, with a warning) | |
| `pwv_mm` | float | 1.6 | 0.5-10 (clipped to 1.0-5.0) | precipitable water vapour |
| `sky_scale` | float | 1.0 | 0.3-3.0 | multiplies the sky emission |
| `aperture.length_fwhm` | float | 1.5 | 0.5-5 | extraction length along the slit in units of the (band) FWHM |
| `aperture.length_arcsec` | float or null | null | | overrides `length_fwhm` |
| `throughput.date` | str or null | null | ISO date | selects the era; null = latest |
| `throughput.scale` | float | 1.0 | 0.1-2 | |
| `target_snr` | float or null | null | > 0 | if set, `exptime_s` is solved for at fixed `n_frames` |
| `snr_reference` | str | `"pixel"` | `pixel`, `resel`, `line` | which S/N `target_snr` refers to |
| `ambient_temp_C` | float or null | null | -10..20 | *v0.6 (P13 = D60), K only:* temperature of the telescope and dome for the thermal background; null = the default (2 C provisionally; the median header `TUBETEMP` of the K sample once built) |

Output (JSON object):

| Field | Meaning |
|-------|---------|
| `meta.keck_etcs_version`, `meta.pypeit_version`, `meta.calib_version`, `meta.era`, `meta.inputs` | versions; era used; validated inputs with defaults filled |
| `wave_A` | vacuum wavelength per spectral pixel over the band window (N2) |
| `dispersion_A_per_pix`, `lsf_fwhm_A`, `resolving_power`, `n_spec_per_resel` | LSF quantities |
| `slit_fraction`, `aperture_fraction`, `n_spatial_pix`, `fwhm_arcsec_band` | slit-loss quantities |
| `throughput`, `atm_transmission`, `filter_transmission` | arrays on `wave_A` |
| `signal_e`, `sky_e`, `dark_e`, `read_noise_e` | electrons per spectral pixel in the aperture, summed over all frames |
| `noise_e`, `snr_pixel`, `snr_resel` | arrays |
| `summary.snr_pixel_median`, `summary.snr_resel_median` | medians over the band window |
| `summary.snr_line`, `summary.line_window_A` | line mode only: S/N within +/- FWHM_obs/2 |
| `summary.exptime_s`, `summary.n_frames`, `summary.total_time_s` | per-frame time (solved if `target_snr`), frames, total |
| `saturation.peak_e_per_frame`, `saturation.peak_adu_per_frame`, `saturation.wave_A`, `saturation.flag` | brightest pixel per frame including sky lines; flag `ok`, `nonlinear_1pct`, `nonlinear_5pct`, `saturated` |
| `thermal_e`, `saturation.frac_pix_nonlinear_1pct` | *v0.6 (P13, P15):* electrons per spectral pixel from the thermal term (zero outside K); fraction of spectral pixels whose brightest spatial pixel exceeds the 1 percent limit |
| `warnings` | list of strings (clipped airmass or PWV, era fallback, etc.) |

The schema files are the contract with WMKO; `etc.validate` applies them and
fills defaults; `compute` never raises on out-of-range physics, it clips and
warns.

### 5.3 The physics

Notation: `lam` wavelength [A, vacuum]; `dlam` dispersion [A/pix]; `A` =
7.23674e5 cm^2; `h c` = 1.98645e-8 erg A; `p` = 0.1798 "/pix; `w` slit width
["]; `t` exposure per frame [s]; `N_f` frames; `X` airmass.

**5.3.1 Source flux.** The chosen shape `f_lambda(lam)` (flat f_nu: f_lambda
~ lam^-2; power law: f_lambda ~ lam^-(alpha+2); user spectrum as given) is
normalized so that its synthetic AB magnitude through the band's filter curve
`F(lam)` equals `source.mag`:

```
m_AB = -2.5 log10( int f_nu F dnu / int F dnu ) - 48.6
```

Vega magnitudes are converted with `m_AB = m_Vega + (m_AB - m_Vega)_band`, the
offset being the synthetic AB magnitude of the Vega spectrum through `F`
(expected ~ +0.91 in J). Extended sources use the same normalization for
surface brightness per arcsec^2. For a line: a Gaussian of integrated flux
`flux_cgs` and intrinsic FWHM `fwhm_kms`, added to the continuum if given.

**5.3.2 Photon rate above the atmosphere.**

```
N0(lam) = f_lambda(lam) * A * lam / (h c)          [photons/s/A]
```

**5.3.3 Atmosphere.** `T_atm(lam; X, PWV)` from the Gemini `mktrans_zm` grid,
interpolated linearly in `X` and in log PWV (N4), then convolved with the LSF
and resampled to `wave_A`.

**5.3.4 System throughput.** `T_sys(lam)` = era median curve (4.5) times the
filter curve `F(lam)` times `throughput.scale`, convolved with the LSF.
*As built:* the era curve is completed over the band window as in 4.5.
The product `N0 T_atm T_sys` is convolved as a whole, rather than each
factor separately, so a line on a telluric feature is handled correctly.

**5.3.5 Slit loss and aperture.** Moffat profile with beta = 3.5 and FWHM
`s` (at the band):

```
I(r) ~ [1 + (r/alpha)^2]^-beta ,   alpha = s / (2 sqrt(2^(1/beta) - 1))
f_slit_ap = int_{-w/2}^{w/2} dx int_{-L/2}^{L/2} dy I(x, y)     (normalized to 1 over the plane)
```

evaluated numerically on a 0.01" grid; `L = aperture.length_fwhm * s` (or
`length_arcsec`). We also report the two marginals separately: `slit_fraction`
(integral over `x` only) and `aperture_fraction = f_slit_ap / slit_fraction`.
For extended sources the top-hat of diameter `source.size_arcsec` is
convolved with the Moffat before the same integral, and the surface
brightness times `w * L` gives the total. The number of spatial pixels in the
aperture is `n_spat = ceil(L / p)`. The central-pixel fraction `f_peak` (the
integral over `x` in the slit and one pixel `p` in `y` at the profile peak) is
kept for saturation.

**5.3.6 LSF and resolution.**

```
FWHM_pix = sqrt( (w / 0.292)^2 + 1.08^2 )        [pixels, D25 as built, S16; was max(w / 0.277, 2.2)]
FWHM_lsf = FWHM_pix * dlam                        [A]
R(lam)   = lam / FWHM_lsf
n_spec   = FWHM_pix                               [pixels per resolution element]
```

The floor and the slope are instrument-config values from the OH-line
measurement (`keck_etcs/data/mosfire/lsf_measurements.ecsv`, S13). The 1"
slit measured FWHM 3.61 px (0.07 px scatter over 19 lines, flat across J2),
R = 2677 at 1.25 um, which sets the interim slope at 0.277"/px. It was
0.24"/px (XTcalc), which overpredicted the width by 15%. The floor (2.2 px)
is not constrained by a 1" slit. Widths other than 1" are provisional
until part 5's KOA nights measure them; the slope-only form predicts R of
about 3820 at 0.7", against the 3318 published by WMKO. The instrument
module uses the measured row where one exists for the slit. *As built (S16):*
the 0.7" OH lines (2.63 px) separated slope and floor. The quadrature
fit gives +3.9 percent at 0.7" and -0.6 percent at 1" against the
interim rule (`keck_etcs.core.lsf.fwhm_pix(form='quadrature')`). The LSF is Gaussian; source spectrum, sky,
transmission and throughput are all convolved with it before sampling on
`wave_A`. A line's observed FWHM is `sqrt(FWHM_line^2 + FWHM_lsf^2)` with
`FWHM_line = lam * fwhm_kms / c`.

*Other bands (v0.6):* the rule is in pixels and is used for every band
until the per-band OH measurement replaces it (P12, 9.5); XTcalc's
per-band resolving powers imply a 0.7" image about 5 percent narrower in H
and K than in Y and J.

**5.3.7 Signal per spectral pixel (electrons, one frame).**

```
S(lam) = N0(lam) * T_atm(lam) * T_sys(lam) * f_slit_ap * dlam * t     [e-/pix/frame]
```

**5.3.8 Sky per spectral pixel.** The Gemini background `B(lam; X, PWV)` is in
photons/s/arcsec^2/nm/m^2; on the ground, so no `T_atm` (N6). Per spatial
pixel in the slit and per spectral pixel:

```
b(lam) = sky_scale * B(lam) / 10 [per A] * A_m2 * T_sys(lam) * w * p * dlam   [e-/s per (spatial pix, spectral pix)]
B_ap(lam) = b(lam) * n_spat * t                                                [e-/pix/frame in the aperture]
```

with `A_m2 = 72.3674`. `B` is convolved with the LSF before sampling, which is
what spreads each OH line over `FWHM_pix` pixels.

*Other bands (v0.6, P13, P14; 9.5):* `B` becomes

```
B_eff(lam) = sky_scale * [ B(lam; X, PWV) + E_band(lam) ] + eps_eff * P_ph(lam, T_amb)
```

where `E_band` is a per-band measured excess of the between-line continuum
over the Gemini model (zero until measured; the 2012 MOSFIRE sky gives
2.4-3.5x the model in H), and the last term is the thermal emission of the
telescope and dome, a grey body in photons/s/arcsec^2/nm/m^2 referred to
above the telescope, with `eps_eff = 0.15` and `T_amb = 275 K` from the
2012 K sky. It is negligible outside K (at the red edge of H it is 1
percent of the continuum) and 10-20x the Gemini continuum at 2.3-2.4 um.
Like the sky it is not attenuated by `T_atm` (N6) and is multiplied by
`T_sys`.

**5.3.9 Detector terms.** Read noise per pixel per frame `RN(N)` from the
table, interpolated linearly in `log2 N`; CDS is `N = 1`. Dark `D = 0.008`
e-/s/pix. In the aperture per frame: `n_spat * D * t` electrons of dark and
`n_spat * RN^2` of read variance.

**5.3.10 Noise and S/N per pixel.** For `nod = stare` (one frame, no sky
subtraction penalty):

```
var_1 = S + B_ap + n_spat D t + n_spat RN^2
```

For `nod = ABBA`, each frame is differenced against an equal-time sky frame
(D15):

```
var_1 = S + 2 ( B_ap + n_spat D t + n_spat RN^2 )
```

Over `N_f` frames the signal and variance add:

```
S_tot = N_f S ,  var_tot = N_f var_1
SNR_pix(lam) = S_tot / sqrt(var_tot) = sqrt(N_f) * S / sqrt(var_1)
SNR_resel(lam) = SNR_pix(lam) * sqrt(n_spec)
```

Line mode: sum `S_tot` and `var_tot` over the pixels within `+/- FWHM_obs/2`
of the line center (a fraction 0.761 of a Gaussian line's flux) and report
their ratio as `snr_line`.

Exposure-time mode (`target_snr = rho`, per pixel, at the wavelength where
the reference is taken, or the band median by iteration): with `S = s t`,
`B_ap = beta t`, `d = n_spat D`, `r2 = n_spat RN^2`, and `k = 2` for ABBA
(1 for stare),

```
N_f s^2 t^2 - rho^2 (s + k beta + k d) t - k rho^2 r2 = 0
t = [ rho^2 (s + k beta + k d) + sqrt( rho^4 (s + k beta + k d)^2 + 4 N_f s^2 k rho^2 r2 ) ] / (2 N_f s^2)
```

For `snr_reference = resel` divide `rho` by `sqrt(n_spec)` first; for `line`
solve on the summed line window.

**5.3.11 Saturation.** Per frame, the brightest pixel is

```
peak_e(lam) = N0 T_atm T_sys f_peak dlam t + b(lam) t + D t
```

maximized over `lam` (sky lines included) and reported with its wavelength;
`peak_adu = peak_e / 2.15`; flags at 26k, 37k and 43k ADU. Persistence is not
modeled; the output carries a fixed warning when the flag is not `ok`.

### 5.4 Data files, formats and provenance

- **Sky and transmission grid** `keck_etcs/data/sky/gemini_mk_sky_grid.fits`:
  HDU `WAVE` (nm, vacuum, 0.05 nm steps, 950-2450 nm, 30000 points), HDU
  `SKYBG` (12 x 30000, photons/s/arcsec^2/nm/m^2), HDU `TRANS` (12 x 30000),
  HDU `GRID` table with `airmass`, `pwv_mm` per row. Header: `SOURCE`
  (Gemini Observatory IR sky background and ATRAN transmission, as
  redistributed in Keck XTcalc v2.3), `REBIN = flux-conserving`, `SCRIPT`,
  `CREATED`, `KETCSVER`. About 3 MB. Built by
  `scripts/mosfire/build_gemini_sky_grid.py`.
- **Filter curves** `keck_etcs/data/mosfire/filters/mosfire_<band>.ecsv`
  (`wave_A`, `transmission`) from the Keck filters page ASCII files, with
  `meta.source_url` and download date.
- **Detector table** `keck_etcs/data/mosfire/detector.ecsv`: `n_reads`,
  `read_noise_e`, plus `meta` for gain, dark, linearity limits, plate scales,
  minimum integration, source URLs.
- **Throughput** per era (4.5) and per standard (4.4), ECSV, with `meta`:
  `instrument`, `band`, `era`, `standards` (list of name/date/KOA id),
  `pypeit_version`, `keck_etcs_version`, `created`, `script`, and the
  reduction provenance of D36 (`image`, `image_digest`, `pypeit_git_sha`,
  `keck_etcs_git_sha`, `job_name`, `s3_prefix`; per-era files carry the list
  of image tags used).
- **Instrument config** in code (`instruments/mosfire.py`): band windows,
  dispersions, LSF parameters, era boundaries, each with a source comment.
- **Registry** `keck_etcs/data/index.yaml`: every shipped file with its
  `calib_version`, creation date and a one-line provenance.

*Other bands (v0.6):* throughput files per band group
(`mosfire_thru_<group>_<era>.ecsv`, the J files renamed), `.sens` files per
band, `sky/mosfire_sky_excess_<band>.ecsv` and the thermal defaults in the
instrument module (P2, P13, P14; 9.5).

### 5.5 Versioning and changelog

Code: semantic version in `keck_etcs.__version__`. Calibration products:
date tags `mosfire-J-YYYY.MM` in `index.yaml` and in each file's `meta`.
Every `compute` output echoes `keck_etcs_version`, `calib_version` and the
`pypeit_version` used to build the products. `CHANGES.md` has a section per
calibration release listing standards added, the era medians before and
after, any change in the detector table, and the image tags (with digests)
of the Nautilus reductions that fed it (4.8.5). A calibration release is one
commit touching only `keck_etcs/data/` and `CHANGES.md`.

*Other bands (v0.6, P2):* one calibration tag per release for all bands,
`mosfire-YYYY.MM`; the per-group files and `index.yaml` entries carry the
bands they cover.

## 6. Validation and testing

### 6.1 Validation on J0841+3814 (2022-04-09)

1. Reduce the four ABBA frames with PypeIt; flux the spec1d with the LDS749B
   sensfunc (`pypeit_flux_calib`).
2. Measured S/N per pixel: `OPT_FLAM * sqrt(OPT_FLAM_IVAR)` (and `S2N`,
   PypeIt's `med_s2n`) from the spec1d, per frame and for the 4-frame coadd;
   spatial FWHM from `FWHMFIT` times the plate scale.
3. ETC run: `spectrum.shape = user` with the fluxed spectrum (smoothed to
   suppress noise), `slit_width_arcsec = 1.0`, the measured FWHM, `exptime_s
   = 150`, `n_frames = 4`, `MCDS 16`, `ABBA`, airmass 1.075, PWV from the
   telluric fit, `throughput.date = 2022-04-09`.
4. Compare `snr_pixel` with the measured S/N in bins of 50 A; target: median
   ratio within 20 percent over 1.117-1.260 um, and tighter (10 percent)
   between OH lines. Also compare the ETC's `sky_e` with the fluxed PypeIt sky
   model to test D14 and set the default `sky_scale` if needed, and the
   predicted `aperture_fraction` against the optimal-extraction effective
   aperture (D16).

The fluxed spectrum is the input and the noise is the output, so the test is
not circular. Later, every KOA quasar night adds a validation point.

*Other bands (v0.6):* one validation night per band with the same 20
percent criterion, plus the thermal continuum in K (9.7).

*Results* (plan S11, 2026-10-05, and the release re-run of 2026-10-09):
see the report, `reports/Keck_MOSFIRE_report_20261009.md`, section 5.

### 6.2 Tests (pytest, `keck_etcs/tests/`)

- Unit tests with analytic cases: Poisson-only limit (`SNR = sqrt(S)` when
  sky, dark and RN are zero); a zero-width source has `slit_fraction = 1`;
  Moffat integral over the plane is 1; `RN(16) = 5.8`, `RN(1) = 21`; ABBA
  variance is stare variance plus the background terms; the exptime solver
  returns `t` such that `compute` gives the target S/N to 1e-6; Vega offset
  for J is within 0.05 of 0.91; the sky grid rebin conserves the integral to
  1e-3.
- Regression: `tests/data/reference_J.json`, `reference_J2.json`,
  `reference_line.json` freeze `compute` outputs for fixed inputs; the test
  fails on any relative change above 1e-6 unless the fixtures are regenerated
  deliberately (a `--regen` option in a helper script, and a `CHANGES.md`
  line).
- Schema: every example input validates; a field outside its range is
  rejected with a message naming the field.
- Slow (`-m slow`, needs `KECK_ETCS_DATA`): the J0841 validation of 6.1 with
  the 20 percent criterion.
- *As built (2026-10-09):* `pytest` runs 111 tests in about 6 s.
  `pytest -m slow --run-slow` adds 3 J0841 tests; all pass. The regression
  helper is `scripts/regen_regression_fixtures.py --regen --note`. Other
  tests cover the harvest, combine, trend, monitor, standards, KOA
  manifest and night-failure logic, and a check that `keck_etcs.core`
  imports without PypeIt, boto3, matplotlib or astropy.
  `scripts/check_docs.py` checks the documents against the schemas and the
  release.
- Not a test: `scripts/mosfire/compare_xtcalc.py` re-implements XTcalc's
  formula on XTcalc's own data files and tabulates the ratio of our S/N to
  XTcalc's for a grid of magnitudes and slits; the result is in the report
  (`reports/Keck_MOSFIRE_report_20261009.md`, section 6) as a sanity check.

## 7. Definition of done, MOSFIRE J milestone

1. Throughput trend table and plot from LDS749B plus at least 10 KOA
   standards spanning at least two eras, with per-era medians and MADs.
2. `compute()` working for J and J2, the JSON schemas published, unit and
   regression tests passing.
3. J0841+3814 S/N reproduced within 20 percent over the band.
4. This design document updated to "as built", and a README usage example
   (Python and CLI).
5. PypeIt branch with `ronoise` from `NUMREADS`/`SAMPMODE` filed for review.
6. A one-page API note for WMKO (inputs, outputs, versions, how to refresh
   calibrations).
7. A calibration-monitor table (4.9) for every reduced night, with the
   monitor trends of 4.6 (D40).

*Status:* see the report, `reports/Keck_MOSFIRE_report_20261009.md`, section 11.

*Other bands (v0.6):* the definition of done for the Y/H/K milestone is in
9.8.

## 8. Open items and TBDs

- **Q3 / Josh Walawender (WMKO):** *closed 2026-10-05.* The KOA census
  answered it from the data (section 4.1): the 5" slit was rare, and
  `long2pos_specphot` carries the wide-slit sample. The question was
  dropped (user).
- **KOA `SAMPMODE` census:** *done 2026-10-05.* Of 168,038 public on-sky
  spectroscopy frames: MCDS 84.2 percent (MCDS-16 73.3), CDS 14.8, UTR 0.94,
  Single 0.06. UTR stays out (D13).
- **PypeIt `ronoise` branch (D19):** *done 2026-10-09 (S17).*
  - A CDS lamp-off flat pair (m220409_0022-0026) gives 21.4 e- against the
    Keck table's 21 e- (`scripts/mosfire/measure_read_noise.py`).
  - The fix is committed on PypeIt `etc-fixes` as `38bb1b7`, with a unit
    test; the patch is `nautilus/patches/pypeit_mosfire_ronoise.patch`.
  - Open: a PR of `etc-fixes` into `develop` (user), and the pin move with
    image 0.2.6.
  - Dev-suite MOSFIRE setups all hold CDS frames, so their reference
    outputs may shift (`scripts/mosfire/devsuite_sampmode_census.py`).
  - 15 of the 20 standard rows were CDS frames reduced with 5.8 e-. Their
    throughput is expected to change well below 1 percent; this is not
    measured.
- **LSF parameters:** *settled at the release (S16).*
  `sqrt((w / 0.292)^2 + 1.08^2)` pix from 1" and 0.7" OH lines (D25, 5.3.6).
  Still open: a third slit width, which the KOA nights did not provide.
- **Sky-model validation (D14): open.**
  - OH lines over the Gemini model, per night, are 0.43-0.91 (median 0.82,
    S16).
  - The continuum between lines is 1.14-1.34x Gemini on 2022-04-09 (S11,
    S18).
  - The default stays 1.0. Lines and continuum disagree, so a better model
    needs separate line and continuum scales (a schema change) and
    sky-limited nights that measure the continuum.
- **Effective extraction aperture (D16): open.** The default 1.5 x FWHM
  gives 0.982 against the release (best 1.88; S11: 2.22). The bright
  validation star constrains it only weakly; a sky-limited night must fix
  it.
- **1" against 5" OH slit normalisation (S6b): open.** The release monitor
  uses science-slit frames only, for `sky_scale`. Check 6 of
  `verify_monitor.py` on a dark-sky wide-slit night has not been run.
- **Answered in S6b:** `pixelflat_waveimg` is filled for MOSFIRE.
  `pixelflat_raw` is in electrons per frame (lamp-on minus lamp-off mean,
  gain 2.15). The 5" standard setup uses the night's single merged
  calibration group, i.e. `WaveCalib_A_1` from the 1" science frames' OH
  lines.
- **J2 red edge:** *answered in S5.* 1.250 um, not 1.260, is the clean red
  edge; the band metrics also use `thru_median_1117_1250`. PypeIt's 1.260
  trim is kept for the fit. The release's common window (11900-12450 A)
  avoids the edge.
- **A0V model (N3):** *settled (S15a, S16).* Vega scaled to 2MASS J with
  photon-counting synthetic photometry. Unsaturated A0V nights give
  `zp_1250` 19.77-19.83 in J against 19.76-19.90 for the white dwarfs.
  - Saturated frames (> 26k ADU) are flagged and excluded.
  - The A0V blue depression is handled by the 11900 A cut (4.5).
  - 55 Dra 2014-10-05 is the one unexplained low night (excluded by 3 MAD).
- **Calibration monitor checks of S6b:** *done* (above).
- **Monitor line lists:** *frozen in S15a* (OH 11591.847, 11788.495,
  12229.206 and 12287.158 A in J2; none in J; `monitor_lines_status =
  frozen`). Lines may be added but never removed (D45).
- **Lamp arcs in KOA:** *answered by the S14 census.* Only 15 of the 43
  `long2pos_specphot` rows have Ne/Ar arcs on the mask; the KOA download
  Job fetches them (`--lamp-arcs`), and those nights are the reducible
  specphot sample (4.1).
- **Gemini grid provenance:** we hold the grids only via XTcalc's IDL save
  files (comment "From Gemini: mk_skybg_zm_16_10.dat"); record the Gemini
  page URL and, if it becomes reachable, verify against the original ASCII.

- **Other bands (v0.7):** the proposals P1-P15 of section 9 are the
  decisions D48-D62 (Q49-Q68 answered 2026-10-26); the two items still to
  verify are listed in 9.9.

Nautilus items (v0.3): the decisions of v0.2 were answered in Q27-Q39 and
are settled as D31-D39. What remains are verifications and one-time actions
by the user, each tied to the plan step that checks it:

- **Local PypeIt checkout (S0):** *settled.* The local work runs on the
  Linux workstation (`pypeit14b`), with the PypeIt checkout at the pin
  (`etc-fixes` `bc18a3b`); `check_pypeit_pin.py` passes with an empty diff.
  The laptop arrangement of v0.3.1 (`orig-hires-fixes`, allow-list) is not
  used. Since S23d (2026-10-30) the checkout is at `b0447b7`, the 0.2.6
  pin, and the check passes locally and against the image. Between S17
  and S23d the checkout was at `38bb1b7`, one commit past the pin, and
  the check fails by design until the pin moves (D35).
- **Credentials (S1b):** *settled.* `prp-s3-credentials` in `pypeit` reads
  and writes `s3://keck-etcs` (inspect pod); the fallback secret was not
  needed.
- **Registry (S4a):** *done* (user, 2026-09-30). GitLab project
  `profx/keck-etcs` with a deploy token (username
  `gitlab+deploy-token-1383`; the token stays with the user). Pushes use
  their own Docker config (`~/.docker-keck-etcs`). Images 0.1.0-0.2.6 are
  listed in `nautilus/README.md`.
- **KOA from the cluster (S14b):** *settled 2026-10-05.* `koa_probe_job.yaml`
  reached KOA's TAP service and downloaded a frame at 10.9 MB/s; the
  downloads run in-cluster (`koa_download_job.yaml`).
- **Base Python (S4b):** *settled.* The dry run on the 3.12 image matched
  the local reference within the gates (4.8.7). No switch to 3.14.
- **Wider bucket access (optional, later):** if WMKO or collaborators ever
  need the S3 products directly, a read policy for named users or pre-signed
  URLs; not part of this plan, since products ship in git. *Not done*
  (optional; noted in `nautilus/README.md` section 1).

## 9. Other bands: Y, H and K (v0.6 proposed; v0.7 decided)

*Added 2026-10-26 ("Other bands" prompt #1). This section extends the J
design to the three remaining spectroscopic bands. Everything not mentioned
here stays as in sections 1-8: the standards and the wide-slit rule (D1-D4),
the eras (D6), the `IR` sensfunc and PWV handling (D7), the Nautilus
reductions (D30-D39), the ETC equations (5.3) and the monitor (4.9). The
section was written as **proposals P1-P15**, each with the question that
put it to the user (Q49-Q63 in the prompt doc). *v0.7:* all were agreed
on 2026-10-26, with notes on Q53, Q60 and Q61 that led to the follow-ups
Q64-Q68 (also agreed); they are the decisions **D48-D62** of section 2
(P*n* = D*n+47*; Q63 is folded into D62, Q64-Q66 into D53, D60 and D61,
and Q68 into D49). The P numbers are kept below so
that the pointers in sections 1-8 stay valid; the paragraphs marked
*v0.7* carry the folded-in answers. The numbers come from
`scripts/mosfire/survey_other_bands.py` and
`scripts/mosfire/inspect_raw_headers.py` unless another source is named.
Implementation: plan Phase 7 (S23-S27) and the per-band prompt docs
`claude_prompts/keck_mosfire/keck_mosfire_prompt_{H,K,Y}.md` (9.10).*

### 9.1 Scope

**P1 = D48 (Q49, agreed).** The second milestone is MOSFIRE long-slit spectroscopy in
**Y, H and K**, with the same readout modes, source types and nod patterns
as J. **J3** (4 public long-slit frames in KOA) and **Ks** (10; an imaging
filter) are not built; J3 would only be a third filter curve on the J
grating if standards ever appear. Multi-slit masks stay out of scope, but
9.2 notes where the slit position matters for H and K.

### 9.2 Instrument facts per band

| | Y | J (as built) | H | K |
|---|---|---|---|---|
| Grating order | 6 | 5 | 4 | 3 |
| Dispersion [A/pix] (PypeIt OH template) | 1.082 | 1.303 (J2 long slit: 1.292) | 1.627 | 2.169 |
| Filter half-power band [A] (shipped curve) | 9719-11243 | 11535-13523 | 14661-18076 | 19215-24046 |
| Filter width [A] / [pix] | 1524 / 1410 | 1988 / 1526 | 3415 / 2099 | 4830 / 2227 |
| Centred long-slit footprint [A] | **9255-11471** (measured: dev-suite `Y_long` `WaveCalib_A_1`, 2040 pix, 1.087 A/pix) | 11110-13755 (J2, 2022-04-09) | **14650.5-17970.7** (measured, S23d: `longslit_3x0.7_H` 2012-11-28, 1.6284 A/pix; nominal was 14680-18040) | **19535.9-23991.1** (measured, S23d: `longslit_3x0.7_K` 2012-11-28, 2.1850 A/pix; `K_long` 2019-10-13 gives 19529.7-23957.1, a 35 A night-to-night spread at the red end) |
| ETC window (filter x footprint, N2) | 9719-11243 (filter-limited) | 11535-13523 | 14660.9-17970.7 (filter at the blue end, **detector** at the red: 105 A of the filter band fall off) | 19535.9-23991.1 (**detector-limited**: 375 A fall off) |
| AB - Vega (filter file, PypeIt Vega) | 0.655 | 0.930 (J2 0.833) | 1.365 | 1.845 |
| Long-slit wavelength calibrator (PypeIt) | `OH_MOSFIRE_Y`, 82 lines in band | `OH_MOSFIRE_J`, 66 | `OH_MOSFIRE_H`, 110 | `OH_MOSFIRE_K`, 86 (sparse beyond 2.3 um) |
| `long2pos_specphot` calibrator (Ne + Ar lines in band) | 9 + 9 | 64 + 30 | 67 + 24 | 59 + 20 |
| PypeIt `tweak_standard` clean window | 9520-11256 (contains the filter band) | J2: 11170-12600 | none | none |
| XTcalc 2012 end-to-end throughput, median (peak) | 0.237 (0.259) | 0.276 (0.319) | 0.338 (0.384) | 0.317 (0.365) |
| Mirror reflectivity per surface used by XTcalc | 0.85 | 0.89 | 0.94 | 0.95 |
| Gemini model, X 1.5, PWV 1.6: between-line continuum / brightest line [ph/s/arcsec^2/nm/m^2] | 1.0 / 970 at 1.083 um | 0.8 / 1460 at 1.291 um | 0.4 / 10800 at 1.583 um | 0.4 at 2.0 um, 2.0 at 2.4 um / 2600 at 2.001 um |
| Time for the brightest line to reach 26k ADU, 0.7" slit, T_sys 0.25 | ~19 min | ~13 min | **~1.5-2 min** | ~7 min |
| Measured May-2012 MOSFIRE sky / Gemini, between lines (model smoothed to 0.7") | 0.8-1.0 | 1.05-1.5 (2022-04-09: 1.14-1.34, S11) | **2.4-3.5** | 4 at 1.97 um, 10-20 at 2.15-2.4 um (**thermal**) |
| KOA public long-slit + long2pos spectroscopy frames | 11317 | 12052 (J2 714) | 15409 | 27575 |
| KOA nights with HIP/HD/CALSPEC-named targets on those masks | 230 | 332 (J2 14) | 415 | 372 |
| of which `long2pos_specphot` nights (the wide-slit sample) | 13 | 50 (J2 2) | 92 | 72 |

Notes.

- **Footprints.** The measured Y footprint is the J2 footprint times 5/6 to
  0.1 percent (9258-11462 A predicted), so Y and J share one grating tilt
  and the Y window is set by the filter alone. The nominal H and K
  coverages do not scale this way (K would be 1.85-2.29 um), so their
  tilts differ; the H and K footprints are measured from the dev-suite
  reductions in the first implementation step (P9). For H and K the band
  is wider than the detector, so a slit away from the CSU centre loses one
  edge of the band; the ETC models the centred long slit and says so.
- **Saturation in H.** The brightest H OH lines (1.58 um) reach the 1
  percent limit in about 1.5-2 minutes through a 0.7" slit, and
  proportionally faster in wider slits. The ETC's saturation output (5.3.11)
  already includes sky lines, so most H runs will carry the persistence
  warning; P15 adds the fraction of affected pixels so that users see how
  much of the band is involved.
- **KOA counts** are a target-name TAP count, not the full census (which
  matches SIMBAD and 2MASS and checks calibrations); the J census turned 332
  such nights into 52 usable rows on 44 nights, so expect a similar
  fraction here. H and K each offer more wide-slit nights than J did.
- **Sky.** The 2012 spectra are "second light" data calibrated by C.
  Steidel (XTcalc `MosfireSkySpec/`); moon and zodiacal light are not
  recorded. Y agrees with Gemini, J confirms the 2022 J2 excess, H is
  2.4-3.5x and K rises steeply with wavelength as a 275 K grey body of
  effective emissivity 0.12-0.15 (flat over 2.15-2.40 um; the fit moves
  to 0.09 at 280 K and 0.21 at 270 K).

### 9.3 Standards, KOA and flux models (sections 4.1, 4.3, 4.4)

**P2 = D49 (Q50, agreed), band groups.** The filter-free throughput is a property of a
grating order, so the analysis is organised by **band group**: `Y`, `J` (=
J, J2, J3), `H`, `K`. Each group gets its own era files
`mosfire_thru_<group>_<era>.ecsv` (the three J files are renamed
`mosfire_thru_J_<era>.ecsv` under the next calibration tag), its own
common window for the band median and the 3-MAD test, its own edge trim
(`EDGE_TRIM_FRAC` 0.9 of the filter peak for every band, generalising the J
rule) and, where A0V curves show a blue-edge depression as in J, its own
`A0V_MIN_WAVE`. In H that is expected: the Brackett limit (1.458 um) and
the dense high-n lines sit at the band's blue edge. One calibration tag per
release covers all groups: `mosfire-YYYY.MM` (replacing `mosfire-J-YYYY.MM`,
D28), with `bands` listed per file in `index.yaml`. *v0.7 (Q68):* the
band-neutral refactor (S23) ends with a **J-only tag** (`mosfire-2026.MM`
at the month S23 lands) whose products carry the same numbers as
`mosfire-J-2026.10` under the new names and columns, verified by a
regression comparison of `compute()` outputs before and after (identical
to 1e-6); the Y/H/K tag of S27 is a second release.

**P3 = D50 (Q51, agreed), KOA census.** `scripts/koa/search_mosfire_standards.py` gains
`--filters` (its `BASE_WHERE` is J-only today) and records the 2MASS H and
Ks magnitudes beside J. The candidate rows of every band go into the one
table `keck_etcs/data/mosfire/koa_standards_candidates.ecsv` with a
`filter` column (H-1 in the H prompt doc); the table is per instrument,
so the other Keck instruments that join later each get their own under
`keck_etcs/data/<instrument>/`, with instrument-neutral column names.
The selection rules of 4.1 are unchanged: wide
slits (>= 3", in practice `long2pos_specphot`) for throughput, a wavelength
calibrator on the night (narrow-slit OH frames >= 55 s in the band, or
Ne/Ar arcs on the long2pos mask), flats in the band. CALSPEC white dwarfs
are the absolute anchors as in J; they are faint in K (GD153 K ~ 14.1
Vega), so the A0V series will dominate H and K.

*Census results (S23c, 2026-10-27; `search_mosfire_standards.py --filters
J Y H K`, 2525 rows on 716 nights; the J rows unchanged; the 9.2 TAP
counts reproduced, J by one frame less because its cache predates the
survey):*

| | Y | J | J2 | H | K |
|---|---|---|---|---|---|
| Candidate rows / nights | 451 / 272 | 570 / 364 | 24 / 18 | 758 / 464 | 722 / 414 |
| Usable wide-slit rows / nights | 23 / 21 | 43 / 38 | 9 / 8 | 87 / 72 | 77 / 60 |
| of which reducible nights | 12 | 16 | 4 | 35 | 55 |
| WD / archive / A0V rows (usable wide) | 9 / 0 / 14 | 3 / 1 / 39 | 7 / 0 / 2 | 1 / 1 / 85 | 1 / 1 / 75 |
| Reducible nights per era (2012-16 / 2017-25 / 2025-) | 0 / 8 / 4 | 7 / 9 / 0 | 0 / 3 / 1 | 16 / 19 / 0 | 19 / 36 / 0 |
| Nights with a WD and an A0V star, wide slit (any slit) | 0 (10) | 0 (7) | 0 (0) | 0 (6) | 0 (9) |

H and K each hold more wide-slit nights than J, almost all A0V on
`long2pos_specphot` with lamp arcs (K: 55 of 60 usable nights reducible),
and one white dwarf each (plus one archive star), so D52's cross-tie in H
and K must use a white dwarf and an A0V star from different nights of the
same era, or the narrow-slit pairs (6 nights in H, 9 in K hold both
classes on some slit). Y has 9 white-dwarf rows (GD153, LDS749B) but no
2012-2016 wide-slit night; its 2025 era has 4.

*S23d result (D52, 2026-10-27; `scripts/mosfire/brackett_mask_check.py`
on HIP 17971, `longslit_3x0.7_H`, 2012-11-28, PypeIt at the pin with the
`slitrange` patch):* PypeIt's IR sensfunc algorithm does not use
`hydrogen_mask_wid` at all (only the UVIS algorithm's `standard_zeropoint`
does), so the 10 A and 30 A runs are identical to 1e-4 mag; and the Vega
model leaves no Brackett residual at R ~ 3000: the per-pixel zero point
minus PypeIt's fit has an rms of 0.019 mag within +-40 A of Br10-18 against
0.018 mag in the line-free continuum (ratio 1.08). D52's mask is therefore
moot for the IR algorithm; the H and K `.sens` files carry no mask line,
and the A0V series in H needs no special treatment at the Brackett lines
beyond the model.

**P4 = D51 (Q51, agreed), A0V model per band.** N3 scales PypeIt's Vega spectrum to the
star's 2MASS J. For the other bands the scaling uses the **band's own 2MASS
magnitude**: J for Y and J, H for H, Ks for K, with PypeIt's `TMASS-J/H/K`
curves (`filtercurves.fits`; Ks half-maximum 2.028-2.299 um lies inside the K
window). This avoids relying on the Vega model's colours over 1 um; the
J-scaled model is kept as a cross-check column (`a0v_scaled_to`,
`a0v_jhk_offset_mag`). `keck_etcs.calib.standards` becomes
`a0v_model(band, mag)`.

**P5 = D52 (Q52, agreed), hydrogen lines.** PypeIt masks the Balmer, Paschen, Brackett
and Pfund lines of a standard with `hydrogen_mask_wid` = 10 A on each side.
At R ~ 3000 an A0V Brackett line in H (Br 10-18, 1.52-1.74 um) is 50-100 A
wide, so the default mask leaves the wings in the zero-point fit. Proposal:
`hydrogen_mask_wid` = 30 A in the H and K `.sens` files (Br gamma 2.166 um
in K), 10 A in Y and J as now, and the value checked on a night with both a
white dwarf and an A0V star in H (cross-tie, D2). If no such night exists
the check uses the smoothness of the A0V zero point across the masked
regions. The PypeIt parameters exist; no PypeIt change is needed.

**P6 = D53 (Q53, agreed), sensfunc parameters.** One repo-owned file per band,
`keck_etcs/data/pypeit_par/keck_mosfire_<band>.sens`, with the J settings
(4.3) except `polyorder` 6 (Y, 1500 A) and, for H (3400 A) and K (4400 A),
**the lowest order that passes a measured test, starting at 5** (*v0.7*,
Q53/Q64: the user prefers a lower order than the proposed 8 if it holds).
The test extends `sensfunc_perturbation_test.py` to loop over `polyorder`
4, 5, 6 and 8 on each band's dev-suite reference night
(`longslit_3x0.7_H` and `_K`, HIP 17971, 2012-11-28, 0.7") and on the
first wide-slit KOA standard reduced per band, and takes the lowest order
that passes both: (a) the 1e-5 perturbation stability of the zero point is
below 1 percent; (b) the zero point differs from the next order up by less
than 1 percent rms over the band's common window and less than 2 percent
within 100 A of its edges, where an underfit shows first. The chosen order
and the test table go into the `.sens` file header and into this section;
the S5 fallback (polyorder 4-5 or a BOX extraction when the fit is
unstable) stays, and Y keeps 6 unless the same test says lower.
`tell_npca` is chosen per band by the same script (default 3;
K has the CO2 bands at 2.01 and 2.06 um and water at both edges, so it may
need more components). PypeIt's `tweak_standard` has no clean window for H
and K; the filter-edge handling stays on the keck-etcs side (the edge trim
of P2), which is not a PypeIt defect.

**P7 = D54 (Q54, agreed), metrics per band.** The harvest row (4.4) keeps its structure
with band-neutral column names: `zp_lo`, `zp_mid`, `zp_hi` at the band's
three nodes, `thru_median_common` over the band's common window, and the
node and window values in the row (`zp_nodes_A`, `common_window_A`) and in
the instrument module. The nodes and windows:

| Group | Zero-point nodes [um] | Common window [um] | PWV window | Notes |
|---|---|---|---|---|
| Y | 1.00, 1.05, 1.10 | 0.98-1.11 | none inside the band: `pwv_weak` | second-order light outside 0.952-1.126 um is already masked by PypeIt |
| J | 1.20, 1.25, 1.30 (J2: 1.15, 1.20, 1.25) | 1.19-1.245 | 1.117-1.26 (as built) | unchanged |
| H | 1.55, 1.65, 1.75 | 1.49-1.78 | band edges only (1.45, 1.80): `pwv_weak` | |
| K | 2.05, 2.15, 2.30 | 1.98-2.37 | 1.95-2.00 and 2.38-2.40 (water); CO2 is not water | thermal continuum measured per night (9.5) |

The J columns `zp_1200`, `zp_1250`, `zp_1300`, `thru_median_1117_1260` and
`thru_median_1117_1250` are regenerated from the harvest files under the
new names in the next release; the report's `thru_common` is already the
band-neutral quantity. Where the PWV estimate is weak it is still recorded
(it only feeds the sky-grid comparison), with `flag = pwv_weak`.

### 9.4 Reductions on Nautilus (sections 4.2, 4.8)

**P8 = D55 (Q55, agreed), multi-band nights.** The night manifests gain a `band` column
and a night observed in several bands becomes several rows. The raw frames
of a night are downloaded once to `mosfire/<night>/raw/` (the download Job
takes a list of bands and fetches each band's flats and arcs); the products
of a (night, band) go to `mosfire/<night>/<band>/{redux,sens,harvest}`,
`run_manifest.json` and `run.log` included, so idempotency (D33) is per
row. J products stay where they are. `reduce_standard.py` already selects a
single filter (`--filter`, from the manifest's `filter` column); it gains
the per-band `.sens` file and the per-band gate values. The gates
(`nautilus/gates.py`) read their windows from the instrument module: the
zero point finite over the band's common window, the `OPT_COUNTS` fidelity
window the middle third of it, and the median throughput within 0.5-1.6x
XTcalc's 2012 median for the band (Y 0.12-0.38, H 0.17-0.54, K 0.16-0.51;
J's 0.15-0.45 is 0.54-1.63x of 0.276). Image, pin, resources and failure
handling are unchanged; the `.sens` files ship as package data.

**P9 = D56 (Q56, agreed), reference reductions.** The dev suite holds one long-slit
night per band with a standard, raw frames on this workstation and PypeIt
files that run at the pin:

| Setup | Night(s) | Standard, slit | Science | Gives |
|---|---|---|---|---|
| `Y_long` | 2019-11-18 (std), 2019-11-20 | GD71 (CALSPEC WD), LONGSLIT-46x1 | quasar J2132-1434, 1" | Y footprint (done), Y LSF at 1", a WD zero point (slit loss included), a Y validation fallback |
| `longslit_3x0.7_H` and `_K` | 2012-11-28 | HIP 17971 (A0V), LONGSLIT-3x0.7 | none | H and K footprints, 0.7" LSF, the Brackett-mask test (P5), the 2012-era K thermal continuum |
| `K_long` | 2019-10-13 | HIP 17971 (A0V), LONGSLIT-46x1.5 | Per-emb 25 | 1.5" LSF, K thermal continuum in 2019, OH wavelength solution beyond 2.3 um |
| `long2pos1_H` | 2018-07-18 | HIP 61138 (A0V), long2pos with Ne/Ar arcs | none | the lamp-calibrated H path |

They are reduced locally first (`pypeit14b`, as 2022-04-09 was for J2) and
then in-pod with `validate_job.yaml` as each band's dry run, with the
gates of P8 and the reference comparison of 4.8.7. Their slits are narrow,
so they are LSF, footprint, sky and pipeline references, not throughput
points (D4).

*S23d results (2026-10-27, rerun 2026-10-30 in image 0.2.6).* The four
setups were reduced with `reduce_standard.py` inside the image (first
0.2.5 at the pin bc18a3b with the `SLITRANGE` patch applied; then, once
that fix was committed and pinned, 0.2.6 at b0447b7, whose products are
the ones kept and staged), the current repository mounted, with the raw
frames staged under `mosfire/20121128/raw` (both H and K), `20191013/raw`
and `20180718/raw` and the products under `mosfire/<night>/<band>/`
(P8). `longslit_3x0.7_H` and `_K`: the HIP 17971 frames (2.9 s) serve as
their own OH arcs as in the dev-suite files (wavelength RMS 0.066 and
0.037 pix), S/N 130-160 per frame, median end-to-end throughput through
the 0.7" slit 0.24 (H) and 0.25 (K) over the common windows, both gates
PASS with the P8 windows. `K_long`: RMS 0.091 pix, HIP 17971 S/N 140,
Per-emb 25 found. `long2pos1_H`: the lamp-calibrated path works (Ne/Ar
arcs, `keck_mosfire_arcs_H.fits`, RMS 0.21 and 0.17 pix on the two
slits), but HIP 61138 is extracted with S/N 2-9 only, in the driver and in
the dev-suite PypeIt file alike, so this is PypeIt's long2pos reduction of
that night, not the driver (the H A0V sample is `long2pos_specphot`, the
bar-split path of S15); to be looked at in S24a. KOA holds no H or K flats
for 2012-11-28 (the dev suite pairs its standard with 2013-10-15 flats), so
the in-pod dry runs take the dev-suite raw frames pushed to
`mosfire/20121128/raw/` and the staged local references
(`nights_dryrun_HK.csv`). A PypeIt defect surfaced: `pypeit_sensfunc` on a
spec1d of a short long slit (`LONGSLIT-3x0.7`) crashes in
`config_specific_par` (`slitrange` is None for a product header);
`nautilus/patches/pypeit_mosfire_slitrange_spec1d.patch` reads the
header's `SLITRANGE` card instead and was applied inside the image for
the reference sensfuncs; it is committed on `etc-fixes` as `b0447b7` and
pinned by image 0.2.6. The 0.2.6 rerun (the first with the CDS read noise
of 21 e-, D19) reproduces the footprints to 0.1 A, the wavelength RMS and
the LSF rows exactly, and lowers the extracted S/N per frame by about 5
percent and the throughput medians by 0.5 percent (H 0.240, K 0.246).

**P10 = D57 (Q57, agreed), order of work.** H first (the largest wide-slit sample, no
new physics; it exercises every band generalisation), then K (the thermal
term), then Y (the smallest sample; shares the J grating tilt). Batches are
sized from the J per-night rate; H and K are each about twice the J batch.

### 9.5 ETC (section 5)

**P11 = D58 (Q58, agreed), schema and instrument module.** `band` takes `Y`, `H`, `K`.
`Band` gains `group`, `order`, `zp_nodes_A`, `common_window_A`,
`pwv_window_A` and a per-band LSF entry; `Instrument.throughput_pattern`
takes `{group}`; `SPLICE_WINDOW` becomes the group's common window;
`throughput_for_window` completes a window from another era of the same
group only. `meta.calib_version` is the release tag. Examples
`examples/{Y,H,K}_point.json` and regression fixtures
`reference_{Y,H,K}.json` are added; the XTcalc comparison runs per band
(its port already carries XTcalc's Y/H/K constants).

**P12 = D59 (Q59, agreed), LSF.** The D25 rule is in pixels and holds to first order in
every band (same slit image, same detector). It is used for Y, H and K
with a warning until the monitor's OH widths (4.9.3; the Y, H and K OH
lists exist) give per-band slope and floor; `lsf_measurements.ecsv` already
has a `filter` column and `Instrument.lsf_fwhm_pix(slit, band)` prefers a
measured row of the band. XTcalc's resolving powers (R x 0.7" = 3380, 3310,
3660, 3620 for Y, J, H, K) imply a 0.7" image of 2.9 pix in Y and J and
2.7 pix in H and K, a 5 percent difference the measurement should show.

*S23d measurements (2026-10-27; `measure_lsf.py --band --record`, OH lines
of the reference reductions):* H at 0.7" (2012-11-28, 8 clean lines of 28,
the H OH lines are dense and blend) 2.560 pix = 4.15 A at 1.65 um, R =
3976; K at 0.7" (2012-11-28, 5 clean lines) 2.613 pix = 5.65 A at 2.15 um,
R = 3803; K at 1.5" (`K_long`, 2019-10-13, 17 lines) 5.370 pix = 11.6 A, R
= 1850. Against the J quadrature rule in pixels (2.627 at 0.7", 5.249 at
1.5") that is -2.6, -0.5 and +2.3 percent: the rule holds in H and K to a
few percent, the expected 5 percent narrowing is not seen at 0.7", and the
rows now take precedence at those slit widths. The table's columns are
band-neutral (`ref_wave_A`, `fwhm_A_ref`, `R_ref`).

**P13 = D60 (Q60, agreed), thermal background in K.** The Gemini model is the sky alone;
MOSFIRE sees the telescope and dome too. The measured 2012 K sky exceeds
the model by a grey body (9.2): 2.7, 5.2, 9.1, 12.8 and 21 ph/s/arcsec^2/nm/m^2
at 2.15, 2.25, 2.30, 2.35 and 2.40 um, i.e. `eps_eff` = 0.15, 0.12, 0.14,
0.13, 0.15 at 275 K. The ETC adds

```
B_th(lam) = eps_eff * P_ph(lam, T_amb)        [ph/s/arcsec^2/nm/m^2]
P_ph      = 2 c / lam^4 / (exp(h c / (lam k T)) - 1) * (arcsec^2 in sr) * 1e-9
```

to the sky before `T_sys` (5.3.8), unattenuated by `T_atm`. `eps_eff` is
referred to above the telescope, so it absorbs the mirrors' own
transmission; it is an instrument-module constant with defaults `eps_eff
= 0.15`, `T_amb = 275 K`, both re-fitted from our K-band frames (the
dark-sky median between lines minus the Gemini model, 2.15-2.40 um, per
night; a monitor metric, 9.6) once the reference and pilot nights are
reduced. Because the term changes by about 50 percent per 5 K, the schema
gains an optional `ambient_temp_C` (default 2 C). The term is computed for
every band and is negligible outside K (eps 0.15 at 1.80 um: 0.05 against
a continuum of 0.4), and the output gains `thermal_e`.

*v0.7 (Q65): the ambient temperature is the header card `TUBETEMP`.*
Every MOSFIRE frame we hold carries `TUBETEMP` ("tube temperature",
degrees C): 238 frames on 30 nights from 2012-09-10 to 2025-07-23, dev
suite and KOA downloads alike (`scripts/mosfire/inspect_raw_headers.py
--stat TUBETEMP --by-night`); median 1.6 C, range -3.4 to +4.9 C, with a
per-night spread usually below 0.5 K. No card gives a dome or mirror
temperature, and the dewar cards (`DWRTMP1-8`, 11-121 K) are irrelevant.
Hence: (a) the monitor records `tube_temp_C` per on-sky frame in every
band (9.6); (b) the per-night K thermal fit holds T at the night's median
`TUBETEMP` and fits `eps_eff` alone, since T and `eps_eff` are degenerate;
(c) the ETC default for `ambient_temp_C` becomes the median `TUBETEMP` of
the K throughput sample once it exists (the 238 frames give 1.6 C, so the
provisional 2 C stands), and the ETC documentation states the spread it
covers: -3.4 to +4.9 C moves the thermal term by about -40 to +35 percent,
which is why the input is exposed. The tube is a proxy for the mirrors
and the dome, the 275 K grey body that `eps_eff ~ 0.15` describes; if the
fitted per-night `eps_eff` correlates with `TUBETEMP`, the model is wrong
and T belongs to something else (the instrument's warm window, which is
not in the header), to be reported in S25.

*S23d first values (2026-10-27; `scripts/mosfire/fit_thermal_continuum.py`
on the K reference nights, sky from the raw frames divided by the pixel
flat and the exposure time, the Gemini model at the frame's airmass and
1.6 mm, both as 10th-percentile floors in 100 A bins over 2.15-2.40 um,
T_sys the **provisional** XTcalc 2012 curve):* 2012-11-28 (four 2.9 s
HIP 17971 frames, `TUBETEMP` 1.59 C): measured floor 20 (2.15 um) to 41
(2.40 um) ph/s/arcsec^2/nm/m^2, 35-40x the model, `eps_eff` = 0.47 at
274.7 K (0.46 at 275 K), declining from 1.09 at 2.155 um to 0.27 at 2.395
um; 2019-10-13 (two 119 s Per-emb 25 and two 2.9 s HIP 17971 frames,
`TUBETEMP` 4.79 C): floor 8.8 to 38.6, 13-18x the model, `eps_eff` = 0.23
at 278 K (0.29 at 275 K), from 0.34 to 0.19 across the band. The 2019
floor rises 4.4x across the band, close to XTcalc's 2012 spectrum (2.7 to
21), while the 2012 night's short frames hold a flat ~20 component at
2.15-2.25 um on top of the thermal rise, which a 2.9 s frame's pedestal or
read floor can produce; in both nights the excess is **flatter than a
275 K grey body** (whose rise over 2.15-2.40 um is 7.8x), so a single
`eps_eff` at the tube temperature does not describe the between-line
floor at the blue end of K: the D61 continuum excess and the D60 thermal
term overlap there, and part K must fit them together (the excess curve
from the long dark frames, the thermal term from the red end) and replace
the provisional T_sys. The red-end values (2.35-2.40 um: 0.19-0.20 on the
2019 night, 0.27-0.33 in 2012) sit 1.3-2x above the design's 0.12-0.15
from XTcalc's 2012 sky, within what the provisional throughput and the
2012 night's pedestal can account for.

**P14 = D61 (Q61, agreed), sky continuum excess.** Between the OH lines the measured sky
exceeds the Gemini model by 1.05-1.5x in J (1.14-1.34x on 2022-04-09) and
2.4-3.5x in H, while Y agrees; a single `sky_scale` cannot fit lines and
continuum (section 8). Proposal: a per-band **additive excess** `E_band(lam)`,
a smooth curve in Gemini units measured from our own reduced frames (dark
sky, Sun below -18 deg, no object in the window; PypeIt's sky model per
frame divided by the night's `T_sys`, the 10th percentile in 100 A bins,
the median over nights), shipped as `sky/mosfire_sky_excess_<band>.ecsv`
and added inside the `sky_scale` bracket (5.3.8). Until a band's curve is
measured it is zero and `compute` warns for H and K that the continuum
between lines is underpredicted. The alternative, a per-band
`sky_continuum_scale`, is simpler but mixes the OH wings into the factor.

*v0.7 (Q61, Q66): which frames qualify.* Twilight frames are excluded in
every band (Sun below -18 deg, the monitor's `twilight` flag). There is no
Moon card in the headers; the monitor computes `moon_alt_deg`,
`moon_illum` and `moon_sep_deg` per frame by ephemeris, exactly as it
computes the Sun's altitude from `MJD-OBS` and the site, and records them
for every band. The user's rule: the Moon should not matter in H or K, so
a cut is applied **only to the Y curve**, and only if enough frames
remain. A frame is "moonlit" when the Moon is above the horizon and more
than 30 percent illuminated; the Y curve uses dark frames if they number
at least 20 over at least 3 nights, otherwise it uses all frames, carries
`moon_included = true` in its metadata, and the dark-minus-moonlit
difference is reported so the cut can be applied at a later release. J, H
and K use all frames (the 2022-04-09 J excess already measured stands).

**P15 = D62 (Q62, agreed), saturation output.** `saturation` gains
`frac_pix_nonlinear_1pct`, the fraction of spectral pixels whose brightest
spatial pixel exceeds 26k ADU in one frame, so that an H-band user sees
whether the flag means a few OH lines or the whole band. The peak and flag
are unchanged.

### 9.6 Monitor (section 4.9)

The configuration becomes per band: FWHM nodes = the zero-point nodes of
P7; flat nodes every 250 A over the window (Y 6, H 14, K 18 nodes);
`band_windows`; monitor lines chosen by the rules of 4.9.4 on each band's
reference and pilot nights (`select_monitor_lines.py --band`, frozen as
for J2), including Ne/Ar lines for lamp nights; `lsf_ref_wave` per band
(the middle node). K adds the metric `sky_continuum` (e-/s/arcsec^2/A and
the same above the instrument) in 2.30-2.40 um on every on-sky frame, which
with the night's median `TUBETEMP` is the per-night input to P13. *v0.7:*
every on-sky monitor row in every band carries `tube_temp_C` (from
`TUBETEMP`) and the ephemeris columns `moon_alt_deg`, `moon_illum` and
`moon_sep_deg` beside the existing `sun_alt_deg`; they are recorded, not
gated, and P14 reads them when selecting frames for the excess curves.

### 9.7 Validation (section 6)

One validation night per band with the 6.1 method and the 20 percent
criterion (D18): `scripts/koa/find_validation_targets.py` is re-run for Y,
H and K (the Hennawi/Yang/Wang quasar nights include Y and K setups;
whether a same-night wide-slit standard exists is what the census says).
Fallbacks from the dev suite: J2132-1434 in Y (2019-11-20; its standard is
GD71 two nights earlier through a 1" slit, so slit loss enters the flux
calibration and the test is weaker) and Per-emb 25 in K (2019-10-13; a
bright embedded source, useful for the thermal continuum, not for the
faint-source regime). In K the sky comparison of 6.1 step 4 includes the
thermal continuum at 2.30-2.40 um, to be within 30 percent.

*Results (S23c, 2026-10-27; `find_validation_targets.py` over all bands,
202 program targets on 24 nights):* Y has 15 validation nights, 9 of them
with a same-night wide-slit standard (LDS749B 2022-04-09, which the
program also observed in Y; GD153 2024-12-29/30, 2025-01-08/25 and
2025-07-17/18/22/23, the last four in era 2025-04..), so the Y validation
night is a KOA night, not the dev-suite fallback. H has one validation
point (J1532+2237, 2022-01-11, GD153 on a 1" slit) and K two (J0313-1806,
2020-12-09, GD153, 1"; J1342+0928, 2021-04-18, P330E, 1"), all with
narrow-slit standards; no H or K program night carries a wide-slit
standard, so the H and K validation nights flux with a narrow-slit
standard (slit loss enters, as for the Y fallback) or use Per-emb 25 in
K.

### 9.8 Definition of done, Y/H/K milestone

0. *(v0.7, Q68)* The band-neutral refactor released as a J-only tag
   `mosfire-2026.MM` whose `compute()` outputs equal those of
   `mosfire-J-2026.10` to 1e-6, before any H product exists.
1. Per band: throughput trend table and plot from at least 10 KOA
   wide-slit standards over at least two eras (Y: at least 5, given its 13
   candidate nights), with era medians and MADs, under one release tag
   `mosfire-YYYY.MM` that also carries the renamed J products.
2. `compute()` for Y, H and K with examples, fixtures and the XTcalc
   comparison per band; the thermal term and the H saturation fraction in
   place; the WMKO API note and the developer docs updated.
3. One validation night per band within 20 percent (K: thermal continuum
   within 30 percent).
4. The H and K footprints, the per-band LSF and the monitor lines measured
   and recorded with provenance.
5. The sky-excess curves measured where the data allow (at least H), or the
   warning in place.
6. This document updated to "as built" for the bands delivered.

### 9.9 Items still to verify

*v0.7:* no open questions remain (Q49-Q68 answered). Two of the four
verification items of v0.6 are settled: the ambient-temperature card is
`TUBETEMP` (P13) and the Moon has no card and is computed (P14). Still to
verify, in S23 and the census: the H and K footprints (P9; measured from
the dev-suite reference reductions before the band windows are frozen);
whether the Hennawi/Yang/Wang nights offer same-night wide-slit standards
in Y, H or K (9.7); and whether any night has both a white dwarf and an
A0V star in H or K (P5).

### 9.10 Implementation (v0.7)

The plan (`docs/keck_mosfire_implementation.md`, v0.5) adds **Phase 7** as
steps S23-S27 in the agreed order: **S23** band-neutral refactor (P2, P7,
P8, P11, the census re-run with `--filters Y,H,K`, the dev-suite reference
reductions of P9, the J rename and regeneration, the J-only tag of Q68);
**S24** H (plus the saturation fraction, which H needs most; H-4 in the H
prompt doc); **S25** K (plus the thermal term and `TUBETEMP`); **S26** Y
(plus the Moon cut); **S27** release and docs. The
prompt docs are one per band, as the user asked:
`keck_mosfire_prompt_H.md` (S23 and S24), `keck_mosfire_prompt_K.md` (S25)
and `keck_mosfire_prompt_Y.md` (S26 and S27), to be run in that order.

## 10. References

- Keck MOSFIRE pages: instrument home, detector (`detector.html`), filters
  (`filters.html`), throughput (`throughput.html`), news (`news.html`), ETC
  landing page (`etc.html`) with XTcalc tarball and
  `XTcalc_dir/MOSFIRE_XTcalc.pdf` in Keck's `XTcalc.tar` (G. C. Rudie, v2.0, 2012-06-29).
- Kulas, K. R., et al. 2012, "Performance of the HgCdTe detector for MOSFIRE",
  Proc. SPIE 8453, arXiv:1208.0314.
- McLean, I. S., et al. 2012, "MOSFIRE, the multi-object spectrometer for
  infra-red exploration at the Keck Observatory", Proc. SPIE 8446.
- Lord, S. D. 1992, NASA Technical Memorandum 103957 (ATRAN), as used in the
  Gemini Observatory Maunakea IR sky background and transmission models.
- Bohlin, R. C., et al., CALSPEC (STScI); PypeIt `data/standards/calspec`.
- PypeIt: Prochaska et al. 2020, JOSS 5, 2308; local checkout 2.0.2.dev1217;
  `pypeit/spectrographs/keck_mosfire.py`, `pypeit/core/flux_calib.py`,
  `pypeit/core/standard.py`, `pypeit/core/telluric.py`, `pypeit/sensfunc.py`.
- Moffat, A. F. J. 1969, A&A 3, 455; Trujillo et al. 2001, MNRAS 328, 977
  (beta ~ 3.5 for ground-based seeing).
- Blanton, M. R., & Roweis, S. 2007, AJ 133, 734 (AB-Vega offsets used by
  XTcalc).
- Skrutskie, M. F., et al. 2006, AJ 131, 1163 (2MASS).
- Repository scripts behind the numbers here:
  `scripts/inspect_mosfire_j2_headers.py`, `scripts/check_mosfire_standards.py`,
  `scripts/inspect_xtcalc_files.py`, `scripts/size_gemini_sky_subset.py`,
  `scripts/mosfire_band_footprints.py`, and for section 9
  `scripts/mosfire/survey_other_bands.py`.
- Keck XTcalc tarball contents used in section 9: `MosfireSkySpec/`
  (C. Steidel, calibrated May-2012 MOSFIRE sky spectra per band, 0.7" slit)
  and `MosfireSpecEff/` (2012 efficiency curves and the per-band mirror
  reflectivities 0.85 / 0.89 / 0.94 / 0.95 for Y / J / H / K).
- Nautilus precedents (D30, section 4.8): the PAB project's
  `Oceanography/python/PAB/nautilus/` (`build_image.sh`, `Dockerfile`,
  `*_job.yaml`, `s3_push.py`, `v2_validate_gates.py`, `rediscover_csv.py`,
  `v2_ingest_failures.py`, `inspect_pod.yaml`), its `HOWTO.md` and
  `claude_prompts/nautilus_prompts.md`; the PypeIt dev suite's
  `PypeIt-development-suite/nautilus/` (`gen_kube_devsuite`,
  `kube_dev_suite.yaml`, `README_s3`, `s3_pypeit_policy.json`); PypeIt's
  `pypeit/pkg/cache.py`, `pypeit/data/s3_url.txt` and the
  `pypeit_install_telluric` / `pypeit_cache_github_data` scripts.
