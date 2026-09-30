# Keck MOSFIRE implementation, part 1: foundations (Phase 0)

## Goals

Set up the out-of-repo data root, cache the external inputs (Keck XTcalc
tarball with the Gemini Maunakea sky grids, PypeIt telluric grid), and turn
the Gemini sky and transmission grids into the committed FITS product that the
ETC will read. These are steps S1-S3 of the implementation plan.

Run order: this doc first. Its steps S1 and S2 are independent of each other;
S3 needs S1. `claude_prompts/koa_search_prompts.md` can run in parallel with
this doc. Part 2 (`keck_mosfire_prompt_2.md`) needs S1 and S2; part 3 needs
S3.

## Context

- Design: `docs/keck_mosfire_design.md`, sections 2 (decisions D23, D24,
  N4-N6), 3 (instrument facts), 4.2 (data root layout), 5.3.3 and 5.3.8 (how
  the grids are used), 5.4 (file format and provenance of
  `gemini_mk_sky_grid.fits`).
- Plan: `docs/keck_mosfire_implementation.md`, steps S1, S2, S3 and the
  "Risks across steps" section.
- Data root: `KECK_ETCS_DATA`, default
  `/Users/xavier/Projects/PypeIt/keck-etcs-data`. Nothing under it is
  committed. Layout: `external/xtcalc/XTcalc_dir/`,
  `mosfire/<YYYYMMDD>/{raw,redux,sens}/`.
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
- PypeIt checkout: `/Users/xavier/Projects/PypeIt/PypeIt` (2.0.2.dev). The
  telluric grid MOSFIRE needs is `TellPCA_3000_26000_R10000.fits` (6 MB),
  fetched from PypeIt's `s3_cloud` host into `~/.cache/pypeit/` by
  `pypeit.dataPaths.tel_model.get_file_path(...)`; the cache module is
  `pypeit.pkg.cache` (`search_cache`, `fetch_remote_file`). PypeIt's OH line
  list for J is `pypeit/data/arc_lines/lists/OH_MOSFIRE_J_lines.dat` (vacuum
  wavelengths).
- Existing scripts: `scripts/inspect_xtcalc_files.py` (reads the tarball's
  throughput, filter and sky files) and `scripts/size_gemini_sky_subset.py`
  (sizes the MOSFIRE-range subset). Their numbers are recorded in the
  Prompt #1 and #2 logs of `keck_mosfire_prompts.md`.
- Rules (CLAUDE.md): the user runs all state-changing git; Python only via
  `conda run -n pypeit14 python`; every calculation is a script on disk under
  `scripts/`; log each prompt here.

## Prompts

1. **S1: data root and external caches.** Create the data root at
   `KECK_ETCS_DATA` (default above) with `external/xtcalc/`, and
   `mosfire/20220409/raw/` holding the 16 dev-suite frames (symlinks are
   fine). Download and unpack the XTcalc tarball into
   `external/xtcalc/XTcalc_dir/`. Add `keck_etcs/paths.py` with
   `data_root()` (env var with the default) and
   `night_dir(instrument, date, kind)`. Add `.gitignore` rules so that FITS,
   `.sav` and `.tar` files outside `keck_etcs/data/` and
   `keck_etcs/tests/data/` are ignored, and document `KECK_ETCS_DATA` in
   `README.md`. Verify: `conda run -n pypeit14 python
   scripts/inspect_xtcalc_files.py $KECK_ETCS_DATA/external/xtcalc/XTcalc_dir`
   reproduces the J end-to-end throughput peak 0.319 / median 0.276 and the
   24 Gemini files; `python -c "from keck_etcs import paths;
   print(paths.data_root())"` prints the root; `git status` shows no data
   files. Log your work.

2. **S2: fetch the PypeIt telluric grid.** Write
   `scripts/fetch_telluric_grid.py` that asks PypeIt for
   `TellPCA_3000_26000_R10000.fits` through `pypeit.dataPaths.tel_model`
   (fall back to whatever PypeIt 2.0 now names it: check
   `pypeit/pkg/pypeitdata.py` and `doc/installing.rst`, "Atmospheric
   Models") and prints the cached path and size. Run it. Verify:
   `pypeit.pkg.cache.search_cache('TellPCA')` returns one path, the file is
   about 6 MB and opens with astropy, and a second run reports it cached
   without downloading. Risk: this step needs the network and the PypeIt API
   may have moved; read the source rather than guessing. Log your work.

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

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs
