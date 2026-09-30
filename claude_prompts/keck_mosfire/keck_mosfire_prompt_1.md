# Keck MOSFIRE implementation, part 1: foundations (Phase 0)

## Goals

Set up the out-of-repo data root, cache the external inputs (Keck XTcalc
tarball with the Gemini Maunakea sky grids, PypeIt telluric grid), turn the
Gemini sky and transmission grids into the committed FITS product that the
ETC will read, and put the Nautilus prerequisites in place: the PypeIt pin
check, access to the private S3 bucket, the sync helper and the first push.
These are steps S0, S1, S1b, S2 and S3 of the implementation plan (v0.3).

Run order: this doc first. Prompts 1-3 (S1, S2, S3) are as before; prompt 4
(S0 check + S1b) needs the user to have done the S0 actions listed in its
text. S1 and S2 are independent of each other; S3 needs S1; S1b needs S1.
`claude_prompts/koa_search_prompts.md` can run in parallel with this doc.
Part 2 (`keck_mosfire_prompt_2.md`) needs S0, S1, S1b and S2; part 3 needs
S3.

## Context

- Design: `docs/keck_mosfire_design.md` (v0.3), sections 2 (decisions D23,
  D24, D30-D32, D35, D39, N4-N6), 3 (instrument facts), 4.2 (S3 layout and
  the local mirror), 4.3 (the telluric grid lives on Nautilus S3), 4.8.1-4.8.3
  (Nautilus conventions, image, storage), 4.8.9 (backup set), 5.3.3 and 5.3.8
  (how the grids are used), 5.4 (file format and provenance of
  `gemini_mk_sky_grid.fits`), 8 (residual verification items).
- Plan: `docs/keck_mosfire_implementation.md` (v0.3), steps S0, S1, S1b, S2,
  S3 and the "Risks across steps" section.
- Data root: `KECK_ETCS_DATA`, default
  `/Users/xavier/Projects/PypeIt/keck-etcs-data`. Nothing under it is
  committed. It is the local mirror of the bucket. Layout:
  `external/xtcalc/XTcalc_dir/`, `mosfire/<YYYYMMDD>/{raw,redux,sens,harvest}/`.
- S3: the **private** bucket `s3://keck-etcs` on Nautilus (created by the
  user 2026-09-30; only the user's keys can list, read or write). Endpoint
  `https://s3-west.nrp-nautilus.io` (in-cluster
  `http://rook-ceph-rgw-nautiluss3.rook`), path-style. Local access through
  the user's AWS profile (same keys as the `nautilus_s3:` rclone remote);
  in-pod access through a mounted secret in namespace `pypeit`, name to be
  verified (`prp-s3-credentials` first; else the user creates
  `keck-etcs-s3-credentials`). Never print or commit a key value.
- Raw data for 2022-04-09 (16 frames):
  `/Users/xavier/Projects/PypeIt/PypeIt-development-suite/RAW_DATA/keck_mosfire/J2_long/`.
- Keck XTcalc tarball: `https://www2.keck.hawaii.edu/inst/mosfire/XTcalc.tar`
  (46 MB). Its `Mauna_Kea_sky/` holds 24 IDL save files:
  `mk_skybg_zm_WW_AA_ph.sav` (sky background, photons/s/arcsec^2/nm/m^2,
  wavelength `lam` in nm, 900-5600 nm at 0.02 nm) and `mktrans_zm_WW_AA.sav`
  (transmission, `tran_lam` in micron), for water vapour WW/10 mm in
  {1.0, 1.6, 3.0, 5.0} and airmass AA/10 in {1.0, 1.5, 2.0}. Read them with
  `scipy.io.readsav`. The gemini.edu site returns HTTP 403, so the tarball is
  our only copy.
- PypeIt checkout: `/Users/xavier/Projects/PypeIt/PypeIt`, to be on
  **`develop`** at the commit in `nautilus/pypeit_pin.txt` (user's git; the
  pin on 2026-09-30 is `f3a1f1d274b15ee1358f167819d77f1948fce1bd`,
  `origin/develop`, expected version `2.0.2.dev1216+gf3a1f1d27`). The
  `pypeit14` env is an editable install, so `pypeit.__version__` may still
  report the old `g017bece06` until `pip install -e ".[dev]"` is re-run there
  (user action). The telluric grid MOSFIRE needs is
  `TellPCA_3000_26000_R10000.fits` (6 MB), fetched by
  `pypeit.dataPaths.telgrid.get_file_path(...)` (host `s3_cloud`) from
  PypeIt's S3 host, which is Nautilus S3: `pypeit/data/s3_url.txt` reads
  `s3-west.nrp-nautilus.io` and the object is the public
  `https://s3-west.nrp-nautilus.io/pypeit/telluric/atm_grids/TellPCA_3000_26000_R10000.fits`.
  The cache module is `pypeit.pkg.cache` (`search_cache`,
  `fetch_remote_file`); the cache directory is astropy's (`~/.cache/pypeit`
  here; `XDG_CACHE_HOME` overrides it). PypeIt's OH line list for J is
  `pypeit/data/arc_lines/lists/OH_MOSFIRE_J_lines.dat` (vacuum wavelengths).
- Nautilus precedents to imitate: `Oceanography/python/PAB/nautilus/s3_push.py`
  (boto3, idempotent by key and size), `inspect_pod.yaml`, and the manifest
  conventions in design 4.8.1.
- Existing scripts: `scripts/inspect_xtcalc_files.py` (reads the tarball's
  throughput, filter and sky files) and `scripts/size_gemini_sky_subset.py`
  (sizes the MOSFIRE-range subset). Their numbers are recorded in the
  Prompt #1 and #2 logs of `keck_mosfire_prompts.md`.
- Rules (CLAUDE.md): the user runs all state-changing git, in this repo and
  in the PypeIt checkout (no `checkout`/`switch` by the session); Python
  only via `conda run -n pypeit14 python`; every calculation is a script on
  disk under `scripts/`; no secret value in the repo or in a log; log each
  prompt here.

## Prompts

1. **S1: data root and external caches.** Create the data root at
   `KECK_ETCS_DATA` (default above) with `external/xtcalc/`, and
   `mosfire/20220409/raw/` holding the 16 dev-suite frames (symlinks are
   fine). Download and unpack the XTcalc tarball into
   `external/xtcalc/XTcalc_dir/`. Add `keck_etcs/paths.py` with
   `data_root()` (env var with the default), `night_dir(instrument, date,
   kind)` and `s3_prefix(instrument, date, kind)` (the matching bucket key,
   e.g. `mosfire/20220409/sens`, with the bucket name `keck-etcs` as a
   module constant overridable by `KECK_ETCS_BUCKET`). Add `.gitignore`
   rules so that FITS, `.sav` and `.tar` files outside `keck_etcs/data/` and
   `keck_etcs/tests/data/` are ignored, and document `KECK_ETCS_DATA` and
   the mirror relationship to the bucket in `README.md`. Verify: `conda run
   -n pypeit14 python scripts/inspect_xtcalc_files.py
   $KECK_ETCS_DATA/external/xtcalc/XTcalc_dir` reproduces the J end-to-end
   throughput peak 0.319 / median 0.276 and the 24 Gemini files; `python -c
   "from keck_etcs import paths; print(paths.data_root(),
   paths.s3_prefix('mosfire', '20220409', 'sens'))"` prints the root and
   `mosfire/20220409/sens`; `git status` shows no data files. Log your work.

2. **S2: fetch the PypeIt telluric grid.** Write
   `scripts/fetch_telluric_grid.py` that asks PypeIt for
   `TellPCA_3000_26000_R10000.fits` through `pypeit.dataPaths.telgrid`
   (read `pypeit/pkg/pypeitdata.py` first in case the name moved on
   `develop`) and prints the cached path, size and sha256, and writes the
   sha256 as one line to `nautilus/telluric_grid.sha256` (the image build of
   part 2 checks its download against it). Run it. Verify:
   `pypeit.pkg.cache.search_cache('TellPCA')` returns one path, the file is
   about 6 MB and opens with astropy, a second run reports it cached without
   downloading, and the sha256 equals that of the public URL in Context
   fetched directly with `curl`. This step works on either PypeIt branch.
   Risk: the API may have moved; read the source rather than guessing. Log
   your work.

3. **S3: Gemini sky and transmission grid as a committed FITS file.** Write
   `scripts/mosfire/build_gemini_sky_grid.py` that reads the 24 `.sav` files,
   rebins each (flux-conserving, not interpolating) to a common 0.05 nm grid
   over 950-2450 nm (30000 points), and writes
   `keck_etcs/data/sky/gemini_mk_sky_grid.fits` with HDUs `WAVE` (nm, vacuum),
   `SKYBG` (12 x 30000, photons/s/arcsec^2/nm/m^2), `TRANS` (12 x 30000) and a
   `GRID` table with `airmass` and `pwv_mm` per row, plus header cards
   `SOURCE` (Gemini Observatory IR sky background and ATRAN transmission, as
   redistributed in Keck XTcalc v2.3), `REBIN`, `SCRIPT`, `CREATED`,
   `KETCSVER`. Create `keck_etcs/data/index.yaml` and register the file with
   `calib_version`. Handle the unit difference: sky wavelengths are nm,
   transmission wavelengths are micron.

   Verification of decision N5 (vacuum vs air) is part of this step: the
   design assumes the Gemini grids are in vacuum. Test it by locating the 10
   strongest OH lines in the 1.10-1.35 um sky grid (at native sampling) and
   comparing their centroids with PypeIt's vacuum list
   `OH_MOSFIRE_J_lines.dat`. Air-vacuum at 1.2 um is about 3.3 A, far larger
   than the 0.2 A sampling, so the answer is unambiguous. Write this as
   `scripts/mosfire/check_gemini_wavelength_convention.py`, record the median
   offset in the log and in the FITS header (`WAVEREF = vacuum` or `air`), and
   if the grids are in air, convert to vacuum in the build script and update
   design decision N5 in `docs/keck_mosfire_design.md`.

   Verify: for every grid the integral of the rebinned sky over 1.17-1.33 um
   matches the native integral to 1e-3; the J-band median transmission at
   PWV 1.6, airmass 1.0 is 0.9976 as in `inspect_xtcalc_files.py`; the file is
   under 5 MB; `git status` shows only the FITS, the two scripts and the index.
   Log your work, including the N5 result.

4. **S0 check and S1b: PypeIt pin, bucket access, sync helper, first push.**
   The user has done, or will do on request, the S0 actions of the plan:
   switched `/Users/xavier/Projects/PypeIt/PypeIt` to `develop` at the pinned
   commit (re-running `pip install -e ".[dev]"` in `pypeit14` if
   `pypeit.__version__` still shows `g017bece06`), and has the Nautilus S3
   keys as an AWS profile locally (`rclone lsd nautilus_s3:keck-etcs` works).
   Do not run any git `checkout`/`switch` yourself; if the checkout is not
   on the pin, stop and say exactly which commands the user should run.
   Then: (a) write `nautilus/pypeit_pin.txt` (one line, the full SHA of the
   commit the checkout is on, which must be on `origin/develop`'s history:
   check with `git -C <checkout> merge-base --is-ancestor <sha>
   origin/develop`, read-only) and `scripts/check_pypeit_pin.py` (prints
   `pypeit.__version__`, `pypeit.__file__`, the checkout's HEAD and branch,
   the pin, and PASS/FAIL on HEAD == pin, version string ends with the pin's
   short SHA, branch is `develop`; non-zero exit on FAIL; a `--image TAG`
   option, for part 2, that compares against a running image's
   `KECK_ETCS_GIT_SHAS`); (b) write `scripts/nautilus/s3_sync.py` (boto3;
   `push`, `pull`, `ls` subcommands over `s3://keck-etcs/<prefix>` and the
   matching `$KECK_ETCS_DATA` path; endpoint from `ENDPOINT_URL` with the
   default above; credentials only from `AWS_PROFILE`/`AWS_*`; idempotent by
   key and size; `--dry-run`, `--jobs`; `AccessDenied` is a hard error naming
   the profile, with no anonymous fallback); (c) write
   `nautilus/inspect_pod.yaml` (namespace `pypeit`, `python:3.12-slim`,
   mounts the secret named by `KECK_ETCS_S3_SECRET`, default
   `prp-s3-credentials`, at `/root/.aws/credentials` subPath `credentials`,
   `pip install boto3`, lists `s3://keck-etcs/` and prints the count; header
   comment with purpose and the three `kubectl` lines per design 4.8.1) and
   `nautilus/README.md` v0 (namespace, bucket and its private status, secret
   names, the layout of design 4.2, the `kubectl` idioms, and the recipe for
   `kubectl -n pypeit create secret generic keck-etcs-s3-credentials
   --from-file=credentials=$HOME/.aws/credentials` if the default secret
   fails the test); (d) push the 16 raw frames plus a `raw/manifest.ecsv`
   (koaid, file, frame type, target, slit, `SAMPMODE`, `NUMREADS`, exptime,
   airmass, sha256) to `mosfire/20220409/raw/`; (e) ask the user to apply
   the inspect pod and paste its log, or apply it yourself if the user has
   said so. Verify: `check_pypeit_pin.py` passes; `s3_sync.py ls
   mosfire/20220409/raw` lists 16 objects with the local sizes and a second
   `push` uploads nothing; `curl -sI
   https://s3-west.nrp-nautilus.io/keck-etcs/mosfire/20220409/raw/manifest.ecsv`
   returns 403 (private); the inspect pod lists the same 16 keys, or reports
   `AccessDenied`, in which case record that the user must create the new
   secret and which `KECK_ETCS_S3_SECRET` value the manifests will use;
   `git status` shows only the pin file, two scripts, the YAML and the
   README; no key value appears anywhere. Log your work, including the pin
   SHA and version string and the outcome of the secret test.

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
