# Keck/MOSFIRE J-band: sensitivity analysis and exposure-time calculator design

*Version 0.5 ("as built"), 2026-10-09. Decisions come from the Q&A in
`claude_prompts/keck_mosfire/keck_mosfire_prompts.md` (rounds 1 and 2, all agreed; round
(d) on Nautilus, Q27-Q39, answered 2026-09-30; Calibrations, Q40-Q48,
answered 2026-10-04). Readers: the PypeIt/keck-etcs
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
- **Pin (D31, 4.8.2):** on PypeIt `etc-fixes` (`bc18a3b`), not `develop`.
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
- `bc18a3b` (0.2.5): `construct_basename`.

Image 0.2.5 is current. The `ronoise` fix (D19) is on `etc-fixes` as
`38bb1b7` and goes into the next image. `nautilus/README.md` has every tag
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
| `band` | str | `"J"` | `J`, `J2` (later Y, J3, H, K) | filter |
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

### 5.5 Versioning and changelog

Code: semantic version in `keck_etcs.__version__`. Calibration products:
date tags `mosfire-J-YYYY.MM` in `index.yaml` and in each file's `meta`.
Every `compute` output echoes `keck_etcs_version`, `calib_version` and the
`pypeit_version` used to build the products. `CHANGES.md` has a section per
calibration release listing standards added, the era medians before and
after, any change in the detector table, and the image tags (with digests)
of the Nautilus reductions that fed it (4.8.5). A calibration release is one
commit touching only `keck_etcs/data/` and `CHANGES.md`.

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

Nautilus items (v0.3): the decisions of v0.2 were answered in Q27-Q39 and
are settled as D31-D39. What remains are verifications and one-time actions
by the user, each tied to the plan step that checks it:

- **Local PypeIt checkout (S0):** *settled.* The local work runs on the
  Linux workstation (`pypeit14b`), with the PypeIt checkout at the pin
  (`etc-fixes` `bc18a3b`); `check_pypeit_pin.py` passes with an empty diff.
  The laptop arrangement of v0.3.1 (`orig-hires-fixes`, allow-list) is not
  used. Since S17 the checkout is at `38bb1b7`, one commit past the pin, and
  the check fails by design until the pin moves (D35).
- **Credentials (S1b):** *settled.* `prp-s3-credentials` in `pypeit` reads
  and writes `s3://keck-etcs` (inspect pod); the fallback secret was not
  needed.
- **Registry (S4a):** *done* (user, 2026-09-30). GitLab project
  `profx/keck-etcs` with a deploy token (username
  `gitlab+deploy-token-1383`; the token stays with the user). Pushes use
  their own Docker config (`~/.docker-keck-etcs`). Images 0.1.0-0.2.5 are
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

## 9. References

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
  `scripts/mosfire_band_footprints.py`.
- Nautilus precedents (D30, section 4.8): the PAB project's
  `Oceanography/python/PAB/nautilus/` (`build_image.sh`, `Dockerfile`,
  `*_job.yaml`, `s3_push.py`, `v2_validate_gates.py`, `rediscover_csv.py`,
  `v2_ingest_failures.py`, `inspect_pod.yaml`), its `HOWTO.md` and
  `claude_prompts/nautilus_prompts.md`; the PypeIt dev suite's
  `PypeIt-development-suite/nautilus/` (`gen_kube_devsuite`,
  `kube_dev_suite.yaml`, `README_s3`, `s3_pypeit_policy.json`); PypeIt's
  `pypeit/pkg/cache.py`, `pypeit/data/s3_url.txt` and the
  `pypeit_install_telluric` / `pypeit_cache_github_data` scripts.
