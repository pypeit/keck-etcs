# Keck MOSFIRE implementation, part 6: wrap-up (Phase 5)

## Goals

File the PypeIt read-noise fix as a branch off `develop` in the PypeIt
checkout, and bring the documentation, README, changelog, the Nautilus
operator guide and the WMKO API note to the "definition of done" state.
These are steps S17 and S18 of the plan (v0.3).

Run order: S17 needs part 3's detector table (S8) and can run any time after
it, in parallel with parts 4 and 5. S18 needs part 3 (S9) for a draft and
part 5 (S16) for the final version.

## Context

- Design: `docs/keck_mosfire_design.md` (v0.3), sections 2 (D12, D13, D19,
  D28, D31, D32, D38, D39), 3 (RN table and `SAMPMODE` codes), 4.8 (the
  Nautilus infrastructure the operator guide documents), 5.2 (the schema
  fields the WMKO note must list), 5.5 (versioning), 7 (definition of done
  items 4-6), 8 (open items).
- Plan: `docs/keck_mosfire_implementation.md` (v0.3), steps S17, S18.
- PypeIt checkout on this laptop: `/Users/xavier/Projects/PypeIt/PypeIt`,
  on `orig-hires-fixes`, MOSFIRE-equivalent to the pin
  `nautilus/pypeit_pin.txt` (verify with `scripts/check_pypeit_pin.py`); it
  stays there and **no PypeIt development happens on this laptop** (user,
  2026-09-30). The `ronoise` branch is created by the user from `develop`
  on the workstation (or wherever PypeIt is developed); the session prepares
  the change as reviewable files in this repo. File
  `pypeit/spectrographs/keck_mosfire.py`, `get_detector_par(self, det,
  hdu=None)`, which sets `ronoise = np.atleast_1d(5.8)` with the comment
  "for 16 non-destructive reads" (identical at the pin: the local diff from
  it is `keck_hires.py` only). Header cards: `SAMPMODE` (1
  Single, 2 CDS, 3 MCDS, 4 UTR) and `NUMREADS`. Keck table: CDS 21, MCDS-4
  10.8, -8 7.7, -16 5.8, -32 4.2, -64 3.5, -128 3.0 e-. Our 2022-04-09 dome
  flats are CDS (`SAMPMODE = 2`, `NUMREADS = 1`), the science and standard
  frames MCDS-16. The PypeIt dev suite
  (`/Users/xavier/Projects/PypeIt/PypeIt-development-suite`) has MOSFIRE
  tests that may encode the fixed value. Raw frames for the read-noise check
  are in `$KECK_ETCS_DATA/mosfire/20220409/raw/` (local; also on S3).
- Image pin: if the `ronoise` branch is later used for reductions, the pin
  in `nautilus/pypeit_pin.txt` moves to that commit with an image tag bump;
  `nautilus/build_image.sh` requires the pin to be on `develop`'s history,
  so a feature-branch pin needs its explicit `--allow-branch` flag and a
  log line (plan S17). Preferably wait for the branch to merge to `develop`.
- Repo state expected by now: `keck_etcs/` with `core/`, `instruments/`,
  `calib/`, `provenance.py`, `etc.py`, `schema/`, `data/index.yaml`,
  `bin/keck_etc`, `examples/`, tests; `nautilus/` with `Dockerfile`,
  `build_image.sh`, `pypeit_pin.txt`, `telluric_grid.sha256`, the Job
  manifests, `gates.py`, `night_failures.py`, `status_table.py`,
  `manifests/`, `README.md`; `scripts/nautilus/{s3_sync,backup_products}.py`;
  `docs/keck_mosfire_design.md` with validation and XTcalc appendices;
  `CHANGES.md` started in part 4.
- Nautilus facts the operator guide must state (design D31, D32, D39):
  namespace `pypeit`; registry `gitlab-registry.nrp-nautilus.io/profx/keck-etcs`
  (public image, built on the Linux workstation); private bucket
  `s3://keck-etcs` (every access needs the user's keys: local AWS profile,
  in-pod secret `KECK_ETCS_S3_SECRET`); no PVC; backup set and timing per
  design 4.8.9 to `AIOcean:keck-etcs/`; products distributed through git.
- Rules (CLAUDE.md): the user runs git in both repositories (the PypeIt
  branch is created and committed by the user; you edit the files and
  provide the commit message); `conda run -n pypeit14`; scripts on disk;
  verified PypeIt defects are fixed in PypeIt, never worked around here; no
  secret value in any doc; log each prompt.

## Prompts

1. **S17: PypeIt `ronoise` from the readout mode (branch off `develop`).**
   First, if the CDS dome flats allow it, check the Keck table empirically:
   write `scripts/mosfire/measure_read_noise.py` that takes the difference
   of two lamp-off flats (m220409_0022-0026, `NUMREADS = 1`), divides by
   sqrt(2), converts to electrons with gain 2.15, and reports the robust
   standard deviation in a low-signal region; compare with 21 e- (CDS).
   Then run `scripts/check_pypeit_pin.py` (to confirm the local
   `keck_mosfire.py` you read is the pin's) and ask the user to create a
   branch **from `develop`** (suggest `mosfire_ronoise`) on the workstation
   or wherever they develop PypeIt, not on this laptop; do not run
   `checkout`/`switch`/`branch` yourself. Prepare the change here as
   `nautilus/patches/pypeit_mosfire_ronoise.patch` (`git diff` format
   against the pin, made from a scratch copy of the two files, never by
   editing the laptop checkout) plus the new test file, for the user to
   apply on that branch. The change: `keck_mosfire.py` so that
   `get_detector_par` reads `SAMPMODE` and
   `NUMREADS` from `hdu` when given and looks up the RN from the Keck table
   (interpolating in log2 N for non-tabulated values; CDS = 21; keep 5.8 as
   the default when `hdu` is None), with the table and its source URL in a
   module-level constant. Add a PypeIt unit test using a synthetic header.
   Verify: `get_detector_par(1, hdu)` returns 21 for the CDS flats and 5.8
   for the MCDS-16 frames; PypeIt's own tests for MOSFIRE pass; note any
   dev-suite expectations that change. Provide the commit message and a
   short PR description for the user, and state in the log whether the image
   pin should move to this branch now (needs `--allow-branch` and a tag
   bump) or wait for the merge to `develop` (recommended); either way a pin
   that changes `keck_mosfire.py` will make the laptop's
   `check_pypeit_pin.py` fail by design until the user updates that checkout
   or the reference reduction is redone on the workstation (design D35).
   Risk: dev-suite reference outputs may shift slightly for CDS calibration
   frames. Log your work in this doc (the PypeIt repo has no prompt doc).

2. **S18: documentation, README, CHANGES, Nautilus operator guide and the
   WMKO API note.** Update `docs/keck_mosfire_design.md` to "as built":
   correct any equation, default or file name that changed during
   implementation, fill the validation (6.1) and XTcalc (appendix) results,
   update section 8 open items (Q3/Josh answer if received, `SAMPMODE`
   census result, PypeIt branch status, the residual Nautilus verification
   items now settled). Finish `nautilus/README.md` as the operator guide:
   image build and push on the workstation, the PypeIt pin and how to move
   it, bucket layout and its private status, secret names and the
   credentials test, the `kubectl` idioms, how to reduce a new batch
   (manifest, ConfigMap, apply, follow), how to sweep failures, how to sync
   products back, how to run `backup_products.py` after a batch and at a
   release, and how to cut a calibration release; note as optional and not
   done any widening of bucket access for collaborators. Write `README.md`
   usage: install, `KECK_ETCS_DATA` and its mirror relationship to the
   bucket, a Python example calling `keck_etcs.etc.compute`, the CLI
   example, and a "Refreshing calibrations" section that points at
   `nautilus/README.md` and the part 5 scripts (bump `index.yaml`, write
   `CHANGES.md`). Bring `CHANGES.md` up to date (each calibration release
   lists the image tags, digests and PypeIt pins behind it). Write
   `docs/wmko_api_note.md` (one page): every input and output field with
   units and defaults, the version fields, error and warning behaviour, the
   calibration refresh cycle, and the dependency footprint of
   `keck_etcs.core`/`etc` (no PypeIt, no Nautilus, no S3 access; all
   calibration products ship in the package). The README and the WMKO note
   also describe the calibration monitor (design 4.9): what
   `keck_etcs/data/mosfire/monitor/calib_monitor.ecsv` holds (columns and
   metrics of 4.9.5), that `compute()` never reads it, and how a new
   instrument (LRIS next) adds its monitor config (4.9.6). Verify: the README examples
   run as written in `pypeit14`; `index.yaml`, `CHANGES.md`,
   `nautilus/README.md` and the output `meta.calib_version` agree, including
   the image tags and pins behind the current calibration; the WMKO note
   lists every field in `keck_etcs/schema/etc_input.json` and
   `etc_output.json` (write a small script to diff them); no secret value
   appears in any document. Log your work and state which items of the
   definition of done (design section 7) are met.

## Q&A

## Logging

The "Logs" section will record Claude's work. Please use the following
format:

### <Date> (Short summary of the work)

<Detailed description of the work and what you learned>

## Logs

### 2026-10-08 (S17: PypeIt MOSFIRE `ronoise` from SAMPMODE/NUMREADS, prepared as a patch)

**Empirical CDS read noise.** `scripts/mosfire/measure_read_noise.py` uses the
2022-04-09 lamp-off dome flats m220409_0022-0026: CDS (`SAMPMODE = 2`,
`NUMREADS = 1`), 8.7 s, one coadd, `BUNIT = 'ADU per coadd'`, median levels
6-16 ADU. It differences consecutive frames and divides by sqrt(2). It takes
the 4-sigma-clipped standard deviation in 64 x 64 tiles whose level is at or
below 10 ADU (2398 tiles over the four pairs), multiplies by gain 2.15, and
removes the residual photon noise per tile.

- Result: **21.4 e-** (16-84 percent of tiles 20.3-22.8; 21.6 before the
  photon correction), against Keck's CDS value of **21 e-** (ratio 1.018).
  The per-pair values are 21.0-21.7 e-.
- The Keck CDS value holds. The lab value of 17.2 e- (Kulas+12) is not what
  the detector gives on the sky.
- A first version used 1.4826 MAD and returned discrete values (20.29,
  22.54). The raw CDS frames come in 0.5 ADU steps, which quantize a MAD of a
  few ADU, so the script now uses a clipped standard deviation.
- Without the tile selection, a pair's whole data section gives 23-26 e-.
  The dome-light structure does not cancel completely there.
- Summary written to `$KECK_ETCS_DATA/mosfire/20220409/read_noise_cds.json`.

**Pin check.** `scripts/check_pypeit_pin.py` passes. The checkout is at the
pin bc18a3ba4 (`etc-fixes`, which descends from `develop` f3a1f1d27), with an
empty diff.

- `get_detector_par` is the same at the pin, at local `develop` and at
  `origin/develop` (8f7ce9866, 28 commits ahead of local `develop`; none of
  them touch `keck_mosfire.py` or the tests).
- `etc-fixes` changes `keck_mosfire.py` only further down: it adds
  `alignment_box_rows`, `long2pos_bar_widths` and `transfer_wavecal`.

**The change** is in `nautilus/patches/pypeit_mosfire_ronoise.patch`, a `git
diff` against the pin, 111 lines added and 1 removed. I made it in a scratch
copy (`git archive` of the pin); the PypeIt checkout was not touched. It
creates the new test file, so no separate copy is needed.

- **`pypeit/spectrographs/keck_mosfire.py`:**
  - new module constant `MOSFIRE_READ_NOISE = {1: 21.0, 4: 10.8, 8: 7.7,
    16: 5.8, 32: 4.2, 64: 3.5, 128: 3.0}`, with the Keck detector-page URL in
    its docstring;
  - `MOSFIRE_DEFAULT_READ_NOISE`, the MCDS-16 value;
  - new function `mosfire_read_noise(sampmode, numreads)`. CDS is N = 1
    whatever `NUMREADS` says. MCDS uses N = `NUMREADS`, interpolated linearly
    in log2 N and held at the end values. Single, UTR and missing or
    non-positive cards return None.
  - `get_detector_par(det, hdu)` reads `SAMPMODE` and `NUMREADS` from
    `hdu[0]`. It keeps 5.8 e- when `hdu` is None, and also when the mode is
    not tabulated, with a `log.warning` in that case.
- **`pypeit/tests/test_keck_mosfire.py`** (new): the table, the
  interpolation (MCDS-2, MCDS-12), clipping above the table (MCDS-256), the
  None cases, and `get_detector_par` with synthetic headers (none, CDS,
  MCDS-16, MCDS-4, UTR, no cards).
- `git apply --check` passes against the pin, local `develop` and
  `origin/develop`.
- The release-notes line (`doc/releases/2.1.0dev.rst` on `develop`) is not in
  the patch, because that file changes often on `develop`. Add it when
  committing.

**Verification.**

- `scripts/mosfire/check_ronoise_patch.py`, run with the scratch copy first
  on `PYTHONPATH`: `get_detector_par(1, hdu)` returns 21.00 e- for all ten
  CDS flats (m220409_0017-0026) and 5.80 e- for the six MCDS-16 science and
  standard frames (0036-0039, 0218-0219). ALL FRAMES AGREE.
- The same script against the unpatched pin gives MISMATCH on the ten CDS
  frames (5.8 e-), as expected.
- PypeIt unit tests on the patched copy: the new file and
  `test_spectrographs.py` give 15 passed. The full suite gives 742 passed and
  1 failed. The failure, `test_pkgdata.py::test_github_contents`, is an
  artifact of the scratch copy: it looks up the scratch repo's branch name
  (`master`) on GitHub. It passes in the real checkout.

**Dev-suite expectations.** No dev-suite unit test checks the MOSFIRE read
noise (`unit_tests/test_spectrographs.py` only counts the J2_long files).
`scripts/mosfire/devsuite_sampmode_census.py` reads the
`RAW_DATA/keck_mosfire` headers:

- **Every setup has CDS frames.** In most they are the flats and arcs, whose
  `ronoise` changes from 5.8 to 21 e-.
- **Science frames are CDS too** in `long2pos1_H`, `long2pos2_H`,
  `longslit_3x0.7_H` and `longslit_3x0.7_K`. Their 2D variance, object
  finding and optimal weights change, and those reference outputs may move
  most.
- `J_multi` has 52 frames with `SAMPMODE = 3`, `NUMREADS = 1` (MCDS-1, the
  same as CDS: 21 e-).
- `mask2_H_with_continuum` science is MCDS-8 (7.7 e-).

**Effect on our own products (not re-reduced).** In `standards.ecsv`, 15 of
the 20 standard rows are CDS (everything 2014-2021, and Feige110 2024-07-21),
and 10 of the 14 that enter the era curves are among them. Their variance was computed with 5.8 e-
where 21 e- is right.

- Boxcar fluxes do not depend on this. Optimal extraction is unbiased for a
  correct profile; only the weights change.
- So the throughput is expected to change at well below the 1 percent level.
  This is not measured: it needs one CDS night reduced with the patch.

**Pin recommendation: wait. Do not pin the `mosfire_ronoise` branch.**

- The branch comes off `develop`, so it lacks the `etc-fixes` commits the
  MOSFIRE reductions need: `get_arc_extract_center`, `alignment_box_rows`,
  `transfer_wavecal`, `long2pos_bar_widths` and the `construct_basename`
  fix. Pinning it would undo those.
- The pin should move once both `etc-fixes` and `mosfire_ronoise` are merged
  into `develop`, to a `develop` commit with both, with a tag bump. If it is
  needed sooner, the patch also applies cleanly on `etc-fixes` at the pin.
- Correction to the prompt and plan: `build_image.sh` has no
  `--allow-branch` flag. It accepts a pin on any branch in `PIN_BRANCHES`
  (default `"develop etc-fixes"`) and warns when that is not `develop`.
- Either way, a pin that changes `keck_mosfire.py` makes the local
  `check_pypeit_pin.py` fail by design until the checkout is updated (D35).
  Here, that means updating the workstation checkout to the new pin.

**Commit message (PypeIt, branch `mosfire_ronoise` off `develop`):**

```
MOSFIRE read noise from the readout mode (SAMPMODE/NUMREADS)

keck_mosfire.get_detector_par hard-coded ronoise = 5.8 e-, the MCDS-16
value, for every frame. CDS frames (SAMPMODE=2), common for MOSFIRE flats,
arcs and short exposures, have 21 e-. The read noise is now taken from the
Keck detector-page table (CDS 21; MCDS-4/8/16/32/64/128 10.8/7.7/5.8/4.2/
3.5/3.0 e-), interpolated in log2(NUMREADS). The 5.8 e- default is kept
without a header and for untabulated modes (Single, UTR), with a warning.
Adds pypeit/tests/test_keck_mosfire.py.
```

**PR description (short):**

> **Summary.** `KeckMOSFIRESpectrograph.get_detector_par` now sets `ronoise`
> from the `SAMPMODE` and `NUMREADS` header cards, using the Keck MOSFIRE
> detector table, instead of always 5.8 e- (MCDS-16):
> - CDS = 21 e-;
> - MCDS-N: 10.8 / 7.7 / 5.8 / 4.2 / 3.5 / 3.0 e- for N = 4 / 8 / 16 / 32 /
>   64 / 128;
> - linear in log2 N in between.
>
> Without a header, or for Single and UTR reads, it stays at 5.8 e- and logs
> a warning.
>
> **Check.** The difference of two CDS lamp-off dome flats (2022-04-09)
> gives 21.4 e- against the table's 21 e-.
>
> **Tests.** New `pypeit/tests/test_keck_mosfire.py` (synthetic headers).
>
> **Dev-suite impact.** Every keck_mosfire setup has CDS calibration frames.
> long2pos1_H, long2pos2_H and longslit_3x0.7_H/K also have CDS science
> frames, so their 2D variance and extraction weights change; expect small
> shifts in those reference outputs.

**Files.**

- New in keck-etcs:
  - `scripts/mosfire/measure_read_noise.py`
  - `scripts/mosfire/check_ronoise_patch.py`
  - `scripts/mosfire/devsuite_sampmode_census.py`
  - `nautilus/patches/pypeit_mosfire_ronoise.patch`
- The patch sits under `nautilus/`, so the image build copies it in. It is
  not applied there and is harmless.
- The user's steps on the workstation:

  ```
  git switch develop && git pull
  git switch -c mosfire_ronoise
  git apply <keck-etcs>/nautilus/patches/pypeit_mosfire_ronoise.patch
  pytest pypeit/tests/test_keck_mosfire.py
  ```

  Then commit and push. Switch back to `etc-fixes` afterwards, so the
  checkout stays at the pin.

### 2026-10-09 (S17 follow-up: patch applied in the PypeIt checkout)

At the user's request, `nautilus/patches/pypeit_mosfire_ronoise.patch` is
applied in `/mnt/tank/Astronomy/PypeIt/PypeIt`. The user chose to stay on
`etc-fixes` (HEAD bc18a3ba4, the pin), not to make a separate branch off
`develop`. A release-notes item is added under "Instrument-specific Updates"
in `doc/releases/2.1.0dev.rst`. The user commits and pushes.

Checks on the real checkout:

- `test_keck_mosfire.py` plus `test_spectrographs.py`: 15 passed.
- `scripts/mosfire/check_ronoise_patch.py`: ALL FRAMES AGREE (CDS 21 e-,
  MCDS-16 5.8 e-).

Because the fix is on `etc-fixes`, it can be pinned directly once
committed: no merge to `develop` is needed first, and `build_image.sh`
already accepts `etc-fixes`. Pinning that commit needs:

1. `nautilus/pypeit_pin.txt` set to the new SHA;
2. an image tag bump to 0.2.6;
3. `check_pypeit_pin.py` rerun.

Until the commit is pinned, `check_pypeit_pin.py` fails here by design (D35):
`keck_mosfire.py` differs from the pin. Nights reduced after the bump carry
the new `pypeit_git_sha`. The mosfire-J-2026.10 products stay as they are
(expected change well under 1 percent; not measured).

The user committed and pushed the fix on 2026-10-09 as `etc-fixes`
38bb1b747d55a5b9205cbeb62734b0e870223990 ("readnoise fix"). The pin stays at
bc18a3b for now. It moves to 38bb1b7, with image 0.2.6, before the next
Nautilus reduction.
