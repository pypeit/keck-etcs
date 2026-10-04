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
