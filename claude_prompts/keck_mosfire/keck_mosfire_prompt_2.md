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
- PypeIt pin: `nautilus/pypeit_pin.txt` (a commit on `develop`; part 1
  wrote it and `scripts/check_pypeit_pin.py` verifies the local checkout and
  `pypeit14` are on it). Every reduction in this doc, local or in-pod, must
  run on that commit, or the 1 percent gate of S4b is meaningless. Moving
  the pin is a deliberate edit plus an image tag bump, recorded in
  `nautilus/README.md`.
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
  (`scripts/check_mosfire_standards.py`). These names were read on
  `orig-hires-fixes`; confirm them on `develop` before coding.
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

1. **S4: reference reduction of the 2022-04-09 night (local, on the pin).**
   First run `conda run -n pypeit14 python scripts/check_pypeit_pin.py`; if
   it fails, stop and tell the user what to switch or reinstall (their git,
   their env). Then write `scripts/mosfire/reduce_standard.py` (v0): given a
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
   (`image = local`, `pypeit_git_sha` from the checkout, `pypeit_version`,
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
   --image TAG` to run the image and compare its PypeIt SHA with the pin.
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
   median throughput 0.15-0.45; with `--reference`: the reference's
   `pypeit_git_sha` equals the pod's, else FAIL before any comparison;
   zero-point agreement to 1 percent over 1.117-1.260 um and `S2N` to 5
   percent; exits non-zero with named failures), `nautilus/night_failures.py`
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
