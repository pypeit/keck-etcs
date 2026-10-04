# Keck/MOSFIRE J: implementation plan

*Version 0.4, 2026-10-04. Companion to `docs/keck_mosfire_design.md` (v0.4);
section numbers below refer to that document. Each step is meant to be one
working session and to become one numbered prompt under "### Implementation"
in `claude_prompts/keck_mosfire_prompts.md`.*

*Change note, v0.2 (Prompt #5):* PypeIt reductions and KOA downloads run as
Nautilus Jobs (design D30, section 4.8). Steps S1-S18 keep their numbers and
meanings so that references from the part prompt docs stay valid; the new
work is added as suffixed steps (**S1b** S3 layout and sync, **S4a**
container image, **S4b** job templates and dry run, **S14b** in-cluster KOA
download Job) and **S4, S5, S6, S13, S14, S15** are re-scoped in place.

*Change note, v0.3 (Prompt #6):* the user's answers Q27-Q39 are folded in
(design D31-D39). Three consequences run through the plan: the bucket
`s3://keck-etcs` exists and is **private**, so every access, local or in-pod,
uses the user's credentials, the public-read policy deliverable is dropped,
and products are distributed through git (S1b, S4b, S14b, S15, S18); PypeIt
is pinned to a commit on **`develop`**, so a new step **S0** checks that the
local PypeIt is equivalent to the pin before the 1 percent gate of S4b means
anything (S0, S4, S4a, S17); and the backup set is defined concretely with
`scripts/nautilus/backup_products.py` run after each S15 batch and at each
release (S15, S16). Step numbers are unchanged; S0 is new and precedes S1.
Steps that still run locally are marked *(local)*; steps that run on
Nautilus are marked *(Nautilus)*.

*Change note, v0.3.1 (2026-09-30, follow-up):* the laptop's PypeIt checkout
stays on `orig-hires-fixes` (user decision; no PypeIt development on this
laptop). Read-only check: the pin `f3a1f1d27` is the merge-base with HEAD
`017bece06`, HEAD is one commit ahead, and the only file that differs is
`pypeit/spectrographs/keck_hires.py`. S0 therefore no longer asks the user
to switch branches or reinstall; `scripts/check_pypeit_pin.py` tests
MOSFIRE-equivalence (pin is an ancestor; diff touches only allow-listed
paths), the reference records `pypeit_git_sha`, `pypeit_pin` and
`pin_check`, and `gates.py --reference` compares pins and check results, not
SHAs (S0, S4, S4a, S4b, S17, risks). Credentials and the registry project,
deploy token and `docker login` are done (user, 2026-09-30).

*Change note, v0.4 (2026-10-04, Prompt #8):* the calibration monitor of
design 4.9 (D40-D47; Q40-Q48) is added as the new step **S6b**, which runs
after S6 and S13, both already done. It covers the module
`keck_etcs/calib/monitor.py`, the MOSFIRE monitor config, the S13 fit
refactored into the module, the in-pod harvest writing
`harvest/<night>_monitor.ecsv`, the merge into
`keck_etcs/data/mosfire/monitor/calib_monitor.ecsv`, and a re-harvest of
2022-04-09 locally and in a pod. Steps re-scoped in place: S13 (its fit now
lives in the module), S14 and S14b (a Ne/Ar lamp-frame census and an
optional lamp download), S15 (S15a freezes the monitor lines on the pilot;
S15c merges the monitor rows), S16 (monitor trends and flags), S18 (the
monitor documented for WMKO), and the risks.

Rules that apply to every step: Python via `conda run -n pypeit14` locally;
git is the user's (including `checkout`/`switch` in the PypeIt repo);
calculations are scripts on disk; nothing under `KECK_ETCS_DATA` is
committed; every new data file carries the provenance `meta` of design 5.4
including the reduction provenance of D36; no secret value is ever written
into the repository or printed into a log (secret *names* and the AWS
profile name are fine); outward-facing infrastructure (image push, jobs
larger than the pilot, anything touching the bucket's access) is confirmed
with the user before it is done; each step ends with a Log entry in the
prompt doc.

## Dependency map

```
Phase 0  S0 user prerequisites (PypeIt checkout on develop at the pin; credentials; registry) ─┐
         S1 data root (local) ──┬── S3 sky grid FITS (local) ─────────────────────────────────┤
         S1b bucket access check, s3_sync.py, push 2022-04-09 raw (needs S0 credentials) ─┐   │
         S2 telluric grid (local; records the sha256 the image checks) ───────────────────┤   │
Phase 1  S4 reference reduction 2022-04-09 (local, PypeIt MOSFIRE-equivalent to the pin; needs S0, S1, S2)
         S4a container image (needs S0 pin, S2 sha256; S6/S8 for a complete image)
         S4b job templates + dry run on 2022-04-09 (Nautilus; needs S1b, S4, S4a) ── 1% gate against S4
         S5 LDS749B sensfunc (local reference + in-pod; needs S2, S4/S4b)
         S6 harvest module + local merge (needs S5, S8 filter curves; runs in-pod from image 0.2.0 on)
         S13 LSF from OH lines (local, on synced WaveCalib; needs S4 or S4b)
         S6b calibration monitor: module, MOSFIRE config, in-pod harvest, merge (needs S6, S13; image rebuild)
Phase 2  S7 core modules (local; needs S3) ── S9 compute()/CLI/regression (needs S7, S8, S10 or provisional)
         S8 mosfire instrument module + data files (local; parallel with S7)
Phase 3  S10 throughput v0 (local; needs S6)   S11 J0841 validation (local; needs S4b sync, S9, S10)   S12 XTcalc (needs S9)
Phase 4  S14 KOA metadata search (local; own prompt doc) ── S14b KOA download Job (Nautilus; needs S1b, S4a, S14)
         S15 batch reductions as Indexed Jobs + backup after each batch (Nautilus; needs S4b, S6, S14b)
         S16 trend + release + release backup (local; needs S15)
Phase 5  S17 PypeIt ronoise branch off develop (local; needs S8)   S18 docs/README/CHANGES/WMKO note/nautilus README (needs S9, S16)
```

Parallel groups: {S0, S1, S2, S14}; {S1b, S3, S4}; {S4a, S7, S8}; {S4b, S5};
{S11, S12, S13}; {S6b, S7, S8}; {S14b, S10}; {S17, S18 draft}. The image (S4a) is rebuilt
and re-tagged whenever `keck_etcs.calib` (now including `monitor.py`), the `.sens` file or the PypeIt pin
changes; S15 always runs on a tagged image recorded in the log with its
digest and pin.

## Phase 0: foundations

### S0. Prerequisites and the pin check *(one local check script; the user actions are done)*
- **Goal:** know that the local PypeIt (`pypeit14`, editable install of the
  laptop checkout on `orig-hires-fixes`, which stays there: user decision
  2026-09-30, no PypeIt development on this laptop) is MOSFIRE-equivalent to
  the `develop` commit the image will pin, and record the prerequisites that
  the user has already provided.
- **Already done by the user (2026-09-30):** the Nautilus S3 keys exist
  locally as an AWS profile and read/write `s3://keck-etcs` (confirmed);
  the GitLab project `profx/keck-etcs` exists with a deploy token (username
  `gitlab+deploy-token-1383`; the token itself is kept by the user) and
  `docker login` is done on the Linux workstation. Nothing here asks the user to switch
  branches or reinstall anything.
- **Facts checked read-only (2026-09-30):** `git merge-base HEAD
  origin/develop` = `f3a1f1d27` = the pin; HEAD `017bece06` is one commit
  ahead, none behind; `git diff --stat origin/develop...HEAD` touches only
  `pypeit/spectrographs/keck_hires.py` (+131/-33). The MOSFIRE code path is
  therefore identical to the pin.
- **Outputs:** `nautilus/pypeit_pin.txt` (one line, the full SHA;
  `f3a1f1d274b15ee1358f167819d77f1948fce1bd` = `origin/develop` on
  2026-09-30 unless deliberately moved); `nautilus/pypeit_pin_allowlist.txt`
  (glob patterns of paths irrelevant to MOSFIRE J reductions:
  `pypeit/spectrographs/*.py` except `keck_mosfire.py`, `spectrograph.py`,
  `util.py`, `__init__.py`; `doc/**`; `**/*.rst`; `pypeit/tests/**`;
  `*/tests/**`); `scripts/check_pypeit_pin.py`, which prints
  `pypeit.__version__`, `pypeit.__file__`, the checkout's HEAD SHA and
  branch, the pin, and the list of files from `git diff --name-only <pin>
  HEAD` plus `git status --porcelain` (uncommitted changes), then PASS/FAIL
  on: (1) `git merge-base --is-ancestor <pin> HEAD`; (2) every listed file
  matches the allow-list. On FAIL it names the offending files and exits
  non-zero. It also writes the result as JSON (`pypeit_git_sha`,
  `pypeit_pin`, `pin_check: {pass, files}`) for `reduce_standard.py` to copy
  into `run_manifest.json`. `--image TAG` (S4a) runs the image and requires
  its `KECK_ETCS_GIT_SHAS.pypeit` to equal the pin exactly. A README line on
  the pin and the check.
- **Verify:** `check_pypeit_pin.py` passes today with files =
  `[pypeit/spectrographs/keck_hires.py]`; it fails when run with a fake
  allow-list that omits `keck_hires.py` (negative test); `rclone lsd
  nautilus_s3:keck-etcs` succeeds and an anonymous request (`curl -sI
  https://s3-west.nrp-nautilus.io/keck-etcs/`) returns 403, confirming the
  bucket is private.
- **Depends on:** nothing. **Risk:** `develop` moves daily; the pin file,
  not the branch tip, is the reference, and every later log records it. If
  the pin is later moved to a commit that changes MOSFIRE-relevant code, the
  local check fails by design; the user then either brings the laptop
  checkout up to date (merge or rebase `orig-hires-fixes` onto `develop`,
  their git) and re-runs the check, or the reference reduction (S4) is
  redone on the workstation on the pin. The local version string will keep
  reporting `2.0.2.dev1217+g017bece06`; that is expected and is why the
  check compares SHAs and diffs, not version strings.

### S1. Data root and external caches *(local)*
- **Goal:** create the out-of-repo data root, the local mirror of the S3
  bucket (design 4.2), and put the XTcalc tarball there; give the package one
  place to resolve paths.
- **Inputs:** `KECK_ETCS_DATA` (default `/Users/xavier/Projects/PypeIt/keck-etcs-data`);
  `https://www2.keck.hawaii.edu/inst/mosfire/XTcalc.tar` (46 MB).
- **Outputs:** directory tree `external/xtcalc/XTcalc_dir/`,
  `mosfire/20220409/raw/` (symlink or copy of the 16 dev-suite frames);
  `keck_etcs/paths.py` (`data_root()`, `night_dir(instrument, date, kind)`,
  and `s3_prefix(instrument, date, kind)` returning the matching bucket key
  so local and S3 layouts cannot drift; the bucket name `keck-etcs` as a
  module constant overridable by `KECK_ETCS_BUCKET`); `.gitignore` rules for
  `*.fits` outside `keck_etcs/data/` and `keck_etcs/tests/data/`, `*.sav`,
  `*.tar`; a `README` line documenting the env var and the mirror
  relationship.
- **Verify:** `scripts/inspect_xtcalc_files.py $KECK_ETCS_DATA/external/xtcalc/XTcalc_dir`
  reproduces the numbers in the Prompt #1 log; `python -c "from keck_etcs
  import paths; print(paths.data_root(), paths.s3_prefix('mosfire',
  '20220409', 'sens'))"` prints the root and `mosfire/20220409/sens`.
- **Depends on:** nothing.

### S1b. Bucket access, the sync helper and the first push *(local + kubectl)*
- **Goal:** confirmed read/write access to the private bucket from the
  workstation and from a pod in namespace `pypeit`, the sync script, and
  the 2022-04-09 raw frames on S3.
- **Inputs:** the private bucket `s3://keck-etcs` (exists; D32); the user's
  AWS profile (S0); `kubectl` context `nautilus`; PAB's `s3_push.py` as the
  model.
- **Outputs:** `scripts/nautilus/s3_sync.py` (boto3; `push`, `pull`, `ls`;
  endpoint from `ENDPOINT_URL`, default `https://s3-west.nrp-nautilus.io`;
  credentials from `AWS_PROFILE`/`AWS_*` only, never from the repo;
  idempotent by key and size; `--dry-run`; `--jobs`; `AccessDenied` is a
  hard error with a message naming the profile, no anonymous fallback);
  `nautilus/inspect_pod.yaml` (`python:3.12-slim` pod in namespace `pypeit`
  that mounts the credentials secret named by `KECK_ETCS_S3_SECRET`, default
  `prp-s3-credentials`, and lists `s3://keck-etcs/` with boto3; this *is*
  the credentials verification of design section 8); `nautilus/README.md`
  v0 (namespace, bucket, its private status and what that implies, secret
  *names*, the layout of design 4.2, the `kubectl` idioms of 4.8.1, and the
  recipe for creating `keck-etcs-s3-credentials` from `~/.aws/credentials`
  if `prp-s3-credentials` fails the test); the 16 raw frames plus
  `raw/manifest.ecsv` at `s3://keck-etcs/mosfire/20220409/raw/`. No bucket
  policy file: the bucket stays private (D32).
- **Verify:** `s3_sync.py ls mosfire/20220409/raw` lists 16 objects whose
  sizes equal the local files; a second `push` uploads nothing; the inspect
  pod's log lists the same 16 keys (if it shows `AccessDenied`, the user
  creates the new secret and the pod is re-run with `KECK_ETCS_S3_SECRET`
  changed); `curl -sI https://s3-west.nrp-nautilus.io/keck-etcs/mosfire/20220409/raw/manifest.ecsv`
  returns 403; `git status` shows only the scripts, YAML and README.
- **Depends on:** S0 (credentials), S1 (layout). **Risk:**
  `prp-s3-credentials` in `pypeit` may hold another user's keys (the dev
  suite is shared); the test above settles it without printing any key.

### S2. Fetch the PypeIt telluric grid *(local)*
- **Goal:** have `TellPCA_3000_26000_R10000.fits` in the local PypeIt cache
  and know its checksum for the image build.
- **Inputs:** network access to PypeIt's S3 host, which is Nautilus S3
  (`pypeit/data/s3_url.txt` = `s3-west.nrp-nautilus.io`; the public object
  is `https://s3-west.nrp-nautilus.io/pypeit/telluric/atm_grids/TellPCA_3000_26000_R10000.fits`;
  the `pypeit` bucket is public, unlike ours).
- **Outputs:** the file in the astropy cache (`~/.cache/pypeit` here);
  `scripts/fetch_telluric_grid.py` that calls
  `pypeit.dataPaths.telgrid.get_file_path(name)` (note: `telgrid`, host
  `s3_cloud`, not `tel_model`), reports the cache path, size and sha256, and
  writes the sha256 to `nautilus/telluric_grid.sha256` for the S4a build
  guard.
- **Verify:** `pypeit.pkg.cache.search_cache('TellPCA')` returns one path;
  size about 6 MB; the file opens with astropy; a second run reports it
  cached; the sha256 equals that of the public URL fetched directly.
- **Depends on:** nothing (runs on either PypeIt branch). **Risk:** low; the
  API names were read from the source on 2026-09-30.

### S3. Gemini sky and transmission grid as committed FITS *(local)*
- Unchanged from v0.1: `scripts/mosfire/build_gemini_sky_grid.py`,
  `keck_etcs/data/sky/gemini_mk_sky_grid.fits` (~3 MB), `index.yaml` entry,
  the N5 vacuum/air check. **Verify** and **Depends on** (S1) as before.

## Phase 1: first sensfunc

### S4. Reference reduction of the 2022-04-09 night *(local, PypeIt MOSFIRE-equivalent to the pin; D35)*
- **Goal:** spec1d files for LDS749B and J0841+3814 from a local `pypeit14`
  run on PypeIt code that the S0 check has shown to be **MOSFIRE-equivalent
  to the commit the image will pin**, which becomes the gate for the
  Nautilus dry run (S4b) and the fallback input for S5/S13 while the image
  is being built.
- **Inputs:** S0 done (`scripts/check_pypeit_pin.py` passes; the run refuses
  to start otherwise and says why, and copies the check's JSON into
  `run_manifest.json` as `pypeit_pin` and `pin_check` next to the actual
  `pypeit_git_sha`); `mosfire/20220409/raw/`; the dev-suite
  `keck_mosfire_j2_long.pypeit` (template; `PATH_TO_RAW_DATA` replaced).
- **Outputs:** `mosfire/20220409/redux/` with `Calibrations/`, `Science/spec1d_*`
  and `spec2d_*`, QA; `scripts/mosfire/reduce_standard.py` v0 (given a night
  directory: `pypeit_setup`, patch the pypeit file (retype standards longer
  than 20 s, `comb_id`/`bkg_id` from `dithpos`, template parameter block),
  `run_pypeit`, then `pypeit_sensfunc` if a `.sens` file is given; **designed
  from the start to be the in-pod driver**: all paths from arguments or
  `KECK_ETCS_DATA`, no interactive steps, exit codes for every failure class
  of design 4.8.6, `--scratch DIR`, and `--s3-pull`/`--s3-push PREFIX` hooks
  that call `scripts/nautilus/s3_sync.py` and are no-ops locally; it writes
  `run_manifest.json` with the D36 fields, `image = local`,
  `pypeit_git_sha` from the checkout); the pypeit file actually run, kept at
  `scripts/mosfire/pypeit_files/keck_mosfire_20220409_J2.pypeit`.
- **Verify:** `run_manifest.json` records `pypeit_version` ending in the
  pin's short SHA; objects found in both standard frames (positive and
  negative traces) and in the four science frames; `FWHM` in pixels
  reported; the LDS749B `S2N` (`med_s2n`) logged; the wavelength solution
  RMS below PypeIt's threshold; `reduce_standard.py --help` documents the S3
  hooks.
- **Depends on:** S0, S1, S2. **Risk:** PypeIt 2.0 may have changed
  `pypeit_setup` options or frame typing since the 1.8 template (the local
  checkout and the pin share every MOSFIRE-relevant file, so what is read
  locally holds at the pin); the run takes tens of minutes; `snr_thresh =
  80` may need lowering for the standard.

### S4a. Container image *(built on the Linux workstation; D31)*
- **Goal:** the public image `gitlab-registry.nrp-nautilus.io/profx/keck-etcs:<tag>`
  with PypeIt at the develop pin, `keck_etcs`, and a populated PypeIt cache.
- **Inputs:** `nautilus/pypeit_pin.txt` (S0); `nautilus/telluric_grid.sha256`
  (S2); PAB's `Dockerfile` and `build_image.sh` as models; the user's GitLab
  project and deploy token (S0 item 4) and a `docker login` on the
  workstation.
- **Outputs:** `nautilus/Dockerfile` (base `python:3.12`; layer 1
  third-party deps from `requirements.txt` plus PypeIt's; layer 2 `ARG
  PYPEIT_SHA` then `pip install git+https://github.com/pypeit/PypeIt.git@${PYPEIT_SHA}`
  and `pip install /opt/src/keck-etcs`; layer 3 `ENV XDG_CACHE_HOME=/opt/cache`,
  `pypeit_cache_github_data keck_mosfire`, `curl` of the TellPCA grid from
  the public Nautilus URL with a sha256 check, `pypeit_install_telluric`;
  `ARG/ENV/LABEL KECK_ETCS_GIT_SHAS` as JSON of the PypeIt and keck_etcs
  SHAs; `MPLBACKEND=Agg`, `PYTHONUNBUFFERED=1`; guards as design 4.8.2; no
  `ENTRYPOINT`); `nautilus/build_image.sh [--push]` (stages this repo into a
  clean context excluding `.git`, caches and `docs/figures`; reads the pin
  and the keck_etcs SHA; refuses to build if `git ls-remote` shows the pin is
  not on `origin/develop`'s history, i.e. `git merge-base --is-ancestor`
  against a fetched `origin/develop` in a temporary clone, never in the
  user's checkout; builds; runs the smoke tests `run_pypeit --help`,
  `pypeit_sensfunc --help`, `python -c "import keck_etcs, pypeit;
  print(pypeit.__version__)"`, `python -c "from pypeit.pkg import cache;
  print(cache.search_cache('TellPCA'))"`; pushes `:<tag>` and `:latest`;
  verifies with `docker manifest inspect`); `keck_etcs/provenance.py`
  (`git_shas()` preferring `KECK_ETCS_GIT_SHAS`, `image_info()` from
  `KECK_ETCS_IMAGE`/`KECK_ETCS_IMAGE_DIGEST` env set by the manifest, used by
  harvest and `reduce_standard.py`); `nautilus/README.md` gains the tag,
  digest and pin table.
- **Verify:** the build guards pass; `docker run --rm <image> python -c
  "import pypeit; assert pypeit.__version__.endswith('g' + open('/opt/src/keck-etcs/nautilus/pypeit_pin.txt').read()[:9])"`
  (or the equivalent with the short SHA inlined); `scripts/check_pypeit_pin.py
  --image <tag>` reports the image's PypeIt SHA equal to the pin (the local
  checkout's SHA differs and is reported alongside, with the allow-listed
  diff); the image
  size is reported (expect 2-3 GB; no torch); `docker run --rm --entrypoint
  bash <image> -lc 'ls $XDG_CACHE_HOME/pypeit'` shows the cache; after the
  push, `docker manifest inspect` succeeds and the digest is recorded in
  `nautilus/README.md`.
- **Depends on:** S0, S2; a *complete* image also needs S6 (harvest) and S8
  (filter curves), so S4a is first built as `0.1.0` for the dry run and
  rebuilt as `0.2.0` before S15. **Risk:** the NRP registry has hung on
  manifest writes before (PAB, 2026-08), so `--push` must be retried rather
  than worked around with a `PYTHONPATH` staging hack; Python 3.12 versus
  the local 3.14 is revisited only if S4b shows a difference (Q31); when the
  S17 `ronoise` branch lands on `develop`, the pin moves to that commit with
  a tag bump.

### S4b. Job templates and the 2022-04-09 dry run *(Nautilus; D33, D35)*
- **Goal:** the manifests and helper scripts of design 4.8.4-4.8.7, exercised
  on one night in namespace `pypeit`, and gated against the local reference
  of S4.
- **Inputs:** image `keck-etcs:0.1.0` (S4a); the raw frames on S3 (S1b); the
  S4 reference products (pushed to `s3://keck-etcs/mosfire/20220409/reference/`
  by `s3_sync.py` so the pod can compare); the credentials secret name
  settled in S1b.
- **Outputs:** `nautilus/night_job.yaml` (Indexed Job template in namespace
  `pypeit`: manifest CSV via ConfigMap, `JOB_COMPLETION_INDEX` selects the
  row, env `BUCKET=keck-etcs`, `ENDPOINT_URL`, `HOME=/root`,
  `KECK_ETCS_IMAGE`, `OMP_NUM_THREADS`, `SPEC2D`, `REPLACE`; the credentials
  secret (`KECK_ETCS_S3_SECRET`) mounted at `/root/.aws/credentials` for the
  pull as well as the push; PROVENANCE block printing `KECK_ETCS_GIT_SHAS`,
  `pypeit.__version__`, image tag and digest; `reduce_standard.py --scratch
  /scratch --s3-pull --s3-push`; gates; harvest; push; `*_DONE`; resources
  and `activeDeadlineSeconds` as design 4.8.4; `emptyDir` at `/scratch`);
  `nautilus/validate_job.yaml` (the one-night dry run: `backoffLimit: 0`,
  `SPEC2D=1`, `--reference`); `nautilus/gates.py` (design 4.8.7; exits
  non-zero with named failures; with `--reference`, first requires the
  reference's recorded `pypeit_pin` to equal the pod's PypeIt SHA and its
  `pin_check.pass` to be true, else FAIL, so the 1 percent gate is never run
  across MOSFIRE-different PypeIt code; the reference's own `pypeit_git_sha`
  is only reported); `nautilus/night_failures.py`;
  `nautilus/status_table.py`; `nautilus/manifests/nights_dryrun.csv`;
  `nautilus/README.md` operator section (build, push, ConfigMap, apply,
  follow, inspect, sync back, re-run a failed night). Run the dry run; then
  `s3_sync.py pull mosfire/20220409` into the data root.
- **Verify:** `yaml.safe_load` and `bash -n` on every manifest; the pod log
  shows the PROVENANCE block with both SHAs and the image digest, and the
  PypeIt SHA equals the pin; all gates pass including zero-point agreement
  with the S4 reference to 1 percent over 1.117-1.260 um and `S2N` to 5
  percent; wall-clock, peak memory and scratch usage are logged and written
  into the `night_job.yaml` header as the measured sizing; the pushed prefix
  contains everything in the design 4.2 push list; re-applying the Job skips
  the night (idempotency) and `REPLACE=1` redoes it; no credential value
  appears in any log.
- **Depends on:** S1b, S4, S4a. **Risk:** in-pod numerical differences from
  the local run (BLAS, Python 3.12 vs 3.14) show up here, which is the point;
  if the 1 percent gate fails for that reason, record the offset and decide
  with the user whether to switch the base image to 3.14 before S15.

### S5. LDS749B sensfunc (J2) *(local reference; in-pod from S4b on)*
- **Goal:** a telluric-corrected `IR` sensfunc for J2, produced identically by
  the local reference run and by the dry-run pod.
- **Inputs:** `spec1d_*LDS749B*.fits` from S4 (local) and from S4b (synced);
  the telluric grid (S2 locally; baked into the image).
- **Outputs:** `keck_etcs/data/pypeit_par/keck_mosfire_J.sens` (polyorder 6,
  design 4.3; ships in the image from `0.1.0` on, so write it before the
  image build or rebuild); `mosfire/20220409/sens/sens_LDS749B_20220409.fits`
  and QA (local, and the synced in-pod copy under the same name); a short
  note on the fitted PWV and airmass; `scripts/mosfire/inspect_sensfunc.py`.
- **Verify:** the zero point is finite over 1.117-1.260 um; the implied
  end-to-end throughput has median 0.15-0.45 over that window (XTcalc's 2012
  value is 0.28); telluric residuals near 1.13 um are below 5 percent; the red
  trim at 1.260 um judged from the fluxed spectrum (D8, open item); local and
  in-pod zero points agree to 1 percent (the S4b gate, re-checked here).
- **Depends on:** S2, S4 (and S4b for the in-pod copy). **Risk:** low S/N
  (J ~ 15 star, 2 x 120 s, 5" slit) may make the polynomial fit unstable;
  fall back to polyorder 4-5 or a BOX extraction; if the telluric fit fails to
  converge, fix PWV and airmass at plausible values and note it.

### S6. Harvest zero points and throughput *(module runs in-pod; merge local; D34)*
- **Goal:** the per-standard table and curve archive of design 4.4, with the
  harvest computed where the sens file is made.
- **Inputs:** `sens_*.fits` files (one so far); `run_manifest.json` for the
  provenance columns; filter curves from S8 (skip the division and set
  `flag = nofilter` if they do not exist yet).
- **Outputs:** `keck_etcs/calib/harvest.py` (reads `SensFunc` fields `wave`,
  `zeropoint`, `throughput`, `airmass`, `exptime`, `std_name`, `std_cal`,
  `telluric` model parameters; computes `zp_1200/1250/1300`,
  `thru_median_1117_1260`; divides out the filter curve; fills the D36
  provenance columns from `run_manifest.json` or `keck_etcs.provenance`);
  `scripts/mosfire/harvest_sens.py` with two modes: `harvest SENS... --out
  DIR` (used by the pod) and `--merge DIR...` (local; appends or replaces
  rows in `keck_etcs/data/mosfire/throughput/standards.ecsv` keyed on
  `(standard, date, koa_id)` and copies curve files into
  `keck_etcs/data/mosfire/throughput/standards/`); the LDS749B row and curve
  from the synced in-pod harvest (or from the local reference, `image =
  local`, until S4b has run).
- **Verify:** the LDS749B row has all fields including the six D36 columns;
  recomputing throughput from the zero point with
  `flux_calib.zeropoint_to_throughput` and A = 72.3674 m^2 matches the stored
  curve to 1e-6 before filter division; the row's `pypeit_version` ends with
  the pin's short SHA; harvesting the synced sens file locally reproduces the
  in-pod row to 1e-6 in every numeric column.
- **Depends on:** S5, S8 (filter curves), S4a for the in-pod path. **Risk:**
  the `SensFunc` datamodel or the telluric parameter layout (`TELL_THETA`)
  may differ on `develop` from what was read on 2026-09-29; keep the reader
  tolerant and log the version.

### S6b. Calibration monitor *(module runs in-pod; merge local; design 4.9, D40-D47)*
- **Goal:** a per-night calibration-monitor table (spatial FWHM,
  flat-lamp brightness, calibration-line widths and brightness), computed
  in the pod beside the harvest and merged locally, so that every S15
  night gets it at no extra cost.
- **Inputs:** a night's `redux/` (spec1d, `Calibrations/Flat_*`,
  `WaveCalib_*`, `Tilts_*`, `Slits_*`), its `raw/` frames and
  `run_manifest.json`; the sens files for `line_flux_above`; locally the
  synced 2022-04-09 products (`s3_sync.py pull mosfire/20220409 --calibs`,
  plus raw).
- **Outputs:**
  - `keck_etcs/calib/monitor.py` (PypeIt imported inside functions only).
    Functions `object_fwhm(spec1d_files, cfg)` (4.9.1),
    `flat_rates(flat_file, cfg, raw_on, raw_off)` (4.9.2),
    `line_widths(wavecalib_file, cfg, source)` (4.9.3; the S13 fit moved
    here unchanged), `line_fluxes(raw_frames, calib_group, cfg, traces,
    sens=None)` (4.9.4) and `monitor_night(redux_dir, raw_dir, manifest,
    cfg) -> astropy.table.Table` in the 4.9.5 format.
  - `keck_etcs/calib/monitor_configs.py` with the MOSFIRE J/J2 block of
    4.9.6: FWHM nodes, flat nodes every 250 A, ±50 A boxes, central 50
    percent of rows, `flat_kind = dome`, the lamp cards `FLAMP1`, `FLAMP2`,
    `FPOWER`, `FLATSPEC` and `DOMEPOSN`, line lists, and a provisional OH
    list until S15a. It moves to `instruments/mosfire.py` once S8 exists.
  - `scripts/mosfire/measure_lsf.py` reduced to a wrapper around
    `monitor.line_widths`, keeping `--record`.
  - `scripts/mosfire/harvest_sens.py` gains `monitor REDUX --raw RAW
    --manifest run_manifest.json --out DIR` (what the pod runs after
    `harvest`), and `--merge` also folds `*_monitor.ecsv` into
    `keck_etcs/data/mosfire/monitor/calib_monitor.ecsv` (keyed per 4.9.5),
    registered in `index.yaml`.
  - `reduce_standard.py`, `night_job.yaml` and `gates.py`: run the monitor
    step after the harvest. A monitor exception writes `flag =
    monitor_failed` into the row file and does not fail the night (D47).
  - `scripts/mosfire/select_monitor_lines.py`, which ranks OH (and, when
    present, Ne/Ar) candidates by the five rules of 4.9.4. Its first run is
    on 2022-04-09 to give the provisional list; the freeze happens in
    S15a.
  - Image rebuild with the module, then a pod re-run of 2022-04-09 with
    `REPLACE=1`, on a tag confirmed with the user.
- **Verify:**
  - `line_widths` on the 2022-04-09 1" `WaveCalib` reproduces the S13 row in
    `lsf_measurements.ecsv` exactly: 3.61 px, 19 lines, R 2677.
  - `pixelflat_raw` units: the median of (lamp-on mean minus lamp-off mean)
    x 2.15 from the raw frames over the same pixels agrees with
    `pixelflat_raw` within 1 percent. If not, the conversion is fixed in
    the module and the finding logged (design 8).
  - The flat stack's peak raw ADU is reported against 26k ADU.
  - The scalar FWHM rows for LDS749B match `seeing_fwhm_pix` in
    `standards.ecsv`.
  - `FWHMFIT` medians exist at the three J2 nodes for every object.
  - `slitloss_gt1pct` is false for LDS749B on the 5" slit and evaluated for
    the J0841 frames on the 1" slit.
  - OH fluxes are finite for all six on-sky frames, and the 1" frames' OH
    flux per arcsec^2 is within 20 percent of the 5" frames' after
    correcting for airmass. A larger difference means the slit-width
    normalisation is wrong.
  - `line_flux_above` for J0841 against the Gemini model at the frame's
    airmass and fitted PWV gives a first `sky_scale`, which is logged.
  - The in-pod monitor file equals the local one to 1e-6 in every numeric
    column.
  - `git status` shows only code, the merged ECSV, `index.yaml` and the
    config.
- **Depends on:** S6, S13, S4a/S4b (image and job templates). S8 is optional:
  until it exists, use the local config and the provisional slit-loss
  integral (design 4.9.1).
- **Risks:**
  - `pixelflat_waveimg` may be empty for MOSFIRE; build the wave image from
    `WaveCalib` and `Tilts`.
  - On a night where a wide-slit standard is the only on-sky frame of its
    setup, which `WaveCalib` serves that setup has to be checked (design 8).
  - Raw-frame processing must use PypeIt's own steps, so that the gain and
    the bad-pixel mask match the reduction.
  - On nod-differenced reductions the spec1d sky is residual, so the OH
    fluxes must come from the single processed frames, as specified.

### S13. LSF from OH lines *(local, on synced WaveCalib)*
- **Goal:** replace the XTcalc LSF constants (2.2 pix floor, 0.24"/pix slope).
- **Inputs:** `Calibrations/WaveCalib*.fits` of the 1" slit from S4 (local)
  or synced from S4b/S15 with `s3_sync.py pull --calibs` (the push list
  includes `Calibrations/`; the backup set does not, D39, so pull it while
  the night is on S3); more slit widths from KOA nights after S15.
- **Outputs:** `scripts/mosfire/measure_lsf.py`;
  `keck_etcs/data/mosfire/lsf_measurements.ecsv` with provenance (committed,
  which is why `WaveCalib*` need not be backed up); values written into
  `instruments/mosfire.py` with source comments; a figure of FWHM_pix versus
  slit width.
- **Verify:** for the 1" slit, FWHM_pix within 20 percent of 1.0/0.24 = 4.2
  pix; R at 1.25 um within 15 percent of 3310 x 0.7 / 1.0 = 2300.
- **Depends on:** S4 or S4b; more slit widths need S15.
- **v0.4:** done on 2026-10-04. In S6b its fit moves into
  `keck_etcs.calib.monitor.line_widths`, and from then on it runs in-pod
  for every night and slit (D44). `measure_lsf.py --record` stays the way
  `lsf_measurements.ecsv` is written. More slit widths come from the S15c
  merge of the monitor rows, not from separate S13 runs.

## Phase 2: ETC core *(all local; unchanged from v0.1)*

### S7. Core modules and schemas
- As v0.1: `keck_etcs/core/{source,atmosphere,sky,slitloss,lsf,detector,snr}.py`,
  the two JSON schemas, analytic unit tests. **Verify:** `pytest keck_etcs/tests
  -k core` passes; Moffat plane integral 1 to 1e-4; exptime solver round-trip
  1e-6; schemas validate the examples. **Depends on:** S3 (loosely). The
  core keeps its no-I/O rule; nothing in this step touches S3 or Nautilus.

### S8. MOSFIRE instrument module and data files
- As v0.1: `instruments/base.py`, `mosfire.py`, filter ECSVs from the Keck
  page, `detector.ecsv`, `index.yaml` entries, Vega-AB offsets. **Verify:**
  `RN(16) = 5.8`, `RN(1) = 21`; J Vega offset 0.85-0.97; J2 half-power
  bandpass 1.181 +/- 0.065 um to 0.01 um; provenance `meta` on every file.
  **Depends on:** nothing. **Note (v0.2):** the filter curves are read by the
  in-pod harvest, so S8 must be merged before the `0.2.0` image build (S4a)
  that precedes S15; until then in-pod rows carry `flag = nofilter`.

### S9. `compute()`, CLI and regression fixtures
- As v0.1: `keck_etcs/etc.py`, `bin/keck_etc`, fixtures, `test_regression.py`,
  `scripts/regen_regression_fixtures.py`; provisional XTcalc throughput if
  S10 has not run. **Verify** as v0.1. **Depends on:** S7, S8; S10 preferred.
  `meta.pypeit_version` continues to come from `index.yaml`, not from
  importing PypeIt; the image tags behind a calibration are in `CHANGES.md`,
  not in `compute` output.

## Phase 3: validation *(all local)*

### S10. Throughput product v0
- As v0.1: `keck_etcs/calib/combine.py`, `mosfire_thru_2017-2025.ecsv` with
  `n_std = 1`, `index.yaml` entry `calib_version = mosfire-J-2026.10-dev`;
  the per-era `meta` lists the image tags of the contributing rows (D36).
  **Verify** as v0.1 plus: `meta.images` equals the set of `image` values in
  the contributing rows. **Depends on:** S6.

### S11. Validation against J0841+3814
- As v0.1, with the inputs now the *synced* products: `s3_sync.py pull
  mosfire/20220409 --spec2d` (the dry run pushed spec2d because `SPEC2D=1`;
  spec2d is not in the backup set, so pull it while the night is on S3),
  then `pypeit_flux_calib` and `pypeit_coadd_1dspec` run locally in
  `pypeit14` (MOSFIRE-equivalent to the pin per the S0 check). **Verify** as
  v0.1 (median
  ETC/measured ratio within 20 percent over 1.117-1.260 um; 10 percent
  between OH lines; N5 and D14 checks). **Depends on:** S4b (or S4 as
  fallback), S9, S10. **Risk:** as v0.1; also, if local and in-pod spec1d
  differ (S4b gate), validate against the in-pod products, since those feed
  the calibration.

### S12. XTcalc sanity comparison
- Unchanged from v0.1. **Depends on:** S9.

## Phase 4: time series

### S14. KOA standards search *(local; own prompt doc)*
- **Goal:** the candidate list of design 4.1 and the `SAMPMODE` census. The
  metadata queries stay local; the downloads move to S14b.
- **Inputs/Outputs:** as v0.1 (`claude_prompts/koa_search_prompts.md`,
  `scripts/koa/search_mosfire_standards.py`,
  `keck_etcs/data/mosfire/koa_standards_candidates.ecsv`, the census), plus
  `nautilus/manifests/nights_<batch>.csv` generated from the candidate table
  by `scripts/koa/make_night_manifest.py` (columns of design 4.8.4; the
  batch order of the koa doc: wide-slit standards, then Hennawi/Yang/Wang
  nights).
- **v0.4 (D44):** the census also counts Ne/Ar lamp frames per candidate
  night: frames with `PWSTATA7`/`PWSTATA8` = 1 (Neon/Argon on, per
  `PWLOCA7`/`PWLOCA8`), matched to the standard's `MASKNAME` and filter, or
  any `long2pos_specphot` arcs. It adds the columns `n_lamp_arcs` and
  `lamp_arcs_match`, and reports the fraction of candidate nights that have
  matching lamp arcs. That fraction decides whether S14b downloads them.
- **Verify:** as v0.1; the dry-run night appears in a one-row manifest whose
  columns match `night_job.yaml`'s expectations.
- **Depends on:** S1 for the local layout; otherwise independent. **Risk:**
  KOA TAP/`pykoa` quirks; proprietary periods; small wide-slit sample (Q3).

### S14b. In-cluster KOA download Job *(Nautilus; D37)*
- **Goal:** raw frames for a batch of nights on S3, downloaded by a pod, with
  manifests; or, if the reachability check fails, downloaded locally and
  pushed.
- **Inputs:** a night manifest (S14); image (S4a; `pykoa` added to the image
  requirements); the private bucket and the credentials secret (S1b).
- **Outputs:** first, a reachability check: a one-off Job on the image that
  runs `pykoa` against one public 2022-04-09 KOA ID and reports success or
  the error (this decides in-cluster versus fallback and is logged);
  `scripts/koa/download_mosfire_night.py` with `--to-s3 PREFIX` (downloads
  the standard, the science frames of interest and the night's dome flats to
  scratch, writes `raw/manifest.ecsv` with koaid, file, frame type, target,
  slit, `SAMPMODE`, `NUMREADS`, exptime, airmass and sha256, pushes with the
  mounted credentials, skips frames already on S3 with the same size; the
  same script with `--to-s3` and the local AWS profile is the fallback);
  `nautilus/koa_download_job.yaml` (Indexed over the manifest, `parallelism:
  2` out of politeness to KOA, small resources, `activeDeadlineSeconds`, the
  credentials secret mounted); a per-night `download_status.ecsv` under
  `runs/<job_name>/`.
- **v0.4 (D44):** if the S14 census shows matching lamp arcs on a useful
  fraction of nights (the user decides after seeing the number), add
  `--lamp-arcs` to the download script so it fetches them with frame type
  `lamp_arc` in `raw/manifest.ecsv`. The reduction still ignores them
  outside `long2pos_specphot`; only the monitor reads them.
- **Verify:** the reachability result is logged before any batch; every
  downloaded night has flats and a standard in its manifest; `s3_sync.py
  ls` sizes match the manifest; total bytes reported; re-applying downloads
  nothing; a night with no flats is recorded `no calibs` and not reduced
  later. Public data only (no KOA login in pods).
- **Depends on:** S1b, S4a, S14. **Risk:** KOA reachability or anonymous
  download from the cluster (the check settles it); KOA rate limits (keep
  `parallelism` at 2).

### S15. Batch reductions, harvest and per-batch backup *(Nautilus; D33, D34, D39)*
- **Goal:** sensfuncs and harvest rows for every candidate night, as Indexed
  Jobs on a tagged image, with a status table, targeted sweeps, and the
  high-level products backed up after each batch.
- **Inputs:** S14b downloads; `night_job.yaml`, `gates.py`,
  `night_failures.py`, `status_table.py` (S4b); image `keck-etcs:0.2.0` or
  later (S4a rebuilt with S6 and S8 merged, and with S15a's A0V support;
  same PypeIt pin unless deliberately moved); `harvest_sens.py --merge`
  (S6).
- **Sub-steps:**
  - **S15a** *(local code, then a Nautilus pilot):* A0V support in
    `keck_etcs/calib/standards.py` (Vega + 2MASS J, N3) wired into
    `reduce_standard.py` and the image; `long2pos` handling; the pilot batch
    of 3-5 wide-slit nights as one Indexed Job. **v0.4:** after the pilot,
    `select_monitor_lines.py` is run on 2022-04-09 plus the pilot nights,
    and the frozen OH (and Ne/Ar, if any) lists are written into the
    monitor config with the script output and its sha256 as provenance
    (D45). The image is rebuilt with the frozen lists, and the pilot nights
    are re-harvested (monitor step only) before S15b, so that every
    production row uses the frozen lists.
  - **S15b** *(Nautilus, several sessions):* the remaining manifests, one Job
    per batch (by year or by program), `parallelism` raised only as far as
    the pilot's measured memory allows; after each batch, `night_failures.py`
    writes the sweep manifest, the sweep Job is applied once, and remaining
    failures are recorded with their data reason; then
    `scripts/nautilus/backup_products.py` (an `rclone copy
    nautilus_s3:keck-etcs/ AIOcean:keck-etcs/` with `--include` filters for
    the D39 set, `--dry-run` first, idempotent) is run and its object count
    and bytes logged.
  - **S15c** *(local):* `s3_sync.py pull` of `harvest/`, `sens/` and
    `Calibrations/WaveCalib*` for every `success` night; `harvest_sens.py
    --merge`, which also merges `harvest/*_monitor.ecsv` into
    `calib_monitor.ecsv` (S6b); `status_table.py` output copied into the
    prompt-doc log.
- **Outputs:** `s3://keck-etcs/mosfire/<YYYYMMDD>/{redux,sens,harvest}` per
  night with `run_manifest.json`; `runs/<job_name>/status.ecsv`; rows
  appended to `standards.ecsv` and curve files; `scripts/nautilus/backup_products.py`
  and the `AIOcean:keck-etcs/mosfire/` mirror of the D39 set; the per-night
  status table (`success`, `no calibs`, `setup failed`, `reduce failed`,
  `no trace`, `sens failed`, `gate failed`, `push failed`) in the prompt-doc
  log, with wall-clock per night and the image tag, digest and PypeIt pin per
  batch.
- **Verify:** every night in every manifest has exactly one status; every
  `success` night has `sens_*.fits`, a harvest row and a `run_manifest.json`
  whose `image_digest` and `pypeit_git_sha` match the batch's recorded
  values; the count of `success` nights equals the number of new rows in
  `standards.ecsv`; every `success` night has a monitor file, and the
  number of nights with `flag = monitor_failed` is reported; narrow-slit standards land in the slit-loss sample with
  their `FWHM` and `flag = narrow`; no pod ran past `activeDeadlineSeconds`;
  a failed night re-applied via the sweep manifest either succeeds or carries
  a data reason; after each batch `rclone check --one-way` with the same
  filters reports the backup complete and `rclone size AIOcean:keck-etcs/`
  is logged; `git status` shows only the ECSV files, manifests and the
  backup script.
- **Depends on:** S4b, S6, S14b. **Risk:** nights without dome flats; masks
  with the standard in a `long2pos` configuration; the sizing is unmeasured
  until the dry run and pilot (take rates from the pilot, not the first pod);
  preemption (idempotent pods resume on re-apply); a wedged pod holds its
  resources until the deadline (hence `activeDeadlineSeconds`); registry
  push hangs when re-tagging the image between batches; Google Drive
  rate-limits many small files (the D39 set is a few files per night, so
  this is minor, but run the backup after the batch, not per pod).

### S16. Trend analysis and first calibration release *(local)*
- As v0.1: `keck_etcs/calib/trend.py`, `scripts/mosfire/plot_throughput_trend.py`,
  per-era `mosfire_thru_<era>.ecsv`, `index.yaml` bumped to
  `mosfire-J-YYYY.MM`, `CHANGES.md` section (now also listing the image tags,
  digests and PypeIt pins of the reductions used, design 4.8.5), fixtures
  regenerated deliberately; then the release backup:
  `backup_products.py --release <calib_version>` copies the D39 set of every
  contributing night into `AIOcean:keck-etcs/releases/<calib_version>/` so
  the release's inputs are frozen (D39). **Verify** as v0.1 plus: every row
  that enters an era median has a non-empty `image_digest` and
  `pypeit_git_sha`, `CHANGES.md` lists each distinct pair, and `rclone check
  --one-way` reports the release backup complete. **v0.4 (D47):**
  `trend.py` also computes per-era medians, MADs and 3-MAD flags for every
  monitor metric (design 4.6). `plot_monitor_trends.py` plots FWHM, the
  dome-flat rate at each node, the line widths against slit width (which
  refits the D25 slope and floor), and the OH-flux / Gemini ratio
  (`sky_scale`) against date. The dome-flat rate at 1.20/1.25 um is
  correlated with `zp_1250`. Any change to the default `sky_scale` or to
  the LSF constants is proposed to the user, not applied silently. **Depends on:** S15.

## Phase 5: wrap-up

### S17. PypeIt `ronoise` branch *(local; off `develop`)*
- As v0.1 (the `get_detector_par` change in `keck_mosfire.py`; unit test;
  commit message for the user), with the branch created by the user **from
  `develop` at or after the pin**, not from `orig-hires-fixes`, and **not on
  this laptop**: per the user (2026-09-30) PypeIt development happens on the
  workstation or wherever PypeIt is developed, so the session prepares the
  change as reviewable files in this repo (`nautilus/patches/pypeit_mosfire_ronoise.patch`
  in `git diff` format against the pin, plus the test file) and the user
  applies them on the branch there. **Note:** once the branch exists, the
  image (S4a) may pin its commit instead of the `develop` pin; that is an
  edit of `nautilus/pypeit_pin.txt` plus a tag bump recorded in
  `nautilus/README.md` and `CHANGES.md`, and any night reduced with it
  carries the new `pypeit_git_sha`. Because `build_image.sh` requires the
  pin to be on `develop`'s history, pinning a feature-branch commit needs an
  explicit `--allow-branch` flag and a log line saying so. A pin that
  changes `keck_mosfire.py` makes the local S0 check fail by design; the
  user then updates the laptop checkout or the reference is redone on the
  workstation before any further gate (D35). **Depends on:** S8.

### S18. Documentation, README, CHANGES, WMKO API note *(local)*
- As v0.1, plus: `nautilus/README.md` finished as the operator guide (image
  build and push, the pin and how to move it, bucket layout and its private
  status, secret names and the credentials test, the `kubectl` idioms, how
  to reduce a new batch, how to sweep failures, how to sync products back,
  how to run the backup, and how to cut a calibration release), and a README
  section "Refreshing calibrations" that points at it. The WMKO note states
  that `keck_etcs.core`/`etc` need neither PypeIt, Nautilus nor S3 access,
  and that all calibration products are in the package (git), the S3 bucket
  being private working storage. An optional, later item is noted (not a
  deliverable): widening bucket access for collaborators. **v0.4:** the
  README and the WMKO note describe `calib_monitor.ecsv` (columns and
  metrics, design 4.9.5), say that `compute()` does not read it, and
  explain how a new instrument adds a monitor config (4.9.6). **Verify:** README
  examples run as written; `index.yaml`, `CHANGES.md` and
  `nautilus/README.md` agree on the image tags and pins behind the current
  calibration; the WMKO note lists every schema field. **Depends on:** S9,
  S16 (a draft can be written after S9).

## Risks across steps

- **LDS749B S/N.** Faint star, wide slit, two frames: the first sensfunc may
  be noisy and the J2 red edge hard to judge; S5 has fallbacks and S15 brings
  brighter stars.
- **PypeIt `develop` drift.** The pin file, not the branch tip, is the
  reference. The image is exactly on the pin; the laptop checkout stays on
  `orig-hires-fixes` and must be MOSFIRE-equivalent to the pin (S0 check:
  pin is an ancestor, diff touches only allow-listed paths; `gates.py
  --reference` requires the reference's recorded pin and a passed check).
  Today the only difference is `keck_hires.py`, so API names read locally
  (`pypeit.core.standard`, `pypeit.pkg.cache`, `pypeit.dataPaths.telgrid`)
  hold at the pin. If a future pin touches MOSFIRE code, the check fails
  until the user updates the laptop checkout or the reference is redone on
  the workstation; that failure is the intended signal. The local version
  string (`dev1217+g017bece06`) legitimately differs from the image's
  (`dev1216+gf3a1f1d27`); nothing compares version strings.
- **Local versus in-pod agreement.** Same PypeIt commit, but the base Python
  (3.12 vs 3.14) and BLAS differ; the S4b gate measures the effect before
  any batch. If it matters, switch the base image, do not loosen the gate.
- **Private bucket.** Every access needs the user's keys: the local AWS
  profile, the pod secret (verified in S1b), and any collaborator must go
  through git for products. A wrong or missing secret shows up as
  `AccessDenied` in the first `s3_sync.py pull` of a pod, so the manifests
  fail fast rather than reduce and then fail to push. No key value is ever
  printed or committed.
- **Image build and registry.** Builds happen on the Linux workstation; the
  NRP registry has hung on manifest writes; a stale image silently reduces
  with old code. Every batch logs the tag, digest and pin, and the
  PROVENANCE block prints the SHAs so a wrong image is visible in the first
  log lines.
- **Storage and backup.** No CephFS PVC is used, so PAB's SQLite hang cannot
  recur; the trade is that a preempted pod loses its scratch and redoes the
  night (minutes to an hour). Nautilus S3 is not backed up: the committed
  products are the primary record, the D39 set is copied to `AIOcean:` after
  each batch and at each release, and anything outside the D39 set
  (`spec2d`, `Calibrations/`) must be pulled locally while the night is on
  S3 if a local step needs it (S11, S13).
- **Secrets and outward-facing actions.** Only secret *names* appear in the
  repo; image pushes, jobs beyond the pilot and any change to bucket access
  are proposed to the user, not run unasked.
- **Wide-slit sample size** depends on Keck practice (Q3, Josh Walawender).
- **Gemini grid provenance** is second hand (XTcalc `.sav`); verify against
  gemini.edu if it becomes reachable.
- **Network dependence.** S2 and S14 need the network locally; S14b needs
  KOA reachable from the cluster (checked first; fallback: local download
  and push); everything else in the pods talks only to Nautilus S3.
- **Run time and sizing.** Per-night wall-clock and memory are unmeasured
  until S4b; size the batch Jobs from the pilot (S15a), never from the first
  pod, and keep `activeDeadlineSeconds` on every Job.
- **Calibration monitor (S6b).** Three things are inferred from the
  datamodel and not yet checked on data: the units of `pixelflat_raw`, the
  wave image, and the OH-flux slit normalisation. S6b checks each one.
  Dome-flat rates also depend on dome position and the screen, so they are
  a trend, never a calibration. Changing the line lists after S15a would
  break the series, so lines are only ever added. A monitor failure must
  not cost a night's sensfunc, which is why the monitor sets flags and
  never gates a night.
- **Regression churn.** Every calibration release changes numbers; the
  fixtures are regenerated only in S16-type steps, with a `CHANGES.md` line.
