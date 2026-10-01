# Keck MOSFIRE implementation, part 2: first sensfunc, image and dry run (Phase 1)

## Goals

Reduce the 2022-04-09 J2 long-slit night once locally as the reference,
build the container image and the Nautilus job templates, reproduce the
reduction in a pod and gate it against the reference, build the LDS749B
sensitivity function with the `IR` (telluric) algorithm, harvest its zero
point and throughput into the per-standard table (in the pod, merged
locally), and measure the line-spread function from OH lines. These are
steps S4, S4a, S4b, S5, S6 and S13 of the plan (v0.3).

Run order: after part 1 (S0 check, S1, S1b, S2). Prompts 1 (S4) -> 5 (S4a)
-> 6 (S4b) -> 2 (S5) -> 3 (S6); prompt 4 (S13) needs only S4 or S4b and can
run in parallel with 2 or 3. Prompts 5 and 6 were added in v0.3 and carry
the numbers 5 and 6 so that the original prompt numbers 1-4 keep their
meaning; the run order above is the one to follow. S6 also needs the filter
curves from part 3 step S8; if part 3 has not run yet, do S6 without the
filter division and note it (`flag = nofilter`). Part 3 (ETC core) can run
in parallel with this doc. The reductions are compute-bound (tens of
minutes locally, similar in a pod); keep S4 and the dry run in their own
sessions.

## Context

- Design: `docs/keck_mosfire_design.md` (v0.3), sections 2 (D1-D8, D19,
  D30-D36, N1, N3), 4.2 (workflow, S3 layout, local mirror), 4.3 (sensfunc
  and telluric settings), 4.4 (metrics and the per-standard table columns,
  now including the six provenance columns), 4.8 (image, storage, jobs,
  provenance, failure handling, dry run and gates), 5.3.6 (LSF model), 8
  (residual verification items).
- Plan: `docs/keck_mosfire_implementation.md` (v0.3), steps S4, S4a, S4b,
  S5, S6, S13 and the risks section.
- Data root `KECK_ETCS_DATA` (default
  `/Users/xavier/Projects/PypeIt/keck-etcs-data`), the local mirror of the
  private bucket `s3://keck-etcs`: raw frames in `mosfire/20220409/raw/`
  (also on S3 from part 1); write local reductions to
  `mosfire/20220409/redux/` and sensfuncs to `mosfire/20220409/sens/`;
  synced in-pod products land in the same places via
  `scripts/nautilus/s3_sync.py pull mosfire/20220409`. Nothing there is
  committed.
- PypeIt pin: `nautilus/pypeit_pin.txt` (a commit on `develop`,
  `f3a1f1d27` on 2026-09-30; part 1 wrote it). The image runs exactly that
  commit. The laptop checkout stays on `orig-hires-fixes` (HEAD `017bece06`,
  one commit ahead of the pin, differing only in
  `pypeit/spectrographs/keck_hires.py`); `scripts/check_pypeit_pin.py`
  verifies that the pin is an ancestor of HEAD and that the diff touches only
  allow-listed, MOSFIRE-irrelevant paths (design D35). The local reference
  records its actual `pypeit_git_sha`, the `pypeit_pin` and the `pin_check`
  result, and the S4b gate compares pins and check results, not SHAs. Moving
  the pin is a deliberate edit plus an image tag bump, recorded in
  `nautilus/README.md`; a pin that changes MOSFIRE code makes the local
  check fail until the user updates the laptop checkout.
- Nautilus: namespace `pypeit`; credentials secret name settled in part 1
  (`KECK_ETCS_S3_SECRET`, default `prp-s3-credentials`), mounted for reads
  and writes because the bucket is private; registry
  `gitlab-registry.nrp-nautilus.io/profx/keck-etcs` (public image; the user
  creates the GitLab project and a `write_registry` deploy token once and
  runs `docker login` on the **Linux workstation**, where images are built:
  this Mac has no `docker`). Conventions to imitate:
  `Oceanography/python/PAB/nautilus/build_image.sh`, PAB's `Dockerfile`
  (deps-first layer, `PAB_GIT_SHAS` build arg, behavioural guards),
  `v2_validate_job.yaml` + `v2_validate_gates.py` (gates that exit non-zero),
  `run1k_job.yaml` (log helper, PROVENANCE block, `*_DONE`, `exit 1` on
  failure, literal `|` block, one-line `python -c`), and design 4.8.1.
- Night contents (from `scripts/inspect_mosfire_j2_headers.py`): dome flats
  m220409_0017-0021 (lamp on) and 0022-0026 (lamp off), 10 s CDS; science
  J0841+3814_OFF m220409_0036-0039, 4 x 150 s, MCDS-16, ABBA +/-2" on
  LONGSLIT-46x1, airmass 1.07; standard LDS749B m220409_0218-0219, 2 x 120 s,
  MCDS-16, AB +/-6.5" on LONGSLIT-46x5, airmass 1.58. No seeing, read-noise or
  PWV cards in the headers.
- Template pypeit file:
  `/Users/xavier/Projects/PypeIt/PypeIt-development-suite/pypeit_files/keck_mosfire_j2_long.pypeit`
  (written with PypeIt 1.8; note the hand-typed `standard` rows, the
  `comb_id`/`bkg_id` pairing for nods, `snr_thresh = 80`, and
  `PATH_TO_RAW_DATA`). PypeIt types MOSFIRE standards by `exptime < 20 s`, so
  the 120 s LDS749B frames must be retyped by hand.
- PypeIt (`develop` at the pin, `/Users/xavier/Projects/PypeIt/PypeIt`):
  CLIs `pypeit_setup -s keck_mosfire -r RAW -d REDUX -c all`, `run_pypeit
  FILE.pypeit -r REDUX`, `pypeit_sensfunc SPEC1D --algorithm IR -s FILE.sens
  -o OUT.fits`; `pypeit_cache_github_data keck_mosfire` and
  `pypeit_install_telluric FILE` populate the cache offline; the cache
  directory follows `XDG_CACHE_HOME`. MOSFIRE defaults in
  `pypeit/spectrographs/keck_mosfire.py`: sensfunc `IR`, `polyorder = 13`,
  `telgridfile = TellPCA_3000_26000_R10000.fits`, `tweak_standard` zeroes J2
  outside 11170-12600 A. The dev suite has one `.sens` example:
  `sensfunc_files/keck_mosfire_Y_long.sens`. The `SensFunc` datamodel
  (`pypeit/sensfunc.py`) holds `wave`, `zeropoint`, `throughput`,
  `airmass`, `exptime`, `std_name`, `std_cal`, `std_ra`, `std_dec`,
  `telluric` (model table with `TELL_THETA`: pressure, temperature, water,
  airmass, resolution, shift, stretch), `algorithm`. Zero point to
  throughput: `pypeit.core.flux_calib.zeropoint_to_throughput(wave,
  zeropoint, eff_aperture)` with Keck `eff_aperture = 72.3674` m^2 (decision
  N1). Standard lookup: `pypeit.core.standard.get_standard_spectrum(ra=,
  dec=)`; LDS749B resolves to CALSPEC `lds749b_stisnic_008.fits.gz`
  (`scripts/check_mosfire_standards.py`). These names were read on the
  local checkout, which differs from the pin only in `keck_hires.py`, so
  they hold at the pin too.
- spec1d fields for QA: `S2N` (`med_s2n`), `FWHM`, `FWHMFIT`, `OPT_COUNTS`,
  `OPT_COUNTS_IVAR`, `OPT_COUNTS_SKY`.
- Existing scripts: `scripts/inspect_mosfire_j2_headers.py`,
  `scripts/check_mosfire_standards.py`, `scripts/mosfire_band_footprints.py`
  (dispersion 1.30 A/pix in J2), `scripts/check_pypeit_pin.py`,
  `scripts/nautilus/s3_sync.py`, `nautilus/inspect_pod.yaml` (part 1).
- Rules (CLAUDE.md): the user runs git in both repositories (no
  `checkout`/`switch` by the session); `conda run -n pypeit14`; scripts on
  disk; if a PypeIt value is verified wrong, fix it on a branch in the
  PypeIt checkout (off `develop`), not here; no secret value in the repo or
  a log; image pushes and job launches are confirmed with the user; log each
  prompt.

## Prompts

1. **S4: reference reduction of the 2022-04-09 night (local, PypeIt
   MOSFIRE-equivalent to the pin).** First run `conda run -n pypeit14
   python scripts/check_pypeit_pin.py`; if it fails, stop, list the
   offending files, and tell the user (it means the laptop checkout has
   drifted from the pin in MOSFIRE-relevant code; they update the checkout
   or the reference is redone on the workstation). Then write
   `scripts/mosfire/reduce_standard.py` (v0): given a
   night directory under the data root, run `pypeit_setup`, patch the
   generated pypeit file (retype standards longer than 20 s as `standard`,
   set nod pairs' `comb_id`/`bkg_id` from `dithpos`, apply the parameter
   block of the dev-suite template), run `run_pypeit` into `redux/`, and
   optionally `pypeit_sensfunc` with a given `.sens` file. Design it as the
   in-pod driver from the start: all paths from arguments or
   `KECK_ETCS_DATA`; no interactive steps; distinct exit codes for the
   failure classes of design 4.8.6 (`no calibs`, `setup failed`, `reduce
   failed`, `no trace`, `sens failed`); `--scratch DIR` to work on a scratch
   directory; `--s3-pull` / `--s3-push PREFIX` hooks that call
   `scripts/nautilus/s3_sync.py` and are no-ops when absent; and a
   `run_manifest.json` written at the end with the design 4.8.5 fields
   (`image = local`, `pypeit_git_sha` from the checkout, `pypeit_pin` and
   `pin_check` copied from the check's JSON, `pypeit_version`,
   `keck_etcs_git_sha`, night, sha256 of inputs and products, the pypeit
   file text, timings). Keep the pypeit file it produces under
   `scripts/mosfire/pypeit_files/keck_mosfire_20220409_J2.pypeit`. Run it on
   `mosfire/20220409/`. Verify: `run_manifest.json` records a
   `pypeit_version` ending in the pin's short SHA; spec1d files exist for
   both LDS749B frames (positive and negative traces) and all four J0841
   frames; report `FWHM` (pixels and arcsec) and `S2N` for every object; the
   wavelength-solution RMS is below PypeIt's threshold; the QA PNGs exist;
   `--help` documents the S3 hooks. Risks: PypeIt `develop` may have changed
   `pypeit_setup` options or frame typing since the 1.8 template;
   `snr_thresh = 80` may need lowering for the standard; the run takes tens
   of minutes, so run it in the background and poll. Log your work,
   including run time, the pin, and any parameter changes.

2. **S5: LDS749B sensfunc for J2.** Create
   `keck_etcs/data/pypeit_par/keck_mosfire_J.sens` with the settings of
   design 4.3 (`algorithm = IR`, `polyorder = 6`, `extrap_blu = extrap_red =
   0`, `[[IR]] telgridfile = TellPCA_3000_26000_R10000.fits`, `maxiter = 2`);
   it ships inside the image, so write it before prompt 5 or note that the
   image must be rebuilt. Run `pypeit_sensfunc` on the local LDS749B spec1d,
   output `mosfire/20220409/sens/sens_LDS749B_20220409.fits` plus QA. Write
   `scripts/mosfire/inspect_sensfunc.py` that opens a `SensFunc` file and
   prints the fitted telluric parameters (PWV, airmass), the zero point at
   1.20, 1.25 and 1.30 um, and the implied end-to-end throughput (via
   `zeropoint_to_throughput` with 72.3674 m^2) at those wavelengths and its
   median over 1.117-1.260 um; with two files it prints their zero-point
   ratio statistics over 1.117-1.260 um (used to compare the local and
   in-pod sensfuncs); also plot the fluxed standard against the CALSPEC
   model to judge the red trim (open item: is 1.260 um the clean red edge?).
   If prompt 6 has run, also sync the in-pod sensfunc
   (`s3_sync.py pull mosfire/20220409 --sens`) and compare. Verify: the zero
   point is finite over 1.117-1.260 um; the median throughput is between
   0.15 and 0.45 (XTcalc's 2012 value is 0.28); telluric residuals near
   1.13 um are below 5 percent; local and in-pod zero points agree to 1
   percent if both exist. Risks: the star is faint (J ~ 15) in a 5" slit
   with two 120 s frames, so the fit may be unstable; fall back to
   `polyorder` 4-5 or `--extr BOX`; if the telluric fit does not converge,
   fix PWV and airmass at plausible values and say so. Log your work, with
   the PWV, airmass, zero points and red-edge judgement.

3. **S6: harvest zero points and throughput (module in the pod, merge
   locally).** Write `keck_etcs/calib/harvest.py` (importable; may import
   PypeIt) that reads one or more `sens_*.fits` files and produces (a) one
   ECSV row per standard with the columns of design 4.4 (`date, mjd,
   koa_id, standard, std_class, std_model, filter, slit_width, slit_length,
   sampmode, numreads, exptime, airmass, pwv_fit, seeing_fwhm_pix, zp_1200,
   zp_1250, zp_1300, thru_median_1117_1260, thru_curve_file,
   pypeit_version, keck_etcs_version, image, image_digest, pypeit_git_sha,
   keck_etcs_git_sha, job_name, s3_prefix, flag`), reading slit width and
   readout mode from the raw header via the sensfunc's spec1d provenance or
   the night manifest and the six provenance columns from the night's
   `run_manifest.json` (or `keck_etcs.provenance` when running inside the
   pod), and (b) the telescope+spectrograph+detector throughput curve on a
   common 1 A vacuum grid with the filter curve divided out (skip the
   division and set `flag = nofilter` if part 3's filter files do not exist
   yet). Add the CLI `scripts/mosfire/harvest_sens.py` with two modes:
   `harvest SENS... --manifest run_manifest.json --out DIR` (what the pod
   runs; writes `<standard>_<date>.ecsv` row and curve into `DIR`) and
   `--merge DIR...` (local; appends or replaces rows in
   `keck_etcs/data/mosfire/throughput/standards.ecsv` keyed on `(standard,
   date, koa_id)` and copies curve files into
   `keck_etcs/data/mosfire/throughput/standards/`), each output with the
   provenance `meta` of design 5.4. Run `harvest` on the local sensfunc
   (`image = local`) and, if prompt 6 has run, `--merge` the synced
   `mosfire/20220409/harvest/` from the pod; the merged table should then
   hold the in-pod row (the local row is kept only if no in-pod row exists).
   Verify: the LDS749B row has every column filled; recomputing throughput
   from the stored zero point with `zeropoint_to_throughput` and 72.3674 m^2
   matches the stored curve to 1e-6 before filter division;
   `pypeit_version` in the row ends with the pin's short SHA; harvesting the
   synced in-pod sens file locally reproduces the in-pod row to 1e-6 in
   every numeric column. Risk: the `SensFunc` datamodel or `TELL_THETA`
   layout may differ on `develop`; read `pypeit/sensfunc.py` and
   `pypeit/core/telluric.py` at the pin first and keep the reader tolerant.
   Log your work.

4. **S13: LSF from OH lines.** Write `scripts/mosfire/measure_lsf.py` that
   reads the `WaveCalib` product of S4 (or the synced in-pod copy: `s3_sync.py
   pull mosfire/20220409 --calibs`; `Calibrations/` is pushed to S3 but is
   not in the backup set, so pull it while the night is there) for the 1"
   slit and reports the LSF FWHM in pixels and in A versus wavelength, and R
   at 1.25 um. Compare with the design's model `FWHM_pix = max(slit / 0.24,
   2.2)` (4.2 pix for 1") and R = 3310 x 0.7 / 1.0 = 2300. Record the
   measured values in a table `keck_etcs/data/mosfire/lsf_measurements.ecsv`
   (slit width, FWHM_pix, R, date, source, provenance) which the instrument
   module of part 3 (S8) will read; because this table is committed, the
   `WaveCalib` files themselves need not be backed up. Verify: FWHM_pix for
   the 1" slit is within 20 percent of 4.2; R within 15 percent of 2300; if
   not, say which of the floor or the slope is off and propose the revised
   constants. Only one slit width is available now; the slope needs the KOA
   nights of part 5. Log your work.

5. **S4a: container image (built on the Linux workstation).** Prerequisites
   from the user: the GitLab project `profx/keck-etcs` (public) with a
   `write_registry` deploy token, `docker login
   gitlab-registry.nrp-nautilus.io` on the workstation, and this repo
   available there (say what you need if it is not). Write
   `nautilus/Dockerfile` following PAB's: base `python:3.12`; layer 1 the
   third-party dependencies from `requirements.txt` plus PypeIt's, before
   any `COPY` of our source; layer 2 `ARG PYPEIT_SHA`, `pip install
   git+https://github.com/pypeit/PypeIt.git@${PYPEIT_SHA}` and `pip install
   /opt/src/keck-etcs`; layer 3 `ENV XDG_CACHE_HOME=/opt/cache`,
   `pypeit_cache_github_data keck_mosfire`, download of the TellPCA grid
   from the public Nautilus URL (Context of part 1) checked against
   `nautilus/telluric_grid.sha256`, `pypeit_install_telluric`; `ARG/ENV/LABEL
   KECK_ETCS_GIT_SHAS` as JSON `{"pypeit": ..., "keck_etcs": ...}`;
   `MPLBACKEND=Agg`, `PYTHONUNBUFFERED=1`; no `ENTRYPOINT`; build guards that
   fail the build: `pypeit.__version__` ends with the pin's short SHA,
   `pypeit.pkg.cache.search_cache('TellPCA')` is non-empty, `run_pypeit
   --help`, `pypeit_sensfunc --help`, `import keck_etcs.calib.harvest`
   (skip that guard with a note if S6 has not run), no `unknown` in
   `KECK_ETCS_GIT_SHAS`. Write `nautilus/build_image.sh [--push]`: stage
   this repo into a clean context (exclude `.git`, caches, `docs/figures`);
   read `nautilus/pypeit_pin.txt` and `git rev-parse --short HEAD` of this
   repo; refuse to build unless the pin is on `origin/develop`'s history
   (check in a temporary shallow clone or via `git ls-remote` plus
   `merge-base` in a scratch clone, never by touching the user's checkout);
   `docker build` with the two build args, tags `:<keck_etcs version>` and
   `:latest`; smoke tests with `docker run --rm` and bounded commands;
   `--push` then `docker manifest inspect`. Write `keck_etcs/provenance.py`
   (`git_shas()` preferring `KECK_ETCS_GIT_SHAS`, falling back to `git
   rev-parse` locally, else `unknown`; `image_info()` from `KECK_ETCS_IMAGE`
   and `KECK_ETCS_IMAGE_DIGEST`). Extend `scripts/check_pypeit_pin.py
   --image TAG` to run the image and require its PypeIt SHA to equal the pin
   exactly (the local checkout's SHA is different by design and is only
   reported).
   Add the tag/digest/pin table to `nautilus/README.md`. Build and tag
   `0.1.0` (the dry-run image; `0.2.0` follows after S6 and S8). Verify: the
   guards pass; `check_pypeit_pin.py --image <tag>` passes; image size
   reported (expect 2-3 GB, no torch); `docker run --rm --entrypoint bash
   <image> -lc 'ls $XDG_CACHE_HOME/pypeit'` shows the cache; after the push,
   `docker manifest inspect` succeeds and the digest is in the README.
   Risks: the NRP registry has hung on manifest writes (retry the push; do
   not work around it with a `PYTHONPATH` staging hack); Python 3.12 vs the
   local 3.14 is revisited only if prompt 6 shows a difference. Log your
   work, with tag, digest and pin.

6. **S4b: job templates and the 2022-04-09 dry run (Nautilus).** Push the
   S4 reference products to `s3://keck-etcs/mosfire/20220409/reference/`
   (`s3_sync.py push`). Write `nautilus/night_job.yaml` (Indexed Job in
   namespace `pypeit`: night manifest CSV as a ConfigMap, the row chosen by
   `JOB_COMPLETION_INDEX`; env `BUCKET=keck-etcs`, `ENDPOINT_URL`,
   `HOME=/root`, `KECK_ETCS_IMAGE`, `KECK_ETCS_IMAGE_DIGEST`,
   `OMP_NUM_THREADS`, `SPEC2D`, `REPLACE`; the credentials secret
   `KECK_ETCS_S3_SECRET` mounted at `/root/.aws/credentials` subPath
   `credentials`, needed for the pull too; `emptyDir` at `/scratch`; `bash
   -lc` literal block with `set -o pipefail`, `log()`, a PROVENANCE block
   printing `KECK_ETCS_GIT_SHAS`, `pypeit.__version__`, image tag and
   digest; skip if `run_manifest.json` exists on S3 unless `REPLACE=1`;
   `reduce_standard.py --scratch /scratch --s3-pull --s3-push` with the
   `.sens` file from the package; `gates.py`; `harvest_sens.py harvest`;
   final push; `NIGHT_DONE`; `exit 1` on any failure after writing the
   status row; resources and `activeDeadlineSeconds` from design 4.8.4 as
   the initial guess; header comment with purpose, sizing to be measured,
   and the three `kubectl` lines). Write `nautilus/validate_job.yaml` (the
   one-night dry run: `backoffLimit: 0`, `SPEC2D=1`, `gates.py --reference
   s3://keck-etcs/mosfire/20220409/reference/`), `nautilus/gates.py`
   (design 4.8.7: spec1d for both LDS749B traces and the four J0841 frames;
   wavelength RMS below threshold; zero point finite over 1.117-1.260 um;
   median throughput 0.15-0.45; with `--reference`: the reference's recorded
   `pypeit_pin` equals the pod's PypeIt SHA and its `pin_check.pass` is true,
   else FAIL before any comparison (the reference's own `pypeit_git_sha` is
   expected to differ and is only reported); then zero-point agreement to 1
   percent over 1.117-1.260 um and `S2N` to 5 percent; exits non-zero with
   named failures), `nautilus/night_failures.py`
   (status table to sweep manifest), `nautilus/status_table.py` (per-night
   status from `run_manifest.json` objects; store-only),
   `nautilus/manifests/nights_dryrun.csv` (one row; columns `night,
   instrument, s3_prefix, standard, slit, spec2d, notes`), and the operator
   section of `nautilus/README.md`. Validate every manifest with
   `yaml.safe_load` and `bash -n`. With the user's go-ahead, create the
   ConfigMap, apply `validate_job.yaml`, follow the log, and afterwards
   `s3_sync.py pull mosfire/20220409` into the data root. Verify: the pod's
   PROVENANCE block shows both SHAs and the digest and the PypeIt SHA equals
   the pin; all gates pass, including the 1 percent zero-point and 5 percent
   `S2N` agreement with the S4 reference; wall-clock, peak memory and
   scratch usage are recorded in the log and written into the
   `night_job.yaml` header as measured sizing; the pushed prefix holds the
   design 4.2 push list; re-applying skips the night and `REPLACE=1` redoes
   it; no credential value appears in any log. If the 1 percent gate fails,
   diagnose whether the cause is the base Python/BLAS (compare per-pixel
   spec1d differences) and put the decision to the user before any batch.
   Log your work, with the timings, the gate results and the image
   tag/digest/pin used.

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-09-30 (Prompt #1 / S4: reference reduction of 2022-04-09 — success, 11 min)

Linux workstation, `pypeit14b`. PypeIt `develop` at the pin: version
`2.0.2.dev1216+gf3a1f1d27`, which ends in the pin's short SHA.

**Pin check.** `check_pypeit_pin.py` passes. HEAD = pin =
`f3a1f1d274b15ee1358f167819d77f1948fce1bd`; no differing files.

**`scripts/mosfire/reduce_standard.py` v0.**
- **Stages:**
  - pin check: the JSON goes to `<night>/pypeit_pin_check.json` and into the
    manifest; stops with exit 15 unless `--skip-pin-check`;
  - optional `--s3-pull` (or `--link-raw-from DIR`);
  - `pypeit_setup -c all` into `redux/setup_files/`;
  - patch;
  - `run_pypeit -o`;
  - QA;
  - optional `--sens`, running `pypeit_sensfunc` per standard spec1d into
    `sens/`;
  - `run_manifest.json`, always written, failures included;
  - optional `--s3-push PREFIX`.
- **Options:** `--scratch DIR` makes DIR the data root. `--setup-only`,
  `--filter`, `--par` and `--save-pypeit`.
- **Exit codes:** 0 success, 10 no calibs, 11 setup failed, 12 reduce
  failed, 13 no trace, 14 sens failed, 15 pin check failed, 16 pull failed,
  17 push failed. They are listed in `--help`, which also documents the S3
  hooks.
- **Error handling:** unexpected exceptions are classified by the stage
  that raised them, and the traceback goes to the manifest.
- **Manifest fields (design 4.8.5):**
  - status and error; `image` (from `KECK_ETCS_IMAGE`, default `local`) and
    `image_digest`;
  - `pypeit_version`, `pypeit_git_sha`, `pypeit_pin` and `pin_check` (copied
    from the check's JSON);
  - `keck_etcs_version`, `keck_etcs_git_sha` and `keck_etcs_git_dirty`;
  - `job_name`, `pod` and `node` (from `JOB_NAME`, `POD_NAME` and
    `NODE_NAME`), `host`, `python`, `started` and `finished`;
  - `night`, `s3_prefix`, the filter, the parameter block and the patch
    notes;
  - the sha256 of the 16 raw frames and of the 17 products (spec1d, spec2d
    and Calibrations), the pypeit file name and text, and the frame table
    (type, target, slit, nod, calib, comb/bkg);
  - `wave_qa`, `objects`, `sensfuncs`, the QA PNG list and
    `gates: null`, pending S4b.

**What `develop` does differently from the 1.8 template (risks confirmed).**
1. **Frame typing is wrong for this night.** PypeIt's MOSFIRE `idname` keys
   on `FLATSPEC`, which is **1 in all 16 headers**, science and standard
   included. `pypeit_setup` therefore types every frame as
   `pixelflat,illumflat,trace`: the lamp-off flats, the 4 science frames and
   the 2 standards. The driver retypes from other cards:
   - `FLAMP1`/`FLAMP2 == on` gives a lamp-on flat;
   - lamps off with `TARGNAME` containing FLAT, or `AXESTAT` not in
     {tracking, slewing}, gives `lampoffflats`;
   - an on-sky frame matched by `pypeit.core.standard.get_archive_standard(ra, dec, check=True)`
     gives `standard`, whatever the exposure time;
   - any other on-sky frame gives `arc,science,tilt`.
   - `AXESTAT` alone does not work: nodded frames read `slewing`, since the
     card is recorded while the telescope moves between nods.
   - Whether this is a PypeIt defect (FLATSPEC semantics) needs frames from
     other nights (KOA). If other nights confirm it, the fix belongs on a
     PypeIt branch off `develop`, per CLAUDE.md. I have not changed PypeIt.
2. **Two setups.** `develop` splits the night into setup A (`slitwid` 1.0:
   flats plus science) and B (5.0: the standard). The driver merges them into
   one file, as the template does. Both long slits have the same spatial
   extent, so the standard (calib 1) uses the 46x1 flats (calib `all`) and
   the OH arcs from the science frames. The setup block keeps A's values.
   `PypeItFile.setup` is a flat dict (`{'Setup A': None, 'dispname': ...}`).
3. **Nod pairing: one spec1d per frame, not combined.** The template
   combines all A frames and all B frames (comb 0/1, 2/3). The driver pairs
   frames in time order within each target and slit, both ways: 0036↔0037,
   0038↔0039, 0218↔0219. The result is 4 J0841 and 2 LDS749B spec1d files,
   one per 150 s or 120 s frame, which is what per-frame S/N validation
   needs. The first attempt (nearest-in-time) used 0037 twice.
4. **Parameters.** The template's block is unchanged: `tweak_slits = False`,
   `fit_min_spec_length = 0.3`, `find_trim_edge = 10,10`,
   `snr_thresh = 80`. `snr_thresh = 80` did not need lowering: the
   standard, at S/N 11-12, is still found.

**Committed pypeit file.** Saved to
`scripts/mosfire/pypeit_files/keck_mosfire_20220409_J2.pypeit`, with the
raw path replaced by `PATH_TO_RAW_DATA`. It vets with
`PypeItFile.from_file(vet=True)`.

**Run.** 22:46:48-22:57:44 UTC. Total 657 s, of which `run_pypeit` took
650 s, so "tens of minutes" was pessimistic on this machine. Exit 0,
`status = success`.

**Results.**
- **Wavelength solution** (one slit, spat_id 1022): RMS **0.092 pix**,
  against PypeIt's MOSFIRE threshold `rms_thresh_frac_fwhm = 0.11` x the arc
  FWHM (3.95 pix), i.e. 0.434 pix. PASS. The arxiv cross-correlation gives
  cc = 0.94 and 0.83. The tilt RMS is 0.071 pix (RMS/FWHM = 0.018).
- **Objects:** one extracted object per spec1d. PypeIt also finds the
  negative traces, which it masks, with `neg_*` QA pages. The two nod
  positions of each target appear as the positive objects of the paired
  frames:

  | frame | target | spat (pix) | FWHM (pix) | FWHM (") | S/N |
  |---|---|---|---|---|---|
  | 0036 (A) | J0841+3814 | 770.9 | 4.97 | 0.89 | 28.9 |
  | 0037 (B) | J0841+3814 | 795.3 | 4.43 | 0.80 | 27.0 |
  | 0038 (A) | J0841+3814 | 771.1 | 5.57 | 1.00 | 25.3 |
  | 0039 (B) | J0841+3814 | 793.1 | 5.61 | 1.01 | 24.9 |
  | 0218 (A) | LDS749B | 978.8 | 6.32 | 1.14 | 11.2 |
  | 0219 (B) | LDS749B | 1052.1 | 6.00 | 1.08 | 12.2 |

  - The platescale is 0.1798"/pix. The nod separations, 24 pix = 4.3" for
    the ±2" pattern and 73 pix = 13.2" for ±6.5", match the headers.
  - The header `TARGNAME` is `LDS749`, so PypeIt names the files
    `...-LDS749_...`. The standard lookup by coordinates finds LDS749B.
- **QA:** 30 PNGs in `redux/QA/PNGs/` (arc 1-D fit, FWHM, tilts, spatial
  illumination, per-object profile and trace for pos and neg), plus HTML
  pages.

**Provenance caveat for this run.** The manifest records `keck_etcs_git_sha
= 586cad3`, `dirty = False`. The user committed `e2f0c75`, which includes
the driver, at 22:53 UTC, during the run.
- So the code that ran was the uncommitted driver, identical to the one in
  `e2f0c75`, and the dirty flag was wrong: it ignored untracked files.
- `timings_s` in this manifest holds stage *start* offsets, not durations
  (`run_pypeit: 5.6`, `qa: 655.8`).
- Both are fixed in the driver since the run: the dirty flag now counts
  untracked files, and `timings_s` holds per-stage durations (verified with
  a `--setup-only` run in scratch). I left this run's manifest as written
  rather than edit a product by hand. The S4b gates do not use either field.
  If an exact manifest is wanted, re-run S4 (11 min) after committing the
  fix.

**Not done here.** No `--sens` (that is S5) and no S3 push of the
reference products (S4b syncs them).

### 2026-09-30 (Prompt #2 / S5: LDS749B J2 sensfunc — median throughput 0.18, red edge 1.250 um)

Linux workstation, `pypeit14b`, PypeIt at the pin. Prompt 6 (in-pod) has not
run, so there is no in-pod sensfunc to compare with yet.

**`keck_etcs/data/pypeit_par/keck_mosfire_J.sens`** (design 4.3):
`algorithm = IR`, `polyorder = 6`, `extrap_blu = extrap_red = 0`,
`[[IR]] telgridfile = TellPCA_3000_26000_R10000.fits`, `maxiter = 2`. It
is written before prompt 5, so the image build will include it. Only
`polyorder` differs from PypeIt's MOSFIRE default (13).

**Scripts.**
- **`scripts/mosfire/build_sensfunc.py DATE --standard NAME`:**
  - Runs `pypeit_sensfunc` on each standard frame's spec1d, giving
    `sens_LDS749B_20220409_{0218,0219}.fits`.
  - Coadds the frames in counts with `pypeit_coadd_1dspec`
    (`flux_value = False`; PypeIt's default coadds FLAM) into
    `spec1d_coadd_LDS749B_20220409.fits`, then runs `pypeit_sensfunc` on the
    coadd, giving the night's product
    **`mosfire/20220409/sens/sens_LDS749B_20220409.fits`**, plus PypeIt's
    QA, fluxed-standard and throughput PDFs.
  - Each call is logged beside its output. The run takes 49 s.
  - `pypeit_sensfunc` with several files *splices* them (for different
    wavelength ranges) and does not combine them, hence the coadd.
  - The coadd copies the first frame's header (a PypeIt "hack"), so
    `EXPTIME` is one frame's 119.29 s. That is the right normalisation for a
    weighted mean of equal-length frames; the script refuses unequal
    exposure times. `AIRMASS` is 0218's 1.578 against a mean of 1.568.
- **`scripts/mosfire/inspect_sensfunc.py SENS [SENS2] [--plot] [--json]`:**
  - Prints the telluric fit, a PWV estimate, the zero point and throughput
    at 1.20, 1.25 and 1.30 um, and the median throughput over
    1.117-1.260 um.
  - Runs the three checks: zero point finite, median throughput within
    0.15-0.45, and the 1.125-1.140 um telluric residual below 5%.
  - Prints a 5 nm red-edge table; with two files, zero-point ratio
    statistics.
  - `--plot` writes `<stem>_vs_calspec.png`: the fluxed standard against
    CALSPEC, with a ratio panel on the same x axis.
- **`scripts/mosfire/compare_standard_frames.py DATE`:** a diagnostic for
  the frame-to-frame difference below.

**Telluric fit: PWV and airmass are not fitted parameters.**
- `TellPCA_*` is a PCA grid (`teltype = pca`, 5 components). The fit
  solves for 5 PCA coefficients, the resolution, a shift and a stretch at the
  *header* airmass.
- Coadd: `SUCCESS`, niter 3, chi2 1130, R 2637, shift +1.36 pix, stretch
  1.0004. Per frame: R 2586 and 1857, both successful. No fallback (fixed
  PWV, lower `polyorder`, BOX extraction) was needed.
- PWV is estimated by matching PypeIt's fitted transmission over
  1.117-1.260 um to our Gemini ATRAN grid, interpolated per N4 to the header
  airmass and smoothed to the fitted R.
  - Result: **1.8 mm for the coadd** (rms 0.019), 1.3 mm for 0218 and
    2.5 mm for 0219.
  - The per-frame spread shows PWV is weakly constrained in J2, where only
    the 1.12-1.16 um water band carries weight. Treat it as "about 1-2.5 mm".
  - Airmass: the header value of 1.578, not fitted.

**Zero points and throughput** (Keck 72.3674 m^2, `zeropoint_to_throughput`):

| file | ZP 1.20 um | ZP 1.25 um | T 1.20 | T 1.25 | median T 1.117-1.260 | tell. resid 1.13 um |
|---|---|---|---|---|---|---|
| coadd (product) | 19.649 | 18.607 | 0.219 | 0.087 | **0.181** | -1.7% |
| 0218 | 19.563 | 18.538 | 0.202 | 0.082 | 0.168 | -1.8% |
| 0219 | 19.705 | 18.664 | 0.231 | 0.092 | 0.189 | -3.6% |

- **1.30 um:** outside the fitted range, because PypeIt trims J2 at
  1.260 um. The J2 filter (1.181/0.129 um, design section 3) does not reach
  1.30. D5's 1.30 um metric applies to J and J3 only.
- **Curve shape (coadd, 10 nm medians):**
  - rises from 0.085 at 1.12 um to a peak of 0.255 at 1.22-1.24 um;
  - then falls to 0.064 at 1.25 um and 0.015 at 1.26 um.
- **The fall is the J2 filter's red edge**, whose half-power point is at
  1.2455 um. It is real, not a fit artefact: the fluxed standard follows
  CALSPEC within ±6% to 1.250 um. The low blue end is the filter's blue
  half-power point (1.1165 um).
- **Consequence:** the 1.117-1.260 um median is dominated by the filter
  shape until S8 divides the filter out (D5).
- **Comparison with XTcalc:** its broad-J end-to-end curve (`J_tp_tot`)
  gives 0.34-0.36 at 1.22-1.24 um, against our 0.255 peak, a ratio of about
  0.73. This is a sanity check only, not a target.

**Checks (coadd and both frames).**
- Zero point finite over 1.117-1.260 um: PASS; fitted range
  11171-12599 A.
- Median throughput within 0.15-0.45: PASS (0.181).
- Telluric residual near 1.13 um below 5%: PASS (-1.7%).
- Local against in-pod agreement to 1%: not applicable yet (prompt 6).
  `inspect_sensfunc.py A B` is ready for it.

**Frame-to-frame difference (open item).**
- **The difference:** the per-frame zero points differ by **12%**. The
  0218/0219 throughput ratio has median 0.880 and std 0.026 over the band,
  and ΔZP = -0.14 mag.
- **It is in the data:** `compare_standard_frames.py` gives extracted-count
  ratios of 0.883 (optimal) and 0.895 (boxcar) over 1.17-1.24 um. The
  exposure times are equal, and ΔX = 0.019 is worth about 0.2% in J.
- **Candidate causes:** transparency, guiding or seeing losses, or the
  illumination correction at the two nod positions (spat 979 against 1052,
  ±6.5"). Two frames cannot separate them.
- **The coadd is consistent:** its ratio is 1.082 against 0218 and 0.950
  against 0219, i.e. between them, as a mean should be.
- **What to expect:** single-standard zero points carry roughly ±6%
  frame-level scatter. S6/S10 should record the per-frame spread; with more
  nights (S15), check whether A and B positions differ systematically.

**Red-edge judgement (the open item of D8).** 1.260 um is **not** the clean
red edge; **1.250 um is**. The coadd's 5 nm median residuals (fluxed/CALSPEC
- 1) are:
- -4.4, -1.5, -3.1, +2.8, +5.9 and +0.9% from 1.220 to 1.250 um;
- then **-8.5%** (1.250-1.255) and **+13.7%** (1.255-1.260), with per-pixel
  spikes of +30% at the trim edge.
- Beyond 1.2455 um the counts fall steeply on the filter edge (T < 0.07),
  and the polynomial zero point rolls off against the trim.
- **Recommendation:** use 1.117-1.250 um for the band metrics (design D5
  and D8, `mosfire_band_footprints.py` CLEAN) and keep PypeIt's 1.260 um trim
  for the fit itself. The blue end is clean from about 1.119 um: the first
  few pixels after 1.117 um drop by about 20%.

**Outputs.** In `$KECK_ETCS_DATA/mosfire/20220409/sens/`: the three
sensfuncs, the coadd spec1d, the `.coadd1d` file, the logs, PypeIt's PDFs,
`sens_LDS749B_20220409_vs_calspec.png` and
`sens_LDS749B_20220409_inspect.json`. `git status` shows the `.sens` file
and the three new scripts.

### 2026-09-30 (Prompt #5 / S4a: image 0.1.0 built and guarded; PypeIt fix on etc-fixes; push pending)

Linux workstation, Docker 29.6.0, `docker login gitlab-registry.nrp-nautilus.io`
already done by the user.

**PypeIt defect found and fixed (user's branch).**
- At the pin `f3a1f1d`, `pypeit_cache_github_data` crashes:
  `pypeit/scripts/cache_github_data.py:143` calls
  `PypeItDataPath.get_file_path(rel_path, force_update=..., quiet=True)`,
  but `get_file_path` (`pypeit/pkg/pypeitdata.py:232`) has no `quiet`
  argument. The crash reproduces locally and in the image build.
- Per CLAUDE.md the fix goes in PypeIt. The user created the branch
  `etc-fixes` off develop; I removed `, quiet=True` there (no git from me);
  the user committed and pushed it as
  **`275a012dfcb708d4f0eaeebd56d2513083244b24`** ("1st fix"). `develop` was
  still at `f3a1f1d`.
- User decision: pin `275a012` now. `nautilus/pypeit_pin.txt` = 275a012...
  `build_image.sh` accepts a pin on `develop` or `etc-fixes`
  (`PIN_BRANCHES`, a recorded exception to D31, noted in design 4.8.2 and
  the README).
- `pypeit/scripts/cache_github_data.py` is on the pin allow-list (user).
  The local pin check passes: HEAD = pin = 275a012, no differing files.
- When the fix merges into develop: re-pin to the merge commit, set
  `PIN_BRANCHES` back to `develop`, bump the tag.
- The editable install still reports `2.0.2.dev1216+gf3a1f1d27`, because
  setuptools_scm stamps the version at install time. That is why the check
  compares SHAs.

**Files.**
- **`nautilus/Dockerfile`** (base `python:3.12`; `MPLBACKEND=Agg`,
  `PYTHONUNBUFFERED=1`, `QT_QPA_PLATFORM=offscreen`; no ENTRYPOINT; workdir
  `/opt/src/keck-etcs`):
  - **(1)** pip installs the dependencies of PypeIt at the pin (generated
    from its `pyproject.toml` by `build_image.sh`), `requirements.txt`
    without `pypeit`, plus boto3 and PyYAML. Only the two requirement files
    are copied before this layer.
  - **(2)** `ARG PYPEIT_SHA`; `pip install git+...PypeIt.git@${PYPEIT_SHA}`,
    with a version guard.
  - **(3)** `ENV XDG_CACHE_HOME=/opt/cache` (astropy 8 puts the cache in
    `$XDG_CACHE_HOME/pypeit`); `pypeit_cache_github_data keck_mosfire`;
    `curl` of the TellPCA grid from the public Nautilus URL;
    `sha256sum -c` against `nautilus/telluric_grid.sha256`;
    `pypeit_install_telluric --local_file`. The cache holds exactly the
    verified bytes.
  - **(4)** `COPY keck-etcs/` and `pip install /opt/src/keck-etcs`. The
    source stays in the image, so job manifests can run `scripts/` and read
    `nautilus/`.
  - Then `ARG/ENV/LABEL KECK_ETCS_GIT_SHAS`, last, and the guards.
  - **Deviation from the prompt's order:** the cache (3) comes before our
    source, because it depends only on PypeIt and the checksum. A keck_etcs
    edit therefore rebuilds only layer 4 (rebuild about 2 min).
    `KECK_ETCS_GIT_SHAS` is declared last for the same reason: PAB's
    Dockerfile notes that an early ARG enters every later cache key.
  - **Caveat:** `pypeit_cache_github_data` fetches PypeIt's GitHub `develop`
    data at build time, not at the pin (`git_branch()` returns `develop`
    when there is no repository).
- **Build guards (all fail the build):**
  - the `KECK_ETCS_GIT_SHAS` keys, no `unknown`, `.pypeit` = `PYPEIT_SHA`,
    and `pypeit.__version__` ending with the pin's short SHA;
  - `search_cache('TellPCA')` non-empty;
  - `run_pypeit`, `pypeit_sensfunc` and `pypeit_setup --help`;
  - keck_etcs package data present;
  - `provenance.git_shas()` without `unknown`;
  - `check_pypeit_pin.py` in image mode;
  - `reduce_standard.py --help` and `s3_sync.py --help`.
  - Skipped: `import keck_etcs.calib.harvest`, because S6 has not run.
    Add it at 0.2.0.
- **`nautilus/build_image.sh [--push]`:**
  - Reads the pin (it must be a full SHA) and `git rev-parse --short HEAD`.
    A dirty tree is recorded as `<sha>-dirty`, and `--push` refuses it.
  - Checks that the pin is an ancestor of `origin/<branch>` for
    `PIN_BRANCHES`, in a throwaway treeless clone (never the user's
    checkout). The same clone gives the pin's `pyproject.toml`, from which
    `pypeit_requirements.txt` (17 dependencies) is written.
  - Stages the repo with rsync, excluding `.git`, `.claude`, caches,
    `docs/figures`, build and dist; the context is 3.7 MB.
  - Refuses credential-like files (names, plus grep for secret-key and
    private-key markers). The first run caught the script itself, so the
    patterns are now split.
  - `docker build` with the two build args; tags `:<keck_etcs.__version__>`
    and `:latest`.
  - Smoke tests with `timeout 300 docker run --rm`: versions and SHAs, the
    in-image pin check, the cache listing, `run_pypeit --help`, the size and
    a check for ML packages.
  - `--push`: push both tags, `docker manifest inspect`, and print the
    digest.
- **`keck_etcs/provenance.py`:** `git_shas()` prefers `KECK_ETCS_GIT_SHAS`,
  then `git rev-parse` of the directories the packages are imported from,
  else `unknown`. `image_info()` reads `KECK_ETCS_IMAGE` and
  `KECK_ETCS_IMAGE_DIGEST`, defaulting to `local`/None.
  `reduce_standard.py` now uses both.
- **`scripts/check_pypeit_pin.py`:**
  - New image mode: with no git work tree and `KECK_ETCS_GIT_SHAS` set, it
    passes if and only if `.pypeit` equals the pin, with `files = []` and
    `mode = image`. Without it, `reduce_standard.py` would have failed its
    first stage in every pod.
  - `--image TAG` (written in part 1) is now tested.
- **Version and packaging:** `keck_etcs.__version__` is now `0.1.0`, and
  `setup.py` reads it from there. `setup.py` gains
  `package_data = {'keck_etcs': ['data/*.yaml', 'data/*/*', 'data/*/*/*']}`;
  `find_packages()` alone would have dropped `keck_etcs/data/`.
- **Documentation:** a pin and tag table in `nautilus/README.md`, and the
  exception note in design 4.8.2.

**Build results (third build; the first two stopped on the self-matching
credential guard and the PypeIt bug).**
- **Version and guards:** in-image PypeIt `2.0.2.dev1217+g275a012df`.
  `GUARDS OK`, and the in-image pin check passes.
- **Cache:** `/opt/cache/pypeit` (153 MB, 375 entries) holds the TellPCA
  grid (sha256 OK) and MOSFIRE's reid_arxiv and line lists.
- **Size:** **2.16 GB** (image ID `e72519c45e13`), with no torch, nvidia,
  tensorflow or jax.
- **Local `check_pypeit_pin.py --image ...:0.1.0`:** PASS. As a negative
  test, `--pin f3a1f1d27` gives check (3) FAIL; checks (1) and (2) still pass
  because `cache_github_data.py` is allow-listed.
- **Not yet clean:** the image was built from a dirty tree, so it records
  `keck_etcs = bd05070-dirty`.

**Pending (needs the user).** Commit the S4a files, then confirm the push;
pushes are confirmed with the user. After that:
`bash nautilus/build_image.sh --push` rebuilds layer 4 with the clean SHA,
pushes `0.1.0` and `latest`, runs `docker manifest inspect`, and the digest
goes into the README table and here.

### 2026-09-30 (Prompt #5 / S4a, completed: 0.1.0 pushed)

The user committed the S4a files (keck-etcs `d4c5871`, clean tree) and
approved the push. `bash nautilus/build_image.sh --push`:
- **Rebuild:** only layer 4 and the guards were rebuilt.
  `KECK_ETCS_GIT_SHAS = {"pypeit": "275a012dfcb708d4f0eaeebd56d2513083244b24",
  "keck_etcs": "d4c5871"}`, with no `-dirty`; the same JSON is in the image
  label `org.opencontainers.image.revision`.
- **Checks:** `GUARDS OK`, and the in-image pin check passes.
- **Push:** `0.1.0` and `latest` were pushed without a registry hang.
  `docker manifest inspect` succeeds.
- **Image:**
  - **tag** `gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.1.0` (and
    `:latest`);
  - **digest**
    `sha256:12793464bc5131985f1289984b7fdb138605861b78abb7e49ecd82400fec7866`;
  - **pin** `275a012dfcb708d4f0eaeebd56d2513083244b24` (`etc-fixes`); PypeIt
    `2.0.2.dev1217+g275a012df`; size 2.16 GB.
- **Public:** `docker manifest inspect` with an empty `DOCKER_CONFIG` (no
  credentials) succeeds, so pods can pull without an `imagePullSecret`. The
  in-cluster pull test belongs to S4b (prompt 6).
- **Recorded:** the digest is in the `nautilus/README.md` table.
- **To do at 0.2.0:**
  - add the `import keck_etcs.calib.harvest` guard once S6 exists;
  - re-pin to develop once the `etc-fixes` fix merges.
