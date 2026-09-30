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
- PypeIt checkout: `/Users/xavier/Projects/PypeIt/PypeIt`, on
  `orig-hires-fixes` (HEAD `017bece06`, `pypeit14` editable install,
  version `2.0.2.dev1217+g017bece06`), and it **stays there**: the user
  (2026-09-30) will not switch it to `develop` and does no PypeIt
  development on this laptop. The image pin is a `develop` commit in
  `nautilus/pypeit_pin.txt` (on 2026-09-30
  `f3a1f1d274b15ee1358f167819d77f1948fce1bd` = `origin/develop`, the
  merge-base with HEAD; HEAD is one commit ahead and the whole diff is
  `pypeit/spectrographs/keck_hires.py`, +131/-33). Design D35: the local
  checkout must *contain* the pin and differ from it only in paths
  irrelevant to MOSFIRE J reductions; `scripts/check_pypeit_pin.py` tests
  exactly that. The telluric grid MOSFIRE needs is
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

4. **S0 check and S1b: PypeIt pin check, bucket access, sync helper, first
   push.** The user has already provided the S0 prerequisites (2026-09-30):
   the Nautilus S3 keys as a local AWS profile that reads and writes
   `s3://keck-etcs` (confirmed), the GitLab project `profx/keck-etcs` with
   a deploy token (username `gitlab+deploy-token-1383`; the token itself
   stays with the user) and `docker login` on the workstation. The PypeIt checkout stays on `orig-hires-fixes`; do not ask
   for a branch switch or a reinstall and do not run any git
   `checkout`/`switch` yourself. Then: (a) write `nautilus/pypeit_pin.txt`
   (one line: the full SHA of `git -C <checkout> merge-base HEAD
   origin/develop`, read-only, which today is
   `f3a1f1d274b15ee1358f167819d77f1948fce1bd`),
   `nautilus/pypeit_pin_allowlist.txt` (glob patterns of paths irrelevant to
   MOSFIRE J reductions: `pypeit/spectrographs/*.py` except
   `keck_mosfire.py`, `spectrograph.py`, `util.py`, `__init__.py`; `doc/**`;
   `**/*.rst`; test directories) and `scripts/check_pypeit_pin.py`, which
   prints `pypeit.__version__`, `pypeit.__file__`, the checkout's HEAD SHA
   and branch, the pin, and the file list from `git diff --name-only <pin>
   HEAD` plus uncommitted changes (`git status --porcelain`), then PASS/FAIL
   on (1) `git merge-base --is-ancestor <pin> HEAD` and (2) every listed
   file matching the allow-list, naming offending files on FAIL with a
   non-zero exit; it also writes a JSON result (`pypeit_git_sha`,
   `pypeit_pin`, `pin_check: {pass, files}`) for the reduction driver to
   copy into `run_manifest.json`, and takes a `--image TAG` option (part 2)
   that runs the image and requires its `KECK_ETCS_GIT_SHAS.pypeit` to equal
   the pin exactly; (b) write `scripts/nautilus/s3_sync.py` (boto3;
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
   said so. Verify: `check_pypeit_pin.py` passes with the diff list equal to
   `[pypeit/spectrographs/keck_hires.py]` (and fails, as a negative test,
   when pointed at an allow-list that omits `keck_hires.py`); `s3_sync.py ls
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

- **2026-09-30, after Prompt #1 (Linux workstation).** Q: `pypeit14` is empty
  here. Which env? A: use `pypeit14b`. Q: The PypeIt checkout is on `develop`
  at the pin `f3a1f1d27`, not `orig-hires-fixes`. Is that right? A: yes, and it
  stays on `develop`. So on this machine Prompt #4's pin check should pass
  with an empty diff list.

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-09-30 (Prompt #1 / S1: data root, XTcalc cache, keck_etcs/paths.py)

Work was done on the Linux workstation, not on the laptop the Context
describes. That changes a few facts; see "Machine differences" below.

**Data root.** Created `~/Projects/PypeIt/keck-etcs-data`
(`/home/xavier/Projects/PypeIt/keck-etcs-data`; `~/Projects/PypeIt` is a
symlink to `/mnt/tank/Astronomy/PypeIt`) with `external/xtcalc/` and
`mosfire/20220409/raw/`. The raw directory holds 16 symlinks to the dev-suite
frames `RAW_DATA/keck_mosfire/J2_long/m220409_{0017..0026,0036..0039,0218,0219}.fits`,
16853760 bytes each.

**XTcalc.** Downloaded `https://www2.keck.hawaii.edu/inst/mosfire/XTcalc.tar`
(46697984 bytes, sha256
`344b45b44c5ca76e93fbae20ee421b2707419ab6082aa5a5a213a7ac353ec4ae`), kept it
beside the unpacked tree, and unpacked it to `external/xtcalc/XTcalc_dir/`
(`bin`, `Mauna_Kea_sky` (24 files), `mosfire`, `MosfireSkySpec`,
`MosfireSpecEff`, `MOSFIRE_XTcalc.pdf`, `run_XTcalc.sav`, `XTcalc`).

**`keck_etcs/paths.py`.** Contains `DEFAULT_DATA_ROOT =
'~/Projects/PypeIt/keck-etcs-data'`, `BUCKET` (from `KECK_ETCS_BUCKET`,
default `keck-etcs`, read at import), `KINDS = (raw, redux, sens, harvest)`,
`data_root()`, `night_dir(instrument, date, kind=None)`,
`s3_prefix(instrument, date, kind=None)` and `xtcalc_dir()`.
- `night_dir` and `s3_prefix` share one helper, which validates `YYYYMMDD`
  and `kind`, so the local and S3 layouts cannot drift.
- The default uses `~` rather than the hard-coded
  `/Users/xavier/Projects/PypeIt/keck-etcs-data` of design D24. That gives
  the same path on the Mac and the right one on Linux, where `/Users` does
  not exist. D24 does not need to change.
- `data_root()` expands `~` and makes the path absolute, but does not
  resolve symlinks. A first version used `Path.resolve()`, which turned the
  root into `/mnt/tank/...`.

**`.gitignore` and README.** Appended `*.fits`, `*.fits.gz`, `*.sav` and
`*.tar`, with `!keck_etcs/data/**/*.fits(.gz)` and
`!keck_etcs/tests/data/**/*.fits(.gz)` exceptions. `git check-ignore` shows
FITS files ignored in `scripts/` and allowed under both exception trees;
`.sav` and `.tar` are ignored everywhere. Added a "Data root" section to
`README.md`: `KECK_ETCS_DATA`, `KECK_ETCS_BUCKET`, the layout, the mirror
relationship to `s3://keck-etcs`, and the fact that `external/` is local
only.

**Verification.**
- `scripts/inspect_xtcalc_files.py $KECK_ETCS_DATA/external/xtcalc/XTcalc_dir`
  gives J end-to-end (Jeff.sm.dat x KMRef^2 = 0.792) peak 0.319 and median
  0.276, and lists all 24 Gemini `.sav` files (12 `mk_skybg_zm_WW_AA_ph`, 12
  `mktrans_zm_WW_AA`). The J median transmission at PWV 1.6 mm, airmass 1.0
  is 0.9976.
- `paths.data_root(), paths.s3_prefix('mosfire','20220409','sens')` prints
  `/home/xavier/Projects/PypeIt/keck-etcs-data mosfire/20220409/sens`, and
  the same with `KECK_ETCS_DATA` unset.
- `KECK_ETCS_BUCKET=foo` changes `paths.BUCKET`.
- `git status` shows only `.gitignore`, `README.md` and `keck_etcs/paths.py`;
  no data files.

**Machine differences (Linux workstation vs. the Context).**
1. Conda env `pypeit14` exists here but is empty: only pip, so no numpy.
   `conda run -n pypeit14 python` fails on `import numpy`. The working env is
   `pypeit14b` (the active one; numpy 2.5.0). The verifications above were
   run with `/home/xavier/miniconda3/envs/pypeit14b/bin/python`. Either
   rebuild `pypeit14` here or let the CLAUDE.md rule accept `pypeit14b` on
   this machine.
2. The PypeIt checkout here is `/mnt/tank/Astronomy/PypeIt/PypeIt`
   (= `~/Projects/PypeIt/PypeIt`), on branch `develop` at `f3a1f1d27`. That
   is exactly the planned pin, and the tree is clean. The installed version
   is `2.0.2.dev1216+gf3a1f1d27`, not `orig-hires-fixes`/`017bece06`.
   Prompt #4's expected diff list (`[keck_hires.py]`) holds only on the
   laptop. Here the pin check should pass with an empty diff.
3. The design and plan paths `/Users/xavier/Projects/PypeIt/...` map to
   `/home/xavier/Projects/PypeIt/...` here.

### 2026-09-30 (Prompt #2 / S2: PypeIt telluric grid fetched, sha256 recorded)

Linux workstation, `pypeit14b`, PypeIt `develop` at `f3a1f1d27`.

**API (read from source; nothing has moved on `develop`).**
- `pypeit.dataPaths.telgrid` is a `PypeItDataPath` for `telluric/atm_grids`
  with host `s3_cloud` (`pypeit/pkg/pypeitdata.py`, `PypeItDataPaths`).
- `telgrid.get_file_path(name, force_update=False)` checks the package tree,
  then calls `pypeit.pkg.cache.fetch_remote_file`. That calls
  `astropy.utils.data.download_file(..., pkgname='pypeit')` and prints an
  "install scripts" warning for every `s3_cloud` file.
- `cache._build_remote_url` keys the cache by a permanent, fake URL,
  `https://s3.cloud.com/pypeit/telluric/atm_grids/<file>`. The real source
  is `https://<s3_url.txt>/pypeit/...`. `_get_s3_hostname()` first tries the
  `release` branch's `s3_url.txt` on GitHub, then the packaged copy
  (`s3-west.nrp-nautilus.io`).
- So the cache survives a change of S3 host, and "is it cached?" is
  `astropy.utils.data.is_url_in_cache(<fake url>, pkgname='pypeit')`.

**Cache location.** The cache on this machine is `~/.pypeit/cache/download/url/<hash>/contents`,
not the `~/.cache/pypeit` the Context names.

**`scripts/fetch_telluric_grid.py`.**
- Reports the data path, cache key, download source and status (in package
  tree / already cached / downloading), then fetches via `get_file_path`.
- Prints the cached path, size, sha256 and HDU shapes (opened with
  astropy), and the `search_cache` hits.
- Writes the sha256 to `nautilus/telluric_grid.sha256` (a new directory).
- `--force-update` re-downloads the file.

**Results.**
- Run 1 downloaded the file (it was not cached before) to
  `~/.pypeit/cache/download/url/da53ec58845fabd86f0bce9cd869c521/contents`.
- Size 6252480 bytes (6.25 MB). HDUs: PRIMARY [11, 54932], [54932],
  [2, 11], [12000, 10].
- sha256 `10d56a6cf5774a352507a69c5cae9a11f158866e47e962ed682bb6e39e2901df`.
- Run 2 reported "already cached, not downloading", with the same path and
  sha256.
- `curl` of the public URL gives the identical sha256; `HTTP/2 200`,
  content-length 6252480, last-modified 2023-12-13, etag
  `a26baecd5f8fe258ef4248a68fa2318b`.

**`search_cache('TellPCA')` returns two paths.** The cache already held
`TellPCA_3000_26000_R25000.fits` (14163840 bytes) from earlier work.
`search_cache('TellPCA_3000_26000_R10000.fits')` returns exactly one path,
which is the meaningful check. The script uses the full name and lists the
other TellPCA grids separately. The R25000 file was left in place, since it
is not ours to delete.

**`git status`.** Shows `nautilus/` (only `telluric_grid.sha256`) and
`scripts/fetch_telluric_grid.py`, plus the uncommitted S1 changes.

### 2026-09-30 (Prompt #3 / S3: Gemini sky+transmission grid FITS; N5 confirmed: vacuum)

Linux workstation, `pypeit14b`.

**N5 result: the Gemini grids are in VACUUM.**
`scripts/mosfire/check_gemini_wavelength_convention.py` finds the 10
strongest OH peaks in `mk_skybg_zm_16_10_ph.sav` over 1100-1350 nm. It
centroids them (7 native pixels, continuum-subtracted) and matches each to
the nearest line of PypeIt's `OH_MOSFIRE_J_lines.dat`.
- **Native 0.02 nm sampling:** median offset (Gemini - PypeIt vacuum)
  **+0.009 A**, against +3.405 A from the same list converted to air (the
  air-vacuum shift is 3.353 A).
  - Nine lines agree to 0.01-0.16 A.
  - One peak (1268.58 nm) matched a neighbouring PypeIt line at +2.6 A,
    because the PypeIt list does not have that line separately. The median is
    robust to it; the scatter with it is 0.76 A.
- **Cross-check, sky smoothed to R=3318** (the resolution at which PypeIt's
  list was built): median +0.010 A, scatter 0.031 A.
- **Consequences:**
  - The header records `WAVEREF = 'vacuum'` and `WAVEOFF = 0.0088` (A).
  - The build does not convert wavelengths; its air-to-vacuum branch is
    coded but inactive.
  - Design decision N5 is unchanged.
- **Two pitfalls fixed along the way:**
  - `pypeit.core.wave.vactoair` always returns Angstrom, whatever the input
    unit, so the script uses `.to(u.nm)`.
  - The match tolerance must exceed the air shift. It is 6 A, so an air grid
    would show up as a -3.3 A offset instead of being dropped as unmatched,
    which would bias the test toward vacuum.

**`scripts/mosfire/build_gemini_sky_grid.py`.**
- **Inputs:** reads the 24 `.sav` files. Sky `lam` is in nm, transmission
  `tran_lam` in micron (multiplied by 1e3).
- **Native grid:** the files store wavelengths as float32. The script
  rebuilds the exact float64 grid `900 + 0.02 i` (235000 points) and checks
  it against the stored values. They deviate by up to 1.2e-3 nm above
  4096 nm (float32 rounding, about 2 ulp) and by <1e-4 nm below 2450 nm; the
  tolerance is 10% of a pixel.
- **Rebin:** flux-conserving. Native pixels are treated as piecewise
  constant; the script builds the cumulative integral, interpolates it
  (exactly) onto 30001 edges from 950 to 2450 nm at 0.05 nm, and takes
  differences. `WAVE` holds the pixel centres, 950.025-2449.975 nm (float64).
  `SKYBG` and `TRANS` are float32 (12, 30000).
- **`GRID`:** rows in PWV-major order ({1.0, 1.6, 3.0, 5.0} mm x
  {1.0, 1.5, 2.0} airmass), with columns `airmass`, `pwv_mm`, `skyfile` and
  `transfile`.
- **Primary header:** `SOURCE`, `SRCURL`, `SRCSHA` (sha256 of XTcalc.tar),
  `REBIN = flux-conserving`, `WAVEREF`, `WAVEOFF`, `SCRIPT`, `CREATED` (UTC),
  `KETCSVER = 0.0.dev0`, `CALIBVER`, `NGRID`, plus the FITS checksums.
- **N5 on every build:** the build imports the check script's `check()` and
  refuses to build if the result is inconclusive.
- **Registry:** writes or updates `keck_etcs/data/index.yaml` under
  `files: sky/gemini_mk_sky_grid.fits`, with `calib_version`, `created`,
  `sha256`, `script`, `waveref` and `provenance`. `calib_version =
  mosfire-J-2026.10-dev` was chosen to match the S10 tag in the plan. The
  grid is not J-specific, but calibration tags are per band; this can be
  revisited.

**Verification** (all passes; the build exits 0).
- **Integral of SKYBG over 1170-1330 nm:** rebinned against native
  (trapezoid on the native samples) agrees to +1.2e-13 to +1.5e-13 for all
  12 grids, far below 1e-3.
- **J-band transmission at PWV 1.6 mm, airmass 1.0 (1170-1350 nm):**
  - The native median is 0.9976, as `inspect_xtcalc_files.py` reports.
  - The rebinned median is **0.9973**, not 0.9976. The median is not
    preserved by averaging: unresolved absorption lines mixed into 0.05 nm
    pixels lower the typical pixel, and a 3-pixel boxcar of the native data
    gives the same 0.9972.
  - The rebinned mean equals the native mean (0.969179 against 0.969189,
    rel -9.6e-6, from float32 storage).
  - So the check requires the native median to be 0.9976 and the mean to be
    conserved to 1e-4, and it reports the rebinned median for information.
    The prompt's "0.9976" holds for the native grid only.
- **File size:** 3139200 bytes (2.99 MiB), under 5 MB.
- **`git status`:** `keck_etcs/data/index.yaml`,
  `keck_etcs/data/sky/gemini_mk_sky_grid.fits` and the two scripts. The
  `.gitignore` exception for `keck_etcs/data/**/*.fits` works.

**Notes.**
- The file's sha256 changes on every rebuild, because `CREATED` and the
  checksum cards change; the data are identical. The build updates the
  `sha256` in `index.yaml` each time, so the pair stays consistent. The last
  build's sha256 is
  `5383f6f7d621e4ca18a6d245f7596ab666bee301afa4d3c0f2f7598fb4e5714a`.
- `keck_etcs` is not installed in `pypeit14b`. The two new scripts put the
  repo root on `sys.path` so they run from a checkout; `pip install -e .`
  would make that unnecessary.

### 2026-09-30 (Prompt #4 / S0 check + S1b: pin check, s3_sync, first push; pod test pending)

Linux workstation, `pypeit14b` (the user installed `keck_etcs` there; I
added `boto3` 1.43.106 with pip). Per the Q&A, the PypeIt checkout is on
`develop`, not `orig-hires-fixes`.

**(a) Pin.**
- **Pin files:**
  - `nautilus/pypeit_pin.txt` = `f3a1f1d274b15ee1358f167819d77f1948fce1bd`
    (= `git merge-base HEAD origin/develop` = `origin/develop` = HEAD,
    read-only git only).
  - The version string is `2.0.2.dev1216+gf3a1f1d27`, from
    `/mnt/tank/Astronomy/PypeIt/PypeIt/pypeit/__init__.py`.
- **`nautilus/pypeit_pin_allowlist.txt`:**
  - Gitignore-like: one glob per line, `**` for any depth including none,
    `!` to exclude, and the last matching line wins.
  - It allows `pypeit/spectrographs/*.py` except `keck_mosfire.py`,
    `spectrograph.py`, `util.py` and `__init__.py`; `doc/**`; `**/*.rst`;
    `pypeit/tests/**`; and `**/tests/**`.
- **`scripts/check_pypeit_pin.py`:**
  - Prints version, file, checkout, HEAD and branch, pin and allow-list;
    lists `git diff --name-only <pin> HEAD` and `git status --porcelain`
    (untracked files and both sides of a rename included).
  - Then checks (1) `merge-base --is-ancestor` and (2) the allow-list,
    naming offending files. Exit codes: 0 PASS, 1 FAIL, 2 git or usage error.
  - Writes JSON (`pypeit_git_sha`, `pypeit_pin`, `pypeit_version`,
    `pypeit_branch`, `checked`, `pin_check: {pass, files, ancestor,
    offending, allowlist[, image]}`), by default to
    `$KECK_ETCS_DATA/pypeit_pin_check.json`, `--json` to override.
  - Options: `--checkout` (default: the checkout `pypeit` is imported from),
    `--pin` (override, for tests), `--allowlist`.
  - `--image TAG` runs `docker run --rm TAG python -c ...`, parses
    `KECK_ETCS_GIT_SHAS` (JSON) and requires `.pypeit == pin`. It is written
    but untested, since the image comes in part 2.

**(a) Pin results.**
- **Positive:** PASS with an empty diff list. This is the expected result
  here: HEAD is the pin. `[keck_hires.py]` was the laptop's expectation.
- **Negative, run:** `--pin HEAD~3` gives FAIL, exit 1, naming 21 offending
  files (e.g. `pypeit/wavecalib.py`, `pypeit/spectrographs/spectrograph.py`,
  `pyproject.toml`).
- **Negative, matcher:** with an allow-list copy that adds
  `!pypeit/spectrographs/keck_hires.py`, `keck_hires.py` goes from allowed
  to not allowed. `keck_mosfire.py`, `spectrograph.py`, `util.py`,
  `__init__.py`, `pypeit/core/wave.py`, nested `spectrographs/sub/x.py` and
  `pypeit/data/...` are rejected under both lists. `keck_lris.py`,
  `doc/...rst`, top-level `README.rst`/`CHANGES.rst` and
  `pypeit/tests/...` are allowed.
- The run-level form of the prompt's negative test (the `keck_hires.py`
  diff) cannot occur on this machine, because the diff is empty.

**(b) `scripts/nautilus/s3_sync.py`.**
- **Commands:** `ls`, `push` and `pull` over
  `s3://$KECK_ETCS_BUCKET/<prefix>` and `$KECK_ETCS_DATA/<prefix>`, via
  `keck_etcs.paths`.
- **Connection:** endpoint from `ENDPOINT_URL` (default
  `https://s3-west.nrp-nautilus.io`; it is already set in this shell),
  path-style, standard retries.
- **Credentials:** from `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` if set,
  else the profile `AWS_PROFILE` (default `default`).
- **Transfers:** idempotent by key and size; `--dry-run`, `--jobs`
  (default 8); `pull --include GLOB...`.
  - `push` follows symlinks, so the raw directory's symlinks upload the real
    frames.
  - `pull` replaces a local symlink rather than writing through it.
- **Access errors:** `AccessDenied`, `InvalidAccessKeyId`,
  `SignatureDoesNotMatch`, HTTP 403, no credentials and an unknown profile
  are all a hard error with exit 3 that names the credential source. There
  is no anonymous or UNSIGNED fallback.
- **Which profile:** the local profiles `default` and `ceph-s3-large-files`
  hold the same key ID as the `nautilus_s3:` rclone remote (compared
  in-process; no value printed). `default` is used.
- **Tests:**
  - `AWS_PROFILE=swot-user` gives `InvalidAccessKeyId`, exit 3.
  - `AWS_PROFILE=no-such-profile` gives exit 3 (it first produced a
    traceback; `ProfileNotFound` is now caught).

**(d) First push.**
- **Manifest:** `scripts/mosfire/make_raw_manifest.py 20220409 --pypeit
  <dev-suite>/pypeit_files/keck_mosfire_j2_long.pypeit` wrote
  `$KECK_ETCS_DATA/mosfire/20220409/raw/manifest.ecsv`. This is a third
  script, not in the prompt's list, but CLAUDE.md requires one.
  - Columns: `koaid, file, frametype, target, slit, sampmode, numreads,
    exptime (TRUITIME), airmass, mjd, size, sha256`.
  - Frame types come from the dev-suite pypeit file: 5 `pixelflat,illumflat,trace`,
    5 `lampoffflats`, 4 `arc,science,tilt`, 2 `standard`.
  - The dev-suite frames have no `KOAID` card, so the KOA IDs are derived as
    `MF.<DATE-OBS>.<int UT s>` (e.g. `MF.20220409.24247` for
    `m220409_0036`) and listed in `meta.koaid_derived`. Check them against
    KOA when the KOA prompt runs.
  - Header `TARGNAME` is `LDS749` for the standard; the pypeit file says
    `LDS749B`.
  - Flats: `SAMPMODE` 2 (CDS), `NUMREADS` 1. Science and standard: 3
    (MCDS), 16.
- **Push:** 17 objects (16 x 16853760 bytes plus manifest.ecsv, 4523 bytes;
  269.7 MB) to `s3://keck-etcs/mosfire/20220409/raw/`.
  - `ls` lists all 17 as "local same size".
  - A second `push` uploads 0 and skips 17.
  - A `pull --include manifest.ecsv 'm220409_021*.fits'` into a scratch
    mirror downloaded 3 files: the pulled `m220409_0218.fits` sha256 equals
    the manifest's, the manifest is byte-identical, and a second pull
    downloads 0.
- **Privacy:** anonymous `curl -sI .../raw/manifest.ecsv` gives HTTP/2 403.
  So does a frame, and an anonymous bucket listing gives `AccessDenied`.

**(c) `nautilus/inspect_pod.yaml` and `nautilus/README.md`.**
- **Pod:** `keck-etcs-inspect` in namespace `pypeit`, `python:3.12-slim`,
  `activeDeadlineSeconds: 600`.
  - Mounts secret `prp-s3-credentials` at `/root/.aws/credentials`
    (subPath `credentials`), with `HOME=/root` and the in-cluster endpoint.
  - Prints the profile names in the mounted file (not values), runs
    `pip install boto3`, lists the bucket and prints `ACCESS_RESULT OK|<code>`,
    the object count and the raw keys, then `INSPECT_DONE`.
  - The header comment gives the purpose and the three `kubectl` lines.
    `KECK_ETCS_S3_SECRET` is applied by `sed` substitution, since YAML
    cannot read the environment; the file applies as is with the default.
- **Pod checks:** `kubectl apply --dry-run=server` passes. The pod's
  `python -c` block, run locally, lists the 17 keys with profile `default`
  and prints `ACCESS_RESULT InvalidAccessKeyId` with `swot-user`.
- **Namespace secrets:** `kubectl -n pypeit get secrets` (names only) shows
  `prp-s3-credentials` exists, created 5y77d ago. It may hold older keys,
  hence the test.
- **README v0:** namespace, bucket and its private status, secret names,
  the design 4.2 layout, the sync helper, the pin files, the kubectl idioms
  and the `keck-etcs-s3-credentials` recipe. The recipe notes that
  `--from-file=$HOME/.aws/credentials` copies every local profile into the
  Secret; a file with only `[default]` is tighter.

**(e) Secret test: PASS with the default secret.** The user applied the
inspect pod on 2026-09-30; the log is appended below. `prp-s3-credentials`
holds profiles `default` and `mskelm`. With `default`, the pod lists
`s3://keck-etcs/` through the in-cluster endpoint (`ACCESS_RESULT OK`):
17 objects, all under `mosfire/20220409/raw/`, with the same keys and sizes
as the local `s3_sync.py ls`. So the manifests use `KECK_ETCS_S3_SECRET =
prp-s3-credentials` (the default), and `keck-etcs-s3-credentials` is not
needed.

**`git status`.**
- New from this prompt: `nautilus/{pypeit_pin.txt, pypeit_pin_allowlist.txt,
  inspect_pod.yaml, README.md}`, `scripts/check_pypeit_pin.py`,
  `scripts/nautilus/s3_sync.py` and `scripts/mosfire/make_raw_manifest.py`.
  The prompt's list omits the allow-list, which it requires, and I added the
  manifest script.
- The S3 files from Prompt #3 are still uncommitted.
- A scan of every tracked or untracked non-FITS file, plus the JSON and the
  manifest in the data root, against the 8 key values in
  `~/.aws/credentials` found none.

```
(pypeit14b) profx> kubectl -n pypeit logs -f keck-etcs-inspect
=== PROVENANCE 2026-09-30T20:37:11+00:00 ===
secret=prp-s3-credentials endpoint=http://rook-ceph-rgw-nautiluss3.rook bucket=keck-etcs profile=default
Python 3.12.12
profiles in mounted credentials: ['default', 'mskelm']
=== INSTALL 2026-09-30T20:37:11+00:00 ===
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run: pip install --upgrade pip
=== LIST 2026-09-30T20:37:23+00:00 ===
ACCESS_RESULT OK secret prp-s3-credentials
objects in s3://keck-etcs/: 17
under mosfire/20220409/raw/: 17
      16853760  mosfire/20220409/raw/m220409_0017.fits
      16853760  mosfire/20220409/raw/m220409_0018.fits
      16853760  mosfire/20220409/raw/m220409_0019.fits
      16853760  mosfire/20220409/raw/m220409_0020.fits
      16853760  mosfire/20220409/raw/m220409_0021.fits
      16853760  mosfire/20220409/raw/m220409_0022.fits
      16853760  mosfire/20220409/raw/m220409_0023.fits
      16853760  mosfire/20220409/raw/m220409_0024.fits
      16853760  mosfire/20220409/raw/m220409_0025.fits
      16853760  mosfire/20220409/raw/m220409_0026.fits
      16853760  mosfire/20220409/raw/m220409_0036.fits
      16853760  mosfire/20220409/raw/m220409_0037.fits
      16853760  mosfire/20220409/raw/m220409_0038.fits
      16853760  mosfire/20220409/raw/m220409_0039.fits
      16853760  mosfire/20220409/raw/m220409_0218.fits
      16853760  mosfire/20220409/raw/m220409_0219.fits
          4523  mosfire/20220409/raw/manifest.ecsv
=== INSPECT_DONE 2026-09-30T20:37:24+00:00 ===
```