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

### 2026-10-01 (Prompt #6 / S4b: job templates, dry runs on Nautilus; gates pass once, then an extraction instability; decision pending)

**Reference re-reduced at the new pin.** The S4 reference recorded
`pypeit_pin = f3a1f1d`, so gate 5 would have failed against the 0.1.x image
pin `275a012`. S4 and S5 were re-run locally:
- PypeIt HEAD = pin = 275a012, `pin_check.pass`, empty diff.
- keck-etcs `f949f2a`, clean; 445 s.
- Results identical to the first S4: same FWHM, S/N and RMS.
- The local version string still reads `2.0.2.dev1216+gf3a1f1d27`, because
  the editable install's metadata is stale; the gates compare SHAs.

`scripts/nautilus/stage_reference.py` copied (not linked) 16 products into
`mosfire/20220409/reference/` with a `MANIFEST.txt` of sha256s, and pushed
them: 17 objects, 6.8 MB, on `s3://keck-etcs/mosfire/20220409/reference/`.

**New files.**
- **`nautilus/night_job.yaml`:** Indexed Job (`completions` = manifest
  rows, `parallelism 4`, `backoffLimit 4`, 6 h); env per the prompt; secret
  at `/root/.aws/credentials`; emptyDir `/scratch`; manifest ConfigMap at
  `/opt/manifest/nights.csv`; `JOB_NAME`, `POD_NAME`, `NODE_NAME` from the
  downward API. The script block does:
  - PROVENANCE, then the manifest row;
  - the skip check: a night is done only if its manifest on the bucket has
    `status == success` and `gates.pass`;
  - `reduce_standard.py --scratch /scratch --s3-pull`, then
    `build_sensfunc.py` (the coadd product named like the reference), then
    `gates.py --update-manifest`, then the harvest (skipped until S6);
  - spec2d removed unless `SPEC2D=1`;
  - USAGE (wall-clock, `du -sb`, cgroup `memory.peak`), written into
    `run_manifest.json.pod_usage`;
  - the push: products, then `run_manifest.json` **last**;
  - the status row, then `NIGHT_DONE`.
  - On failure it records the status and error in the manifest, pushes the
    products and logs for diagnosis, writes the status row and exits 1.
  - `REPLACE=1` pushes with `--force`.
- **`nautilus/validate_job.yaml`:** the same block, kept byte-identical and
  checked by `validate_manifests.py`; 1 row, `backoffLimit 0`, `SPEC2D=1`,
  `GATES_REFERENCE=s3://keck-etcs/mosfire/20220409/reference`, 2 h.
- **`nautilus/gates.py`** (design 4.8.7; the revised tolerances are below):
  - every night: `spec1d` (all on-sky frames have objects; the standard at
    nod positions A and B), `wave_rms`, `zp_finite`, `thru_median`;
  - with `--reference`: `ref_pin` (fails before any comparison),
    `spec1d_agree`, `zp_agree`, `s2n_agree`.
  - It pulls an `s3://` reference with `s3_sync`, writes `gates.json`, and
    with `--update-manifest` records the result and the sens sha256s in the
    manifest.
- **`nautilus/status_row.py`:** one ECSV row per pod at
  `runs/<job>/status/<index>_<night>.ecsv`, so parallel pods never write the
  same key.
- **`nautilus/night_failures.py`:** concatenates the rows into
  `status.ecsv` and writes a sweep manifest. A night with two data-reason
  failures (`no calibs`, `no trace`) is not retried.
- **`nautilus/status_table.py`:** a store-only table from the
  `<instr>/<date>/run_manifest.json` objects.
- **`nautilus/manifests/nights_dryrun.csv`;** `nautilus/validate_manifests.py`
  (yaml.safe_load, namespace, `bash -n`, secret mount, emptyDir, env,
  identical blocks).
- **`scripts/nautilus/s3_sync.py`:** `push --include` and `push --force`.
- **Diagnostics:** `scripts/nautilus/compare_sensfunc_stacks.py`,
  `scripts/mosfire/sensfunc_perturbation_test.py`,
  `nautilus/compare_spec1d.py [--within]`, `nautilus/compare_spec2d.py`.
- **Documentation:** the operator section of `nautilus/README.md`.

**Local tests.**
- `validate_manifests.py`: MANIFESTS OK. `kubectl apply --dry-run=server`
  passes; it is refused only when a completed Job of the same name exists,
  because the template is immutable, hence the usage's delete first.
- `gates.py` against the local reference: all PASS (ratio exactly 1). A
  fake reference pin `f3a1f1d` gives `ref_pin` FAIL and no comparisons,
  exit 1.
- Status rows to a sweep manifest: one retry, plus one night with two
  data-reason failures that is not retried.

**Images.** Each rebuild only touches layer 4, about 5 min with the push.
Each was committed by the user first, and the pin is always 275a012.

| tag | keck-etcs | digest | why |
|---|---|---|---|
| 0.1.1 | f211d4d | `sha256:44faabcd081e96617ebeed3d05ce3b6d67883dab274c8cc17efa16ed36de09df` | helpers and `s3_sync --include/--force` in the image (no ConfigMap shadowing) |
| 0.1.2 | 534725e | `sha256:51f39684e765569099d7f6e0b55668179f1f43ee05d4070546ff0e59ce1ab19c` | revised `gates.py` |

The in-cluster anonymous pull works, since the pods started. In every pod,
PROVENANCE shows both SHAs and the digest, and PypeIt = pin.

**Dry runs** (`keck-etcs-validate`, namespace `pypeit`, ConfigMap
`keck-etcs-nights-dryrun`):
1. **0.1.1, node `k8s-chase-ci-02`:** 1390 s up to the gates
   (`run_pypeit` 20 min on about 1.0 CPU, 3.4 GiB). All gates pass except
   `zp_agree` at 1 percent: median 0.9902, 5-95% 0.975-0.998, S2N within
   0.01%.
   - **Diagnosis (the prompt's Python/BLAS question): not the stack.**
     `compare_sensfunc_stacks.py` fits the same local coadd twice locally
     and once in the image (Python 3.14.6/numpy 2.5.0/scipy 1.18.0 against
     3.12.14/2.5.3/1.18.1). All three are **bit-identical**.
   - **The telluric fit is chaotic in its input.**
     `sensfunc_perturbation_test.py` perturbs the counts by 1e-5, 1e-4 and
     1e-3: the per-pixel zero point moves by up to 4.8% (5-95% range) and
     the band median by up to 0.9%.
   - **User decision:** a band-level gate. `zp_agree` requires the median
     within 2% and the 5-95% range within ±5%; a new `spec1d_agree`
     requires each frame's median `OPT_COUNTS` within 0.1%. Recorded in
     design 4.8.7.
   - Script bugs found and fixed: the failure path had pushed
     `run_manifest.json`, which would have made the night "done", and no
     products.
2. **0.1.2, node `hcc-gpengine-shor-c5303.unl.edu`:** the skip check
   retried the night (previous gates failed). **All gates PASS:**
   `spec1d_agree` within 7e-5; `zp_agree` median 1.0011, 5-95%
   0.9965-1.0032; S2N within 0.01%; median throughput 0.1815.
   - **Measured:** wall-clock 850 s (`run_pypeit` 12 min); peak memory
     **5.84 GiB** (cgroup); scratch **1.78 GB** (raw 258 MB, redux with
     spec2d about 1.5 GB); push 104 objects, 1.5 GB. Written into the
     `night_job.yaml` header: CPU about 1 core and memory under 6 GiB, so
     the cpu 4 / 16Gi requests over-provision.
3. **Re-apply, `REPLACE=0`:** `SKIP: mosfire/20220409 is done`, a `skipped`
   status row, `NIGHT_DONE` in 4 s. The skip works.
4. **`REPLACE=1`, same node, same image:** re-reduced, pushed 105 objects
   with `--force`; the failure status is now recorded in the manifest
   (fix applied).
   - **`spec1d_agree` FAILED on frame m220409_0037:** OPT 1.161 and BOX
     1.162 against the reference; FWHM 4.962 against 4.433; S2N +1.6%.
     Every other frame agrees to 3e-4, and both standard frames are
     identical in every run.
   - `compare_spec2d.py` (pod against local spec2d of 0037): SCIIMG,
     IVARRAW, TILTS and WAVEIMG agree to numerical noise (median |d|
     1.7e-5). The divergence is in the extraction mask: 2040 pixels with
     bit `EXTRACT` (256) differ, in columns 731-832 around the traces at
     spat 771 and 795; the CR masks differ by 4 pixels (9058 against 9054).
     The local sky / extraction outlier rejection takes one of two paths.
   - `compare_spec1d.py --within` (each frame's BOX counts against the
     median of the 4 J0841 frames): in the **reference** 0037 is
     **0.82**, an 18% outlier; in the REPLACE pod it is **0.95**,
     consistent (the others are 1.14, 1.01, 0.99 in both runs).
   - **So the branch taken by the reference, both local runs and pod runs
     1-2 over-rejects on-trace pixels and biases 0037 about 16% low. The
     "failing" pod is the plausible reduction.**

**State on the bucket.** `mosfire/20220409/` now holds run 4's products,
with status `gate failed`. `reference/` is unchanged. Status rows are under
`runs/keck-etcs-validate/status/`.

**Open, needs the user before any batch.** How to treat the bistable
extraction of 0037: investigate the PypeIt local-sky/extraction rejection
(a candidate PypeIt defect, to be fixed in PypeIt), or scope the gate. The
`s3_sync.py pull mosfire/20220409` into the data root waits for a passing
run on the bucket.

No credential value appears in any pod log, local log or file:
`prp-s3-credentials` is mounted, never printed, and `status_row` and the
manifests carry no keys.

### 2026-10-01 (Prompt #6 / S4b, continued: investigating the 0037 extraction in PypeIt; paused)

User decision: investigate the bistable extraction of m220409_0037 in
PypeIt before any batch. If it is a PypeIt defect, fix it on `etc-fixes`,
re-pin, rebuild, then redo the reference and the dry run.

**Harness: `scripts/mosfire/extraction_stability_test.py DATE [--eps --n --jobs --outdir]`.**
- Reduces only the night's flats, the standard and the 0036/0037 pair,
  reusing copies of the local `Calibrations/`, with the pair's raw frames
  scaled by `1 + eps*N(0,1)`. About 5 min per realization.
- The **standard must stay in the file.** Without it the image processing is
  still bit-identical, but the global sky and the extraction differ
  (0036 S/N 22.96 against 28.87), because PypeIt uses the standard's trace
  as the tracing crutch for the science objects of the same calib group.
- With the standard, the unperturbed realization reproduces the reference
  exactly: 0037 FWHM 4.4326, S/N 27.05.

**Evidence so far.**
- The `EXTRACT` bit (256) comes from the outlier mask of
  `skysub.local_skysub_extract` (`extraction.py:813`; `sigrej = 3.5`,
  profile refit per iteration).
- In the reference branch, **4576 pixels within ±8 px of the 0037 trace are
  flagged `EXTRACT`, against 421 for 0036.**
- Object-finding QA: in 0037 the positive trace (spat about 795) lies
  24 px (4.3") from the negative trace of its background frame 0036
  (spat about 771), and that negative is stronger (collapsed S/N about −250
  against +220). This is a hypothesis to test: the negative trace's
  masking or wings may interact with the local sky and profile rejection.

**Running when paused.** A 6-realization run at eps = 1e-6 (outdir in this
session's scratchpad, so it may not survive the logout). To resume:

    conda run -n pypeit14b python scripts/mosfire/extraction_stability_test.py 20220409 \
        --n 6 --jobs 3 --eps 1e-6 --outdir $KECK_ETCS_DATA/mosfire/20220409/extraction_stability

Then compare the branches' profile fits (FWHMFIT, `pos_*obj_prof` QA, the
`EXTRACT` map around the trace). Next, test the negative-trace hypothesis,
e.g. by reducing 0037 against 0039 instead of 0036, or by changing the
`sigrej`/`no_local_sky` settings in the pair's PypeIt file.

**Bucket state.** `mosfire/20220409/` holds the REPLACE run (status
`gate failed`), so the data-root pull still waits.

**Uncommitted.**
- `nautilus/night_job.yaml` and `validate_job.yaml`: digest 0.1.2, the
  manifest-status fix in the failure path, the measured sizing.
- `nautilus/compare_spec1d.py`, `nautilus/compare_spec2d.py`,
  `scripts/mosfire/extraction_stability_test.py`, and this log.

### 2026-10-01/02 (Prompt #6 / S4b, investigation: the 0037 instability is the trace walk inside local_skysub_extract)

The scripts and results below were made on 10-01, 12:14-12:24, after the
pause, but never logged. This entry records them, plus one check made on
resuming.

**New scripts** (all diagnostic):
- `scripts/mosfire/trace_vs_centroid.py`: PypeIt's `TRACE_SPAT` against the
  object centroid in `SCIIMG - SKYMODEL`, in 51-row blocks.
- `scripts/mosfire/extract_mask_map.py`: `EXTRACT` fraction and normalized
  residual against the offset from the trace and along the spectrum.
- `scripts/mosfire/run_pypeit_fixed_trace.py`: **an experiment, not for
  production.** It runs `run_pypeit` with `spatialprofile.fit_profile`
  wrapped to return its *input* trace, so `local_skysub_extract` keeps the
  object-finding trace through all its iterations.

**1. The bistability reproduces locally**
(`extraction_stability_test.py --eps 1e-6 --n 6`;
`$KECK_ETCS_DATA/mosfire/20220409/extraction_stability/summary_eps1e-6.ecsv`).
- 0036 is stable in all 6 realizations: FWHM 4.974, S/N 28.87, BOX 4602,
  421 `EXTRACT` pixels within ±8 px.
- 0037 takes the reference branch in 5 of 6 (FWHM 4.433, S/N 27.05,
  BOX 3314, 4576 `EXTRACT`). In 1 of 6 (k = 3) it takes the other branch:
  FWHM 4.962, S/N 27.47, BOX 3834 (+16%), 3868 `EXTRACT`. That is the same
  branch as the REPLACE pod.
- So a 1e-6 change to the input flips it, on one machine and one stack.
  Neither the node nor the image is the cause.

**2. With the trace held fixed, 0037 is stable and consistent**
(`run_pypeit_fixed_trace.py` in the harness;
`.../extraction_stability_fixed/summary.ecsv`, realizations 0, 1, 3 at
eps 1e-6).
- 0037 is identical in all three: FWHM 5.029, S/N 28.34, BOX 4549, and
  only **611** `EXTRACT` pixels on the trace (0036: 576).
- 0037's BOX against 0036 is now **0.99**. In the reference it is 0.72, in
  the other branch 0.83.
- 0036 shifts slightly: trace 770.63 against 770.94, S/N 28.95 against
  28.87.

**3. The walked trace is off the object** (`trace_vs_centroid.py`, run on
resuming; trace minus centroid per 51-row block):

| run | frame | median | rms | max | blocks > 0.75 px |
|---|---|---|---|---|---|
| reference | 0036 | -0.70 px | 0.30 | 1.86 | 9/39 |
| reference | **0037** | **+1.26 px** | **1.08** | **2.64** | **24/36** |
| fixed trace | 0037 | +0.04 px | 0.26 | 0.79 | 1/36 |

**Conclusion.**
- **Mechanism:** the trace refinement inside
  `skysub.local_skysub_extract`, i.e. the updated trace returned by
  `spatialprofile.fit_profile` on each iteration, walks 0037's trace
  1.3 px (up to 2.6 px) off the object. A profile centred on the wrong
  position misfits the core and wings, and the 3.5σ rejection flags about
  4000 on-trace pixels (`EXTRACT`). The extracted flux is then 16-28% low,
  and the fitted FWHM narrower.
- **Why it is bistable:** where the walk ends depends on 1e-6-level input
  differences.
- **With the walk disabled,** the extraction is stable, on the object, and
  consistent with the sibling frames.
- **Status:** a PypeIt defect candidate in the trace update of
  `fit_profile` / `local_skysub_extract`. The 24-px-away negative trace of
  the background frame may be what pulls it. 0036 is walked too, but only
  -0.7 px.

**Next (needs the user):** design the fix on PypeIt `etc-fixes`. For
example, bound or reject a trace update that moves the trace away from the
data centroid, or keep the object-finding trace when the update does not
improve chi^2. Then re-pin, rebuild, and re-run the reference and the dry
run. `run_pypeit_fixed_trace.py` is not a fix and must not be used for
production.

### 2026-10-02 (Prompt #6 / S4b: PypeIt fix for the trace walk on etc-fixes — uncommitted, awaiting the user)

User decision: a flag plus a MOSFIRE default of off.

**PypeIt changes** (branch `etc-fixes`, uncommitted, 5 files, +54/-4):
- `pypeit/par/pypeitpar.py`: new `ExtractionPar.refine_trace` (bool,
  default `True`). Drafted by the unlogged 10-01 session and reviewed here.
- `pypeit/core/skysub.py`: `local_skysub_extract(..., refine_trace=True)`.
  When False, the object profile is still refit every iteration, but
  `TRACE_SPAT` is not replaced by `fit_profile`'s trace (also from the
  draft).
- `pypeit/extraction.py`: `MultiSlitExtract` passes the parameter (draft).
  Echelle extraction is unchanged.
- `pypeit/spectrographs/keck_mosfire.py`:
  `par['reduce']['extraction']['refine_trace'] = False`, with a comment on
  the 0037 case.
- `doc/releases/2.1.0dev.rst`: the new parameter (Functionality), the
  MOSFIRE default (Instrument-specific), and the `pypeit_cache_github_data`
  `quiet` fix of 275a012 (Bug Fixes; it had no entry).
- **Not included:** a regenerated `doc/pypeit_par.rst`. Running
  `doc/scripts/build_par_rst.py` locally rewrote 545 lines, mostly
  table-padding and whitespace from the local formatting library, so the
  file was restored from a copy. Regenerate it with PypeIt's usual
  `update_docs` before the PR.

**Root cause, from reading `spatialprofile.fit_profile`.**
- The trace correction starts at the peak of a non-parametric b-spline
  profile (`peak_x`) plus three shift iterations. It is accepted when the
  median |correction| is below `max_trace_corr = 2 px`.
- `local_skysub_extract` calls `fit_profile` on each of its 4 iterations,
  starting from the already-shifted trace, with sticky outlier masks.
- So nothing bounds the cumulative shift. Rejections on one side of the
  core make the profile asymmetric, the peak moves, and more pixels are
  rejected.

**Verification.**
- **Defaults:** MOSFIRE False; the generic default and DEIMOS True.
- **PypeIt tests:** `test_pypeitpar.py`, `test_spectrographs.py` and
  `test_skysub.py`: 61 passed.
- **Harness, flag set in the PypeIt file** (`--no-refine-trace`, new
  option; `.../extraction_stability_norefine/`): 6 of 6 realizations
  identical. 0036: trace 770.63, FWHM 4.981, S/N 28.95, BOX 4593, 576
  `EXTRACT`. 0037: trace 793.30, FWHM 5.03, S/N 28.34, BOX 4549, 611
  `EXTRACT`. This matches the monkeypatch experiment exactly.
- **Harness, MOSFIRE default, no flag**
  (`.../extraction_stability_mosfire_default/`, seeds 0, 1 and 3, where
  seed 3 had flipped): identical to the above.
- **Full night with the flag**
  (`~/Projects/PypeIt/keck-etcs-data-tests/norefine`, `--skip-pin-check`
  because of the uncommitted PypeIt edits; 652 s):
  - J0841 BOX counts relative to the target median: 1.06, 1.05, 0.95,
    0.93. In the reference: 1.14, 0.82, 1.01, 0.99. The first nod pair now
    sits about 10% above the second, consistently.
  - LDS749B: OPT -0.6 to -0.8%, BOX +0.5%, S/N 11.0/12.0 against
    11.2/12.2, FWHM 6.48/6.05 against 6.32/6.00.
  - Coadd median throughput (1.117-1.260 um) 0.1786 against 0.1809
    (-1.3%); ZP ratio median 0.980, 5-95% 0.934-0.992.
  - Wavelength RMS unchanged (0.092 px).

**Next (needs the user).**
1. Commit and push the PypeIt changes on `etc-fixes`; I run no git.
2. Re-pin `nautilus/pypeit_pin.txt` to the new commit, which only changes
   files that matter to MOSFIRE. `cache_github_data.py` stays on the
   allow-list.
3. `pip install -e` refresh is optional; the check compares SHAs.
4. Re-run the local reference (S4 + S5) and re-stage it.
5. Bump the version and rebuild and push the image (0.1.3).
6. Re-run the dry run, then the skip and REPLACE tests, then the pull.

The reference's numbers will change: 0037 by +16-37%, the standard by
about 0.7%, the median throughput by about -1.3%. That is the purpose of
the fix.

### 2026-10-02 (Prompt #6 / S4b: re-pinned to 8017f47, reference re-made and pushed; 0.1.3 prepared)

- **PypeIt:** the user committed and pushed the fix as
  `8017f47997d6417d797be6d0a0358d7acb8918b5` on `etc-fixes` ("fixes
  underway", the 5 files of the previous entry). `develop` is still
  `f3a1f1d`.
- **Pin:** `nautilus/pypeit_pin.txt` = 8017f47. The local pin check passes
  (HEAD = pin, no differing files). The pin references in the
  `build_image.sh` comment, the allow-list comment and design 4.8.2 now
  record the re-pin.
- **Reference re-run** (`reduce_standard.py` + `build_sensfunc.py`, 460 s;
  the committed PypeIt file re-saved):
  - 0036: FWHM 4.98, S/N 29.0. 0037: FWHM 5.03, S/N 28.3. 0038: 5.62,
    25.4. 0039: 5.57, 24.9. LDS749B: 6.48/11.0 and 6.05/12.0.
  - Wavelength RMS 0.092 px.
  - Coadd sensfunc: median throughput **0.1788**; ZP 19.624 mag at 1.20 um
    and 18.599 at 1.25 um; telluric residual near 1.13 um -2.1%; PWV
    about 1.3 mm.
  - Manifest: PypeIt SHA = pin = 8017f47, `pin_check.pass`, keck-etcs
    `534725e` with `dirty = true` (uncommitted diagnostics; the gates do
    not use it).
- **Staged and pushed** with `--force`:
  `s3://keck-etcs/mosfire/20220409/reference/`, 17 objects, 8.0 MB. The
  local gates self-check passes.
- **Prepared:** `keck_etcs` 0.1.3; both job YAMLs point at
  `profx/keck-etcs:0.1.3` with the digest TBD; MANIFESTS OK. Waiting for
  the user's commit before the build and push.

### 2026-10-02 (Prompt #6 / S4b: image 0.1.3, dry run: extraction fixed, ZP gate fails narrowly; the telluric PCA is the cause)

**Registry login.** The first 0.1.3 push was `denied`. `~/.docker/config.json`
had been rewritten on 10-01 at 10:46 with `gitlab+deploy-token-1384`
(another project); the keck-etcs token is `-1383`. On advice, the user ran
a one-time login into a separate config directory, `~/.docker-keck-etcs`
(user `gitlab+deploy-token-1383`). The push then ran as
`DOCKER_CONFIG=~/.docker-keck-etcs bash nautilus/build_image.sh --push`
with the committed script, so the tree was clean.

**Image 0.1.3:** keck-etcs `d9f6d5f`, PypeIt pin `8017f47`
(`2.0.2.dev1218+g8017f4799`), digest
`sha256:2635e79f811b77b486fd9cf6243fcd7697d520af169cca52597b60a751ee4e64`,
2.16 GB, `GUARDS OK`.

Then, uncommitted:
- `build_image.sh` now pushes and inspects with
  `PUSH_DOCKER_CONFIG` (default `~/.docker-keck-etcs`), and before building
  it fails if that config has no login for the registry. The one-time setup
  is in its header.
- `nautilus/README.md`: a "Registry login" note and the 0.1.3 row of the
  tag table.
- Both job YAMLs carry the 0.1.3 digest.

**Dry run (0.1.3, node `k8s-haosu-11.sdsc.optiputer.net`, 990 s).**
- The skip check retried the night: the previous run had status `gate
  failed`.
- **`spec1d_agree` PASS:** every frame within 1.1e-4, 0037 at 0.999987.
  The trace fix works in the pod.
- **`s2n_agree` PASS:** +0.00% on every frame.
- spec1d, wave_rms (0.092), zp_finite, thru_median (0.1821) and ref_pin:
  PASS.
- **`zp_agree` FAIL:** median 1.0159 (within 2%) but 5-95%
  0.998-**1.057**, past the ±5% band.
- The extraction is identical, so this is purely the telluric-fit
  instability. The pod pushed 105 objects with status `gate failed`.

**Diagnosis: the 5-component PCA telluric model, not the optimizer
tolerance.** `sensfunc_perturbation_test.py` on the new reference coadd,
1e-5 input noise, 5 realizations per variant (`.sens` variants in
`~/Projects/PypeIt/keck-etcs-data-tests/sensfunc_stability/`):

| variant | worst 5-95% / median deviation | median throughput range |
|---|---|---|
| default (`tell_npca 5`, `tol 1e-3`, `popsize 30`), earlier test | 1.5-4.8% | 0.179-0.182 |
| `tol = 1e-6` | 7.9% | 0.179-0.182 |
| `popsize = 60`, `tol = 1e-5` | 5.1% (three of 5 runs about 1.4% low) | 0.179-0.183 |
| **`tell_npca = 3`** | **0.64%** (3 of 5 within 1e-4) | 0.1803-0.1810 |

**Fit quality, `tell_npca` 3 against 5 on the same coadd.**
- chi2 1154.9 against 1172.5: lower with fewer components, so the
  5-component fit lands in poorer local minima.
- Telluric residual near 1.13 um: -2.3% against -2.1%.
- The red-edge 5 nm residual pattern is identical, within 0.4%.
- PWV estimate 1.66 against 1.32 mm. Median throughput 0.1803 against
  0.1788.
- ZP ratio (3/5): median 1.010, 5-95% 0.9985-1.047.
- **Conclusion:** over the narrow J2 window the 5-component PCA is
  degenerate, and the differential-evolution fit wanders among
  near-equivalent solutions. 3 components fit at least as well and are
  stable.

**Open (needs the user):** whether to set `tell_npca = 3` in
`keck_etcs/data/pypeit_par/keck_mosfire_J.sens`. That is a sensfunc setting
in the repo's own parameter file (design 4.3), not a PypeIt defect. If yes:
re-make the reference sensfunc (about 1 min) and re-stage it, build 0.1.4
(the `.sens` file ships in the image), and re-run the dry run, the skip test
and REPLACE.

### 2026-10-02 (Prompt #6 / S4b: tell_npca = 3 adopted, reference sensfunc re-made; 0.1.4 prepared)

- **User decision:** `tell_npca = 3`. Set in
  `keck_etcs/data/pypeit_par/keck_mosfire_J.sens`, with the reason in its
  header, and in design 4.3.
- **Reference sensfuncs re-made** (`build_sensfunc.py`; the reduction is
  unchanged). A first attempt ran the environment's Python directly, without
  `conda run`, so `pypeit_sensfunc` was not on PATH and nothing was
  re-fitted; it was redone through `conda run`.
  - Coadd: `sensfunc.par` shows `tell_npca = 3`; chi2 1154.9; PCA
    coefficients (-78.85, 0.479, 1.046); R 2743; median throughput
    **0.1803**; ZP 19.636 at 1.20 um and 18.597 at 1.25 um; telluric
    residual near 1.13 um -2.3%; PWV about 1.7 mm; all checks pass.
  - Per-frame: the 0218/0219 ratio median is 0.886 with std **0.009**
    (0.026 with 5 components). The 12% frame-to-frame difference in the data
    is unchanged.
- **Re-staged and force-pushed** `mosfire/20220409/reference/`: 17
  objects. The bucket's coadd sensfunc sha256 equals the local one
  (3d72a31b...). The gates self-check passes.
- **Prepared:** `keck_etcs` 0.1.4; YAMLs on `:0.1.4` with the digest TBD;
  MANIFESTS OK.
- **To commit (user):** `.sens`, design, `__init__`, the YAMLs,
  `build_image.sh` (per-project Docker config), `nautilus/README.md`, this
  log.

### 2026-10-02 (Prompt #6 / S4b: 0.1.4 pushed, dry run applied; session paused)

- **Image 0.1.4:** keck-etcs `83ba931`, PypeIt pin `8017f47`, `tell_npca 3`,
  digest
  `sha256:1a1d45f06bffb31dbfb965cbfaa927d011d9cb04f273775e3a48808a9f24cced`.
  Pushed through `~/.docker-keck-etcs`; the new `PUSH_DOCKER_CONFIG` path
  works. The digest is in both YAMLs (uncommitted).
- **`keck-etcs-validate` applied with 0.1.4** at about 16:15 UTC; it keeps
  running on Nautilus.
- **To resume:**
  - check `kubectl -n pypeit logs job/keck-etcs-validate`, or `pod.log` and
    `gates.json` under `s3://keck-etcs/mosfire/20220409/`;
  - then the skip test (re-apply), then REPLACE=1
    (`sed 's|REPLACE, value: "0"|REPLACE, value: "1"|' nautilus/validate_job.yaml | kubectl apply -f -`,
    after deleting the Job);
  - then `s3_sync.py pull mosfire/20220409`, the README 0.1.4 row, and the
    final S4b log.

### 2026-10-04 (Prompt #6 / S4b COMPLETE: image 0.1.4 passes every gate, twice; skip and REPLACE verified; night pulled)

**Image used:** `gitlab-registry.nrp-nautilus.io/profx/keck-etcs:0.1.4`,
digest
`sha256:1a1d45f06bffb31dbfb965cbfaa927d011d9cb04f273775e3a48808a9f24cced`,
keck-etcs `83ba931`, PypeIt pin
`8017f47997d6417d797be6d0a0358d7acb8918b5` (`etc-fixes` = develop
`f3a1f1d` + the `pypeit_cache_github_data` fix + `refine_trace`, off for
MOSFIRE), `tell_npca = 3` in the packaged `.sens`. In every pod the
PROVENANCE block shows both SHAs and the digest, and PypeIt = pin.

**Runs** (`keck-etcs-validate`, gates against
`s3://keck-etcs/mosfire/20220409/reference/`, which was re-made at 8017f47
with `tell_npca 3`):

| run | node | wall | result |
|---|---|---|---|
| dry run, 10-02 | gpu-14.nrp.mghpcc.org | 1682 s | **all gates PASS**: spec1d_agree within 3e-5 (0037 1.000022); zp_agree median 0.9996, 5-95% 0.9964-1.0005, max 0.9%; s2n_agree 0.00%; throughput 0.1803 |
| re-apply, 10-04 | — | 2 s | `SKIP: mosfire/20220409 is done`, status `skipped` |
| REPLACE=1, 10-04 | exp-19-11.sdsc.optiputer.net | 800 s | **all gates PASS**: spec1d_agree within 3e-4; zp_agree median 0.9976, 5-95% 0.985-1.001, max 1.9%; throughput 0.1797; pushed 104 objects with `--force` |

**Measured sizing:** wall-clock 800-1682 s, with `run_pypeit` taking
10-22 min depending on the node, on about 1 CPU. Peak memory 6.07 GiB
(cgroup). Scratch 1.78 GB. Push 1.5 GB with spec2d. Written into the
`night_job.yaml` header: the cpu 4 / 16Gi requests over-provision, so
revisit after the pilot.

**Push list on the bucket** (design 4.2): 16 raw frames + manifest; the
pypeit file; 7 Calibrations; 6 spec1d; 6 spec2d (SPEC2D=1); 43 QA; 3 sens;
`run_manifest.json`, `run.log`, `pod.log`, `gates.json`. `harvest/` waits
for S6.

**Pull into the data root.**
- `s3_sync.py pull mosfire/20220409` downloaded 77 objects and skipped 76
  by size. **19 of 21 products were then still the local S4 versions**,
  because every spec1d and spec2d of the night has the same size in both
  reductions, and the pod manifest's `product_sha256` did not match them.
- Fix: `s3_sync.py pull --force`, mirroring `push --force`. A forced pull
  of `redux/*`, `sens/*`, `harvest/*` and the night-level files
  (119 objects, 1.5 GB) gave **21 of 21 products matching the pod
  manifest's sha256**.
- `reference/` is untouched (sens sha256 3d72a31b...), and `raw/` stays
  the dev-suite symlinks.
- README: the dry-run pull now uses `--force --include ...`, with a
  "pulling over local products" note.

**Other checks:**
- A credential scan of 33 files (pod logs, push logs, `run.log`,
  `nautilus/*`, prompt docs) against the 8 local key values found none.
- `validate_manifests.py`: MANIFESTS OK.

**PypeIt checkout note (10-04):** the local checkout is now on the user's
branch `speed_up_qa` (HEAD b8e5f9321). That branch has neither
`refine_trace` nor the `cache_github_data` fix, so the local pin check
would fail, correctly. This does not affect the pods (the image carries
8017f47) or anything run here since. Local reductions need `etc-fixes`.

**Uncommitted:** `scripts/nautilus/s3_sync.py` (`pull --force`),
`nautilus/README.md` (0.1.1-0.1.4 tag rows, registry login, pull note),
`nautilus/night_job.yaml` and `validate_job.yaml` (0.1.4 digest, sizing),
this log.

**What S4b established for the batches:**
1. The pod reproduces the local reduction to 1e-4 in counts and 0.0% in
   S/N.
2. The J2 zero point reproduces to about 1% (5-95%) with `tell_npca 3`.
3. The skip, REPLACE, failure-status and status-row paths all work.
4. The remaining PypeIt dependency is `etc-fixes`, until its two fixes
   merge into develop (then re-pin, as design 4.8.2 describes).

Next in part 2's run order: prompt 3 (S6, harvest). Prompt 4 (S13, LSF)
can run in parallel.

### 2026-10-04 (Prompt #3 / S6: harvest module, CLI and merge; LDS749B row in standards.ecsv)

PypeIt checkout back on `etc-fixes` (`8017f47`); local pin check PASS.

**New.**
- **`keck_etcs/calib/__init__.py` and `keck_etcs/calib/harvest.py`:** file
  reading, no plotting.
  - `read_sensfunc` is tolerant: it uses `SensFunc.wave/zeropoint`
    (PypeIt's extrapolated fit) and the telluric model if present.
  - `throughput_curve`: the zero point on the common 1 A vacuum grid
    (integer A from 9000), `thru_raw = zeropoint_to_throughput(...,
    72.3674 m^2)`, and an optional filter division; without a filter,
    `filter_trans` and `thru` are masked.
  - `estimate_pwv` and `gemini_trans` moved here from `inspect_sensfunc.py`,
    which now calls them (one implementation, same 1.58 mm result).
  - `harvest(sens, run_manifest, standard, filter_curve, raw_dir)` returns
    the row with the design 4.4 columns plus the curve with design 5.4
    `meta` (the row, provenance, pin and pin_check, sens and manifest
    sha256, telluric grid/npca/R/chi2, PWV method). Inputs: the night's
    `run_manifest.json` (frames, objects, filter, provenance, version) and
    `raw/manifest.ecsv` (KOA IDs, SAMPMODE, NUMREADS, MJD), else the raw
    headers.
  - `row_table` and `write_outputs`.
- **`scripts/mosfire/harvest_sens.py`:**
  - `harvest SENS... --manifest --out [--raw]`, or `harvest DATE
    --standard NAME`. The DATE form is what `night_job.yaml` already calls;
    it writes `<night>/harvest/`, which the job pushes.
  - `--merge DIR...` updates `keck_etcs/data/mosfire/throughput/standards.ecsv`
    keyed on `(standard, date, koa_id)`: in-pod replaces local, local never
    replaces in-pod, otherwise the newer harvest wins. It copies the curves
    to `standards/` and registers the table in `index.yaml`
    (`calib_version mosfire-J-2026.10-dev`).
- **`scripts/mosfire/verify_harvest.py`:** the S6 checks, plus
  `--reharvest`.
- **`keck_etcs/tests/test_harvest.py`:** 5 passed.
- **`nautilus/Dockerfile` guards:** `import keck_etcs.calib.harvest` and
  `harvest_sens.py --help` (the guard deferred in S4a; effective from the
  next image).
- **Design 4.4:** the implementation conventions.

**Choices (design 4.4 note):**
- an extra `thru_median_1117_1250` (S5 red edge);
- `zp_1300` masked for J2;
- `pwv_fit` from the Gemini-grid match;
- `seeing_fwhm_pix` = the median PypeIt FWHM of the standard's objects
  (this also covers item 1 of prompt #7 in `keck_mosfire_prompts.md`,
  which is not yet discussed);
- `koa_id` joined with `+`;
- `slit_length` in CSU bars;
- `std_class` WD unless the model is Vega-scaled (A0V).

**Results for LDS749B, 2022-04-09.**
- **In-pod reduction** (the data root after S4b's forced pull; image
  0.1.4, `keck-etcs-validate`):
  - zp 19.634 mag at 1.20 um and 18.597 at 1.25 um; `zp_1300` masked;
  - `thru_median_1117_1260` **0.1798**; `_1117_1250` **0.1872**;
  - `pwv_fit` 1.58 mm; `seeing_fwhm_pix` 6.26; airmass 1.578; exptime
    119.29 s; SAMPMODE 3, NUMREADS 16; slit 5" x 46 bars;
  - KOA `MF.20220409.55932+MF.20220409.56084` (derived);
  - `flag nofilter` (no part-3 filter files yet).
- **Local reference** (`reference/`, `image = local`): zp 19.636 and
  18.597; `thru_median_1117_1260` 0.1805 (+0.4%, within the telluric-fit
  spread).
- **Merge sequence:** local (added), then in-pod (replaced), then local
  again (kept in-pod). `standards.ecsv` holds the in-pod row; the curve in
  `standards/` is the in-pod one.

**Verification (`verify_harvest.py --reharvest <pod sens> <pod run_manifest>`):**
- every column filled except `zp_1300`: PASS;
- `thru_raw` against `zeropoint_to_throughput` from the stored zero point:
  max relative difference 0.0, PASS;
- `pypeit_version` `2.0.2.dev1218+g8017f4799` ends with the pin's short
  SHA: PASS;
- curve `meta['row']` equals the table row: PASS;
- re-harvest of the synced in-pod sens file equals the row to 1e-6: PASS.

**Not yet possible: an in-pod harvest.** The 0.1.x images predate
`harvest_sens.py`, so no pod has written `harvest/`. The table's in-pod row
was harvested locally from the pod's synced products, exactly the inputs a
pod would use. The true in-pod row, and the check that a local re-harvest
reproduces it (`verify_harvest.py --reharvest`), come with the next image
(0.2.0, after S8) and a night run.

**Local version string.** The local row's `pypeit_version` is the stale
editable-install string `2.0.2.dev1216+gf3a1f1d27`; its `pypeit_git_sha` is
correctly 8017f47. A local row would fail check 3. Refreshing the editable
install (`pip install -e . --no-deps` in the PypeIt checkout, the user's
call) fixes it. In-pod rows are unaffected.

### 2026-10-04 (Prompt #4 / S13: LSF from OH lines — 1" slit FWHM 3.61 px, R 2677 at 1.25 um)

**Input.** `WaveCalib_A_1_DET01.fits` of 2022-04-09, the synced in-pod copy
from the 0.1.4 REPLACE run (pulled with `--force` in S4b, sha256
f7d5735d...). Its arc spectrum is the OH sky of the four J0841 science
frames: a LONGSLIT-46x1, i.e. 1", uniformly illuminated slit.

**`scripts/mosfire/measure_lsf.py DATE [--wavecalib] [--slit] [--record] [--plot]`.**
- For each of the 48 lines PypeIt identified (`pixel_fit`, `wave_fit`), it
  fits a Gaussian plus a linear baseline to the arc spectrum within ±8 px.
- It flags blends against PypeIt's resolved vacuum `OH_R24000_lines.dat`:
  a companion within 1.5 expected FWHM with at least 10% of the amplitude,
  or no list line within 2 px. 25 lines are flagged.
- It converts FWHM to A with the local dispersion of the wavelength
  solution, and computes R = lambda / FWHM_A.
- It fits FWHM_pix against lambda linearly over the clean lines, with
  3-sigma clipping.
- Outputs: the per-line table and plot in `<night>/lsf/` (data root), and
  with `--record` the summary row in
  `keck_etcs/data/mosfire/lsf_measurements.ecsv`. That row holds `date,
  filter, slit_width, fwhm_pix, fwhm_pix_scatter, fwhm_A_1250, R_1250,
  dfwhm_dlam, n_lines, pypeit_arc_fwhm_pix, source, source_sha256`, the
  provenance (image, digest, PypeIt and keck-etcs SHAs, job) and the
  method. It is registered in `index.yaml`.
- Exit status 1 when a design check fails.

**Results** (identical on the local reference copy of the WaveCalib):
- 19 clean lines, scatter **0.069 px**, almost no trend: -0.05 px per
  1000 A. The clean lines span 1.13-1.33 um.
- **At 1.25 um: FWHM 3.606 px = 4.67 A** (dispersion 1.295 A/px), **R = 2677**.
- PypeIt's own arc FWHM estimate is 3.95 px; it includes the blended
  lines, which run high.

**Design checks** (D25/5.3.6):
- FWHM_pix: model max(1.0/0.24, 2.2) = 4.17 px; measured/model = **0.866,
  within 20%: PASS**.
- R: model 3310 x 0.7 / 1.0 = 2317; measured/model = **1.155, outside 15%:
  FAIL** (by 0.5%).

**Which constant is off: the slope, not the floor.**
- At 1" the LSF is slit-dominated (FWHM 3.6 px against the 2.2 px floor),
  so the floor is unconstrained here.
- A slit-limited LSF with slope s gives FWHM = w/s. The measurement implies
  s = 1.0"/3.606 px = **0.277"/px**, not 0.24"/px: the design overpredicts
  the 1" width by 15%.

**Proposed revised constants** (not yet applied; the user to decide):
- **(a) Interim, slope only:** FWHM_pix = max(w / 0.277, 2.2). It
  reproduces the 1" measurement exactly and predicts R(0.7") of about
  3820, against the MOSFIRE web page's 3318 (the source of the design's
  3310 x 0.7).
- **(b) Quadrature form:** FWHM_pix^2 = (w/s)^2 + f^2, fitted to this
  measurement plus the web page's 0.7" value (FWHM 2.90 px at 1.25 um),
  gives s of about 0.33"/px and f of about 2.0 px. It matches both, but
  the 0.7" point is a published nominal, not a measurement.
- The two forms differ by about 15% at 0.7". Separating slope and floor
  needs measured LSFs at other slit widths: the 0.7" and other KOA nights of
  part 5 (S15). Until then, S8 should use the measured row of
  `lsf_measurements.ecsv` for 1" and a provisional form for other widths,
  marked as such.

Caveat: the arc is the combination of 4 frames (nods A and B). Any flexure
between them would broaden the lines, so the true single-frame LSF is at
most 3.6 px. That strengthens the conclusion.

**User decision (2026-10-04): interim slope 0.277"/px.**
- Applied in design D25 and 5.3.6, and in the residual-items list
  (section 8): `FWHM_pix = max(w / 0.277, 2.2)`; widths other than 1" are
  provisional until part 5.
- Applied in part 3's prompt doc (`keck_mosfire_prompt_3.md` Context and S7
  text), so S8 reads the measured row first and uses 0.277"/px otherwise.
- `docs/keck_mosfire_implementation.md` S13's verify text (4.2 px, 2300)
  is left as the historical acceptance test.
